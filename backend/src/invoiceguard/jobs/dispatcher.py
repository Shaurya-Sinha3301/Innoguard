"""Outbox dispatcher process: python -m invoiceguard.jobs.dispatcher"""

import logging
import time

from invoiceguard.db.session import SessionLocal
from invoiceguard.jobs.outbox import dispatch_pending
from invoiceguard.jobs.tasks import publish

log = logging.getLogger("invoiceguard.dispatcher")


def main(poll_seconds: float = 1.0) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log.info("dispatcher started")
    while True:
        try:
            result = dispatch_pending(SessionLocal, publish)
            if result.sent or result.failed:
                log.info("outbox sent=%s failed=%s", result.sent, result.failed)
        except Exception:  # database briefly unavailable: log and keep polling
            log.exception("dispatch pass failed")
        time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
