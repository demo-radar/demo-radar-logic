"""Assemble task services while lifecycle owns the HTTP client and server lock."""

from dataclasses import dataclass

from service.config import InferenceConfig
from service.gems.factory import GemFactory
from service.inference.coordinator import InferenceService
from service.inference.profiles import TaskProfiles
from service.persistence.journal import Journal
from service.providers.factory import create_provider, create_summary_provider
from service.summary.config import SummaryConfig
from service.summary.coordinator import SummaryService


@dataclass
class TaskServices:
    service: InferenceService
    profiles: TaskProfiles
    gems: TaskProfiles
    gems_by_base: dict
    summary: SummaryService | None

    def attach(self, state):
        """Keep the existing route dependencies on application state."""
        state.service, state.profiles, state.summary = self.service, self.profiles, self.summary
        state.gems, state.gems_by_base = self.gems, self.gems_by_base

    async def close(self):
        """Drain active work before lifecycle closes the shared HTTP client."""
        for service in [*self.profiles.services.values(), *self.gems.services.values()]:
            await service.close()


class TaskServiceFactory:
    """Build approved task profiles using one managed client and durable journal."""

    def __init__(self, runtime, client):
        self.runtime, self.client = runtime, client
        self.journal = Journal(runtime.database, max_attempts=runtime.max_attempts_per_event)

    def _tagging(self):
        versions = dict.fromkeys(
            (self.runtime.config_id, *self.runtime.retained_tag_configs, "gemini-v4-v1")
        )
        profiles = TaskProfiles()
        for version in versions:
            config = InferenceConfig(self.runtime.root, version)
            profiles.add(
                InferenceService(
                    self.runtime,
                    config,
                    self.journal,
                    create_provider(self.runtime, config, self.client),
                )
            )
        return profiles

    def _gems(self, profiles):
        factory = GemFactory(self.runtime.root)
        gems, by_base = TaskProfiles(), {}
        for base in profiles.services.values():
            for version in factory.catalog.gems:
                service = factory.create(
                    base.config, self.runtime, self.journal, self.client, version
                )
                gems.add(service)
                if version == factory.catalog.default_tagging:
                    by_base[base.config.version] = service
        return gems, by_base

    def _summaries(self, profiles):
        if not self.runtime.summary_enabled:
            return None
        default = None
        versions = dict.fromkeys(
            (
                self.runtime.summary_config_id,
                *self.runtime.retained_summary_configs,
                "hetzner-daily-v1",
                "gemini-daily-v1",
            )
        )
        for version in versions:
            config = SummaryConfig(self.runtime.root, version)
            service = SummaryService(
                self.runtime,
                config,
                Journal(self.runtime.database, max_attempts=self.runtime.summary_max_attempts),
                create_summary_provider(self.runtime, config, self.client),
            )
            profiles.add(service)
            if version == self.runtime.summary_config_id:
                default = service
        return default

    def create(self):
        profiles = self._tagging()
        default = profiles.services[("tagging", self.runtime.config_id)]
        gems, by_base = self._gems(profiles)
        summary = self._summaries(profiles)
        return TaskServices(default, profiles, gems, by_base, summary)
