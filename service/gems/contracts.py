"""Bounded Gem inputs and reviewable JSON output."""

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from demo_logic.taxonomy import topic_tags
from service.contracts import ExecutionContext, Fingerprint, Identifier, TagRequest, TagResponse


class GemTag(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    slug: str = Field(min_length=1, max_length=48)
    label: str = Field(min_length=1, max_length=100)


class GemContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    external_id: Identifier
    title: str = Field(min_length=1, max_length=4000)
    start_date: str | None = Field(default=None, max_length=160)
    end_date: str | None = Field(default=None, max_length=160)
    raw_address: str | None = Field(default=None, max_length=4000)
    raw_zip: str | None = Field(default=None, max_length=160)
    raw_route: str | None = Field(default=None, max_length=16000)
    current_tags: list[str] = Field(default_factory=list, max_length=2)
    catalog: list[GemTag] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def approved_catalog(self):
        slugs = [tag.slug for tag in self.catalog]
        if len(slugs) != len(set(slugs)) or not set(slugs) <= topic_tags("v2"):
            raise ValueError("Use a distinct approved tag catalog")
        try:
            json.dumps(self.model_dump(), ensure_ascii=False).encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("Gem context must use valid Unicode") from exc
        return self


class GemReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    external_id: Identifier
    tags: list[Annotated[str, Field(min_length=1, max_length=48)]] = Field(max_length=2)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    reason: str = Field(min_length=1, max_length=2000, pattern=r".*\S.*")


class GemPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    profile_id: Identifier
    profile_sha256: Fingerprint
    context: GemContext


class GemExecution(ExecutionContext):
    """A Gem is an explicitly authorized manual execution with a pinned profile."""

    task: Literal["tagging"] = "tagging"
    origin: Literal["manual_api"] = "manual_api"


class GemRequest(TagRequest):
    input_variant: Literal["GEM-v1"] = "GEM-v1"
    execution: GemExecution
    context: GemContext

    @model_validator(mode="after")
    def same_event(self):
        if self.event.title != self.context.title or self.event.id not in {
            self.context.external_id,
            "synthetic-" + self.context.external_id,
        }:
            raise ValueError("Gem context must describe the requested demonstration")
        return self


class GemResponse(TagResponse):
    """Saved task evidence with the validated model JSON kept intact."""

    gem_reply: GemReply | None
