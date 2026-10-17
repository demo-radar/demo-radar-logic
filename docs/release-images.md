# Tested ARM64 releases

**Publish tested ARM64 service image** runs automatically on every push to
`main`, or manually for a rerun. It runs the shared CI workflow first, then builds a `linux/arm64` image on GitHub's native
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

Docker image IDs can refer to the configuration or the manifest/provenance
index, depending on its storage backend. Verification checks the matching
registry identity and preserves provenance.

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

## Manual deployment

Publication does not deploy. PRs run CI without package-write credentials;
`main` runs shared CI once through the release workflow, then publishes only
if all jobs pass. This avoids a second independent CI run on the same push.

Choose the digest from a successful release artifact. Follow the service's
maintenance and journal-backup procedure before replacing its container. Keep
the current project name, network overrides, runtime settings and journal
volume. Set `DEMOLOGIC_IMAGE` to the approved digest in `service/.env`.

Using the existing Compose invocation, run `pull demologic`, then
`up -d --no-build --no-deps --pull never --wait demologic`. Check readiness
before resuming admission. The Demo Radar operator README provides the `logic`
shell helper with the production network override. Never use `down -v` or
start a second journal when deploying. Retain the previous digest and its
compatible configuration for a manual rollback.

## Image-only staging promotion

DemoLogic deploys independently through `scripts/deploy/image.sh`. Demo Radar's
Jenkins staging flag deploys Radar only; it never selects or replaces Logic.
GitHub Actions publishes the service image but has no access to either runtime host.

Use the successful release's `registry_ref` and `source_commit`, the existing
operator's read-only package login and the target's private runtime settings.
The helper checks a clean matching checkout, Linux ARM64, free disk space and
the persistent journal before replacement. `DEPLOY_MIN_FREE_MB` defaults to 2048;
raise it to cover the actual journal backup and reserve. Images are pulled and
checked before admission is paused or the container is stopped.

The shared network override keeps the API private. Staging remains manual at
five demos per tagging batch and one attempt; production retains its approved
schedules and budgets. Deployment does not edit these settings.

The deployment helper can also be run by an operator in either environment:

```bash
export LOGIC_PROJECT=demologic-staging   # production uses demologic-prod
export DEPLOYMENT_ENV=staging           # or production
export RADAR_DIR=/path/to/existing/demo-radar
export DEMO_RADAR_NETWORK=demo-radar-staging_default
bash scripts/deploy/image.sh --check "$LOGIC_REF" "$LOGIC_COMMIT"
# After approval:
bash scripts/deploy/image.sh --apply "$LOGIC_REF" "$LOGIC_COMMIT"
```

Select the real existing project, checkout and network for that environment.
The helper requires a running service and checks Linux ARM64 and source revision
before maintenance or replacement. It verifies the existing named journal
volume and database path, then blocks new admission, refuses active or unknown
attempts, stops the drained container, and copies its full state
directory before replacement. A missing or empty backup prevents replacement;
the backup checksum is saved with its release record. It uses `--no-build --no-deps --pull never`.

The helper also holds `RADAR_DIR/data/releases/deployment.lock`, alongside its
own lock, so it cannot overlap a Radar deployment. Failure records retain the
phase and exit code. A failure never silently resumes admission or replaces the
previous accepted image reference. Backups include checksums for SQLite side files
as well as the main journal.
Health checks confirm that the saved maintenance state survived. No provider
requests are made. Backups and previous image records are private under
`data/releases`; they must not be committed or uploaded as public CI artifacts.

Admission remains paused for operator acceptance. Resume through authenticated
`DELETE /v1/maintenance` and verify `/health/ready` only after checking the
combined application. If backup fails after stopping the old container, it
stays stopped; fix the backup before safely restarting that same container.
A failed health check leaves the record for manual recovery. Retain previous
digests and compatible configuration; do not delete volumes to roll back.

Deployment helpers are grouped under `scripts/deploy/`: `image.sh` handles
container operations and `state.py` checks the existing journal and admission
state. Runtime network fragments live in Demo Radar's `deploy/` directory;
Markdown under `docs/` contains instructions only. Radar and Logic remain separate operations: Radar owns its database backup;
Logic owns its journal backup. Radar never invokes this helper during its own
release. Neither application resumes admission automatically.
