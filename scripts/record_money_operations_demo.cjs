const { chromium } = require('playwright');
const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const root = path.resolve(__dirname, '..');
const out = path.resolve(root, 'qa-evidence/money-operations-demo');
const ffmpegCandidates = [
  process.env.FFMPEG,
  'ffmpeg',
].filter(Boolean);

fs.mkdirSync(out, { recursive: true });

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function convert(webm, mp4) {
  const ffmpeg = ffmpegCandidates.find(candidate => fs.existsSync(candidate));
  if (!ffmpeg) throw new Error('ffmpeg not found');
  const result = spawnSync(ffmpeg, [
    '-y', '-i', webm,
    '-t', '45',
    '-an',
    '-c:v', 'libx264',
    '-pix_fmt', 'yuv420p',
    '-movflags', '+faststart',
    mp4,
  ], { encoding: 'utf8' });
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout || 'ffmpeg failed');
  }
}

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}),
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: out, size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();
  await page.goto(pathToFileURL(path.join(root, 'static/money-operations.html')).href);
  await sleep(2200);

  await page.locator('[data-mode="demo"]').click();
  await sleep(900);
  await page.getByRole('button', { name: 'Enter the close' }).click();
  await page.locator('#content').waitFor();
  await sleep(8500);

  await page.locator('[data-view="variances"]').click();
  await sleep(3200);
  await page.locator('[data-variance="gross_revenue"]').first().click();
  await sleep(3000);
  await page.locator('[data-variance="other_opex"]').last().click();
  await sleep(4000);

  await page.locator('[data-view="analyst"]').click();
  await sleep(2000);
  await page.locator('[data-prompt="Draft the executive headline"]').click();
  await sleep(2800);
  await page.getByRole('button', { name: 'Confirm for this close' }).click();
  await sleep(2800);

  await page.locator('[data-view="memo"]').click();
  await sleep(8500);

  await page.locator('[data-view="overview"]').click();
  await sleep(5500);

  const video = page.video();
  await context.close();
  await browser.close();
  const webm = await video.path();
  const mp4 = path.join(out, 'mandate-money-operations-45s.mp4');
  convert(webm, mp4);
  const stat = fs.statSync(mp4);
  for (const leftover of fs.readdirSync(out)) {
    if (leftover.endsWith('.webm')) fs.unlinkSync(path.join(out, leftover));
  }
  console.log(JSON.stringify({ mp4, bytes: stat.size }, null, 2));
})().catch(error => {
  console.error(error);
  process.exit(1);
});
