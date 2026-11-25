# Local credentials with Bitwarden Secrets Manager

DemoLogic and Demo Radar can read credentials from Bitwarden at Compose startup.
This is a local setup for developers. Keep each environment's credentials in its
own project and use a read-only local machine account.

## Keep real credentials outside agent access

Use two environments. Give agents an isolated VM or sandbox with its own
Docker daemon and separate synthetic credentials. Run the real stack in an
operator-controlled VM with its own Docker daemon and private checkout. Agents
must lack access to the operator VM's console, SSH, filesystem, Docker socket
and contexts, Bitwarden session, machine token, and app administration. Keep
the original credential files and any recovery copies outside agent access.
Share health results through app endpoints or sanitized output. Before moving
real credentials, verify from the agent environment that it cannot open the
operator checkout, reach operator SSH or Docker, or use the operator's vault.
Use dummy credentials for that check.

Build or pull and review the exact images in the operator environment before
loading any credentials. Review the Compose files and keep the operator copies
outside agent write access. The Radar override removes development source
mounts so editing a checkout cannot change the code that receives credentials.
Keep the machine token in an operator-only password manager or keychain and
use it from the operator's terminal. A read-only machine account still reads
every credential granted to it.

[Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/) mount
per-service files and reduce accidental exposure through environment inspection.
The application and anyone controlling its Docker daemon can still read the
mounted files. This setup relies on the isolated operator environment and uses
the apps' existing environment-variable interfaces.

## Prepare the project

1. Install the [Secrets Manager CLI](https://bitwarden.com/help/secrets-manager-cli/).
   Create a local project and give a [machine account](https://bitwarden.com/help/machine-accounts/)
   read access to it. Store its access token in your local keychain or password
   manager. Use the vault's server configuration for your account region.
2. In the Secrets Manager web app, add each active credential under its exact
   environment variable name. Copy the existing value unchanged.

   | Used by | Secret names |
   | --- | --- |
   | Both apps | `DEMOLOGIC_SERVICE_TOKEN` |
   | DemoLogic | `OPENAI_API_KEY`, `GEMINI_API_KEY`, `HETZNER_API_KEY` for the providers you use |
   | Demo Radar | `POSTGRES_PASSWORD`, `GRAFANA_ADMIN_PASSWORD`, `GRAFANA_DB_PASSWORD` if separate, `SECRET_KEY`, `MFA_ENCRYPTION_KEY`, `RECOVERY_CODE_PEPPER`, `USER_EVENT_IP_SALT`, `ORS_API_KEY`, `GEOAPIFY_API_KEY`, `DEEPL_API_KEY`, `MCP_API_TOKENS` if configured |

   Check that the existing service tokens match before storing the shared
   value. Preserve the existing database password for an initialized database,
   and keep existing session and encryption keys to preserve sessions and MFA.
   Store only the documented variable names in this project.
3. Keep an encrypted recovery copy of the original local settings until both
   apps pass the startup check. Keep non-secret settings in DemoLogic's
   `service/.env` and Radar's `.env` and optional `.env_ai`. Remove credential
   assignments and credential-bearing connection strings before the test.
   Radar Compose builds its local database URL from the injected password.
   Leave existing volume settings intact if reusing local data. Notebook
   credentials are managed separately from this service setup.

## Start and verify

Use Bash inside the operator environment. Set the project ID and reviewed
checkout paths, then enter the machine token at the hidden prompt. Set
`DEMOLOGIC_IMAGE` in `service/.env` to the reviewed local image or digest.
Have the reviewed Radar and dependency images available in the same Docker
daemon under the names selected by the Radar Compose project. Startup uses only
those images and removes the machine token before running Compose.

```bash
(
  set +x
  set -e
  export BWS_PROJECT_ID=your-local-project-id
  read -rs -p 'Bitwarden machine token: ' BWS_ACCESS_TOKEN
  printf '\n'
  export BWS_ACCESS_TOKEN
  export LOGIC_DIR=/absolute/path/to/demo-radar-logic
  export RADAR_DIR=/absolute/path/to/demo-radar
  export DEMOLOGIC_PORT=8005

  bws run --project-id "$BWS_PROJECT_ID" -- \
    'unset BWS_ACCESS_TOKEN; cd "$LOGIC_DIR" && docker compose --env-file service/.env up -d --no-build --pull never'

  bws run --project-id "$BWS_PROJECT_ID" -- \
    'unset BWS_ACCESS_TOKEN; cd "$RADAR_DIR" && docker compose --env-file .env -f docker-compose.yml -f "$LOGIC_DIR/compose.radar-local.yml" up -d --no-build --pull never db redis backend frontend'
)
```

For the first verification, use dummy credentials, disposable development
volumes and DemoLogic's `DEMOLOGIC_MODE=demo`. Keep Radar's live and scheduled
inference disabled.
Check Radar in the browser and confirm that its backend can reach DemoLogic
with the shared token. From the Radar checkout, run this against the running stack.

```bash
docker exec "$(docker ps -q --filter label=com.docker.compose.project=demo-radar \
  --filter label=com.docker.compose.service=backend)" python -c '
import os
from urllib.request import Request, urlopen
request = Request(os.environ["DEMOLOGIC_BASE_URL"] + "/health/ready",
                  headers={"Authorization": "Bearer " + os.environ["DEMOLOGIC_SERVICE_TOKEN"]})
with urlopen(request, timeout=5) as response:
    print(response.status)
'
```

The check should print `200`. Adjust the Compose project name in the filter if
you set a custom name. On Linux, use a DemoLogic URL reachable from the Radar
backend container, such as a private shared Docker network. Pass a matching
`DEMOLOGIC_BASE_URL` through the launcher.

Supply the secrets again when recreating containers. Keep the machine token and
provider keys out of the Radar backend and frontend. Compose passes credentials
as container environment variables, which users with Docker access can inspect.
Avoid printing rendered Compose configuration or container environments.
