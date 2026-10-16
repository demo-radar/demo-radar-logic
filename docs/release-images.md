# Tested ARM64 releases

Run **Publish tested ARM64 service image** manually from `main`. It runs the
shared CI workflow first, then builds a `linux/arm64` image on GitHub's native
ARM runner. The final image passes the offline API, authentication, tag and
summary replay, maintenance and restart checks before it is pushed.

The job uses GitHub's `GITHUB_TOKEN` with package write access. No provider
keys, private datasets or runtime `.env` files are needed. The publishing
Docker configuration is temporary and is removed after the step.

The release tag is:

```text
ghcr.io/demo-radar/demo-radar-logic:sha-<full-source-commit>
```

Download the `service-release-<commit>` workflow artifact. It contains:

- `release.json`: source commit, platform, tested image ID, smoke-log hash and
  the registry digest reference.
- `smoke.log`: the synthetic API and restart check output.

Keep a copy of the current and previous release records before the 90-day
artifact retention expires. CI does not delete registry versions. Keep the
previous version available for rollback.

Publishing refuses dirty sources, feature branches, changed images or changed
smoke evidence. Existing commit tags with different contents cannot be
replaced. A registry or permission error fails the release; it does not
silently skip verification or create a new image build.

For a private image, give the target account package read access only. Keep
publishing credentials off production. Enter the read-only token at Docker's
password prompt:

```bash
docker login ghcr.io --username YOUR_GITHUB_USERNAME
docker pull ghcr.io/demo-radar/demo-radar-logic@sha256:DIGEST_FROM_RELEASE_JSON
```

Use that same digest reference in every environment. Do not rebuild during
promotion. Publication does not deploy the service or change its runtime AI
settings. Test the deployment separately before accepting it.

For local image verification without publishing:

```bash
commit=$(git rev-parse HEAD)
docker build --platform linux/arm64 \
  --label "org.opencontainers.image.revision=$commit" \
  --label "org.opencontainers.image.source=https://github.com/demo-radar/demo-radar-logic" \
  -t "demologic:verify-$commit" .
python3 scripts/release_service.py verify "demologic:verify-$commit"
```

Verification may record uncommitted work for review, but it cannot publish
that work as a release. The release workflow rebuilds the reviewed commit,
verifies it and pushes the verified image without another build.
