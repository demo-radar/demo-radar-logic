#!/usr/bin/env bash
# Pull a reviewed image, then explicitly replace an existing service after drain and backup.
set -euo pipefail
umask 077
[[ $# == 3 && ( "$1" == --check || "$1" == --apply ) ]] || { echo 'Usage: deploy_image.sh --check|--apply DIGEST_REF SOURCE_COMMIT' >&2; exit 2; }
mode=$1
export DEMOLOGIC_IMAGE=$2
revision=$3
[[ "$DEMOLOGIC_IMAGE" =~ ^ghcr[.]io/demo-radar/demo-radar-logic@sha256:[0-9a-f]{64}$ && "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo 'Use a digest and source commit from successful release evidence.' >&2; exit 2; }
: "${LOGIC_PROJECT:?Set the existing DemoLogic project}"
: "${RADAR_DIR:?Set the Demo Radar checkout}"
: "${DEMO_RADAR_NETWORK:?Set the existing Demo Radar network}"
[[ "$LOGIC_PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || exit 2
[[ "${DEPLOYMENT_ENV:-}" == staging || "${DEPLOYMENT_ENV:-}" == production ]] || { echo 'Choose staging or production.' >&2; exit 2; }
cd "$(dirname "$0")/.."
compose=(docker compose -p "$LOGIC_PROJECT" --env-file service/.env -f compose.yml -f compose.images.yml -f "$RADAR_DIR/docs/operators/compose.demologic-network.yml")
if [[ "$DEPLOYMENT_ENV" == staging ]]; then
    compose+=(-f "$RADAR_DIR/docs/operators/compose.demologic-staging.yml")
fi
"${compose[@]}" config --quiet
container=$("${compose[@]}" ps -q demologic)
[[ -n "$container" ]] || { echo 'Existing DemoLogic service is required; refusing a new journal.' >&2; exit 1; }
"${compose[@]}" pull demologic
identity=$(docker image inspect --format '{{.Os}}/{{.Architecture}}|{{index .Config.Labels "org.opencontainers.image.revision"}}' "$DEMOLOGIC_IMAGE")
[[ "$identity" == "linux/arm64|$revision" ]] || { echo 'DemoLogic architecture or source commit differs.' >&2; exit 1; }
[[ "$mode" == --apply ]] || { echo 'DemoLogic image checked. No containers changed.'; exit 0; }
mkdir -p data/releases
lock=data/releases/deployment.lock
mkdir "$lock" 2>/dev/null || { echo 'Another DemoLogic deployment holds the lock.' >&2; exit 1; }
trap 'rmdir "$lock"' EXIT
record=$(mktemp -d data/releases/release-XXXXXXXX)
docker inspect --format '{{.Config.Image}}|{{.Image}}' "$container" > "$record/previous-image.txt"
printf '%s\n%s\n' "$DEMOLOGIC_IMAGE" "$revision" > "$record/requested-image.txt"
# The token stays inside the running container and is never printed.
docker exec -i "$container" python - <<'PYTHON'
import json, os, urllib.request
request = urllib.request.Request('http://localhost:8000/v1/maintenance', method='POST',
    headers={'Authorization': 'Bearer ' + os.environ['DEMOLOGIC_SERVICE_TOKEN']})
with urllib.request.urlopen(request, timeout=15) as response:
    state = json.load(response)
if not state.get('drained'):
    raise SystemExit('Inference is unresolved. Maintenance remains enabled; inspect recovery before retrying.')
PYTHON
# Stop only after confirmed drainage; copy SQLite and its side files together.
docker stop --time 90 "$container" >/dev/null
docker cp "$container:/app/data/service/." "$record/journal/"
"${compose[@]}" up -d --no-build --no-deps --pull never --wait demologic
"${compose[@]}" exec -T demologic python - <<'PYTHON'
import json, os, urllib.request, urllib.error
request = urllib.request.Request('http://localhost:8000/health/ready',
    headers={'Authorization': 'Bearer ' + os.environ['DEMOLOGIC_SERVICE_TOKEN']})
try:
    response = urllib.request.urlopen(request, timeout=15)
except urllib.error.HTTPError as error:
    if error.code != 503:
        raise
    response = error
with response:
    state = json.load(response)
assert state.get('maintenance') and state.get('drained'), 'Journal maintenance state was not preserved'
PYTHON
printf 'DEMOLOGIC_IMAGE=%s\n' "$DEMOLOGIC_IMAGE" > "$record/current-image.env"
cp "$record/current-image.env" data/releases/current-image.env.tmp
mv data/releases/current-image.env.tmp data/releases/current-image.env
echo "DemoLogic updated; admission stays paused for operator acceptance. Private backup: $record"
