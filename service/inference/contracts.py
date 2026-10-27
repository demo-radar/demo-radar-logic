"""Typed public descriptions of executable task profiles."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from service.contracts import Fingerprint, Identifier
from service.summary.contracts import SummaryProfileContract


class TaggingProfileContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    config_id: Identifier
    config_sha256: Fingerprint
    rubric_sha256: Fingerprint
    taxonomy_version: Literal["v2"]
    provider: str = Field(min_length=1)
    requested_model: str = Field(min_length=1)
    maximum_tags: int = Field(ge=2, le=2)


class ProfileDescriptor(BaseModel):
    """Publish only reviewed identities and limits, never private configuration."""

    model_config = ConfigDict(extra="forbid", strict=True)
    task: Literal["tagging", "daily-summary"]
    profile_id: Identifier
    profile_sha256: Fingerprint
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    instructions_sha256: Fingerprint
    example_sha256: Fingerprint | None
    schema_sha256: Fingerprint
    maximum_output_tokens: int = Field(gt=0)
    enabled: bool
    contract: TaggingProfileContract | SummaryProfileContract
    unavailable_reason: str | None = None

    @field_validator("contract", mode="before")
    @classmethod
    def task_contract(cls, value, info: ValidationInfo):
        schema = (
            TaggingProfileContract if info.data.get("task") == "tagging" else SummaryProfileContract
        )
        return schema.model_validate(value)

    @model_validator(mode="after")
    def consistent_identity(self):
        model = self.contract.requested_model if self.task == "tagging" else self.contract.model
        if (
            self.profile_id != self.contract.config_id
            or self.profile_sha256 != self.contract.config_sha256
            or self.provider != self.contract.provider
            or self.model != model
        ):
            raise ValueError("Profile metadata must match its contract")
        return self


class ProfileCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: int = Field(ge=1, le=1)
    profiles: list[ProfileDescriptor] = Field(max_length=100)
    unavailable_tasks: list[Literal["tagging", "daily-summary", "routes"]] = Field(max_length=3)

    @model_validator(mode="after")
    def distinct_profiles(self):
        identities = [(profile.task, profile.profile_id) for profile in self.profiles]
        if len(identities) != len(set(identities)):
            raise ValueError("Task profiles must have distinct identities")
        return self
