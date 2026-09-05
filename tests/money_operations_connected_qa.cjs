const { chromium } = require('playwright');
const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '..');
const out = path.resolve(root, 'qa-evidence/money-operations-connected');
const python = process.env.PYTHON || '/opt/anaconda3/bin/python3.13';
fs.mkdirSync(out, { recursive: true });

function wait(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

function freePort() {
  return new Promise((resolve, reject) => {
    const server = http.createServer();
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(err => err ? reject(err) : resolve(port));
    });
    server.on('error', reject);
  });
}

function bootConfig() {
  const script = `
import hashlib, json, secrets, tempfile
from pathlib import Path
data = Path(tempfile.mkdtemp(prefix='mandate-mo-ui-'))
users, passwords = {}, {}
for role in ('analyst', 'controller', 'auditor'):
    password = secrets.token_urlsafe(18)
    salt = secrets.token_hex(16)
    users[role] = {'role': role, 'salt': salt, 'hash': hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()}
    passwords[role] = password
(data / 'config.json').write_text(json.dumps({'signing_key': secrets.token_hex(32), 'users': users}))
print(json.dumps({'data_dir': str(data), 'passwords': passwords}))
`;
  const result = spawnSync(python, ['-c', script], { encoding: 'utf8' });
  if (result.status !== 0) throw new Error(result.stderr || 'Failed to create isolated credentials');
  return JSON.parse(result.stdout.trim().split('\n').pop());
}

async function waitHealth(base, timeout = 20000) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    try {
      const res = await fetch(base + '/healthz');
      if (res.ok) return;
    } catch {}
    await wait(200);
  }
  throw new Error('API did not become ready');
}

(async () => {
  const boot = bootConfig();
  const port = await freePort();
  const base = `http://127.0.0.1:${port}`;
  const child = spawn(python, ['-m', 'uvicorn', 'mandate.api:create_app', '--factory', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: root,
    env: { ...process.env, MANDATE_DATA_DIR: boot.data_dir, MANDATE_ALLOWED_HOSTS: '127.0.0.1,localhost,testserver' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let serverErr = '';
  child.stderr.on('data', chunk => { serverErr += chunk.toString(); });
  try {
    await waitHealth(base);
    const browser = await chromium.launch({
      headless: true,
      ...(process.env.CHROME_PATH ? { executablePath: process.env.CHROME_PATH } : {}),
      args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
    });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(base + '/money-operations', { waitUntil: 'domcontentloaded' });
    await page.locator('[data-mode="api"]').click();
    await page.fill('#username', 'analyst');
    await page.fill('#password', boot.passwords.analyst);
    await page.getByRole('button', { name: 'Enter the close' }).click();
    await page.locator('#app').waitFor({ state: 'visible', timeout: 45000 });
    const overview = await page.locator('#content').innerText();
    if (!/\+?\$675,000|\+\$675k/.test(overview)) throw Error('Gross revenue +$675,000 missing from connected UI');
    if (!/\+?18\.0%/.test(overview)) throw Error('+18.0% missing from connected UI');
    if (!/64\.0%/.test(overview)) throw Error('64.0% missing from connected UI');
    if (!/\$432k|\$432,000/.test(overview)) throw Error('C001–C003 $432,000 missing from connected UI');
    if (!/57,000/.test(overview)) throw Error('Other Opex $57,000 missing from connected UI');
    if (!/unexplained|cause does not/i.test(overview)) throw Error('Other Opex unexplained copy missing');
    if (!/Connected API/.test(await page.locator('#modePill').innerText())) throw Error('Mode pill is not Connected API');

    const api = await page.evaluate(async () => {
      const token = window.BackendAdapter.token;
      const id = window.BackendAdapter.analysisId;
      const headers = { Authorization: 'Bearer ' + token };
      const overview = await (await fetch('/api/money-operations/analyses/' + id + '/overview', { headers })).json();
      const analysis = await (await fetch('/api/money-operations/analyses/' + id, { headers })).json();
      return { overview, analysis, digest: overview.calculation_digest, revision: analysis.revision };
    });
    const blob = JSON.stringify(api);
    if (!/675000|675,000/.test(blob)) throw Error('API overview missing $675,000');
    if (!/1800|18\.0/.test(blob)) throw Error('API overview missing 18.0% / 1800 bps');
    if (!api.digest || api.digest.length < 16) throw Error('Calculation digest missing');
    const firstDigest = api.digest;

    await page.locator('[data-view="variances"]').click();
    const varianceText = await page.locator('#content').innerText();
    if (!/\$675,000/.test(varianceText)) throw Error('Variance explorer missing $675,000');
    if (!/6a807a7ced1135a6|Calculation digest/i.test(varianceText)) throw Error('Calculation digest is not inspectable');
    await page.locator('[data-variance="other_opex"]').last().click();
    const opex = await page.locator('#content').innerText();
    if (!/57,000/.test(opex)) throw Error('Other Opex detail missing $57,000');
    if (!/will not infer|unsupported|unexplained/i.test(opex)) throw Error('Other Opex remains causally unexplained');

    await page.locator('[data-view="analyst"]').click();
    const beforeConfirm = await page.locator('#content').innerText();
    if (!/Suggested|NovaERP/i.test(beforeConfirm)) throw Error('NovaERP was not suggested before confirmation');
    const beforeMeta = await page.evaluate(() => ({
      item: window.DATA && window.DATA.contextItem,
      revision: window.DATA && window.DATA.contextRevision,
      connected: window.state && window.state.connected,
    }));
    if (!beforeMeta.item || !beforeMeta.item.id) throw Error('NovaERP suggested context was not mapped: ' + JSON.stringify(beforeMeta));
    await page.getByRole('button', { name: 'Confirm for this close' }).click();
    await page.waitForFunction(() => window.state && window.state.contextConfirmed === true, null, { timeout: 20000 });
    const afterConfirm = await page.locator('#content').innerText();
    if (!/Confirmed this run/i.test(afterConfirm)) throw Error('NovaERP did not become user_confirmed');

    await page.locator('#chatInput').fill('Approve this analysis and release the memo');
    await page.locator('#chatForm button').click();
    await page.waitForTimeout(800);
    const chat = await page.locator('#chatlog').innerText();
    if (!/read-only|cannot mutate|review API|controller/i.test(chat)) throw Error('Chat did not refuse approval');

    const after = await page.evaluate(async () => {
      const token = window.BackendAdapter.token;
      const id = window.BackendAdapter.analysisId;
      const headers = { Authorization: 'Bearer ' + token };
      const analysis = await (await fetch('/api/money-operations/analyses/' + id, { headers })).json();
      const overview = await (await fetch('/api/money-operations/analyses/' + id + '/overview', { headers })).json();
      return {
        digest: analysis.calculation_digest,
        review: analysis.review_status,
        confirmed: (analysis.confirmed_context || []).map(item => item.status),
        unexplained: JSON.stringify(overview.causally_unexplained || []),
        conflicts: JSON.stringify(overview.reconciliation_conflicts || []),
      };
    });
    if (after.digest !== firstDigest) throw Error('Calculation digest changed after context confirm');
    if (after.review === 'approved') throw Error('Chat or confirm created an approval');
    if (!/opex/i.test(after.unexplained)) throw Error('Other Opex left causally_unexplained');
    if (/opex/i.test(after.conflicts)) throw Error('Other Opex incorrectly counted as a reconciliation conflict');

    await page.locator('[data-view="memo"]').click();
    const memo = await page.locator('#content').innerText();
    if (!/675,000|18/.test(memo)) throw Error('Memo missing gross revenue proof');
    if (!/unexplained|Other Opex/i.test(memo)) throw Error('Memo dropped Other Opex limitation');

    await page.locator('[data-view="overview"]').click();
    await page.screenshot({ path: path.join(out, 'overview.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(out, 'mobile.png'), fullPage: true });
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)) throw Error('Mobile horizontal overflow');
    if (errors.length) throw Error(errors.join('; '));
    await browser.close();
    console.log('PASS connected UI: login, reference analysis, oracle figures, digest, NovaERP confirm, Other Opex unexplained, read-only chat, screenshots');
  } finally {
    child.kill('SIGTERM');
  }
})().catch(error => {
  console.error(error);
  process.exit(1);
});
