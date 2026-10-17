#!/usr/bin/env bash
# Pull a reviewed image, then explicitly replace an existing service after drain and backup.
set -euo pipefail
umask 077
[[ $# == 3 && ( "$1" == --check || "$1" == --pause || "$1" == --apply ) ]] || { echo 'Usage: image.sh --check|--pause|--apply DIGEST_REF SOURCE_COMMIT' >&2; exit 2; }
mode=$1
export DEMOLOGIC_IMAGE=$2
revision=$3
[[ "$DEMOLOGIC_IMAGE" =~ ^ghcr[.]io/demo-radar/demo-radar-logic@sha256:[0-9a-f]{64}$ && "$revision" =~ ^[0-9a-f]{40}$ ]] || { echo 'Use a digest and source commit from successful release evidence.' >&2; exit 2; }
: "${LOGIC_PROJECT:?Set the existing DemoLogic project}"
: "${RADAR_DIR:?Set the Demo Radar checkout}"
: "${DEMO_RADAR_NETWORK:?Set the existing Demo Radar network}"
[[ "$LOGIC_PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || exit 2
[[ "${DEPLOYMENT_ENV:-}" == staging || "${DEPLOYMENT_ENV:-}" == production ]] || { echo 'Choose staging or production.' >&2; exit 2; }
cd "$(dirname "$0")/../.."
if [[ "$mode" != --check ]]; then
    mkdir -p data/releases "$RADAR_DIR/data/releases"
    shared_lock="$RADAR_DIR/data/releases/deployment.lock"
    lock=data/releases/deployment.lock
    mkdir "$shared_lock" 2>/dev/null || { echo 'Another application deployment holds the shared lock.' >&2; exit 1; }
    if ! mkdir "$lock" 2>/dev/null; then
        rmdir "$shared_lock"
        echo 'Another DemoLogic deployment holds the lock.' >&2; exit 1
    fi
    phase=preflight
    record=$(mktemp -d data/releases/release-XXXXXXXX)
    finish() {
        result=$?
        trap - EXIT
        printf 'phase=%s\nexit_code=%s\n' "$phase" "$result" > "$record/result.txt"
        rmdir "$lock" "$shared_lock"
        exit "$result"
    }
    trap finish EXIT
fi
[[ "$(git rev-parse HEAD)" == "$revision" && -z "$(git status --porcelain --untracked-files=no)" ]] || { echo 'Use the clean reviewed source revision.' >&2; exit 1; }
host=$(docker info --format '{{.OSType}}/{{.Architecture}}')
[[ "$host" == linux/arm64 || "$host" == linux/aarch64 ]] || { echo 'This release requires Linux ARM64.' >&2; exit 1; }
minimum=${DEPLOY_MIN_FREE_MB:-2048}
[[ "$minimum" =~ ^[1-9][0-9]*$ ]] || { echo 'DEPLOY_MIN_FREE_MB must be positive.' >&2; exit 2; }
check_space() {
    available=$(df -Pk . | awk 'NR == 2 {print $4}')
    [[ "$available" =~ ^[0-9]+$ && "$available" -ge "$((minimum * 1024))" ]] || { echo 'Insufficient free disk space for deployment and backup.' >&2; exit 1; }
}
check_space
compose=(docker compose -p "$LOGIC_PROJECT" --env-file service/.env -f compose.yml -f compose.images.yml -f "$RADAR_DIR/deploy/compose.demologic-network.yml")
if [[ "$DEPLOYMENT_ENV" == staging ]]; then
    compose+=(-f "$RADAR_DIR/deploy/compose.demologic-staging.yml")
fi
"${compose[@]}" config --quiet
container=$("${compose[@]}" ps -q demologic)
[[ -n "$container" ]] || { echo 'Existing DemoLogic service is required; refusing a new journal.' >&2; exit 1; }
mount=$(docker inspect --format '{{.State.Running}}|{{range .Mounts}}{{if eq .Destination "/app/data/service"}}{{.Type}}|{{.Name}}{{end}}{{end}}' "$container")
[[ "$mount" == "true|volume|${LOGIC_PROJECT}_inference-state" ]] || { echo 'Existing journal volume differs; refusing a new or relocated journal.' >&2; exit 1; }
docker exec -i "$container" python - journal < scripts/deploy/state.py
"${compose[@]}" pull demologic
identity=$(docker image inspect --format '{{.Os}}/{{.Architecture}}|{{index .Config.Labels "org.opencontainers.image.revision"}}' "$DEMOLOGIC_IMAGE")
[[ "$identity" == "linux/arm64|$revision" ]] || { echo 'DemoLogic architecture or source commit differs.' >&2; exit 1; }
check_space
[[ "$mode" != --check ]] || { echo 'DemoLogic image checked. No containers changed.'; exit 0; }
phase=drain
[[ "$("${compose[@]}" ps -q demologic)" == "$container" ]] || { echo 'DemoLogic changed during validation; retry after checking the active deployment.' >&2; exit 1; }
# The token stays inside the running container and is never printed.
docker exec -i "$container" python - pause < scripts/deploy/state.py
[[ "$mode" == --apply ]] || { echo 'DemoLogic is drained; admission remains paused.'; exit 0; }
docker inspect --format '{{.Config.Image}}|{{.Image}}' "$container" > "$record/previous-image.txt"
printf '%s\n%s\n' "$DEMOLOGIC_IMAGE" "$revision" > "$record/requested-image.txt"
# Stop only after confirmed drainage; copy SQLite and its side files together.
phase=backup
docker stop --time 90 "$container" >/dev/null
docker cp "$container:/app/data/service/." "$record/journal/"
[[ -s "$record/journal/inference.sqlite" ]] || { echo "Journal backup is missing or empty. Keep the old container stopped; see $record" >&2; exit 1; }
(cd "$record/journal" && sha256sum ./*) > "$record/journal.sha256"
phase=replace
"${compose[@]}" up -d --no-build --no-deps --pull never --wait demologic
phase=verify
"${compose[@]}" exec -T demologic python - paused < scripts/deploy/state.py
printf 'DEMOLOGIC_IMAGE=%s\n' "$DEMOLOGIC_IMAGE" > "$record/current-image.env"
cp "$record/current-image.env" data/releases/current-image.env.tmp
mv data/releases/current-image.env.tmp data/releases/current-image.env
phase=awaiting_acceptance
echo "DemoLogic updated; admission stays paused for operator acceptance. Private backup: $record"
