"""Admit daily drafts through the same durable slot used for tagging."""

import asyncio
import logging
import time

import httpx

from service.contracts import AttemptStatistics
from service.errors import error_detail
from service.inference.coordinator import InferenceService
from service.inference.results import fingerprint, usage_counts, utc_now
from service.persistence.journal import AdmissionError
from service.providers.base import ProviderFailure
from service.summary.config import schema_claim_length
from service.summary.contracts import SummaryResponse

logger = logging.getLogger(__name__)


class SummaryService(InferenceService):
    """Coordinate one-shot drafts with shared replay, maintenance and drainage.

    Inherits active task lifetime only. The daily contract and parsing are
    separate from tagging. All summaries require staff review, never publication.
    The worker schedules up to three (optionally five) attempts per input.
    This service makes one call per request and never retries an unknown outcome.
    """

    async def suggest(self, request):
        """Return (saved draft, HTTP status); replay cannot create another call."""
        if (
            request.model_id != self.config.version
            or request.model_id == "daily-summary-v1"
            and request.config_sha256 != self.config.sha256
        ):
            raise AdmissionError("unsupported_configuration", 422)
        if not self.settings.summary_enabled:
            raise AdmissionError("summary_disabled", 503)
        if self.settings.mode == "demo" and any(
            not event.id.startswith("synthetic-") for event in request.snapshot.events
        ):
            raise AdmissionError("synthetic_event_required", 422)
        payload = self.config.payload(request.snapshot)
        identity = fingerprint(
            {
                "request": request.model_dump(),
                "config": self.config.sha256,
                "mode": self.settings.mode,
                "task": "daily-summary",
            }
        )
        key = self.config.identity(request.snapshot_sha256, self.settings.mode)
        # Empty days need no provider call and do not occupy the journal slot.
        if not request.snapshot.events:
            return self._response(request, None, None, "empty", None, 0), 200
        return await self._admit(
            request,
            identity,
            key,
            lambda: self._draft(request, payload, key),
            event_id="daily-" + key,
            max_attempts=self.settings.summary_max_attempts,
        )

    async def _draft(self, request, payload, key):
        """Bound the call, check citations, save outcome before releasing admission."""
        started, wall_start = time.monotonic(), utc_now()
        draft, metadata, state, failure = None, {}, "ok", None
        try:
            async with asyncio.timeout(self.settings.summary_timeout_seconds):
                draft, metadata = await self.provider.draft(payload)
            draft = self.config.resolve_references(draft, request.snapshot)
            self._validate_draft(draft, request.snapshot, metadata)
        except ProviderFailure as exc:
            failure, metadata = exc, exc.metadata
            state = "unknown" if exc.unknown else "failed"
        except (TimeoutError, httpx.RequestError):
            failure = ProviderFailure("provider_outcome_unknown", 504, unknown=True)
            state = "unknown"
        stats = AttemptStatistics(
            schema_version=1,
            attempt_id=request.request_id,
            attempt_number=self.journal.attempt_count(key),
            provider=self.config.provider if self.settings.mode == "live" else "synthetic",
            requested_model=self.config.model,
            returned_model=metadata.get("model"),
            provider_request_id=metadata.get("id"),
            started_at=wall_start,
            finished_at=utc_now(),
            duration_seconds=time.monotonic() - started,
            provider_call_occurred=self.settings.mode == "live",
            outcome=state,
            usage_raw=metadata.get("usage"),
            **usage_counts(metadata.get("usage")),
        )
        status = failure.status if failure else 200
        result = self._response(
            request,
            draft if state == "ok" else None,
            stats,
            "draft" if state == "ok" else state,
            failure,
            int(self.settings.mode == "live"),
        )
        self.journal.finish(
            request.request_id, result, status, state, failure.retry_after if failure else 0
        )
        return result, status

    def _validate_draft(self, draft, snapshot, metadata):
        """Check cited sources and the configured coverage policy before saving prose.

        Historical prompts require full theme coverage; current prompts cite only
        selected events. The full input remains saved. Neither policy establishes that
        the model understood the sources; staff still reviews both languages.
        """
        allowed = {event.id for event in snapshot.events}
        self._validate_writing_limits(draft, snapshot, metadata)
        if any(
            not claim.text.strip() or len(claim.text) > schema_claim_length(self.config.data)
            for claim in draft.overview
        ):
            raise ProviderFailure("invalid_summary_schema", metadata=metadata)
        groups = [(claim, self.config.maximum_claim_sources) for claim in draft.overview]
        groups += [(topic, self.config.maximum_topic_sources) for topic in draft.topics]
        if draft.highlight:
            groups.append((draft.highlight, 1))
        for claim, maximum in groups:
            if (
                not set(claim.event_ids) <= allowed
                or len(set(claim.event_ids)) != len(claim.event_ids)
                or len(claim.event_ids) > maximum
            ):
                logger.warning(
                    "event=summary_rejected reason=citations unknown=%s repeated=%s count=%s maximum=%s",
                    len(set(claim.event_ids) - allowed),
                    len(claim.event_ids) - len(set(claim.event_ids)),
                    len(claim.event_ids),
                    maximum,
                )
                raise ProviderFailure("invalid_summary_citations", metadata=metadata)
        if self.config.data.get("draft_schema_version") != 2:
            return
        if self.config.data.get("topic_prose") and any(
            not topic.text or not topic.text.strip() for topic in draft.topics
        ):
            raise ProviderFailure("invalid_summary_schema", metadata=metadata)
        highlight_schema = self.config.data["draft_schema"]["properties"]["highlight"]["anyOf"][0]
        if (
            draft.highlight
            and "title" in highlight_schema.get("required", [])
            and not draft.highlight.title
        ):
            raise ProviderFailure("invalid_summary_schema", metadata=metadata)
        coverage = {identifier for topic in draft.topics for identifier in topic.event_ids}
        labels = [topic.label.strip().casefold() for topic in draft.topics]
        if (
            (self.config.data.get("coverage_style") != "selected-claims-v1" and coverage != allowed)
            or not draft.topics
            or len(draft.overview)
            > self.config.data["draft_schema"]["properties"]["overview"]["maxItems"]
            or len(draft.limitations) != 1
            or len(labels) != len(set(labels))
            or any(not label for label in labels)
            or draft.highlight
            and len(draft.highlight.text) > 400
        ):
            logger.warning(
                "event=summary_rejected reason=coverage_or_shape missing=%s topics=%s overview=%s limitations=%s repeated_labels=%s",
                len(allowed - coverage),
                len(draft.topics),
                len(draft.overview),
                len(draft.limitations),
                len(labels) - len(set(labels)),
            )
            raise ProviderFailure("invalid_summary_schema", metadata=metadata)

    def _validate_writing_limits(self, draft, snapshot, metadata):
        """Reject verbose prose and known example-only phrases before saving a draft.

        A rejected completed answer keeps its usage and releases admission.
        These checks limit length and catch a copied example slogan; they do not
        establish that the model's remaining statements are factually correct.
        """
        maximum = self.config.data.get("maximum_briefing_prose_words")
        if maximum is None:
            return  # Historical configurations retain their original limits.
        visible = [topic.text or "" for topic in draft.topics if topic.include_in_briefing]
        if draft.highlight:
            visible.extend([draft.highlight.title or "", draft.highlight.text])
        visible.extend(draft.limitations)
        words = len(" ".join(visible).split())
        if words > maximum or any(
            len(claim.text.split()) > self.config.data["maximum_overview_words"]
            for claim in draft.overview
        ):
            logger.warning(
                "event=summary_rejected reason=word_limit words=%s maximum=%s", words, maximum
            )
            raise ProviderFailure("summary_word_limit", metadata=metadata)
        # Require protected example phrases to be supported by their cited titles.
        claims = [*draft.overview, *draft.topics, *([draft.highlight] if draft.highlight else [])]
        titles = {event.id: event.title.casefold() for event in snapshot.events}
        for phrase in (self.config.example or {}).get("protected_phrases", []):
            for claim in claims:
                text = " ".join([claim.text or "", getattr(claim, "title", "") or ""]).casefold()
                if phrase.casefold() in text and not any(
                    phrase.casefold() in titles.get(identifier, "")
                    for identifier in claim.event_ids
                ):
                    raise ProviderFailure("summary_example_leakage", metadata=metadata)

    def _response(self, request, draft, statistics, status, failure, calls):
        """Validate saved response; citations establish traceability, not factuality."""
        return SummaryResponse(
            request_id=request.request_id,
            job_id=request.job_id,
            date=request.snapshot.date,
            snapshot_sha256=request.snapshot_sha256,
            config_version=self.config.version,
            config_sha256=self.config.sha256,
            mode=self.settings.mode,
            status=status,
            draft=draft,
            error=error_detail(failure.code, failure.status, failure.retry_after)
            if failure
            else None,
            replayed=False,
            new_provider_calls=calls,
            statistics=statistics,
        ).model_dump(mode="json")
