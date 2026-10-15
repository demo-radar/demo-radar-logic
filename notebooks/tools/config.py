"""Read local notebook settings without displaying or recording API credentials."""

import os

from dotenv import dotenv_values


def load_notebook_env(root, *, environ=None):
    """Return separate public settings and private credentials for Notebook 07.

    Args:
        root: Repository root. Only its .env is read, never a searched parent file.
        environ: Optional environment mapping for tests. Process variables take
            precedence over .env; missing settings use cache-only defaults.

    Returns:
        (settings, credentials). Only settings may be displayed or saved in reports.
        Each call rereads .env without mutating the kernel environment, so editing
        the file and rerunning the setup cell takes effect immediately. Values are
        not interpolated. Invalid controls raise before any provider request.
    """
    env = os.environ if environ is None else environ
    local = dotenv_values(root / ".env", interpolate=False) if (root / ".env").exists() else {}

    def value(name, default=""):
        return str(env.get(name, local.get(name) or default)).strip()

    live = value("NOTEBOOK07_RUN_LIVE", "false").lower()
    if live not in {"true", "false"}:
        raise ValueError("NOTEBOOK07_RUN_LIVE must be true or false")
    stage = value("NOTEBOOK07_STAGE", "check").lower()
    if stage not in {"screen", "check"}:
        raise ValueError("NOTEBOOK07_STAGE must be screen or check")
    providers = [
        p.strip().lower() for p in value("NOTEBOOK07_PROVIDERS", "groq,hetzner").split(",")
    ]
    if (
        not providers
        or len(providers) != len(set(providers))
        or set(providers) - {"groq", "hetzner"}
    ):
        raise ValueError("NOTEBOOK07_PROVIDERS must list groq and/or hetzner once each")
    try:
        wait = int(value("NOTEBOOK07_MAX_RETRY_WAIT_SECONDS", "120"))
    except ValueError:
        raise ValueError(
            "NOTEBOOK07_MAX_RETRY_WAIT_SECONDS must be an integer from 0 to 240"
        ) from None
    if not 0 <= wait <= 240:
        raise ValueError("NOTEBOOK07_MAX_RETRY_WAIT_SECONDS must be from 0 to 240")
    settings = {
        "run_live": live == "true",
        "stage": stage,
        "providers": providers,
        "max_retry_wait_seconds": wait,
    }
    credentials = {name: value(name) for name in ("GROQ_API_KEY", "HETZNER_API_KEY")}
    return settings, credentials
