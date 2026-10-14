import puppeteer from 'puppeteer-core';
import path from 'path';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const URL = 'http://127.0.0.1:5173';
const OUTPUT_DIR = path.resolve(__dirname, '../../screenshots');

async function main() {
  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
  }

  const browser = await puppeteer.launch({
    executablePath: EDGE_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1050'],
    defaultViewport: { width: 1600, height: 1050 },
  });

  try {
    const page = await browser.newPage();
    page.on('console', (msg) => console.log('PAGE LOG:', msg.text()));
    page.on('pageerror', (err) => console.error('PAGE ERROR:', err));
    page.on('requestfailed', (req) => console.error('REQ FAILED:', req.url(), req.failure()?.errorText));

    console.log(`Navigating to ${URL}...`);
    await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 15000 });

    await page.waitForSelector('main', { timeout: 10000 });
    // Wait 2.5s for initial status hydration
    await new Promise((r) => setTimeout(r, 2500));

    // Capture 1: Main Autonomous Live Dashboard
    const liveShot = path.join(OUTPUT_DIR, 'autonomous-run-live.png');
    await page.screenshot({ path: liveShot, fullPage: false });
    console.log(`Saved screenshot 1: ${liveShot}`);

    // Click "Inspect" button on Evidence Vault card
    console.log('Clicking Inspect button on Evidence Vault card...');
    const clickedInspect = await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('button'));
      const btn = btns.find((b) => b.textContent?.trim() === 'Inspect');
      if (btn) {
        btn.click();
        return true;
      }
      return false;
    });

    if (clickedInspect) {
      await new Promise((r) => setTimeout(r, 2000));

      // Capture 2: Evidence Vault & Findings Inspector Modal (Findings Tab)
      const modalShot = path.join(OUTPUT_DIR, 'autonomous-evidence-inspector.png');
      await page.screenshot({ path: modalShot, fullPage: false });
      console.log(`Saved screenshot 2: ${modalShot}`);

      // Click "Cryptographic Ledger" Tab
      console.log('Switching to Cryptographic Ledger tab...');
      await page.evaluate(() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const tab = btns.find((b) => b.textContent?.includes('Cryptographic Ledger'));
        tab?.click();
      });
      await new Promise((r) => setTimeout(r, 1500));

      // Click first ledger row in table to open side drawer
      console.log('Clicking first ledger row to inspect payload drawer...');
      await page.evaluate(() => {
        const row = document.querySelector('tbody tr');
        if (row && typeof row.click === 'function') {
          row.click();
        }
      });

      // Wait for the detail drawer content to load
      try {
        await page.waitForSelector('pre', { timeout: 8000 });
      } catch {
        // Fallback wait
        await new Promise((r) => setTimeout(r, 3000));
      }

      // Capture 3: Cryptographic Ledger & Payload Inspector Drawer
      const ledgerShot = path.join(OUTPUT_DIR, 'autonomous-evidence-ledger-drawer.png');
      await page.screenshot({ path: ledgerShot, fullPage: false });
      console.log(`Saved screenshot 3: ${ledgerShot}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((err) => {
  console.error('Screenshot capture failed:', err);
  process.exit(1);
});
