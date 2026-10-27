"""Gemini response shapes; usable usage survives invalid generated content."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class GeminiUsage(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    prompt_tokens: int | None = Field(default=None, alias="promptTokenCount", ge=0)
    output_tokens: int | None = Field(default=None, alias="candidatesTokenCount", ge=0)
    thinking_tokens: int | None = Field(default=None, alias="thoughtsTokenCount", ge=0)
    total_tokens: int | None = Field(default=None, alias="totalTokenCount", ge=0)
    cached_tokens: int | None = Field(default=None, alias="cachedContentTokenCount", ge=0)

    @field_validator(
        "prompt_tokens",
        "output_tokens",
        "thinking_tokens",
        "total_tokens",
        "cached_tokens",
        mode="before",
    )
    @classmethod
    def unknown_counter(cls, value):
        # Invalid/missing counters are unknown, not evidence of zero spend.
        return value if type(value) is int and value >= 0 else None

    def normalized(self, raw):
        output = (
            self.output_tokens + self.thinking_tokens
            if self.output_tokens is not None and self.thinking_tokens is not None
            else None
        )
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": output,
            "total_tokens": self.total_tokens,
            "prompt_tokens_details": {"cached_tokens": self.cached_tokens},
            "completion_tokens_details": {"reasoning_tokens": self.thinking_tokens},
            "gemini": raw,
        }


class GeminiMetadata(BaseModel):
    """Read evidence before checking candidates, including blocked responses."""

    model_config = ConfigDict(extra="ignore", strict=True)
    model_version: str | None = Field(default=None, alias="modelVersion")
    response_id: str | None = Field(default=None, alias="responseId")
    usage: GeminiUsage | None = Field(default=None, alias="usageMetadata")

    @field_validator("model_version", "response_id", mode="before")
    @classmethod
    def usable_identity(cls, value):
        return value if isinstance(value, str) else None

    @field_validator("usage", mode="before")
    @classmethod
    def usable_usage(cls, value):
        return value if isinstance(value, dict) else None

    def evidence(self, body):
        return {
            "model": self.model_version,
            "id": self.response_id,
            "usage": self.usage.normalized(body["usageMetadata"])
            if self.usage is not None
            else None,
        }


class GeminiPart(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    text: str | None = None
    thought: bool = False

    @model_validator(mode="after")
    def visible_text(self):
        if not self.thought and self.text is None:
            raise ValueError("A visible response part needs text")
        return self


class GeminiContent(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    parts: list[GeminiPart] = Field(min_length=1)


class GeminiCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    finish_reason: str = Field(alias="finishReason")
    content: GeminiContent


class GeminiCompletion(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    model_version: str = Field(alias="modelVersion")
    candidates: list[GeminiCandidate] = Field(min_length=1, max_length=1)


class GeminiTokenCount(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    total_tokens: int = Field(alias="totalTokens", ge=0)
