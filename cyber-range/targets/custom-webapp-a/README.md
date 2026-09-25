# Cyber Range/Targets/Custom Webapp A

> Status: VALIDATED

Target ID: `lab-webapp-a`. Flask app with intentional vulnerabilities (lab-isolated only).

## Vulnerable Endpoints
- `GET /api/users/search?q=` — SQLi (string concat)
- `GET /search?q=` — Reflected XSS (unescaped output)
- `GET /files?name=` — Path Traversal (unsanitized join)

## Safe Endpoints
- `GET /` — Welcome page
- `GET /health` — Health check
- `POST /reset` — State reset (re-init DB)
- `GET /api/products` — Parameterized query

## Files
- `app.py` — Single-file web app (stdlib http.server + sqlite3)
- `Dockerfile` — python:3.12-alpine
- `health-check.sh` / `reset-state.sh` — Shell scripts
- `ground-truth.json` — All 3 vuln families = true

Runtime vertical slice implements this target behavior inside the internal lab network. No runtime deployment claim beyond this slice. No VALIDATED status without evidence.
