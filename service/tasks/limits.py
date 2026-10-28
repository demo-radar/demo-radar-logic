"""Server-owned execution ceilings shared by admission and persistence."""

from dataclasses import dataclass

MAX_JOB_ATTEMPTS = 30
MAX_JOB_EVENTS = 40


@dataclass(frozen=True)
class ExecutionLimits:
    """A task may lower the service ceiling, never raise it."""

    max_attempts: int | None = None
    max_job_attempts: int = MAX_JOB_ATTEMPTS

    def __post_init__(self):
        if (
            type(self.max_job_attempts) is not int
            or not 1 <= self.max_job_attempts <= MAX_JOB_ATTEMPTS
        ):
            raise ValueError(f"Job attempts must be 1–{MAX_JOB_ATTEMPTS}")
        if self.max_attempts is not None and (
            type(self.max_attempts) is not int or self.max_attempts < 1
        ):
            raise ValueError("Input attempts must be a positive integer")
