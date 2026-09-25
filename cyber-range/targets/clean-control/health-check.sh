#!/usr/bin/env bash
# Health check for lab-clean-control
set -euo pipefail
TARGET_HOST="${TARGET_HOST:-localhost}"
TARGET_PORT="${TARGET_PORT:-8080}"
response=$(curl -sf "http://${TARGET_HOST}:${TARGET_PORT}/health")
echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok', f'bad status: {d}'; print('PASS: health-check lab-clean-control')"
