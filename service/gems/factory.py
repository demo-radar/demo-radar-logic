"""Load approved Gem versions and assemble their provider-backed services."""

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from service.gems.config import GemConfig
from service.gems.coordinator import GemService
from service.gems.definition import GemDefinition
from service.providers.factory import create_provider


class GemAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(pattern=r"^[a-z0-9-]+\.json$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class GemCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: int = Field(ge=1, le=1)
    default_tagging: str
    gems: dict[str, GemAsset]


class GemFactory:
    """Resolve named, fingerprinted assets; callers cannot supply arbitrary paths."""

    def __init__(self, root):
        self.directory = root / "configs/gems"
        self.catalog = GemCatalog.model_validate_json(
            (self.directory / "catalog.json").read_bytes()
        )

    def definition(self, version=None):
        version = version or self.catalog.default_tagging
        asset = self.catalog.gems.get(version)
        if asset is None:
            raise ValueError("Unsupported Gem version")
        raw = (self.directory / asset.path).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        data = json.loads(raw)
        if digest != asset.sha256 or data["version"] != version:
            raise ValueError("Gem asset does not match its approved version and fingerprint")
        return GemDefinition(version, tuple(data["system"]), data["schema"], digest)

    def config(self, base, version=None):
        return GemConfig(base, self.definition(version))

    def create(self, base, runtime, journal, client, version=None):
        config = self.config(base, version)
        return GemService(runtime, config, journal, create_provider(runtime, config, client))
