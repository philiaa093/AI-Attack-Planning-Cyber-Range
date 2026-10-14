import puppeteer from 'puppeteer-core';
import path from 'path';

const EDGE_PATH = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';
const OUTPUT_PATH = path.resolve('../../screenshots/control-center-deny-demo.png');

async function capture() {
  console.log('Launching Edge for live dashboard screenshot...');
  const browser = await puppeteer.launch({
    executablePath: EDGE_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    defaultViewport: {
      width: 1680,
      height: 1050,
      deviceScaleFactor: 1,
    },
  });

  const page = await browser.newPage();
  console.log('Navigating to http://127.0.0.1:5173...');
  await page.goto('http://127.0.0.1:5173', { waitUntil: 'domcontentloaded', timeout: 15000 });

  console.log('Waiting for main dashboard cards and SSE events...');
  await page.waitForSelector('main', { timeout: 10000 });
  await new Promise((r) => setTimeout(r, 2500));

  console.log(`Saving screenshot to ${OUTPUT_PATH}...`);
  await page.screenshot({ path: OUTPUT_PATH, fullPage: true });
  console.log('Screenshot successfully captured.');

  await browser.close();
}

capture().catch((err) => {
  console.error('Screenshot capture failed:', err);
  process.exit(1);
});
