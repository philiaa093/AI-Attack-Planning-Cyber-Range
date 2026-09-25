#!/usr/bin/env bash
# Health check all cyber-range targets.
# Usage: ./health-check-all.sh [host]
# Status: IMPLEMENTED
set -euo pipefail

HOST="${1:-localhost}"
TARGETS=("lab-webapp-a:18085" "lab-webapp-b:18086" "lab-clean-control:18087")

fail_count=0
for entry in "${TARGETS[@]}"; do
  tid="${entry%%:*}"
  port="${entry##*:}"
  echo "Checking ${tid} on port ${port}..."
  if response=$(curl -sf "http://${HOST}:${port}/health" 2>&1); then
    status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unknown")
    if [ "$status" = "ok" ]; then
      echo "  PASS: ${tid}"
    else
      echo "  FAIL: ${tid} status=${status}"
      ((fail_count++)) || true
    fi
  else
    echo "  FAIL: ${tid} unreachable"
    ((fail_count++)) || true
  fi
done

if [ "$fail_count" -gt 0 ]; then
  echo "WARN: ${fail_count} target(s) unhealthy"
  exit 1
fi
echo "PASS: all targets healthy"
