"""Summary adapters reuse Hetzner transport but never apply the tag parser."""

import logging

from pydantic import ValidationError

from service.providers.base import ProviderFailure, response_metadata
from service.providers.hetzner import QwenProvider, strict_json
from service.summary.contracts import SummaryDraft

logger = logging.getLogger(__name__)


class HetznerSummaryProvider(QwenProvider):
    """One Qwen completion returning a draft and original usage metadata."""

    def __init__(self, client, config, key):
        super().__init__(client, config, key)
        self.assignment_style = config.data.get("assignment_style")
        self.omit_unassigned = config.data.get("unused_topic_policy") == "omit-unassigned-v1"
        self.draft_schema_version = config.data.get("draft_schema_version", 1)
        self.returned_models = config.data.get("returned_model_ids", [config.model])

    async def draft(self, payload):
        """Reject malformed/truncated output; never convert failures to empty prose."""
        body = await self.response_body(payload)
        metadata = response_metadata(body)
        try:
            choice = body["choices"][0]
            reason = choice["finish_reason"]
            content = choice["message"]["content"]
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
        if (
            self.omit_unassigned
            and isinstance(parsed, dict)
            and isinstance(parsed.get("topics"), list)
        ):
            topics = parsed["topics"]
            # An empty claim has no support and is never published as prose.
            if all(
                isinstance(topic, dict) and isinstance(topic.get("event_ids"), list)
                for topic in topics
            ):
                parsed["topics"] = [topic for topic in topics if topic["event_ids"]]
                omitted = len(topics) - len(parsed["topics"])
                if omitted:
                    logger.info("event=summary_unassigned_topics_omitted count=%s", omitted)
        if self.draft_schema_version == 2 and (
            not isinstance(parsed, dict)
            or set(parsed) != {"overview", "topics", "highlight", "limitations"}
        ):
            logger.warning(
                "event=summary_rejected reason=fields schema=%s", self.draft_schema_version
            )
            raise ProviderFailure("invalid_summary_schema", metadata=metadata)
        try:
            draft = SummaryDraft.model_validate(parsed, strict=True)
        except ValidationError as exc:
            # Record only field paths and error types; never source facts or prose.
            issues = [
                (error["loc"], error["type"])
                for error in exc.errors(include_input=False, include_url=False)
            ]
            logger.warning("event=summary_rejected reason=shape issues=%s", issues)
            raise ProviderFailure("invalid_summary_schema", metadata=metadata) from exc
        return draft, response_metadata(body)

    @staticmethod
    def normalize_assignments(parsed, payload, metadata):
        """Turn required per-event theme numbers into the public topic source lists.

        There is exactly one entry per source event, in its original order.
        Each entry contains distinct, valid topic numbers. No missing event is
        silently assigned by the service; invalid output remains a saved failure.
        """
        required = {"overview", "topics", "assignments", "highlight", "limitations"}
        if not isinstance(parsed, dict) or set(parsed) != required:
            raise ProviderFailure("invalid_summary_schema", metadata=metadata)
        source = strict_json(payload["messages"][-1]["content"])
        references = source["required_event_ids"]
        assignments, topics = parsed["assignments"], parsed["topics"]
        if not isinstance(assignments, list) or len(assignments) != len(references):
            logger.warning(
                "event=summary_rejected reason=assignments expected=%s returned=%s",
                len(references),
                len(assignments) if isinstance(assignments, list) else -1,
            )
            raise ProviderFailure("invalid_summary_schema", metadata=metadata)
        topic_schema = payload["response_format"]["json_schema"]["schema"]["properties"]["topics"][
            "items"
        ]
        required_fields = set(topic_schema["required"])
        allowed_fields = {"label", "text", "include_in_briefing"}
        if (
            not isinstance(topics, list)
            or not 1 <= len(topics) <= 8
            or any(
                not isinstance(topic, dict) or not required_fields <= set(topic) <= allowed_fields
                for topic in topics
            )
        ):
            raise ProviderFailure("invalid_summary_schema", metadata=metadata)
        result = {key: value for key, value in parsed.items() if key != "assignments"}
        result["topics"] = [{**topic, "event_ids": []} for topic in topics]
        for identifier, numbers in zip(references, assignments, strict=True):
            if (
                not isinstance(numbers, list)
                or not numbers
                or any(
                    type(number) is not int or not 1 <= number <= len(topics) for number in numbers
                )
                or len(numbers) != len(set(numbers))
            ):
                raise ProviderFailure("invalid_summary_schema", metadata=metadata)
            for number in numbers:
                result["topics"][number - 1]["event_ids"].append(identifier)
        return result


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
