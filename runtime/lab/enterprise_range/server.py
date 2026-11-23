"""CLI Entrypoint to run an individual Enterprise Range Target in a Docker Container."""
from __future__ import annotations

import os
import sys
import threading
from http.server import ThreadingHTTPServer

from runtime.lab.enterprise_range.control import ControlPlaneHandler
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
    control_port = int(os.environ.get("CONTROL_PORT", "9090"))
    control_token = os.environ.get("RANGE_CONTROL_TOKEN", "")

    if target_id not in HANDLERS:
        print(f"Error: Unknown target ID '{target_id}'", file=sys.stderr)
        sys.exit(1)
    if len(control_token) < 32:
        print("Error: RANGE_CONTROL_TOKEN must be provided with at least 32 characters", file=sys.stderr)
        sys.exit(1)

    handler_cls, zone_id = HANDLERS[target_id]
    state = TargetState(target_id=target_id, zone_id=zone_id)

    class ContainerBoundHandler(handler_cls):
        target_state = state

    class ContainerControlHandler(ControlPlaneHandler):
        target_state = state

    ContainerControlHandler.control_token = control_token

    data_server = ThreadingHTTPServer(("0.0.0.0", port), ContainerBoundHandler)
    control_server = ThreadingHTTPServer(("0.0.0.0", control_port), ContainerControlHandler)
    control_thread = threading.Thread(
        target=control_server.serve_forever,
        name=f"ControlPlane-{target_id}",
        daemon=True,
    )
    control_thread.start()
    print(f"Starting {target_id} ({zone_id}) data and authenticated control planes...")
    try:
        data_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        data_server.server_close()
        control_server.shutdown()
        control_server.server_close()
        control_thread.join(timeout=2.0)


if __name__ == "__main__":
    main()
