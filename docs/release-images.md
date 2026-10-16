# Tested ARM64 releases

Run **Publish tested ARM64 service image** manually from `main`. It runs the
shared CI workflow first, then builds a `linux/arm64` image on GitHub's native
ARM runner (`ubuntu-26.04-arm`). The final image passes the offline API,
authentication, tag and summary replay, maintenance and restart checks before
it is pushed.

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

## Private package access

Keep this GHCR package **Private**, even though the source repository is public.
Check **Organization > Packages > demo-radar-logic > Package settings**.
New GHCR packages start private. Organization settings should allow only private
package creation. Keep this repository's **Manage Actions access** role at
**Write** so the workflow can publish with its temporary `GITHUB_TOKEN`; no
additional publishing secret is needed in GitHub Actions.

Production uses a separate personal access token **(classic)** with only
`read:packages`. Its owner must have read access to the package; the scope
alone does not grant membership. Authorize organization SSO if required.
Set an expiry and rotate before it expires. Do not grant `repo`, write or
delete access to production. Never copy Jenkins' publishing token there.

Run login on the target host as the account that runs Docker/Compose. Preserve
any existing credential helper. Without one, Docker stores credentials encoded
rather than encrypted, so protect its config with mode `600` and the parent
directory with mode `700`. Enter the token at Docker's password prompt, never
in a command, `.env`, Git or chat message:

```bash
install -d -m 700 "$HOME/.docker"
docker login ghcr.io --username YOUR_GITHUB_USERNAME
chmod 600 "$HOME/.docker/config.json"
docker pull ghcr.io/demo-radar/demo-radar-logic@sha256:DIGEST_FROM_RELEASE_JSON
```

Before pulling, inspect the manifest and confirm `linux/arm64`. Older image
versions may be AMD64 and are not suitable for the current servers. Verify the
approved ARM64 digest can be pulled with the production token. Confirm
package visibility and anonymous access denial too; a network error or missing
digest alone does not prove privacy. To rotate, log in with a replacement
read-only token, verify the pull, then revoke the old token. Running
`docker logout ghcr.io` removes this operator's saved login.

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
