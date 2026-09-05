const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const out = path.resolve(__dirname, '../qa-evidence/money-operations-ui');
fs.mkdirSync(out, { recursive: true });

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}),
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.resolve(__dirname, '../demo.html')).href);

  if (!await page.evaluate(() => window.STANDALONE === true)) throw Error('file:// demo must run standalone');
  await page.locator('#enter').click();
  if (!await page.locator('#content').innerText().then(text => /Standalone synthetic proof of concept/i.test(text))) throw Error('Standalone banner is missing');
  await page.screenshot({ path: path.join(out, 'overview.png'), fullPage: true });
  const overview = await page.locator('#content').innerText();
  if (!overview.includes('+$675k') || !overview.includes('64.0%')) throw Error('Reference metrics are missing');
  if (!overview.includes('cause does not')) throw Error('Human decision boundary is missing');

  await page.locator('[data-view="variances"]').click();
  await page.screenshot({ path: path.join(out, 'variance-explorer.png'), fullPage: true });
  await page.locator('[data-variance="other_opex"]').last().click();
  if (!await page.locator('#content').innerText().then(text => /will not infer/i.test(text))) throw Error('Other Opex guardrail is missing');

  await page.locator('[data-view="analyst"]').click();
  await page.locator('[data-prompt="Can we explain Other Opex?"]').click();
  if (!await page.locator('#chatlog').innerText().then(text => /does not prove its business cause/i.test(text))) throw Error('Guarded chat response is missing');
  await page.getByRole('button', { name: 'Confirm for this close' }).click();
  await page.screenshot({ path: path.join(out, 'analyst.png'), fullPage: true });

  await page.locator('[data-view="review"]').click();
  await page.getByRole('button', { name: 'Approve memo draft' }).click();
  if (!await page.locator('#content').innerText().then(text => /Memo approved/i.test(text))) throw Error('Review state did not update');

  await page.locator('[data-view="memo"]').click();
  if (!await page.locator('#content').innerText().then(text => /Controller approved/i.test(text))) throw Error('Approved memo state is missing');
  await page.screenshot({ path: path.join(out, 'memo.png'), fullPage: true });

  await page.locator('[data-view="assurance"]').click();
  const assurance = await page.locator('#content').innerText();
  if (!/Awaiting live trace/i.test(assurance) || !/Evaluation pending/i.test(assurance)) throw Error('Sponsor status boundaries are missing');

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('[data-view="overview"]').click();
  await page.screenshot({ path: path.join(out, 'mobile.png'), fullPage: true });
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw Error('Mobile horizontal overflow');
  if (errors.length) throw Error(errors.join('; '));

  console.log('PASS UI: overview, WebGL surface, drilldown, guarded chat, context, approval, memo, integrations, mobile');
  await browser.close();
})().catch(error => {
  console.error(error);
  process.exit(1);
});
