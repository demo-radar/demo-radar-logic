"""Load the evaluated inference contract and explicit service runtime settings."""

import copy
import hashlib
import json
import os
from dataclasses import field
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field
from pydantic.dataclasses import dataclass

from service.environment import SETTINGS_VALIDATION, env_bool, env_number
from service.providers.gemini import GeminiProvider
from service.providers.hetzner import HetznerProvider


@dataclass(frozen=True, config=SETTINGS_VALIDATION)
class Settings:
    """Runtime controls, supplied by Compose or the process environment.

    Demo mode returns synthetic responses without network access. Live mode
    requires a confirmed free Hetzner account or explicitly enabled Gemini.
    Gemini dispatch also requires configured monetary limits and an account.
    The SQLite path must be persistent and shared by all local service processes.

    Inputs are environment variables from service/.env (loaded by Compose), or
    explicit constructor arguments in tests. Defaults use demo mode, 60-second
    timeout, one-second pacing and three attempts/event. Secrets are excluded
    from the object's repr. Raising attempts is an operator action, never an API
    parameter; it does not remove the 40-event/30-attempt batch ceiling.
    """

    token: Annotated[str, Field(min_length=1)] = field(repr=False)
    database: Path
    mode: Literal["demo", "live"] = "demo"
    provider_key: str = field(default="", repr=False)
    free_tier_confirmed: bool = False
    timeout_seconds: Annotated[int | float, Field(ge=1, le=60)] = 60
    min_interval_seconds: Annotated[int | float, Field(ge=0, le=300)] = 1
    max_attempts_per_event: Annotated[int, Field(ge=1, le=10)] = 3
    summary_config_id: str = "hetzner-daily-v1"
    summary_enabled: bool = False
    summary_max_attempts: Literal[3, 5] = 3
    summary_timeout_seconds: Annotated[int | float, Field(ge=1, le=60)] = 60
    config_id: str = "qwen-v4-v1"
    retained_tag_configs: tuple[str, ...] = ()
    retained_summary_configs: tuple[str, ...] = ()
    gemini_key: str = field(default="", repr=False)
    gemini_enabled: bool = False
    paid_account: str = ""
    paid_run_usd: str = ""
    paid_period_usd: str = ""
    paid_account_usd: str = ""
    environment: Literal["unspecified", "local", "staging", "production", "test"] = "unspecified"
    root: Path = Path(__file__).resolve().parents[1]

    def __post_init__(self):
        """Fail startup on missing credentials or unsafe runtime limits."""
        if (
            self.mode == "live"
            and not self.gemini_enabled
            and (not self.provider_key or not self.free_tier_confirmed)
        ):
            raise ValueError(
                "Live mode requires a confirmed free-provider account "
                "or an explicitly enabled paid provider"
            )

    @classmethod
    def from_env(cls):
        """Read process variables; never load or print the notebook credential file."""
        return cls(
            token=os.environ.get("DEMOLOGIC_SERVICE_TOKEN", ""),
            database=Path(os.environ.get("DEMOLOGIC_DATABASE", "data/service/inference.sqlite")),
            mode=os.environ.get("DEMOLOGIC_MODE", "demo"),
            provider_key=os.environ.get("HETZNER_API_KEY", ""),
            free_tier_confirmed=env_bool("DEMOLOGIC_FREE_TIER_CONFIRMED"),
            timeout_seconds=env_number("DEMOLOGIC_TIMEOUT_SECONDS", 60, kind=float),
            min_interval_seconds=env_number("DEMOLOGIC_MIN_INTERVAL_SECONDS", 1, kind=float),
            max_attempts_per_event=env_number("DEMOLOGIC_MAX_ATTEMPTS_PER_EVENT", 3),
            summary_config_id=os.environ.get("DEMOLOGIC_SUMMARY_CONFIG_ID", "hetzner-daily-v1"),
            summary_enabled=env_bool("DEMOLOGIC_SUMMARY_ENABLED"),
            summary_max_attempts=env_number("DEMOLOGIC_SUMMARY_MAX_ATTEMPTS", 3),
            summary_timeout_seconds=env_number("DEMOLOGIC_SUMMARY_TIMEOUT_SECONDS", 60, kind=float),
            config_id=os.environ.get("DEMOLOGIC_CONFIG_ID", "qwen-v4-v1"),
            retained_tag_configs=tuple(
                filter(None, os.environ.get("DEMOLOGIC_RETAINED_TAG_CONFIGS", "").split(","))
            ),
            retained_summary_configs=tuple(
                filter(None, os.environ.get("DEMOLOGIC_RETAINED_SUMMARY_CONFIGS", "").split(","))
            ),
            environment=os.environ.get("DEMOLOGIC_ENVIRONMENT", "unspecified"),
            gemini_key=os.environ.get("GEMINI_API_KEY", ""),
            gemini_enabled=env_bool("DEMOLOGIC_GEMINI_ENABLED"),
            paid_account=os.environ.get("DEMOLOGIC_GEMINI_ACCOUNT", ""),
            paid_run_usd=os.environ.get("DEMOLOGIC_PAID_RUN_USD", ""),
            paid_period_usd=os.environ.get("DEMOLOGIC_PAID_PERIOD_USD", ""),
            paid_account_usd=os.environ.get("DEMOLOGIC_PAID_ACCOUNT_USD", ""),
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
            raise ValueError("Configuration does not match its registered tagging profile")
        endpoints = {
            "hetzner": HetznerProvider.ENDPOINT,
            "gemini": GeminiProvider.endpoint_for(self.model),
        }
        if self.endpoint != endpoints.get(self.provider):
            raise ValueError("Only approved provider endpoints are supported")

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
