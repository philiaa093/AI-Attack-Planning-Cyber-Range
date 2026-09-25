#!/usr/bin/env bash
# Reset all cyber-range targets to clean initial state.
# Usage: ./reset-all-targets.sh [host] [base_port]
# Status: IMPLEMENTED
set -euo pipefail

HOST="${1:-localhost}"
BASE_PORT="${2:-18085}"
TARGETS=("lab-webapp-a:18085" "lab-webapp-b:18086" "lab-clean-control:18087")

fail_count=0
for entry in "${TARGETS[@]}"; do
  tid="${entry%%:*}"
  port="${entry##*:}"
  echo "Resetting ${tid} on port ${port}..."
  if response=$(curl -sf -X POST "http://${HOST}:${port}/reset" 2>&1); then
    echo "  OK: ${response}"
  else
    echo "  FAIL: ${tid} on port ${port}"
    ((fail_count++)) || true
  fi
done

if [ "$fail_count" -gt 0 ]; then
  echo "WARN: ${fail_count} target(s) failed to reset"
  exit 1
fi
echo "PASS: all targets reset"
