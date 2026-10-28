"""Versioned instructions and execution policy for one approved Gem."""

from dataclasses import dataclass, field

from service.execution import ExecutionLimits


@dataclass(frozen=True)
class GemDefinition:
    version: str
    system: tuple[str, ...]
    output_schema: dict
    sha256: str
    limits: ExecutionLimits = field(
        default_factory=lambda: ExecutionLimits(max_attempts=1, max_job_attempts=1)
    )
