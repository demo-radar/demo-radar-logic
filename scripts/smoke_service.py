"""Build-independent Docker smoke check using only a synthetic, offline API fixture.

Run after building an image: python scripts/smoke_service.py demologic:local.
Creates its own container, private temporary token file and temporary volume,
then removes those resources. Never reads .env or sends provider requests.
"""

import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


def docker(*args):
    """Run Docker without a shell; return captured output for checks, not logs."""
    return subprocess.check_output(["docker", *args], text=True).strip()


def check(image):
    """Verify container startup, auth, replay and drain persistence across restart."""
    name = "demologic-smoke-" + uuid4().hex[:12]
    volume = name + "-state"
    token = secrets.token_urlsafe(32)
    docker("volume", "create", volume)
    try:
        with tempfile.TemporaryDirectory(prefix="demologic-smoke-") as tmp:
            env = Path(tmp) / "runtime.env"
            env.write_text(
                f"DEMOLOGIC_SERVICE_TOKEN={token}\nDEMOLOGIC_MODE=demo\n"
                "DEMOLOGIC_SUMMARY_ENABLED=true\nDEMOLOGIC_MIN_INTERVAL_SECONDS=0\n"
            )
            env.chmod(0o600)
            docker(
                "run",
                "-d",
                "--name",
                name,
                "--env-file",
                str(env),
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "-v",
                f"{volume}:/app/data/service",
                "-p",
                "127.0.0.1::8000",
                image,
            )

        def address():
            return "http://" + docker("port", name, "8000/tcp").splitlines()[0]

        def call(path, method="GET", body=None, authorized=True):
            headers = {"Content-Type": "application/json"}
            if authorized:
                headers["Authorization"] = f"Bearer {token}"
            req = Request(
                address() + path,
                method=method,
                headers=headers,
                data=json.dumps(body).encode() if body is not None else None,
            )
            try:
                with urlopen(req, timeout=5) as response:
                    return response.status, json.load(response)
            except HTTPError as exc:
                return exc.code, json.load(exc)

        def wait_alive():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                try:
                    if call("/health/live")[0] == 200:
                        return
                except (URLError, ConnectionError, TimeoutError):
                    pass
                time.sleep(0.2)
            raise RuntimeError("Container did not become alive within 20 seconds")

        wait_alive()
        assert call("/v1/task-profiles", authorized=False)[0] == 401
        status, catalog = call("/v1/task-profiles")
        assert status == 200 and catalog["unavailable_tasks"] == ["routes"]
        assert {p["task"] for p in catalog["profiles"]} == {"tagging", "daily-summary"}
        data = {
            "request_id": "smoke-request",
            "job_id": "smoke-job",
            "source_version": "synthetic-v1",
            "event": {"id": "synthetic-smoke", "title": "Für sichere Radwege"},
        }
        assert call("/v1/tag-suggestions", "POST", data, authorized=False)[0] == 401
        status, first = call("/v1/tag-suggestions", "POST", data)
        assert status == 200 and first["tags"] == ["mobility"] and first["mode"] == "demo"
        assert first["new_provider_calls"] == 0
        status, execution = call("/v1/attempts/smoke-request/execution")
        assert status == 200 and execution["profile_sha256"] == first["config_sha256"]
        assert execution["origin"] == "legacy" and execution["provider_seconds"] >= 0
        assert call("/v1/tag-suggestions", "POST", data)[1]["replayed"]
        snapshot = {
            "schema_version": 1,
            "date": "2026-10-10",
            "timezone": "Europe/Berlin",
            "language": "de",
            "visibility_rule": "active-public-feed-v1",
            "coverage": "registered-feed-only",
            "exclusions": [],
            "events": [
                {
                    "id": "synthetic-daily",
                    "title": "Für sichere Radwege",
                    "start": None,
                    "end": None,
                    "location": None,
                    "route": None,
                    "tags": [],
                    "cancelled": None,
                    "uncertainty": [],
                }
            ],
        }
        status, summary_contract = call("/v1/daily-summary-contract")
        assert status == 200
        summary = {
            "request_id": "smoke-summary",
            "job_id": "smoke-summary-job",
            "model_id": summary_contract["config_id"],
            "config_sha256": summary_contract["config_sha256"],
            "snapshot": snapshot,
            "snapshot_sha256": hashlib.sha256(
                json.dumps(
                    snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
        }
        status, daily = call("/v1/daily-summary-drafts", "POST", summary)
        assert status == 200 and daily["status"] == "draft", (status, daily.get("error"))
        assert daily["new_provider_calls"] == 0 and daily["requires_staff_review"]
        assert call("/v1/daily-summary-drafts", "POST", summary)[1]["replayed"]
        assert call("/v1/maintenance", "POST")[1]["drained"]
        assert call("/health/ready")[0] == 503
        docker("stop", "--time", "90", name)
        docker("start", name)
        wait_alive()
        assert call("/health/ready")[0] == 503
        replay = call("/v1/tag-suggestions", "POST", data)[1]
        assert replay["replayed"] and replay["statistics"] == first["statistics"]
        saved_daily = call("/v1/attempts/smoke-summary")[1]
        assert saved_daily["replayed"] and saved_daily["draft"] == daily["draft"]
        assert saved_daily["statistics"] == daily["statistics"]
        assert call("/v1/attempts/smoke-request/execution")[1] == execution
        assert call("/v1/maintenance", "DELETE")[0] == 200
        assert call("/health/ready")[0] == 200
        assert docker("exec", name, "id", "-u") == "10001"
        print(
            "Docker smoke check passed: auth, synthetic tags/daily draft, replay and maintenance restart."
        )
        print("No provider requests or .env access.")
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)
        subprocess.run(["docker", "volume", "rm", volume], capture_output=True, check=False)


if __name__ == "__main__":
    os.umask(0o077)
    check(sys.argv[1] if len(sys.argv) > 1 else "demologic:local")
