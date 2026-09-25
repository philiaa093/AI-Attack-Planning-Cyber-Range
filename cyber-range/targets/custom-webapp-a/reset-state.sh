#!/usr/bin/env bash
# State reset for lab-webapp-a
set -euo pipefail
TARGET_HOST="${TARGET_HOST:-localhost}"
TARGET_PORT="${TARGET_PORT:-8080}"
response=$(curl -sf -X POST "http://${TARGET_HOST}:${TARGET_PORT}/reset")
echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='reset', f'bad status: {d}'; print('PASS: state-reset lab-webapp-a')"
