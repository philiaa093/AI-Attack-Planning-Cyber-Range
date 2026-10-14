/**
 * Real Browser Capture & DOM Verification for Autonomous Cyber Range Control Center.
 * Uses puppeteer-core to launch local Chrome or Microsoft Edge headless browser,
 * verifies real DOM rendering for Overview, Runs, and Compare pages,
 * and saves genuine live browser screenshots to dashboards/screenshots/.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import puppeteer from '../../dashboards/app/frontend/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..', '..');
const SCREENSHOTS_DIR = path.join(ROOT, 'dashboards', 'screenshots');

if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

// Find Chrome or Edge executable on Windows
function findBrowserExecutable() {
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      return p;
    }
  }
  throw new Error('No Chrome or Edge executable found on system.');
}

async function capture() {
  const browserPath = findBrowserExecutable();
  console.log(`[+] Using browser executable: ${browserPath}`);

  const browser = await puppeteer.launch({
    executablePath: browserPath,
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-gpu',
    ],
  });

  const page = await browser.newPage();

  // Test targets
  const views = [
    {
      name: 'demo-overview-live',
      url: 'http://127.0.0.1:5173/#overview',
      width: 1920,
      height: 1080,
      expectedSelectors: ['header', 'h1', '[aria-label="System Components Overview"]'],
      desc: 'Control Center Overview (Presentation Mode Active + Operational Cards)',
    },
    {
      name: 'demo-presentation-mode-live',
      url: 'http://127.0.0.1:5173/#overview',
      width: 1366,
      height: 768,
      expectedSelectors: ['[aria-label="Professor Presentation Mode Hero"]'],
      desc: 'Presentation Mode Hero View (Current Step Hero + Safety Gate Hero)',
    },
    {
      name: 'demo-runs-live',
      url: 'http://127.0.0.1:5173/#runs',
      width: 1920,
      height: 1080,
      expectedSelectors: ['header', 'table', 'input[placeholder]'],
      desc: 'Run History & Indexed Run Ledger (RULE vs LLM Fallback runs)',
    },
    {
      name: 'demo-compare-live',
      url: 'http://127.0.0.1:5173/#compare',
      width: 1920,
      height: 1080,
      expectedSelectors: ['header', 'select'],
      desc: 'Planner Experiment Comparison (RULE Baseline vs LLM Fallback)',
    },
    {
      name: 'demo-replay-live',
      url: 'http://127.0.0.1:5173/#runs/RUN-AUTONOMOUS-PENTEST-1791712598',
      width: 1920,
      height: 1080,
      expectedSelectors: ['header', 'button', 'input[type="range"]'],
      desc: 'Historical Run Replay Player (Verified Audit Ledger, Step Scrubber & Zero Dispatch Guarantee)',
    },
    {
      name: 'demo-safety-deny-live',
      url: 'http://127.0.0.1:5173/#overview',
      width: 1920,
      height: 1080,
      actionBeforeCapture: async (p) => {
        // Trigger the deny-demo preset scenario via client-side fetch or preset button
        await p.evaluate(async () => {
          try {
            await fetch('http://127.0.0.1:8000/api/runs', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                mode: 'deny-demo',
                planner: 'rule',
                control_mode: 'AUTONOMOUS',
                target: 'lab-ecommerce',
                max_decisions: 1,
              }),
            });
          } catch (e) {
            console.error('Trigger deny error', e);
          }
        });
        // Wait for SSE event to propagate and UI state to render
        await new Promise((r) => setTimeout(r, 2000));
      },
      expectedSelectors: ['[aria-label="Professor Presentation Mode Hero"]'],
      desc: 'Safety Gate Refusal Hero (Live Deny State, Red Alert & Zero Outbound Network Dispatch Guarantee)',
    },
  ];

  const receipts = [];

  for (const view of views) {
    console.log(`\n[*] Capturing: ${view.name} (${view.width}x${view.height}) from ${view.url}...`);
    await page.setViewport({ width: view.width, height: view.height, deviceScaleFactor: 1 });

    try {
      await page.goto(view.url, { waitUntil: 'networkidle0', timeout: 15000 });
    } catch {
      // If network idle takes too long, wait for DOM content loaded
      await page.goto(view.url, { waitUntil: 'domcontentloaded', timeout: 15000 });
    }

    // Wait 1.5 seconds for React components and animations to stabilize
    await new Promise((r) => setTimeout(r, 1500));

    if (typeof view.actionBeforeCapture === 'function') {
      console.log(`  [*] Running pre-capture action for ${view.name}...`);
      await view.actionBeforeCapture(page);
    }

    // Verify DOM elements
    const verifiedSelectors = [];
    for (const sel of view.expectedSelectors) {
      const el = await page.$(sel);
      if (el) {
        verifiedSelectors.push(sel);
      } else {
        console.warn(`  [!] Warning: Selector "${sel}" not found in live DOM.`);
      }
    }

    const outputPath = path.join(SCREENSHOTS_DIR, `${view.name}.png`);
    await page.screenshot({ path: outputPath, fullPage: false });

    const stats = fs.statSync(outputPath);
    console.log(`  [+] Saved screenshot: ${outputPath} (${(stats.size / 1024).toFixed(1)} KB)`);
    console.log(`  [+] Verified DOM selectors: ${verifiedSelectors.join(', ')}`);

    receipts.push({
      file: `${view.name}.png`,
      url: view.url,
      resolution: `${view.width}x${view.height}`,
      bytes: stats.size,
      verified_dom_selectors: verifiedSelectors,
      description: view.desc,
      captured_at_utc: new Date().toISOString(),
    });
  }

  await browser.close();
  console.log('\n[+] Real browser capture completed successfully!');
  console.log(JSON.stringify(receipts, null, 2));

  // Write receipts manifest to dashboards/screenshots/capture_receipts.json
  const manifestPath = path.join(SCREENSHOTS_DIR, 'capture_receipts.json');
  fs.writeFileSync(manifestPath, JSON.stringify(receipts, null, 2), 'utf-8');
}

capture().catch((err) => {
  console.error('[-] Error capturing browser screenshots:', err);
  process.exit(1);
});
