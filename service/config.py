"""Load the evaluated inference contract and explicit service runtime settings."""

import copy
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from service.providers.hetzner import QwenProvider


@dataclass(frozen=True)
class Settings:
    """Runtime controls, supplied by Compose or the process environment.

    Demo mode returns synthetic responses without network access. Live mode
    requires explicit confirmation of the free Hetzner account. Paid candidates
    need the later shared spending guard and are not enabled by this prototype.
    The SQLite path must be persistent and shared by all local service processes.

    Inputs are environment variables from service/.env (loaded by Compose), or
    explicit constructor arguments in tests. Defaults use demo mode, 60-second
    timeout, one-second pacing and three attempts/event. Secrets are excluded
    from the object's repr. Raising attempts is an operator action, never an API
    parameter; it does not remove the 40-event/120-attempt batch ceiling.
    """

    token: str = field(repr=False)
    database: Path
    mode: str = "demo"
    provider_key: str = field(default="", repr=False)
    free_tier_confirmed: bool = False
    timeout_seconds: float = 60
    min_interval_seconds: float = 1
    max_attempts_per_event: int = 3
    summary_config_id: str = "daily-summary-v1"
    summary_enabled: bool = False
    summary_max_attempts: int = 3
    summary_timeout_seconds: float = 60
    config_id: str = "qwen-v4-v1"
    root: Path = Path(__file__).resolve().parents[1]

    def __post_init__(self):
        """Fail startup on missing credentials or unsafe runtime limits."""
        if not self.token or self.mode not in {"demo", "live"}:
            raise ValueError("Set DEMOLOGIC_SERVICE_TOKEN and mode demo or live")
        if not 1 <= self.timeout_seconds <= 60 or not 0 <= self.min_interval_seconds <= 300:
            raise ValueError("Timeout must be 1–60 seconds; interval must be 0–300 seconds")
        if (
            type(self.max_attempts_per_event) is not int
            or not 1 <= self.max_attempts_per_event <= 10
        ):
            raise ValueError(
                "Attempts per event must be 1–10; batch attempts remain limited to 120"
            )
        if self.summary_max_attempts not in {3, 5}:
            raise ValueError("Summary attempts must be 3 or 5")
        if not 1 <= self.summary_timeout_seconds <= 60:
            raise ValueError("Summary timeout must be 1–60 seconds")
        if self.mode == "live" and (not self.provider_key or not self.free_tier_confirmed):
            raise ValueError("Live mode requires a Hetzner key and confirmed free-tier account")

    @classmethod
    def from_env(cls):
        """Read process variables; never load or print the notebook credential file."""
        return cls(
            token=os.environ.get("DEMOLOGIC_SERVICE_TOKEN", ""),
            database=Path(os.environ.get("DEMOLOGIC_DATABASE", "data/service/inference.sqlite")),
            mode=os.environ.get("DEMOLOGIC_MODE", "demo"),
            provider_key=os.environ.get("HETZNER_API_KEY", ""),
            free_tier_confirmed=os.environ.get("DEMOLOGIC_FREE_TIER_CONFIRMED") == "true",
            timeout_seconds=float(os.environ.get("DEMOLOGIC_TIMEOUT_SECONDS", "60")),
            min_interval_seconds=float(os.environ.get("DEMOLOGIC_MIN_INTERVAL_SECONDS", "1")),
            max_attempts_per_event=int(os.environ.get("DEMOLOGIC_MAX_ATTEMPTS_PER_EVENT", "3")),
            summary_config_id=os.environ.get("DEMOLOGIC_SUMMARY_CONFIG_ID", "daily-summary-v1"),
            summary_enabled=os.environ.get("DEMOLOGIC_SUMMARY_ENABLED") == "true",
            summary_max_attempts=int(os.environ.get("DEMOLOGIC_SUMMARY_MAX_ATTEMPTS", "3")),
            summary_timeout_seconds=float(
                os.environ.get("DEMOLOGIC_SUMMARY_TIMEOUT_SECONDS", "60")
            ),
            config_id=os.environ.get("DEMOLOGIC_CONFIG_ID", "qwen-v4-v1"),
        )


class InferenceConfig:
    """Verified public prompt assets; no private benchmark files are loaded.

    Request generation matches Notebook 23: full rubric in the system message,
    JSON-encoded original title in the user message, and unchanged model settings.
    A rubric edit fails startup instead of silently changing evaluated behavior.
    """

    def __init__(self, root: Path, config_id: str = "qwen-v4-v1"):
        """Load an explicitly registered configuration and verify its rubric.

        Args:
            root: Repository/image root containing public config and rubric files.
            config_id: Registered configuration ID, not an arbitrary path or URL.
        Raises:
            ValueError: Unknown config, altered rubric, unsupported contract or
                unapproved endpoint. No credentials or network are used here.

        Model/settings and catalog metadata live in JSON. The catalog pins the
        exact evaluated asset; the endpoint allowlist is a deployment boundary.
        """
        catalog = json.loads((root / "configs/inference/catalog.json").read_text())
        if catalog["schema_version"] != 1 or config_id not in catalog["configurations"]:
            raise ValueError("Unknown inference configuration or catalog schema")
        registration = catalog["configurations"][config_id]
        config_path = (root / registration["path"]).resolve()
        if not config_path.is_relative_to((root / "configs/inference").resolve()):
            raise ValueError("Configuration path must remain inside the public catalog")
        config_bytes = config_path.read_bytes()
        self.sha256 = hashlib.sha256(config_bytes).hexdigest()
        if self.sha256 != registration["sha256"]:
            raise ValueError("Approved configuration contract fingerprint changed")
        self.data = json.loads(config_bytes)
        rubric_bytes = (root / self.data["rubric"]["path"]).read_bytes()
        if hashlib.sha256(rubric_bytes).hexdigest() != self.data["rubric"]["sha256"]:
            raise ValueError("Pinned rubric fingerprint changed; approve a new configuration")
        self.rubric = rubric_bytes.decode("utf-8")
        self.rubric_sha256 = self.data["rubric"]["sha256"]
        self.version = self.data["version"]
        self.provider = registration["provider"]
        self.rubric_version = registration["rubric_version"]
        self.model = self.data["candidate"]["model"]
        self.endpoint = self.data["candidate"]["endpoint"]
        if (
            self.version != config_id
            or self.data["taxonomy_version"] != "v2"
            or not isinstance(self.model, str)
            or not self.model
            or self.data["candidate"]["settings"]["model"] != self.model
            or self.data["maximum_predicted_tags"] != 2
        ):
            raise ValueError("Configuration differs from the supported qwen-v4-v1 contract")
        if self.provider != "hetzner" or self.endpoint != QwenProvider.ENDPOINT:
            raise ValueError("Only the approved Hetzner endpoint is supported")

    def payload(self, title: str) -> dict:
        """Build one independent provider payload using the unchanged template.

        Args:
            title: Original event title, already validated by TagRequest.
        Returns:
            A new dictionary with model settings, full rubric system message and
            JSON-encoded title. IDs, reference tags and past responses stay out.
        """
        payload = copy.deepcopy(self.data["candidate"]["settings"])
        payload["messages"] = [
            {
                "role": "system",
                "content": self.data["wrapper"].replace("RUBRIC_VERSION", self.rubric_version)
                + self.rubric,
            },
            {"role": "user", "content": json.dumps({"title": title}, ensure_ascii=False)},
        ]
        return payload
