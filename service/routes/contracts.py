"""Versioned route review data, independent of providers and public map writes."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Fingerprint = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]


class RouteSource(BaseModel):
    """Explicit public source and saved geocoding context for a private preview."""

    model_config = ConfigDict(extra="forbid", strict=True)
    external_id: Text
    raw_route: Annotated[str, StringConstraints(max_length=20000)]
    topic: str | None
    start_date: str
    end_date: str
    plz: str | None
    strasse: str | None
    parser_waypoints: list[Text] = Field(max_length=200)
    stored_waypoints: list[Text] = Field(max_length=200)
    resolved_waypoints: list[dict] = Field(max_length=200)
    route_status: str | None
    route_error: str | None = None
    issue_types: list[Literal["missing_route_row", "missing_route_anchors", "partial_geocode"]] = (
        Field(default_factory=list, max_length=3)
    )


class BrokenWaypoint(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    original_text: Text
    suggested_fix: Text
    error_type: Literal[
        "typo",
        "wrong_suffix",
        "nonexistent_street",
        "duplicate_anchor",
        "missing_anchor",
        "formatting_anomaly",
        "ambiguous",
    ]


class RouteProposal(BaseModel):
    """Manual reply bound to the exact exported source, never a generated polyline."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    contract_version: Literal["route-review-v1"]
    external_id: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    source_sha256: Fingerprint
    corrected_route: list[Text] = Field(max_length=200)
    reason: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    needs_review: bool
    has_route_error: bool | None = None
    broken_waypoints: list[BrokenWaypoint] = Field(default_factory=list, max_length=200)
    distance_check_passed: bool | None = None
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


def route_contract():
    """Describe disabled groundwork without advertising an executable profile."""
    return {
        "contract_version": "route-review-v1",
        "task": "routes",
        "enabled": False,
        "reason": "Route execution requires a separate pilot and enablement decision.",
        "source_schema": RouteSource.model_json_schema(),
        "proposal_schema": RouteProposal.model_json_schema(),
    }
