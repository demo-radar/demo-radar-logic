"""Daily public facts and traceable draft output, separate from tag requests.

Unknown facts stay null. No private review text or arbitrary model settings are
accepted. Limits reject a busy snapshot rather than silently dropping events.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from service.contracts import AttemptStatistics, ErrorDetail, Identifier
from service.inference.results import fingerprint

Text = Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class DailyEvent(BaseModel):
    """One distinct dated demonstration, containing only public source facts.

    Times are Berlin-local ISO strings with UTC offsets, or null when not known.
    A date-only feed value must not be presented as a known midnight start.
    Tags are approved slugs; neither staff notes nor raw feed objects are allowed.
    """

    model_config = ConfigDict(extra="forbid", strict=True)
    id: Identifier
    title: Text
    start: str | None
    end: str | None
    location: Text | None
    route: Annotated[str, StringConstraints(max_length=12000)] | None
    tags: list[Identifier] = Field(max_length=13)
    cancelled: bool | None = None
    uncertainty: list[Annotated[str, StringConstraints(max_length=300)]] = Field(max_length=6)

    @field_validator("title")
    @classmethod
    def meaningful_title(cls, value):
        """Reject empty source titles and Unicode that cannot be sent as UTF-8."""
        if not value.strip():
            raise ValueError("Title must contain text")
        value.encode("utf-8")
        return value

    @field_validator("start", "end")
    @classmethod
    def offset_time(cls, value):
        """Require an offset so callers cannot confuse Berlin and UTC dates."""
        if value is not None and datetime.fromisoformat(value).utcoffset() is None:
            raise ValueError("Event times need a UTC offset")
        return value


class DailySnapshot(BaseModel):
    """Canonical daily source, independent of map geometry or viewport filters."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    date: str
    timezone: Literal["Europe/Berlin"] = "Europe/Berlin"
    language: Literal["de", "en"] = "de"
    visibility_rule: Literal["active-public-feed-v1"] = "active-public-feed-v1"
    coverage: Literal["registered-feed-only"] = "registered-feed-only"
    exclusions: list[Annotated[str, StringConstraints(max_length=300)]] = Field(max_length=6)
    events: list[DailyEvent] = Field(max_length=200)

    @field_validator("date")
    @classmethod
    def iso_date(cls, value):
        """Accept a plain ISO date, without time or timezone shorthand."""
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use YYYY-MM-DD")
        return value

    @model_validator(mode="after")
    def distinct_ids(self):
        """Repeated source IDs are invalid; recurring dates remain separate IDs."""
        ids = [event.id for event in self.events]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate event ID")
        return self


class SummaryRequest(BaseModel):
    """One stable daily request; hash includes every supplied public fact."""

    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: Identifier
    job_id: Identifier
    model_id: Identifier = "daily-summary-v1"
    config_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")] | None = None
    snapshot_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    snapshot: DailySnapshot

    @model_validator(mode="after")
    def valid_hash(self):
        """Reject a mislabeled snapshot before a provider attempt is admitted."""
        if fingerprint(self.snapshot.model_dump()) != self.snapshot_sha256:
            raise ValueError("Snapshot fingerprint mismatch")
        return self


class SummaryClaim(BaseModel):
    """A short statement and the source IDs that staff must check against it."""

    model_config = ConfigDict(extra="forbid", strict=True)
    text: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    event_ids: list[Identifier] = Field(min_length=1, max_length=20)


class SummaryTopic(BaseModel):
    """One editorial group, including private assignments for unclear titles.

    False keeps the group out of the reader briefing without losing source IDs.
    Older saved groups default to visible. Counts are for review, not prose.
    """

    model_config = ConfigDict(extra="forbid", strict=True)
    label: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    text: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = None
    event_ids: list[Identifier] = Field(min_length=1, max_length=200)
    include_in_briefing: bool = True


class SummaryHighlight(SummaryClaim):
    """One selected event, with an optional short title for bilingual display.

    Older saved drafts have no title. Radar translates a new title with DeepL,
    keeping the original event reference for staff checks.
    """

    title: Annotated[str, StringConstraints(min_length=1, max_length=160)] | None = None


class SummaryDraft(BaseModel):
    """Structurally validated prose; human factuality review is still required."""

    model_config = ConfigDict(extra="forbid", strict=True)
    overview: list[SummaryClaim] = Field(min_length=1, max_length=6)
    # Defaults allow reading older saved highlights; the new provider requires both fields.
    topics: list[SummaryTopic] = Field(default_factory=list, max_length=8)
    highlight: SummaryHighlight | None = None
    limitations: list[Annotated[str, StringConstraints(min_length=1, max_length=400)]] = Field(
        max_length=6
    )


class SummaryResponse(BaseModel):
    """Saved draft or failure, including the original usage on every replay."""

    request_id: str
    job_id: str
    date: str
    snapshot_sha256: str
    config_version: str
    config_sha256: str
    mode: Literal["demo", "live"]
    status: Literal["draft", "empty", "failed", "unknown"]
    draft: SummaryDraft | None
    requires_staff_review: Literal[True] = True
    error: ErrorDetail | None
    replayed: bool
    new_provider_calls: int
    statistics: AttemptStatistics | None
