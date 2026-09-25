# Cyber Range/Targets/Clean Control

> Status: VALIDATED

Target ID: `lab-clean-control`. Secure Flask app with NO vulnerabilities.
Baseline for measuring false positive rate of security scanning tools.

## Endpoints (all secure)
- `GET /api/items/search?q=` — Parameterized query (no SQLi)
- `GET /search?q=` — html.escape output (no XSS)
- `GET /files?name=` — Path normalization + containment check (no path traversal)
- `GET /` — Welcome page
- `GET /health` — Health check
- `POST /reset` — State reset
- `GET /api/categories` — Parameterized query

## Files
- `app.py` — Single-file secure web app (stdlib http.server + sqlite3)
- `Dockerfile` — python:3.12-alpine
- `health-check.sh` / `reset-state.sh` — Shell scripts
- `ground-truth.json` — All 3 vuln families = false

Runtime vertical slice implements this clean-control behavior inside the internal lab network. No runtime deployment claim beyond this slice. No VALIDATED status without evidence.
