"""Close investigated unknown outcomes while the DemoLogic server is stopped.

Example:
    python -m service.persistence.recover --request-id REQUEST_ID \
        --operator local-admin --reason "Investigated saved timeout; abandon result" \
        --accept-unknown-outcome

This requires a local file lock held by the API throughout its lifetime. No
provider call is made. Original unknown responses remain available for lookup.
"""

import argparse

from service.config import Settings
from service.persistence.journal import Journal
from service.persistence.locking import server_lock


def main():
    """Require explicit acknowledgement, an idle server and a paused journal."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--accept-unknown-outcome", action="store_true", required=True)
    args = parser.parse_args()
    settings = Settings.from_env()
    with server_lock(settings.database, exclusive=True):
        journal = Journal(settings.database)
        result = journal.close_unknown(args.request_id, operator=args.operator, reason=args.reason)
        print(
            "Unknown result retained; unrelated work may resume. Resolution:", result["request_id"]
        )


if __name__ == "__main__":
    main()
