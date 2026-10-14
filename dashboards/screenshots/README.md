# Dashboards/Screenshots

> Status: SPEC_ONLY

Placeholder contract only. No runtime, deployment, target, adapter, planner, dashboard, experiment result, or integration claim.

---

# Dashboard UI Screenshots & Visual Verification Receipts

This directory houses visual artifacts demonstrating the **Autonomous Cyber Range Control Center**. In accordance with Phase 7 requirements, all presentation claims strictly differentiate between **Real Browser Captures** and **Generated Presentation Images**.

---

## 1. Provenance Audit: Real Browser Captures vs. Generated Images

| File | Type | Source Engine | Viewport / Specs | DOM Selectors Verified | Purpose |
|---|---|---|---|---|---|
| `demo-overview-live.png` | **REAL BROWSER CAPTURE** | Headless Chrome (via Puppeteer) | 1920 × 1080 | `header`, `h1`, `[aria-label="System Components Overview"]` | Full Control Center overview in live presentation mode |
| `demo-presentation-mode-live.png` | **REAL BROWSER CAPTURE** | Headless Chrome (via Puppeteer) | 1366 × 768 | `[aria-label="Professor Presentation Mode Hero"]` | High-contrast Hero view (Current Step Hero + Safety Gate Hero) |
| `demo-runs-live.png` | **REAL BROWSER CAPTURE** | Headless Chrome (via Puppeteer) | 1920 × 1080 | `header`, `table`, `input[placeholder]` | Historical run table, filter bar, and replay entry points |
| `demo-compare-live.png` | **REAL BROWSER CAPTURE** | Headless Chrome (via Puppeteer) | 1920 × 1080 | `header`, `select` | Side-by-side run comparison (RULE vs LLM Fallback metrics diff) |
| `demo-replay-live.png` | **REAL BROWSER CAPTURE** | Headless Chrome (via Puppeteer) | 1920 × 1080 | `header`, `button`, `input[type="range"]` | Historical Run Replay Player (Timeline scrubber & verified ledger) |
| `demo-safety-deny-live.png` | **REAL BROWSER CAPTURE** | Headless Chrome (via Puppeteer) | 1920 × 1080 | `[aria-label="Professor Presentation Mode Hero"]` | Live Safety Gate Refusal state with Guaranteed 0 Network Dispatches |
| `planner-comparison.png` | *GENERATED PRESENTATION IMAGE* | Python PIL (`generate_phase6_screenshots.py`) | 1600 × 900 (Synthetic) | N/A | Static architectural visualization of metrics diff |
| `run-history.png` | *GENERATED PRESENTATION IMAGE* | Python PIL (`generate_phase6_screenshots.py`) | 1600 × 900 (Synthetic) | N/A | Static mockup of run table layout |
| `run-replay.png` | *GENERATED PRESENTATION IMAGE* | Python PIL (`generate_phase6_screenshots.py`) | 1600 × 900 (Synthetic) | N/A | Static mockup of timeline replay player |

> **Note on Verification**: Under Phase 7 & 8, the system strictly relies on `demo-*-live.png` as definitive evidence of live UI execution. Static PIL images are preserved solely for diagrammatic comparison.

---

## 2. Capture Receipts & Environment Metadata

Generated automatically by `scripts/demo/capture_real_browser_screenshots.mjs`:

```json
[
  {
    "file": "demo-overview-live.png",
    "url": "http://127.0.0.1:5173/#overview",
    "resolution": "1920x1080",
    "bytes": 168323,
    "verified_dom_selectors": [
      "header",
      "h1",
      "[aria-label=\"System Components Overview\"]"
    ],
    "description": "Control Center Overview (Presentation Mode Active + Operational Cards)",
    "captured_at_utc": "2026-10-12T10:18:38.070Z"
  },
  {
    "file": "demo-presentation-mode-live.png",
    "url": "http://127.0.0.1:5173/#overview",
    "resolution": "1366x768",
    "bytes": 125060,
    "verified_dom_selectors": [
      "[aria-label=\"Professor Presentation Mode Hero\"]"
    ],
    "description": "Presentation Mode Hero View (Current Step Hero + Safety Gate Hero)",
    "captured_at_utc": "2026-10-12T10:18:54.832Z"
  },
  {
    "file": "demo-runs-live.png",
    "url": "http://127.0.0.1:5173/#runs",
    "resolution": "1920x1080",
    "bytes": 192958,
    "verified_dom_selectors": [
      "header",
      "table",
      "input[placeholder]"
    ],
    "description": "Run History & Indexed Run Ledger (RULE vs LLM Fallback runs)",
    "captured_at_utc": "2026-10-12T10:19:11.634Z"
  },
  {
    "file": "demo-compare-live.png",
    "url": "http://127.0.0.1:5173/#compare",
    "resolution": "1920x1080",
    "bytes": 98367,
    "verified_dom_selectors": [
      "header",
      "select"
    ],
    "description": "Planner Experiment Comparison (RULE Baseline vs LLM Fallback)",
    "captured_at_utc": "2026-10-12T10:19:28.320Z"
  },
  {
    "file": "demo-replay-live.png",
    "url": "http://127.0.0.1:5173/#runs/RUN-AUTONOMOUS-PENTEST-1791712598",
    "resolution": "1920x1080",
    "bytes": 92473,
    "verified_dom_selectors": [
      "header",
      "button",
      "input[type=\"range\"]"
    ],
    "description": "Historical Run Replay Player (Verified Audit Ledger, Step Scrubber & Zero Dispatch Guarantee)",
    "captured_at_utc": "2026-10-12T10:19:45.044Z"
  },
  {
    "file": "demo-safety-deny-live.png",
    "url": "http://127.0.0.1:5173/#overview",
    "resolution": "1920x1080",
    "bytes": 202917,
    "verified_dom_selectors": [
      "[aria-label=\"Professor Presentation Mode Hero\"]"
    ],
    "description": "Safety Gate Refusal Hero (Live Deny State, Red Alert & Zero Outbound Network Dispatch Guarantee)",
    "captured_at_utc": "2026-10-12T10:20:04.633Z"
  }
]
```

---

## 3. Academic & Security Invariants Disclosed in UI

1. **Centralized Safety Gate Authority**:
   - The UI displays explicit verdicts (`PERMITTED` vs `DENIED`).
   - Every `DENIED` decision displays the cryptographic guarantee: `GUARANTEED ZERO OUTBOUND NETWORK DISPATCH (Dispatches: 0)`.
2. **Honest LLM Provenance Disclosure**:
   - The top banner discloses: `LLM PROVIDER E2E NOT RUN — CREDENTIAL NOT CONFIGURED`.
   - The verified `RULE` baseline planner operates without external internet dependencies.
3. **Bilingual Support (Vietnamese & English)**:
   - Full 1-click internationalization toggle on Header persisted in `localStorage`.
