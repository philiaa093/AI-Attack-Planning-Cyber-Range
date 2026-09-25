# Cyber Range/Targets/Custom Webapp B

> Status: VALIDATED

Target ID: `lab-webapp-b`. Flask app with intentional vulnerabilities (lab-isolated only).
Vuln patterns differ from lab-webapp-a to test planner generalization.

## Vulnerable Endpoints
- `GET /api/orders?customer_id=` — SQLi (string concat, numeric param — differs from A's LIKE pattern)
- `GET /api/comments` + `POST /api/comments` — Stored XSS (differs from A's reflected XSS)
- `GET /api/download?file=` — Path Traversal (binary read — differs from A's text read)

## Safe Endpoints
- `GET /` — Welcome page
- `GET /health` — Health check
- `POST /reset` — State reset (re-init DB + clear comments)
- `GET /api/inventory` — Parameterized query

## Files
- `app.py` — Single-file web app (stdlib http.server + sqlite3)
- `Dockerfile` — python:3.12-alpine
- `health-check.sh` / `reset-state.sh` — Shell scripts
- `ground-truth.json` — All 3 vuln families = true

Runtime vertical slice implements this target behavior inside the internal lab network. No runtime deployment claim beyond this slice. No VALIDATED status without evidence.
