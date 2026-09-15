const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

async function record() {
  const videoDir = path.join(__dirname, 'recordings');
  if (!fs.existsSync(videoDir)) fs.mkdirSync(videoDir, { recursive: true });

  const browser = await chromium.launch({
    headless: true,
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: {
      dir: videoDir,
      size: { width: 1280, height: 720 }
    }
  });

  const page = await context.newPage();
  console.log('Navigating to http://localhost:8080...');
  await page.goto('http://localhost:8080', { waitUntil: 'networkidle' });

  // 1. Hero & Stats (12 sec)
  console.log('Scene 1: Hero & Stats...');
  await page.waitForTimeout(12000);

  // 2. Smooth scroll to Architecture GCP flow (14 sec)
  console.log('Scene 2: Architecture flow...');
  await page.evaluate(async () => {
    window.scrollBy({ top: 400, behavior: 'smooth' });
  });
  await page.waitForTimeout(14000);

  // 3. Scroll to Review Feed and hover on PR #42 (16 sec)
  console.log('Scene 3: PR #42 Deep Dive...');
  await page.evaluate(async () => {
    window.scrollBy({ top: 450, behavior: 'smooth' });
  });
  await page.waitForTimeout(3000);
  try {
    await page.hover('.review-card');
  } catch (e) {}
  await page.waitForTimeout(13000);

  // 4. Multi-language cards (10 sec)
  console.log('Scene 4: Multi-language showcase...');
  await page.evaluate(async () => {
    window.scrollBy({ top: 200, behavior: 'smooth' });
  });
  await page.waitForTimeout(10000);

  // 5. Scroll back up to Hero and hold (8 sec)
  console.log('Scene 5: Back to top & outro...');
  await page.evaluate(async () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  await page.waitForTimeout(8000);

  await page.close();
  await context.close();
  await browser.close();

  const files = fs.readdirSync(videoDir).filter(f => f.endsWith('.webm'));
  if (files.length > 0) {
    const rawVideo = path.join(videoDir, files[0]);
    const finalMp4 = path.join(__dirname, 'product_walkthrough_60s.mp4');
    console.log('Finished! Video saved to:', rawVideo);
  }
}

record().catch(console.error);
