"""Read-only approved profiles and startup-owned task services."""

from demo_logic.taxonomy import topic_tags
from service.inference.contracts import ProfileCatalog, ProfileDescriptor
from service.persistence.journal import AdmissionError


def describe_profile(task, config, enabled=True):
    """Return public identities and limits, never instructions or credentials."""
    from service.inference.results import fingerprint

    if task == "tagging":
        instructions = fingerprint(
            {"wrapper": config.data["wrapper"], "rubric_sha256": config.rubric_sha256}
        )
        example = None
        schema = {
            "taxonomy": "v2",
            "maximum_tags": config.data["maximum_predicted_tags"],
            "allowed_tags": sorted(topic_tags("v2")),
        }
        schema = config.data.get("output_schema", schema)
        output_tokens = config.data["candidate"]["settings"]["max_completion_tokens"]
    else:
        instructions = fingerprint(config.data["system"])
        example = config.data.get("example", {}).get("sha256")
        schema = config.data["settings"].get("response_format", {})
        output_tokens = config.data["settings"]["max_completion_tokens"]
    contract = (
        config.contract()
        if task == "daily-summary"
        else {
            "config_id": config.version,
            "config_sha256": config.sha256,
            "rubric_sha256": config.rubric_sha256,
            "taxonomy_version": "v2",
            "provider": config.provider,
            "requested_model": config.model,
            "maximum_tags": 2,
        }
    )
    descriptor = {
        "contract": contract,
        "task": task,
        "profile_id": config.version,
        "profile_sha256": config.sha256,
        "provider": config.provider,
        "model": config.model,
        "instructions_sha256": instructions,
        "example_sha256": example,
        "schema_sha256": fingerprint(schema),
        "maximum_output_tokens": output_tokens,
        "enabled": enabled,
    }
    return ProfileDescriptor.model_validate(descriptor).model_dump(mode="json", exclude_unset=True)


class TaskProfiles:
    """Resolve only explicitly loaded profiles; defaults belong to Demo Radar."""

    def __init__(self):
        self.services = {}

    def add(self, service):
        key = (service.task, service.config.version)
        if key in self.services:
            raise ValueError("Duplicate task profile")
        self.services[key] = service

    def resolve(self, task, request):
        if request.execution is not None and request.execution.task != task:
            raise AdmissionError("unsupported_task_profile", 422)
        service = self.services.get((task, request.model_id))
        if service is None:
            raise AdmissionError("unsupported_configuration", 422)
        if (
            request.execution is not None
            and request.execution.profile_sha256 != service.config.sha256
        ):
            raise AdmissionError("unsupported_configuration", 422)
        return service

    @staticmethod
    def describe(service):
        from service.persistence.spending import policy

        enabled, reason = True, None
        try:
            policy(service.settings, service.config)
        except AdmissionError as exc:
            enabled, reason = False, exc.code
        descriptor = describe_profile(service.task, service.config, enabled)
        if service.task == "daily-summary":
            descriptor["contract"]["max_attempts"] = service.settings.summary_max_attempts
        return ProfileDescriptor.model_validate(
            {**descriptor, "unavailable_reason": reason}
        ).model_dump(mode="json", exclude_unset=True)

    def catalog(self):
        catalog = ProfileCatalog(
            schema_version=1,
            profiles=[self.describe(service) for service in self.services.values()],
            unavailable_tasks=[
                task
                for task in ("tagging", "daily-summary", "routes")
                if not any(key[0] == task for key in self.services)
            ],
        )
        return catalog.model_dump(mode="json", exclude_unset=True)
