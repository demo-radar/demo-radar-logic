#!/usr/bin/env bash
set -euo pipefail
# Read the pins from Dockerfile so there is only one source of truth.
images=()
while IFS= read -r image; do
  images+=("$image")
done < <(awk 'toupper($1) == "FROM" && $2 ~ /@sha256:/ {print $2}' Dockerfile | sort -u)
if [[ ${#images[@]} == 0 ]]; then
  echo "::error::No pinned base images found in Dockerfile."
  exit 1
fi
for image in "${images[@]}"; do
  for attempt in 1 2 3; do
    if docker pull "$image"; then
      break
    else
      status=$?
    fi
    if [[ "$attempt" == 3 ]]; then
      exit "$status"
    fi
    echo "::warning::Base image pull failed; retrying in $((attempt * 10)) seconds ($attempt/3)."
    sleep $((attempt * 10))
  done
done
