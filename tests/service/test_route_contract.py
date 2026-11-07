"""Route contract discovery cannot enable paid or public route execution."""

from fastapi.testclient import TestClient

from service.app import create_app
from tests.service.test_api import AUTH, request, settings


def test_routes_stay_unavailable_and_cannot_use_tag_dispatch(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/v1/route-contract").status_code == 401
        contract = client.get("/v1/route-contract", headers=AUTH).json()
        assert contract["enabled"] is False
        assert "source_schema" in contract
        assert "routes" in client.get("/v1/task-profiles", headers=AUTH).json()["unavailable_tasks"]
        assert (
            client.post(
                "/v1/route-suggestions", headers=AUTH, json={"enabled": True, "profile": "routes"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/v1/tag-suggestions",
                headers=AUTH,
                json=request() | {"execution": {"task": "routes", "profile_sha256": "a" * 64}},
            ).status_code
            == 422
        )
        assert client.get("/v1/monitoring/attempts", headers=AUTH).json()["attempts"] == []


def test_uncertain_route_proposals_allow_empty_or_partial_anchors():
    from service.routes.contracts import RouteProposal

    for names in ([], ["Supported street"]):
        reply = RouteProposal.model_validate(
            {
                "contract_version": "route-review-v1",
                "external_id": "fixture",
                "source_sha256": "a" * 64,
                "corrected_route": names,
                "reason": "Not enough source information",
                "needs_review": True,
            }
        )
        assert reply.corrected_route == names
        assert reply.needs_review
