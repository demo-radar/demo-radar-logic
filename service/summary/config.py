"""Load the versioned daily prompt without altering the evaluated tag prompt."""

import copy
import hashlib
import json

from service.inference.results import fingerprint
from service.persistence.journal import AdmissionError
from service.providers.gemini import GeminiProvider
from service.providers.hetzner import HetznerProvider

# Older saved jobs keep their original ID and fingerprint.
LEGACY_CONFIG_IDS = {"daily-summary-v1": "hetzner-daily-v1"}


class SummaryConfig:
    """Read one pinned public config and build bounded, search-free requests.

    The full UTF-8 payload is capped at 64,000 bytes without truncation.
    Paid requests count input tokens before reserving their maximum cost;
    the pinned output limit includes reasoning tokens.
    """

    def __init__(self, root, config_id="hetzner-daily-v1"):
        directory = root / "configs/summary"
        catalog = json.loads((directory / "catalog.json").read_text())
        registration = catalog["configurations"][LEGACY_CONFIG_IDS.get(config_id, config_id)]
        self.requires_fingerprint = registration.get("requires_fingerprint", False)
        path = (directory / registration["path"]).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("Summary config must stay inside its catalog")
        raw = path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        if self.sha256 != registration["sha256"]:
            raise ValueError("Summary config fingerprint changed; version the new prompt")
        self.data = json.loads(raw)
        # Store long instructions as readable lines; send the same prompt text.
        if isinstance(self.data["system"], list):
            self.data["system"] = " ".join(self.data["system"])
        self.example = None
        provider_profile = registration.get("provider_profile")
        if provider_profile is not None:
            if provider_profile not in {"hetzner", "gemini"}:
                raise ValueError("No adapter is installed for this summary provider")
            profile = (directory / "providers" / (provider_profile + ".json")).read_bytes()
            if (
                registration.get("provider_sha256", hashlib.sha256(profile).hexdigest())
                != hashlib.sha256(profile).hexdigest()
            ):
                raise ValueError("Summary provider profile changed")
            example = (directory / self.data["example"]["path"]).read_bytes()
            if hashlib.sha256(example).hexdigest() != self.data["example"]["sha256"]:
                raise ValueError("Summary example changed; version the example")
            self.example = json.loads(example)
            self.data.update(json.loads(profile))
            # The product owns its output shape; the adapter owns transport settings.
            if "draft_schema" in self.data:
                self.data["settings"]["response_format"]["json_schema"]["schema"] = self.data[
                    "draft_schema"
                ]
                self.data["settings"]["max_completion_tokens"] = self.data["maximum_output_tokens"]
            # Pin the actual prompt, example AND deployment profile in each result.
            self.sha256 = hashlib.sha256(raw + example + profile).hexdigest()
        self.maximum_topic_sources = (
            self.data["settings"]["response_format"]["json_schema"]["schema"]["properties"]
            .get("topics", {})
            .get("items", {})
            .get("properties", {})
            .get("event_ids", {})
            .get("maxItems", self.data["maximum_events"])
        )
        self.version = config_id if provider_profile is not None else self.data["version"]
        self.provider = self.data["provider"]
        self.model = self.data["model"]
        self.endpoint = self.data["endpoint"]
        output_format = self.data["settings"].get("response_format", {})
        schema = output_format.get("json_schema", {}).get("schema", {})
        self.maximum_claim_sources = (
            schema.get("properties", {})
            .get("overview", {})
            .get("items", {})
            .get("properties", {})
            .get("event_ids", {})
            .get("maxItems", 20)
        )
        if (
            catalog["schema_version"] != 1
            or self.version != config_id
            or self.endpoint
            != {
                "hetzner": HetznerProvider.ENDPOINT,
                "gemini": GeminiProvider.endpoint_for(self.model),
            }.get(self.provider)
            or self.data["settings"]["model"] != self.model
        ):
            raise ValueError("Unsupported daily summary configuration")

    def payload(self, snapshot):
        """Encode supplied public facts; reject oversized requests before dispatch."""
        payload = copy.deepcopy(self.data["settings"])
        source = self.source_for_model(snapshot)
        if self.data.get("assignment_style") == "per-event-position-v1":
            # One entry per source event, without a large per-ID grammar.
            assignment = payload["response_format"]["json_schema"]["schema"]["properties"][
                "assignments"
            ]
            assignment["minItems"] = assignment["maxItems"] = len(source["events"])
        if self.data.get("coverage_style") == "selected-claims-v1":
            # Constrain generated citations to actual sources; the example is context only.
            properties = payload["response_format"]["json_schema"]["schema"]["properties"]
            for claim_schema in (
                properties["overview"]["items"],
                properties["topics"]["items"],
                properties["highlight"]["anyOf"][0],
            ):
                claim_schema["properties"]["event_ids"]["items"]["enum"] = source[
                    "available_event_ids"
                ]
        payload["messages"] = [{"role": "system", "content": self.data["system"]}]
        if self.example and self.example.get("kind") == "worked-example":
            # Distinct example IDs prevent its citations from validating as real sources.
            payload["messages"].extend(
                [
                    {
                        "role": "user",
                        "content": json.dumps(self.example["input"], ensure_ascii=False),
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps(self.example["output"], ensure_ascii=False),
                    },
                ]
            )
        elif self.example:
            # Historical guide configurations still load for saved-result lookups.
            payload["messages"][0]["content"] += "\nWriting guidance:\n" + json.dumps(
                self.example, ensure_ascii=False
            )
        payload["messages"].append(
            {"role": "user", "content": json.dumps(source, ensure_ascii=False)}
        )
        if (
            len(json.dumps(payload, ensure_ascii=False).encode())
            > self.data["maximum_payload_bytes"]
        ):
            raise AdmissionError("summary_input_too_large", 422)
        return payload

    def source_for_model(self, snapshot):
        """Use short references for copying; keep real IDs in the saved request."""
        source = snapshot.model_dump()
        if self.data.get("citation_style") == "short-ids-v1":
            for number, event in enumerate(source["events"], start=1):
                event["id"] = f"d{number:03d}"
            key = (
                "available_event_ids"
                if self.data.get("coverage_style") == "selected-claims-v1"
                else "required_event_ids"
            )
            source[key] = [event["id"] for event in source["events"]]
        return source

    def resolve_references(self, draft, snapshot):
        """Map model references back to real IDs before normal citation checks.

        Unknown references remain unchanged and are rejected by validation.
        This mapping never changes source titles, prose, usage or saved input.
        """
        if self.data.get("citation_style") != "short-ids-v1":
            return draft
        mapping = {
            f"d{number:03d}": event.id for number, event in enumerate(snapshot.events, start=1)
        }
        result = draft.model_copy(deep=True)
        for item in [
            *result.overview,
            *result.topics,
            *([result.highlight] if result.highlight else []),
        ]:
            item.event_ids = [mapping.get(identifier, identifier) for identifier in item.event_ids]
        return result

    def contract(self):
        """Publish model settings and limits from this sole service-owned catalog."""
        return {
            "contract_version": 1,
            "config_id": self.version,
            "config_sha256": self.sha256,
            "provider": self.provider,
            "model": self.model,
            "maximum_events": self.data["maximum_events"],
            "maximum_payload_bytes": self.data["maximum_payload_bytes"],
            "maximum_output_tokens": self.data["settings"]["max_completion_tokens"],
            "returned_model_ids": self.data.get("returned_model_ids", [self.model]),
            "maximum_claim_sources": self.maximum_claim_sources,
            "maximum_topic_sources": self.maximum_topic_sources,
            "languages": ["de", "en"],
            "draft_schema_version": self.data.get("draft_schema_version", 1),
            "prompt_revision": self.data.get("prompt_revision", 1),
            "topic_prose": self.data.get("topic_prose", False),
            "maximum_claim_length": schema_claim_length(self.data),
            "maximum_briefing_prose_words": self.data.get("maximum_briefing_prose_words"),
            "coverage_style": self.data.get("coverage_style", "full-theme-coverage-v1"),
        }

    def identity(self, snapshot_hash, mode):
        """Identify one day/input/configuration across jobs and process restarts."""
        return fingerprint(
            {
                "task": "daily-summary",
                "snapshot": snapshot_hash,
                "config": self.sha256,
                "mode": mode,
            }
        )


def schema_claim_length(data):
    """Expose the product's paragraph limit so Radar does not copy the schema."""
    schema = data["settings"].get("response_format", {}).get("json_schema", {}).get("schema", {})
    return (
        schema.get("properties", {})
        .get("overview", {})
        .get("items", {})
        .get("properties", {})
        .get("text", {})
        .get("maxLength", 400)
    )
