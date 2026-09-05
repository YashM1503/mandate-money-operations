const { chromium } = require('playwright');
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const root = path.resolve(__dirname, '..');
const out = path.resolve(root, 'qa-evidence/money-operations-demo');
const ffmpeg = process.env.FFMPEG || 'ffmpeg';

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function installCursor(page, chip) {
  await page.addStyleTag({
    content: `
      #demo-cursor{position:fixed;left:48px;top:48px;width:16px;height:16px;border-radius:50%;
        background:#d4b56a;border:3px solid #14332c;z-index:2147483647;pointer-events:none;
        transform:translate(-20%,-20%)}
      #demo-chip{position:fixed;right:16px;bottom:16px;z-index:2147483647;pointer-events:none;
        background:#14332c;color:#e7f2e3;font:600 12px/1.35 Inter,system-ui,sans-serif;
        padding:8px 10px;border-radius:8px;letter-spacing:.02em}
    `,
  });
  await page.evaluate((label) => {
    let cursor = document.getElementById('demo-cursor');
    if (!cursor) {
      cursor = document.createElement('div');
      cursor.id = 'demo-cursor';
      document.body.appendChild(cursor);
    }
    let chipEl = document.getElementById('demo-chip');
    if (!chipEl) {
      chipEl = document.createElement('div');
      chipEl.id = 'demo-chip';
      document.body.appendChild(chipEl);
    }
    chipEl.textContent = label;
  }, chip);
}

async function point(page, locator, { click = false, steps = 14 } = {}) {
  const box = await locator.boundingBox();
  if (!box) return;
  const x = box.x + Math.min(Math.max(box.width * 0.4, 12), 90);
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y, { steps });
  await page.evaluate(([cx, cy]) => {
    const cursor = document.getElementById('demo-cursor');
    if (cursor) {
      cursor.style.left = `${cx}px`;
      cursor.style.top = `${cy}px`;
    }
  }, [x, y]);
  if (click) {
    await locator.click();
    await sleep(180);
  }
}

function convert(webm, mp4) {
  const result = spawnSync(ffmpeg, [
    '-y', '-i', webm,
    '-t', '90',
    '-an',
    '-c:v', 'libx264',
    '-pix_fmt', 'yuv420p',
    '-movflags', '+faststart',
    mp4,
  ], { encoding: 'utf8' });
  if (result.status !== 0) throw new Error(result.stderr || 'ffmpeg failed');
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}),
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: out, size: { width: 1920, height: 1080 } },
  });
  const page = await context.newPage();

  await page.goto(pathToFileURL(path.join(out, 'slides.html')).href);
  const holds = [3000, 6000, 6000, 5000, 6000, 7000, 5000, 4000, 3000, 2200];
  for (let i = 0; i < holds.length; i += 1) {
    await page.evaluate((n) => window.showSlide(n), i + 1);
    await sleep(holds[i]);
  }

  await page.goto(pathToFileURL(path.join(root, 'static/money-operations.html')).href);
  await installCursor(page, 'Observe · first pass');
  await sleep(400);
  await point(page, page.locator('[data-mode="demo"]'), { click: true });
  await point(page, page.getByRole('button', { name: 'Enter the close' }), { click: true });
  await page.locator('#content').waitFor();
  await installCursor(page, 'Observe · 18% only');
  await page.evaluate(() => {
    window.state.messages = [{
      role: 'assistant',
      text: 'Revenue increased 18%.',
      sources: ['VAR-REV'],
    }];
  });
  await point(page, page.locator('[data-view="analyst"]'), { click: true });
  await sleep(900);

  await installCursor(page, 'Improve · recompute drivers');
  await point(page, page.locator('[data-view="overview"]'), { click: true });
  const rerun = page.locator('#rerun');
  if (await rerun.count()) await point(page, rerun, { click: true });
  await sleep(1600);

  await installCursor(page, 'Improve · 18% / 32% / 64%');
  await point(page, page.locator('[data-view="analyst"]'), { click: true });
  await point(page, page.locator('[data-prompt="Draft the executive headline"]'), { click: true });
  await sleep(700);
  const claim = page.locator('[data-claim]').first();
  if (await claim.count()) await point(page, claim, { click: true });
  await sleep(700);

  await installCursor(page, 'Prove · source trail');
  await point(page, page.locator('[data-view="variances"]'), { click: true });
  await point(page, page.locator('[data-variance="gross_revenue"]').first(), { click: true });
  await sleep(600);
  await point(page, page.locator('[data-variance="other_opex"]').last(), { click: true });
  await sleep(700);
  const evidence = page.locator('[data-action="evidence"]');
  if (await evidence.count()) await point(page, evidence.first(), { click: true });

  await installCursor(page, 'Human in the loop');
  await point(page, page.locator('[data-view="review"]'), { click: true });
  const leaveOpen = page.locator('[data-action="leave-open"]');
  if (await leaveOpen.count()) await point(page, leaveOpen, { click: true });
  await sleep(400);
  const confirm = page.getByRole('button', { name: 'Confirm context' });
  if (await confirm.count()) await point(page, confirm, { click: true });
  await sleep(350);
  const approve = page.getByRole('button', { name: 'Approve memo draft' });
  if (await approve.count()) await point(page, approve, { click: true });
  await sleep(400);

  await installCursor(page, 'Prove · review-ready memo');
  await point(page, page.locator('[data-view="memo"]'), { click: true });
  await sleep(5200);

  const video = page.video();
  await context.close();
  await browser.close();
  const webm = await video.path();
  const mp4 = path.join(out, 'mandate-money-operations-90s.mp4');
  convert(webm, mp4);
  for (const leftover of fs.readdirSync(out)) {
    if (leftover.endsWith('.webm')) fs.unlinkSync(path.join(out, leftover));
  }
  const stat = fs.statSync(mp4);
  console.log(JSON.stringify({ mp4, bytes: stat.size }, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
