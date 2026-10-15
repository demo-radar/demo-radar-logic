"""Explicit operator recovery; never turn unknown usage into a success."""

import logging

from service.persistence.locking import activity_lock

logger = logging.getLogger(__name__)


class RecoveryService:
    """Close a finalized timeout while excluding all local inference processes.

    The caller supplies the authenticated operator and a reason. Journal guards
    require a saved unknown result at least 15 minutes old. The original result
    and attempt count stay unchanged, and that exact input remains blocked.
    This records an accepted uncertainty; it cannot cancel or inspect a remote
    provider call. A crashed, unfinished marker still needs offline investigation.
    """

    def __init__(self, journal):
        self.journal = journal

    def close(self, request_id, *, operator, reason):
        """Return the saved resolution and resume admission, without inference.

        Repeating the same decision is safe after a lost response. A conflicting
        decision or active local call is rejected. If validation fails after
        pausing, maintenance stays enabled for the operator to inspect.
        """
        with activity_lock(self.journal.path, exclusive=True):
            self.journal.maintenance(True)
            resolution = self.journal.close_unknown(request_id, operator=operator, reason=reason)
            state = self.journal.maintenance(False)
        logger.warning("event=unknown_attempt_closed request=%s", request_id)
        return {"resolution": resolution, **state}
