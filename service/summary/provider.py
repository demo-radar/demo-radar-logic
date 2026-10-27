"""Provider-independent summary parsing and transport composition."""

import logging

from pydantic import ValidationError

from service.providers.base import ProviderFailure, response_metadata
from service.providers.hetzner import strict_json
from service.summary.contracts import (
    SummaryAssignments,
    SummaryDraft,
    SummaryDraftV2,
    TopicGroups,
)

logger = logging.getLogger(__name__)


class SummaryParser:
    """Apply the pinned summary schema independently of provider transport."""

    def __init__(self, config):
        self.assignment_style = config.data.get("assignment_style")
        self.omit_unassigned = config.data.get("unused_topic_policy") == "omit-unassigned-v1"
        self.draft_schema_version = config.data.get("draft_schema_version", 1)
        self.returned_models = config.data.get("returned_model_ids", [config.model])
        schemas = {1: SummaryDraft, 2: SummaryDraftV2}
        if type(self.draft_schema_version) is not int or self.draft_schema_version not in schemas:
            raise ValueError("Unsupported summary draft schema")
        self.draft_schema = schemas[self.draft_schema_version]

    def parse_draft(self, body, payload):
        """Apply the same output checks to every approved summary provider."""
        metadata = response_metadata(body)
        try:
            reason = body["choices"][0]["finish_reason"]
            content = body["choices"][0]["message"]["content"]
        except (TypeError, KeyError, IndexError) as exc:
            raise ProviderFailure("invalid_summary_envelope", metadata=metadata) from exc
        if reason != "stop":
            raise ProviderFailure("incomplete_summary_response", metadata=metadata)
        if body.get("model") not in self.returned_models:
            raise ProviderFailure("summary_model_mismatch", metadata=metadata)
        try:
            parsed = strict_json(content)
        except (ValueError, TypeError) as exc:
            raise ProviderFailure("invalid_summary_json", metadata=metadata) from exc
        if self.assignment_style == "per-event-position-v1":
            parsed = self.normalize_assignments(parsed, payload, metadata)
        try:
            if self.omit_unassigned:
                groups = TopicGroups.model_validate(parsed)
                topics = [
                    raw
                    for raw, topic in zip(parsed["topics"], groups.topics, strict=True)
                    if topic.event_ids
                ]
                omitted = len(groups.topics) - len(topics)
                if omitted:
                    logger.info("event=summary_unassigned_topics_omitted count=%s", omitted)
                parsed = {**parsed, "topics": topics}
            draft = self.draft_schema.model_validate(parsed, strict=True)
        except ValidationError as exc:
            # Field paths may contain generated keys; log categories and counts only.
            issues = exc.errors(include_input=False, include_url=False)
            categories = sorted({issue["type"] for issue in issues})
            logger.warning(
                "event=summary_rejected reason=shape error_types=%s count=%s",
                categories,
                len(issues),
            )
            raise ProviderFailure("invalid_summary_schema", metadata=metadata) from exc
        return draft, response_metadata(body)

    @staticmethod
    def normalize_assignments(parsed, payload, metadata):
        """Turn required per-event theme numbers into the public topic source lists.

        There is exactly one entry per source event, in its original order.
        Each entry contains distinct, valid topic numbers. No missing event is
        silently assigned by the service; invalid output remains a saved failure.
        """
        source = strict_json(payload["messages"][-1]["content"])
        references = source["required_event_ids"]
        topic_schema = payload["response_format"]["json_schema"]["schema"]["properties"]["topics"][
            "items"
        ]
        try:
            assignments = SummaryAssignments.model_validate(
                parsed, context={"required_topic_fields": set(topic_schema["required"])}
            )
        except ValidationError as exc:
            raise ProviderFailure("invalid_summary_schema", metadata=metadata) from exc
        if len(assignments.assignments) != len(references):
            logger.warning(
                "event=summary_rejected reason=assignments expected=%s returned=%s",
                len(references),
                len(assignments.assignments),
            )
            raise ProviderFailure("invalid_summary_schema", metadata=metadata)
        result = {key: value for key, value in parsed.items() if key != "assignments"}
        result["topics"] = [{**topic, "event_ids": []} for topic in parsed["topics"]]
        for identifier, numbers in zip(references, assignments.assignments, strict=True):
            for number in numbers:
                result["topics"][number - 1]["event_ids"].append(identifier)
        return result


class SummaryProvider:
    """Combine the selected vendor transport with the shared summary parser."""

    def __init__(self, transport, config):
        self.transport = transport
        self.parser = SummaryParser(config)

    async def count_tokens(self, payload):
        """Use the selected transport's token count before paid admission."""
        return await self.transport.count_tokens(payload)

    async def draft(self, payload):
        body = await self.transport.response_body(payload)
        return self.parser.parse_draft(body, payload)


class SyntheticSummaryProvider:
    """Invented fixture for offline contract checks, not a live fallback."""

    async def draft(self, payload):
        """Return traceable placeholder prose without contacting any provider."""
        snapshot = strict_json(payload["messages"][-1]["content"])
        return SummaryDraft.model_validate(
            {
                "overview": [
                    {
                        "text": (
                            "Synthetischer Testentwurf; keine geprüfte Zusammenfassung."
                            if snapshot["language"] == "de"
                            else "Synthetic draft; not a reviewed summary."
                        ),
                        "event_ids": [snapshot["events"][0]["id"]],
                    }
                ],
                "topics": [
                    {
                        "label": "Test",
                        "text": "Synthetisches Thema.",
                        "event_ids": [event["id"] for event in snapshot["events"]],
                    }
                ],
                "highlight": None,
                "limitations": ["Dies ist nur ein Offline-Test."],
            }
        ), {"model": "synthetic-fixture-not-qwen"}
