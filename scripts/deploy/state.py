"""Check the existing journal and control admission without provider calls."""

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def check_journal():
    path = Path(os.environ.get("DEMOLOGIC_DATABASE", "/app/data/service/inference.sqlite"))
    if path != Path("/app/data/service/inference.sqlite") or not path.is_file():
        raise RuntimeError("Expected the existing inference journal; refusing a different database")


def control(action):
    check_journal()
    if action == "journal":
        return
    path, method = ("/v1/maintenance", "POST") if action == "pause" else ("/health/ready", "GET")
    request = Request(
        "http://localhost:8000" + path,
        method=method,
        headers={"Authorization": "Bearer " + os.environ["DEMOLOGIC_SERVICE_TOKEN"]},
    )
    try:
        response = urlopen(request, timeout=15)
    except HTTPError as error:
        if action != "paused" or error.code != 503:
            raise
        response = error
    with response:
        state = json.load(response)
    if not state.get("maintenance") or not state.get("drained") or state.get("unresolved_attempts"):
        raise RuntimeError(
            "Inference is unresolved or admission is open. Keep maintenance on and inspect recovery."
        )


if __name__ == "__main__":
    if sys.argv[1:] not in (["journal"], ["pause"], ["paused"]):
        raise SystemExit("Usage: state.py journal|pause|paused")
    control(sys.argv[1])
