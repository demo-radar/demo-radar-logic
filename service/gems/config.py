"""Pin the Gem instructions, model profile and structured reply together."""

import copy
import json

from service.inference.results import fingerprint
from service.persistence.journal import AdmissionError
from service.providers.models import MODEL_CATALOG


class GemConfig:
    def __init__(self, base, gem):
        self.gem = gem
        self.gem_sha256 = gem.sha256
        self.base_profile_id = base.version
        self.version = base.version + "-" + gem.version
        self.sha256 = fingerprint({"base": base.sha256, "gem": self.gem_sha256})
        self.provider, self.model, self.endpoint = base.provider, base.model, base.endpoint
        model = MODEL_CATALOG[self.model]
        self.returned_models = (self.model, *model.returned_model_aliases)
        self.rubric_sha256, self.rubric = self.gem_sha256, ""
        settings = copy.deepcopy(base.data["candidate"]["settings"])
        settings["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "tagging_gem",
                "strict": True,
                "schema": gem.output_schema,
            },
        }
        self.data = {
            "wrapper": " ".join(gem.system),
            "maximum_predicted_tags": 2,
            "output_schema": gem.output_schema,
            "candidate": {"settings": settings},
        }

    def payload(self, context):
        payload = copy.deepcopy(self.data["candidate"]["settings"])
        payload["messages"] = [
            {"role": "system", "content": self.data["wrapper"]},
            {
                "role": "user",
                "content": json.dumps(context.model_dump(), ensure_ascii=False, sort_keys=True),
            },
        ]
        # Leave room for output within Radar's minimum 32,000-token reservation.
        if len(json.dumps(payload, ensure_ascii=False).encode()) > 24000:
            raise AdmissionError("gem_input_too_large", 422)
        return payload
