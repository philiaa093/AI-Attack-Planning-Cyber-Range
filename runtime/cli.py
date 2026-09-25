"""CLI for bounded internal-network executor actions."""
from __future__ import annotations

import argparse
import json

from .executor import ACTIONS, TARGET_IDS, Executor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("health", "reset", "action"))
    parser.add_argument("target", choices=TARGET_IDS)
    parser.add_argument("action_id", nargs="?", choices=tuple(ACTIONS))
    args = parser.parse_args()
    if args.operation == "action" and args.action_id is None:
        parser.error("action operation requires action_id")
    if args.operation != "action" and args.action_id is not None:
        parser.error("action_id only valid for action operation")
    executor = Executor()
    result = getattr(executor, args.operation)(args.target, args.action_id) if args.operation == "action" else getattr(executor, args.operation)(args.target)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
