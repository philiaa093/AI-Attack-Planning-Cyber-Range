"""Generate high-fidelity UI screenshots for Phase 6 Research Experiment Dashboard."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SCREENSHOTS_DIR = ROOT / "dashboards" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Color Palette matching Tailwind dark-slate UI
BG_DARK = (10, 14, 23)        # #0a0e17
BG_CARD = (17, 23, 36)        # #111724
BG_PANEL = (15, 23, 42)       # #0f172a
BORDER = (30, 41, 59)         # #1e293b
BORDER_ACCENT = (51, 65, 85)  # #334155
TEXT_WHITE = (248, 250, 252)
TEXT_GRAY = (148, 163, 184)
TEXT_MUTED = (100, 116, 139)
BLUE_ACCENT = (37, 99, 235)   # #2563eb
BLUE_LIGHT = (96, 165, 250)
CYAN_ACCENT = (6, 182, 212)
EMERALD_GREEN = (16, 185, 129)
EMERALD_BG = (6, 78, 59, 180)
AMBER_YELLOW = (245, 158, 11)
AMBER_BG = (120, 53, 15, 180)
ROSE_RED = (244, 63, 94)
ROSE_BG = (136, 19, 55, 180)


def draw_header(draw: ImageDraw.ImageDraw, active_tab: str = "Overview", run_id: str = "RUN-AUTONOMOUS-LIVE"):
    # Header background
    draw.rectangle([0, 0, 1600, 60], fill=(17, 23, 36))
    draw.line([0, 60, 1600, 60], fill=BORDER, width=1)

    # Shield icon badge & Title
    draw.rectangle([20, 12, 54, 46], fill=(23, 37, 84), outline=(30, 58, 138))
    draw.text((28, 20), "🛡", fill=BLUE_LIGHT)
    draw.text((64, 15), "AUTONOMOUS CYBER RANGE CONTROL CENTER", fill=TEXT_WHITE)
    draw.rectangle([455, 16, 545, 34], fill=(6, 78, 59), outline=(4, 120, 87))
    draw.text((465, 19), "ISOLATED LAB", fill=EMERALD_GREEN)
    draw.text((64, 35), "Research Prototype: Bounded Autonomous Discovery & Policy Enforcement", fill=TEXT_MUTED)

    # Center Tabs: Overview, Runs, Compare
    tab_x = 640
    tabs = ["Overview", "Runs", "Compare"]
    for t in tabs:
        is_active = (t == active_tab)
        w = 90
        if is_active:
            draw.rectangle([tab_x, 14, tab_x + w, 44], fill=BLUE_ACCENT)
            draw.text((tab_x + 18, 22), t, fill=TEXT_WHITE)
        else:
            draw.rectangle([tab_x, 14, tab_x + w, 44], fill=(15, 23, 42), outline=BORDER)
            draw.text((tab_x + 18, 22), t, fill=TEXT_GRAY)
        tab_x += w + 8

    # Right: Operational Strip
    # Run ID badge
    draw.rectangle([1020, 16, 1230, 42], fill=(15, 23, 42), outline=BORDER)
    draw.text((1030, 23), f"RUN: {run_id[:16]}", fill=TEXT_GRAY)

    # Mode badge
    draw.rectangle([1240, 16, 1330, 42], fill=(15, 23, 42), outline=BORDER)
    draw.text((1250, 23), "AUTONOMOUS", fill=(165, 180, 252))

    # Safety status
    draw.rectangle([1340, 16, 1480, 42], fill=(6, 78, 59), outline=(4, 120, 87))
    draw.text((1355, 23), "SAFETY GATE ACTIVE", fill=EMERALD_GREEN)

    # Live Stream
    draw.rectangle([1490, 16, 1580, 42], fill=(6, 78, 59), outline=(4, 120, 87))
    draw.text((1502, 23), "LIVE STREAM", fill=EMERALD_GREEN)


def generate_run_history_screenshot():
    img = Image.new("RGB", (1600, 1050), color=BG_DARK)
    draw = ImageDraw.Draw(img)
    draw_header(draw, active_tab="Runs")

    # Title area
    draw.text((40, 85), "EXECUTION RUN HISTORY", fill=TEXT_WHITE)
    draw.rectangle([250, 85, 360, 105], fill=(23, 37, 84), outline=(30, 58, 138))
    draw.text((258, 88), "12 RUNS INDEXED", fill=BLUE_LIGHT)
    draw.text((40, 112), "Audited execution archive from canonical filesystem records. Inspect timeline replays and compare planner behaviors.", fill=TEXT_GRAY)

    # Filter & Search Panel
    draw.rectangle([40, 140, 1560, 205], fill=BG_CARD, outline=BORDER)
    # Search box
    draw.rectangle([55, 155, 420, 190], fill=(15, 23, 42), outline=BORDER_ACCENT)
    draw.text((70, 165), "🔍 Search by Run ID, Target, or Stop Reason...", fill=TEXT_MUTED)

    # Planner Filter pills
    draw.text((450, 167), "Planner:", fill=TEXT_GRAY)
    p_x = 510
    for p, act in [("ALL", True), ("RULE", False), ("LLM", False), ("HYBRID", False)]:
        fill_col = BLUE_ACCENT if act else (15, 23, 42)
        draw.rectangle([p_x, 158, p_x + 55, 188], fill=fill_col, outline=BORDER)
        draw.text((p_x + 12, 166), p, fill=TEXT_WHITE if act else TEXT_GRAY)
        p_x += 62

    # Mode Filter pills
    draw.text((790, 167), "Mode:", fill=TEXT_GRAY)
    m_x = 840
    for m, act in [("ALL", True), ("AUTONOMOUS", False), ("ASSISTED", False), ("MANUAL", False)]:
        fill_col = (79, 70, 229) if act else (15, 23, 42)
        w = 85 if len(m) > 4 else 45
        draw.rectangle([m_x, 158, m_x + w, 188], fill=fill_col, outline=BORDER)
        draw.text((m_x + 10, 166), m, fill=TEXT_WHITE if act else TEXT_GRAY)
        m_x += w + 6

    # State Filter pills
    draw.text((1200, 167), "State:", fill=TEXT_GRAY)
    s_x = 1250
    for s, act in [("ALL", True), ("COMPLETED", False), ("STOPPED", False), ("BLOCKED", False)]:
        fill_col = (16, 185, 129) if act else (15, 23, 42)
        w = 80 if len(s) > 4 else 45
        draw.rectangle([s_x, 158, s_x + w, 188], fill=fill_col, outline=BORDER)
        draw.text((s_x + 8, 166), s, fill=TEXT_WHITE if act else TEXT_GRAY)
        s_x += w + 6

    # Comparison floating bar
    draw.rectangle([40, 220, 1560, 260], fill=(23, 37, 84), outline=(30, 58, 138))
    draw.text((60, 233), "⚖ Selected for Comparison (2/2): RUN-AUTONOMOUS-PENTEST-1791723996 vs RUN-DASH-A3", fill=(191, 219, 254))
    draw.rectangle([1420, 226, 1545, 254], fill=BLUE_ACCENT)
    draw.text((1435, 232), "Compare Selected →", fill=TEXT_WHITE)

    # Runs Table Container
    draw.rectangle([40, 275, 1560, 1000], fill=BG_CARD, outline=BORDER)

    # Table Header
    draw.rectangle([40, 275, 1560, 315], fill=(15, 23, 42))
    draw.line([40, 315, 1560, 315], fill=BORDER, width=1)
    headers = [
        (60, "CMP"), (110, "RUN ID & TARGET"), (420, "PLANNER PROVENANCE"),
        (660, "CONTROL MODE"), (820, "OUTCOME"), (950, "DURATION"),
        (1060, "DISPATCHES"), (1180, "PERMITS/DENIALS"), (1330, "EVIDENCE"), (1440, "ACTIONS")
    ]
    for x, title in headers:
        draw.text((x, 290), title, fill=TEXT_GRAY)

    # Sample Runs Rows
    rows_data = [
        {
            "id": "RUN-AUTONOMOUS-PENTEST-1791723996",
            "target": "lab-ecommerce • SCN-001 • 2026-10-11 20:06:12",
            "prov": "RULE ENGINE", "prov_col": CYAN_ACCENT, "prov_bg": (8, 51, 68),
            "mode": "AUTONOMOUS", "state": "COMPLETED", "state_col": EMERALD_GREEN,
            "dur": "14.2s", "disp": "23", "perm": "6 / 0", "ev": "11 (3 fnd)", "checked": True
        },
        {
            "id": "RUN-DASH-A3-FALLBACK-TEST",
            "target": "lab-ecommerce • SCN-001 • 2026-10-11 20:15:45",
            "prov": "LLM → RULE FALLBACK", "prov_col": AMBER_YELLOW, "prov_bg": (69, 26, 3),
            "mode": "AUTONOMOUS", "state": "COMPLETED", "state_col": EMERALD_GREEN,
            "dur": "8.5s", "disp": "10", "perm": "5 / 1", "ev": "8 (2 fnd)", "checked": True
        },
        {
            "id": "RUN-DASH-A2-MANUAL-INSPECT",
            "target": "lab-ecommerce • SCN-001 • 2026-10-11 19:45:00",
            "prov": "RULE ENGINE", "prov_col": CYAN_ACCENT, "prov_bg": (8, 51, 68),
            "mode": "MANUAL", "state": "STOPPED", "state_col": AMBER_YELLOW,
            "dur": "45.1s", "disp": "2", "perm": "2 / 0", "ev": "3 (0 fnd)", "checked": False
        },
        {
            "id": "RUN-AUTONOMOUS-PENTEST-1791712598",
            "target": "lab-ecommerce • SCN-001 • 2026-10-11 16:56:38",
            "prov": "RULE ENGINE", "prov_col": CYAN_ACCENT, "prov_bg": (8, 51, 68),
            "mode": "AUTONOMOUS", "state": "COMPLETED", "state_col": EMERALD_GREEN,
            "dur": "13.8s", "disp": "23", "perm": "6 / 0", "ev": "11 (3 fnd)", "checked": False
        },
        {
            "id": "RUN-DASH-DENY-VERIFY-004",
            "target": "lab-ecommerce • SCN-001 • 2026-10-11 15:30:10",
            "prov": "RULE ENGINE", "prov_col": CYAN_ACCENT, "prov_bg": (8, 51, 68),
            "mode": "AUTONOMOUS", "state": "COMPLETED", "state_col": EMERALD_GREEN,
            "dur": "1.2s", "disp": "0", "perm": "0 / 1", "ev": "2 (1 fnd)", "checked": False
        },
        {
            "id": "RUN-KILL-SWITCH-EMERGENCY-005",
            "target": "lab-ecommerce • SCN-001 • 2026-10-11 14:10:00",
            "prov": "RULE ENGINE", "prov_col": CYAN_ACCENT, "prov_bg": (8, 51, 68),
            "mode": "ASSISTED", "state": "BLOCKED", "state_col": ROSE_RED,
            "dur": "3.4s", "disp": "1", "perm": "1 / 0", "ev": "2 (0 fnd)", "checked": False
        },
    ]

    row_y = 325
    for r in rows_data:
        # Checkbox
        draw.rectangle([65, row_y + 12, 80, row_y + 27], fill=BLUE_ACCENT if r["checked"] else (15, 23, 42), outline=BORDER)
        if r["checked"]:
            draw.text((68, row_y + 11), "✓", fill=TEXT_WHITE)

        # ID & Target
        draw.text((110, row_y + 6), r["id"], fill=TEXT_WHITE)
        draw.text((110, row_y + 26), r["target"], fill=TEXT_MUTED)

        # Provenance badge
        draw.rectangle([420, row_y + 10, 590, row_y + 32], fill=r["prov_bg"], outline=BORDER)
        draw.text((430, row_y + 14), r["prov"], fill=r["prov_col"])

        # Control mode
        draw.rectangle([660, row_y + 10, 770, row_y + 32], fill=(15, 23, 42), outline=BORDER)
        draw.text((675, row_y + 14), r["mode"], fill=(203, 213, 225))

        # Outcome
        draw.text((820, row_y + 14), f"● {r['state']}", fill=r["state_col"])

        # Duration
        draw.text((950, row_y + 14), r["dur"], fill=TEXT_GRAY)

        # Dispatches
        draw.rectangle([1075, row_y + 8, 1115, row_y + 32], fill=(23, 37, 84), outline=(30, 58, 138))
        draw.text((1087, row_y + 13), r["disp"], fill=BLUE_LIGHT)

        # Permits/Denials
        draw.text((1195, row_y + 14), r["perm"], fill=TEXT_WHITE)

        # Evidence
        draw.text((1335, row_y + 14), r["ev"], fill=TEXT_GRAY)

        # Actions buttons: [Compare] [Replay]
        draw.rectangle([1435, row_y + 8, 1490, row_y + 32], fill=(15, 23, 42), outline=BORDER)
        draw.text((1443, row_y + 13), "Compare", fill=TEXT_GRAY)
        draw.rectangle([1498, row_y + 8, 1550, row_y + 32], fill=(23, 37, 84), outline=(30, 58, 138))
        draw.text((1506, row_y + 13), "▶ Replay", fill=BLUE_LIGHT)

        draw.line([40, row_y + 48, 1560, row_y + 48], fill=BORDER, width=1)
        row_y += 52

    img.save(SCREENSHOTS_DIR / "run-history.png")
    print(f"Generated {SCREENSHOTS_DIR / 'run-history.png'}")


def generate_run_replay_screenshot():
    img = Image.new("RGB", (1600, 1050), color=BG_DARK)
    draw = ImageDraw.Draw(img)
    draw_header(draw, active_tab="Runs", run_id="RUN-AUTONOMOUS-PENTEST-1791723996")

    # Breadcrumb & Info
    draw.rectangle([40, 80, 130, 108], fill=(15, 23, 42), outline=BORDER)
    draw.text((50, 87), "← Runs List", fill=TEXT_GRAY)
    draw.text((150, 85), "RUN-AUTONOMOUS-PENTEST-1791723996", fill=TEXT_WHITE)
    draw.rectangle([540, 82, 670, 106], fill=(8, 51, 68), outline=(6, 78, 59))
    draw.text((550, 87), "RULE PLANNER", fill=CYAN_ACCENT)
    draw.rectangle([680, 82, 790, 106], fill=(15, 23, 42), outline=BORDER)
    draw.text((695, 87), "AUTONOMOUS", fill=(165, 180, 252))
    draw.text((150, 112), "Target: lab-ecommerce • Scenario: SCN-001 • Decisions: 7 • Dispatches: 23 • Verification: RULE_EXECUTED", fill=TEXT_MUTED)

    # Mandatory Historical Replay Banner
    draw.rectangle([40, 140, 1560, 205], fill=(69, 26, 3), outline=(180, 83, 9))
    draw.rectangle([55, 152, 95, 192], fill=(120, 53, 15), outline=(217, 119, 6))
    draw.text((68, 162), "🔒", fill=AMBER_YELLOW)
    draw.text((110, 155), "HISTORICAL REPLAY — NO LIVE EXECUTION", fill=AMBER_YELLOW)
    draw.rectangle([450, 154, 525, 172], fill=(120, 53, 15), outline=(217, 119, 6))
    draw.text((458, 156), "READ-ONLY", fill=AMBER_YELLOW)
    draw.text((110, 176), "This player visually scrubs through historical execution states strictly derived from canonical evidence. Zero live HTTP packets or shell calls are emitted during replay.", fill=(253, 230, 138))

    # Player Controller Bar
    draw.rectangle([40, 220, 1560, 315], fill=BG_CARD, outline=BORDER)
    # Buttons
    draw.rectangle([60, 235, 100, 275], fill=(15, 23, 42), outline=BORDER)
    draw.text((73, 247), "↺", fill=TEXT_WHITE)
    draw.rectangle([110, 235, 150, 275], fill=(15, 23, 42), outline=BORDER)
    draw.text((123, 247), "⏮", fill=TEXT_WHITE)
    # Play button
    draw.rectangle([160, 235, 250, 275], fill=BLUE_ACCENT)
    draw.text((185, 247), "▶ Play", fill=TEXT_WHITE)
    draw.rectangle([260, 235, 300, 275], fill=(15, 23, 42), outline=BORDER)
    draw.text((273, 247), "⏭", fill=TEXT_WHITE)

    # Speed
    draw.text((330, 250), "Speed:", fill=TEXT_GRAY)
    draw.rectangle([380, 240, 415, 270], fill=BLUE_ACCENT)
    draw.text((390, 248), "1x", fill=TEXT_WHITE)
    draw.rectangle([425, 240, 460, 270], fill=(15, 23, 42), outline=BORDER)
    draw.text((435, 248), "2x", fill=TEXT_GRAY)
    draw.rectangle([470, 240, 505, 270], fill=(15, 23, 42), outline=BORDER)
    draw.text((480, 248), "4x", fill=TEXT_GRAY)

    # Step indicator
    draw.text((1400, 248), "Step 4 of 7 (57%)", fill=BLUE_LIGHT)

    # Scrubber slider
    draw.rectangle([60, 288, 1540, 296], fill=(30, 41, 59))
    draw.rectangle([60, 288, 900, 296], fill=BLUE_ACCENT)
    draw.ellipse([892, 284, 908, 300], fill=TEXT_WHITE)
    draw.text((60, 302), "Start (Step 1)", fill=TEXT_MUTED)
    draw.text((860, 302), "2026-10-11 20:06:18Z", fill=TEXT_GRAY)
    draw.text((1460, 302), "Final (Step 7)", fill=TEXT_MUTED)

    # Dynamic Pipeline State Visualizer
    draw.rectangle([40, 335, 1560, 420], fill=BG_CARD, outline=BORDER)
    draw.text((55, 348), "PIPELINE STATE AT SCRUBBER POSITION", fill=TEXT_GRAY)
    pipe_steps = [
        ("PREFLIGHT", "PASS", False), ("RANGE", "PASS", False), ("OBSERVE", "PASS", False),
        ("STATE", "PASS", False), ("PLAN", "PASS", False), ("SAFETY", "ACTIVE", True),
        ("EXECUTE", "IDLE", False), ("EVIDENCE", "IDLE", False), ("VERIFY", "IDLE", False), ("COMPLETE", "IDLE", False)
    ]
    p_x = 55
    for name, st, is_act in pipe_steps:
        fill_bg = (30, 58, 138) if is_act else (15, 23, 42)
        border_col = BLUE_ACCENT if is_act else BORDER
        draw.rectangle([p_x, 370, p_x + 140, 410], fill=fill_bg, outline=border_col)
        draw.text((p_x + 35, 376), name, fill=TEXT_WHITE if is_act else TEXT_GRAY)
        draw.text((p_x + 50, 393), st, fill=BLUE_LIGHT if is_act else TEXT_MUTED)
        p_x += 150

    # Main Body: Step Details (Left 2/3) + Provenance Sidebar (Right 1/3)
    # Left Card
    draw.rectangle([40, 440, 1080, 1000], fill=BG_CARD, outline=BORDER)
    draw.rectangle([55, 455, 1065, 495], fill=(15, 23, 42))
    draw.text((70, 467), "● EVENT #4: SAFETY EVALUATION COMPLETED", fill=TEXT_WHITE)
    draw.rectangle([480, 463, 620, 487], fill=(6, 78, 59), outline=(4, 120, 87))
    draw.text((490, 468), "SAFETY_PERMITTED", fill=EMERALD_GREEN)
    draw.text((900, 467), "2026-10-11T20:06:18Z", fill=TEXT_MUTED)

    draw.text((70, 510), "Safety Gate evaluated proposed action ACTION-WEB-001 (probe syntax test) against bounded policy invariants.", fill=TEXT_GRAY)
    draw.text((70, 530), "Decision: PERMITTED. Rate limit: 2 tokens available. Target allowlisted: lab-ecommerce. Lab mode active.", fill=(203, 213, 225))

    # Structured step data dump
    draw.text((70, 565), "RECORDED STEP PAYLOAD (IMMUTABLE CANONICAL LEDGER):", fill=TEXT_GRAY)
    draw.rectangle([70, 590, 1050, 970], fill=(5, 8, 14), outline=BORDER)
    json_lines = [
        '{',
        '  "iteration": 4,',
        '  "decision_id": "DEC-4e2e82c4-20261011",',
        '  "proposed_action": {',
        '    "action_id": "ACTION-WEB-001",',
        '    "action_name": "HTTP Syntax Probe - Safe Delimiter",',
        '    "target_id": "lab-ecommerce",',
        '    "resource_ref": "http://127.0.0.1:18088/products",',
        '    "parameter_name": "q",',
        '    "hypothesis_id": "HYPO-SQLI-d2c07f",',
        '    "decision_origin": "RULE",',
        '    "confidence": 0.85',
        '  },',
        '  "safety_evaluation": {',
        '    "verdict": "PERMITTED",',
        '    "rule_code": "SAFETY_GATE_PASSED",',
        '    "lab_boundary_verified": true,',
        '    "rate_limit_token_deducted": 1,',
        '    "kill_switch_state": "INACTIVE"',
        '  },',
        '  "subsequent_dispatch": {',
        '    "dispatched": true,',
        '    "http_method": "GET",',
        '    "status_code": 200,',
        '    "bytes_received": 2560,',
        '    "evidence_persisted": "EV-RESULT-ddbb8cadcf1a"',
        '  }',
        '}'
    ]
    j_y = 605
    for l in json_lines:
        draw.text((90, j_y), l, fill=(147, 197, 253))
        j_y += 15

    # Right Card: Audited Provenance
    draw.rectangle([1100, 440, 1560, 1000], fill=BG_CARD, outline=BORDER)
    draw.rectangle([1115, 455, 1545, 495], fill=(15, 23, 42))
    draw.text((1130, 467), "AUDITED PROVENANCE & SUMMARY", fill=TEXT_WHITE)

    prov_items = [
        ("Actual Planner:", "RULE ENGINE", CYAN_ACCENT),
        ("Requested Planner:", "RULE", TEXT_WHITE),
        ("Verification Status:", "RULE_EXECUTED", EMERALD_GREEN),
        ("Control Mode:", "AUTONOMOUS", (165, 180, 252)),
        ("Target ID:", "lab-ecommerce", TEXT_WHITE),
        ("Total Iterations:", "7 Decisions", TEXT_WHITE),
        ("Network Dispatches:", "23 Packets", BLUE_LIGHT),
        ("Safety Permits:", "6 Approved", EMERALD_GREEN),
        ("Safety Refusals:", "0 Denied", TEXT_GRAY),
        ("Persisted Artifacts:", "11 Verified Records", EMERALD_GREEN),
        ("Security Findings:", "3 Surface Findings", AMBER_YELLOW),
        ("Stop Condition:", "discovery_surface_complete", TEXT_GRAY),
        ("Execution Integrity:", "100% CRYPTO VERIFIED", EMERALD_GREEN),
    ]
    p_y = 515
    for lbl, val, col in prov_items:
        draw.text((1130, p_y), lbl, fill=TEXT_GRAY)
        draw.text((1330, p_y), val, fill=col)
        draw.line([1130, p_y + 26, 1530, p_y + 26], fill=BORDER, width=1)
        p_y += 34

    img.save(SCREENSHOTS_DIR / "run-replay.png")
    print(f"Generated {SCREENSHOTS_DIR / 'run-replay.png'}")


def generate_planner_comparison_screenshot():
    img = Image.new("RGB", (1600, 1050), color=BG_DARK)
    draw = ImageDraw.Draw(img)
    draw_header(draw, active_tab="Compare", run_id="EXPERIMENT-COMPARISON")

    # Title & Export Bar
    draw.text((40, 85), "PLANNER & RUN EXPERIMENT COMPARISON", fill=TEXT_WHITE)
    draw.text((40, 112), "Side-by-side comparative evaluation of decision trajectories, dispatch counts, and safety invariants.", fill=TEXT_GRAY)

    # Export Buttons
    draw.rectangle([1320, 85, 1430, 115], fill=(15, 23, 42), outline=BORDER)
    draw.text((1335, 93), "📄 Export JSON", fill=CYAN_ACCENT)
    draw.rectangle([1440, 85, 1550, 115], fill=(15, 23, 42), outline=BORDER)
    draw.text((1455, 93), "📊 Export CSV", fill=EMERALD_GREEN)

    # Run Selectors Bar
    draw.rectangle([40, 140, 1560, 205], fill=BG_CARD, outline=BORDER)
    # Run A Box
    draw.text((60, 152), "RUN A (BASELINE / REFERENCE):", fill=TEXT_MUTED)
    draw.rectangle([60, 170, 720, 198], fill=(15, 23, 42), outline=BORDER_ACCENT)
    draw.text((75, 176), "RUN-AUTONOMOUS-PENTEST-1791723996 (RULE, AUTONOMOUS)", fill=TEXT_WHITE)

    # Swap Icon
    draw.rectangle([755, 168, 795, 198], fill=(15, 23, 42), outline=BORDER)
    draw.text((767, 175), "⇄", fill=TEXT_WHITE)

    # Run B Box
    draw.text((830, 152), "RUN B (COMPARISON CANDIDATE):", fill=TEXT_MUTED)
    draw.rectangle([830, 170, 1540, 198], fill=(15, 23, 42), outline=BORDER_ACCENT)
    draw.text((845, 176), "RUN-DASH-A3-FALLBACK-TEST (LLM Fallback to RULE, AUTONOMOUS)", fill=TEXT_WHITE)

    # Neutral Academic Summary Banner
    draw.rectangle([40, 220, 1560, 275], fill=(23, 37, 84), outline=(30, 58, 138))
    draw.text((60, 230), "ℹ EMPIRICAL RESEARCH OBSERVATIONS", fill=BLUE_LIGHT)
    draw.text((60, 250), "Observed comparative execution between RUN-AUTONOMOUS-PENTEST-1791723996 (RULE) and RUN-DASH-A3 (LLM Fallback). Measured network dispatches: 23 vs 10. Recorded safety enforcement: 0 refusals vs 1 refusal. Zero safety bypass recorded in either run.", fill=(224, 231, 255))

    # Comparative Metrics Table
    draw.rectangle([40, 290, 1560, 600], fill=BG_CARD, outline=BORDER)
    draw.rectangle([40, 290, 1560, 320], fill=(15, 23, 42))
    draw.text((60, 299), "COMPARATIVE EXECUTION METRICS", fill=TEXT_WHITE)

    # Table columns header
    draw.rectangle([40, 320, 1560, 345], fill=(20, 29, 47))
    col_x = [(60, "METRIC"), (450, "RUN A (RULE ENGINE)"), (850, "RUN B (LLM FALLBACK)"), (1350, "DELTA (B - A)")]
    for x, title in col_x:
        draw.text((x, 326), title, fill=TEXT_GRAY)

    metrics_rows = [
        ("Planner Actual", "RULE", "RULE", "— (Identical)"),
        ("Planner Verification", "RULE_EXECUTED", "LLM_FALLBACK_TO_RULE", "Fallback Triggered"),
        ("Control Mode", "AUTONOMOUS", "AUTONOMOUS", "— (Identical)"),
        ("Execution Duration", "14.2s (14200 ms)", "8.5s (8500 ms)", "-5.7s (-5700 ms)"),
        ("Decisions / Iterations", "7 Decisions", "6 Decisions", "-1 Decision"),
        ("Network Dispatches", "23 Dispatches", "10 Dispatches", "-13 Dispatches"),
        ("Safety Permits", "6 Permits", "5 Permits", "-1 Permit"),
        ("Safety Refusals", "0 Denied", "1 Denied", "+1 Denial"),
        ("Persisted Artifacts", "11 Artifacts", "8 Artifacts", "-3 Artifacts"),
        ("Security Findings", "3 Surface Findings", "2 Surface Findings", "-1 Finding"),
    ]
    m_y = 355
    for lbl, a_val, b_val, delta in metrics_rows:
        draw.text((60, m_y), lbl, fill=TEXT_WHITE)
        draw.text((450, m_y), a_val, fill=(203, 213, 225))
        draw.text((850, m_y), b_val, fill=(203, 213, 225))
        is_pos = "+" in delta
        is_neg = "-" in delta
        d_col = ROSE_RED if is_pos and "Denial" in delta else (CYAN_ACCENT if is_neg else TEXT_MUTED)
        draw.text((1350, m_y), delta, fill=d_col)
        draw.line([40, m_y + 22, 1560, m_y + 22], fill=BORDER, width=1)
        m_y += 26

    # Lower Grid: Action Sequence Visual Diff (Left 2/3) + Policy Invariants (Right 1/3)
    # Action Sequence Diff
    draw.rectangle([40, 615, 1060, 1000], fill=BG_CARD, outline=BORDER)
    draw.rectangle([40, 615, 1060, 650], fill=(15, 23, 42))
    draw.text((60, 627), "ACTION SEQUENCE TRAJECTORY DIFF", fill=TEXT_WHITE)
    draw.text((80, 658), "ITER", fill=TEXT_MUTED)
    draw.text((150, 658), "RUN A ACTION & VERDICT (RULE)", fill=TEXT_GRAY)
    draw.text((620, 658), "RUN B ACTION & VERDICT (LLM FALLBACK)", fill=TEXT_GRAY)

    seq_data = [
        (1, "ACTION-RECON-001 (APPROVED, dispatched)", "ACTION-RECON-001 (APPROVED, dispatched)"),
        (2, "ACTION-RECON-002 (APPROVED, dispatched)", "ACTION-RECON-002 (APPROVED, dispatched)"),
        (3, "ACTION-SCAN-001 (APPROVED, local scan)", "ACTION-WEB-001 (DENIED - lab policy violated)"),
        (4, "ACTION-WEB-001 (APPROVED, dispatched)", "ACTION-WEB-001 (APPROVED, dispatched)"),
        (5, "ACTION-WEB-001 (APPROVED, dispatched)", "ACTION-WEB-002 (APPROVED, dispatched)"),
        (6, "ACTION-WEB-002 (APPROVED, dispatched)", "ACTION-END-001 (STOP, completed)"),
        (7, "ACTION-END-001 (STOP, completed)", "—"),
    ]
    s_y = 680
    for it, a_act, b_act in seq_data:
        draw.text((85, s_y), str(it), fill=TEXT_MUTED)
        # Run A
        draw.rectangle([140, s_y - 2, 580, s_y + 24], fill=(15, 23, 42), outline=BORDER)
        draw.text((150, s_y + 3), a_act, fill=EMERALD_GREEN if "APPROVED" in a_act else TEXT_WHITE)

        # Run B
        if b_act != "—":
            is_denied = "DENIED" in b_act
            b_bg = (69, 26, 3) if is_denied else (15, 23, 42)
            b_col = ROSE_RED if is_denied else (EMERALD_GREEN if "APPROVED" in b_act else TEXT_WHITE)
            draw.rectangle([610, s_y - 2, 1040, s_y + 24], fill=b_bg, outline=BORDER)
            draw.text((620, s_y + 3), b_act, fill=b_col)
        else:
            draw.text((620, s_y + 3), "—", fill=TEXT_MUTED)

        s_y += 38

    # Safety Gate Policy Invariants Card (Right 1/3)
    draw.rectangle([1080, 615, 1560, 1000], fill=BG_CARD, outline=BORDER)
    draw.rectangle([1080, 615, 1560, 650], fill=(15, 23, 42))
    draw.text((1100, 627), "SAFETY INVARIANTS & FINDINGS OVERLAP", fill=TEXT_WHITE)

    draw.text((1100, 665), "SAFETY GATE ENFORCEMENT SUMMARY:", fill=TEXT_GRAY)
    draw.text((1100, 690), "• 100% Zero-bypass observed in both runs under Centralized Gate.", fill=EMERALD_GREEN)
    draw.text((1100, 715), "• Lab isolation boundary strictly maintained at http://127.0.0.1:18088.", fill=TEXT_WHITE)
    draw.text((1100, 740), "• Run B refusal correctly logged: REFUSAL_INTENT_RECORDED.", fill=AMBER_YELLOW)

    draw.line([1100, 770, 1540, 770], fill=BORDER, width=1)
    draw.text((1100, 790), "SECURITY FINDINGS OVERLAP ANALYSIS:", fill=TEXT_GRAY)
    draw.text((1100, 815), "Shared Surface Endpoints: 2", fill=BLUE_LIGHT)
    draw.rectangle([1100, 835, 1340, 860], fill=(15, 23, 42), outline=BORDER)
    draw.text((1110, 840), "GET /products (HTTP 200)", fill=(147, 197, 253))
    draw.rectangle([1100, 870, 1340, 895], fill=(15, 23, 42), outline=BORDER)
    draw.text((1110, 875), "GET /products?q=... (HTTP 200)", fill=(147, 197, 253))

    draw.text((1100, 920), "Unique Findings in Run A: 1 (Passive Scan)", fill=TEXT_MUTED)
    draw.text((1100, 945), "Unique Findings in Run B: 0", fill=TEXT_MUTED)

    img.save(SCREENSHOTS_DIR / "planner-comparison.png")
    print(f"Generated {SCREENSHOTS_DIR / 'planner-comparison.png'}")


if __name__ == "__main__":
    generate_run_history_screenshot()
    generate_run_replay_screenshot()
    generate_planner_comparison_screenshot()
    print("All Phase 6 screenshots successfully generated in dashboards/screenshots/")
