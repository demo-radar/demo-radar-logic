"""Run a Gem through the existing admission, spending, journal and recovery flow."""

import time

import httpx
from pydantic import ValidationError

from service.gems.contracts import GemReply, GemResponse
from service.inference.coordinator import InferenceService
from service.inference.results import AttemptOutcome, build_result, fingerprint, utc_now
from service.inference.validation import validate_tags
from service.providers.base import ProviderFailure, response_metadata
from service.providers.hetzner import strict_json


class GemService(InferenceService):
    """One attempt per deliberate send; prior classification is not eligibility.

    Radar supplies a fresh job ID for each authorized manual send. Request replay,
    global unknown-outcome blocking, provider pacing and spending stay shared.
    """

    @property
    def execution_limits(self):
        return self.config.gem.limits

    def attempt_key(self, request):
        """Keep all attempts within one explicit execution under a single limit."""
        return fingerprint({"gem_execution": request.job_id, "mode": self.settings.mode})

    def allowance_key(self, request):
        return self.attempt_key(request)

    def payload_for(self, request):
        return self.config.payload(request.context)

    async def _generate(self, request, payload):
        if self.settings.mode == "demo":
            tags = ["mobility"] if "rad" in request.context.title.lower() else []
            reply = GemReply(
                external_id=request.context.external_id,
                tags=tags,
                confidence=0.5,
                reason="Synthetic Gem reply for offline checks; not a model judgment.",
            )
            return reply, {"model": "synthetic-fixture-not-qwen", "usage": None, "id": None}
        body = await self.provider.response_body(payload)
        metadata = response_metadata(body)
        if metadata.get("model") not in self.config.returned_models:
            raise ProviderFailure("gem_model_mismatch", metadata=metadata)
        try:
            choice = body["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError("Incomplete completion")
            reply = GemReply.model_validate(strict_json(choice["message"]["content"]))
            if reply.external_id != request.context.external_id or not set(reply.tags) <= {
                tag.slug for tag in request.context.catalog
            }:
                raise ValueError("Reply does not match the supplied demo/catalog")
            validate_tags(reply.tags, metadata)
        except (ValueError, KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ProviderFailure("invalid_gem_response", metadata=metadata) from exc
        return reply, metadata

    async def _infer(self, request, attempt_number):
        started, wall_start = time.monotonic(), utc_now()
        outcome, reply = AttemptOutcome(), None
        payload = self.payload_for(request)
        try:
            reply, metadata = await self._call_provider(
                request.request_id, self._generate(request, payload), self.settings.timeout_seconds
            )
            outcome.tags, outcome.metadata = reply.tags, metadata
        except ProviderFailure as exc:
            outcome = AttemptOutcome(
                metadata=exc.metadata,
                state="unknown" if exc.unknown else "failed",
                code=exc.code,
                http_status=exc.status,
                retry_after=exc.retry_after,
            )
        except (TimeoutError, httpx.RequestError):
            outcome = AttemptOutcome(
                state="unknown", code="provider_outcome_unknown", http_status=504
            )
        result = build_result(
            request,
            self.config,
            self.settings,
            outcome,
            started,
            wall_start,
            attempt_number,
            payload=payload,
        )
        result["gem_reply"] = reply.model_dump(mode="json") if outcome.state == "ok" else None
        result = GemResponse.model_validate(result).model_dump(mode="json")
        self.journal.finish(
            request.request_id, result, outcome.http_status, outcome.state, outcome.retry_after
        )
        return result, outcome.http_status
