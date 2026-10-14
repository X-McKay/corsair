import { test, expect, type Page } from '@playwright/test';

async function firstRun(page: Page, request: any, agent: string) {
  const data = await (await request.get('/api/evaluations')).json();
  return data.runs.filter((r: any) => r.agent === agent).map((r: any) => r.run);
}

test('the API projects real v2 records without private text', async ({ request }) => {
  const evals = await (await request.get('/api/evaluations')).json();
  expect(evals.runs.map((r: any) => r.agent).sort()).toEqual(['chain', 'reviewer', 'reviewer']);
  const chain = evals.runs.find((r: any) => r.agent === 'chain');
  expect(chain.overall.dispositions.runs).toBeGreaterThan(100);
  const runs = await (await request.get('/api/runs')).json();
  expect(runs.runs).toHaveLength(4);
  expect(runs.warnings.join(' ')).toContain('20261013T000000Z-broken');
  expect(runs.runs.find((r: any) => r.id === '20261014T000000Z-00000000').state).toBe('incomplete');
  const detail = await (await request.get(`/api/evaluations/chain/${chain.run}`)).text();
  // the evaluator's failure text and the agents' message histories never leave the server
  expect(detail).not.toContain('"failure":');
  expect(detail).not.toContain('messages');
  expect((await request.post('/api/runs')).status()).toBe(405);
  expect((await request.get('/api/runs/..%2f..%2fetc')).status()).toBe(400);
});

test('runs list verdicts and the detail renders a real record safely', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/runs');
  await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible();
  await expect(page.getByText(/20261013T000000Z-broken: record unavailable/)).toBeVisible();
  await page.getByLabel('Filter verdict').selectOption('LIKELY_EXPLOITABLE');
  await expect(page.locator('table').first().locator('tbody tr')).toHaveCount(1);
  await page.locator('table').first().locator('tbody tr a.row-title').click();
  await expect(page.getByRole('heading', { name: '<img src=x onerror=alert(1)>' })).toBeVisible();
  expect(await page.locator('main img').count()).toBe(0);
  await expect(page.getByRole('heading', { name: 'Probe outcomes' })).toBeVisible();
  await expect(page.locator('.probe-cell').first()).toContainText('passed');
  await expect(page.getByRole('heading', { name: 'Outcome-blind review' })).toBeVisible();
  await page.goto('/runs/20261014T000000Z-00000000');
  await expect(page.getByText(/This record has no verdict \(incomplete\)/)).toBeVisible();
  await page.goto('/runs/missing-run');
  await expect(page.getByRole('heading', { name: 'Unable to load evidence' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('a chain eval links each attempt to its own run record', async ({ page, request }) => {
  const [run] = await firstRun(page, request, 'chain');
  await page.goto(`/evaluations/chain/${run}`);
  await expect(page.getByRole('heading', { name: 'chain evaluation' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Dispositions' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'By language' })).toBeVisible();
  await page.locator('a[href*="/attempts/"]').first().click();
  await expect(page.getByText(/Chain eval attempt \d+ for case/)).toBeVisible();
  await expect(page.getByRole('link', { name: /Chain eval/ })).toBeVisible();
});

test('a second eval run compares against the previous one', async ({ page, request }) => {
  const [newest] = await firstRun(page, request, 'reviewer');
  await page.goto(`/evaluations/reviewer/${newest}`);
  await expect(page.getByRole('heading', { name: 'reviewer evaluation' })).toBeVisible();
  await expect(page.getByText(/with previous run/)).toBeVisible();
  await page.getByLabel('Not clean only').check();
  await expect(page.getByText('Every attempt is clean.')).toBeVisible();
});

test('agents, runtime and system read their sources', async ({ page }) => {
  await page.goto('/agents');
  await expect(page.locator('.agent-card')).toHaveCount(7);
  await expect(page.locator('.agent-card').filter({ hasText: 'reviewer' }).first()).toContainText('Latest scripted run');
  await page.goto('/runtime');
  await expect(page.getByRole('heading', { name: 'Runtime matrix', exact: true })).toBeVisible();
  expect(await page.locator('.runtime-card').count()).toBeGreaterThan(1);
  await page.goto('/system');
  await expect(page.getByText('Data sources available')).toBeVisible();
  await expect(page.getByText('Run records', { exact: true })).toBeVisible();
});

test('theme, mobile navigation, history and layout remain usable', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  if (testInfo.project.name === 'mobile') await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByLabel('Appearance', { exact: true }).selectOption('dark');
  await expect(page.locator('html')).toHaveClass(/dark/);
  await page.getByRole('navigation', { name: 'Main navigation' }).getByRole('link', { name: /Evaluations/ }).click();
  await expect(page.getByRole('heading', { name: 'Evaluations', exact: true })).toBeVisible();
  await page.locator('a.row-title').first().click();
  await expect(page.getByRole('heading', { name: / evaluation$/ })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading', { name: 'Evaluations', exact: true })).toBeVisible();
  await page.reload();
  await expect(page.locator('html')).toHaveClass(/dark/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});

test('empty and connection failure states are actionable', async ({ page }) => {
  // Fault injection supplements, rather than replaces, the real API tests above.
  await page.route('**/api/evaluations', (route) => route.fulfill({ json: { runs: [], warnings: [] } }));
  await page.route('**/api/runs', (route) => route.fulfill({ json: { runs: [], warnings: [] } }));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'No recorded runs' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'No recorded evaluations' })).toBeVisible();
  await page.unroute('**/api/evaluations');
  await page.route('**/api/evaluations', (route) => route.abort());
  await page.getByRole('button', { name: 'Refresh evidence' }).click();
  await expect(page.getByRole('heading', { name: 'Unable to load evidence' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
});

test('visual review captures every primary screen without horizontal overflow', async ({ page, request }, testInfo) => {
  const [chain] = await firstRun(page, request, 'chain');
  for (const [name, url] of [['overview', '/'], ['runs', '/runs'], ['evaluations', '/evaluations'],
    ['chain', `/evaluations/chain/${chain}`], ['attempt', `/evaluations/chain/${chain}/attempts/0001`],
    ['agents', '/agents'], ['runtime', '/runtime'], ['system', '/system']]) {
    await page.goto(url);
    await expect(page.locator('h1')).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
    await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true });
  }
});
