"""CLI Entrypoint to run an individual Enterprise Range Target in a Docker Container."""
from __future__ import annotations

import os
import sys
from http.server import ThreadingHTTPServer

from runtime.lab.enterprise_range.services import (
    CleanControlServiceHandler,
    DecoyServiceHandler,
    DMZServiceHandler,
    InternalServiceHandler,
    RestrictedServiceHandler,
    TargetState,
)

HANDLERS = {
    "lab-enterprise-dmz": (DMZServiceHandler, "ZONE_DMZ"),
    "lab-enterprise-internal": (InternalServiceHandler, "ZONE_INTERNAL"),
    "lab-enterprise-restricted": (RestrictedServiceHandler, "ZONE_RESTRICTED"),
    "lab-enterprise-decoy": (DecoyServiceHandler, "ZONE_DECOY"),
    "lab-enterprise-clean": (CleanControlServiceHandler, "ZONE_CLEAN"),
}


def main() -> None:
    target_id = os.environ.get("TARGET_ID", "lab-enterprise-dmz")
    port = int(os.environ.get("PORT", "8080"))

    if target_id not in HANDLERS:
        print(f"Error: Unknown target ID '{target_id}'", file=sys.stderr)
        sys.exit(1)

    handler_cls, zone_id = HANDLERS[target_id]
    state = TargetState(target_id=target_id, zone_id=zone_id)

    class ContainerBoundHandler(handler_cls):
        target_state = state

    server = ThreadingHTTPServer(("0.0.0.0", port), ContainerBoundHandler)
    print(f"Starting {target_id} ({zone_id}) on port {port}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
