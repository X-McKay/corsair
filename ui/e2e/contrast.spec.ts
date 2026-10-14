import { test, expect } from '@playwright/test';
import { contrastProblems } from './support/contrast';
for (const path of ['/', '/runs', '/evaluations', '/agents', '/runtime', '/system']) {
  test(`text contrast ${path}`, async ({ page }, info) => {
    test.skip(info.project.name === 'mobile', 'Same palette covered by desktop and dark');
    await page.goto(path); await expect(page.locator('h1')).toBeVisible();
    await page.waitForLoadState('networkidle');
    expect(await contrastProblems(page)).toEqual([]);
  });
}
test('text contrast run detail', async ({ page, request }, info) => {
  test.skip(info.project.name === 'mobile', 'Same palette covered by desktop and dark');
  const runs = await (await request.get('/api/runs')).json();
  await page.goto(`/runs/${runs.runs.find((r: any) => r.label).id}`);
  await expect(page.locator('h1')).toBeVisible();
  await page.waitForLoadState('networkidle');
  expect(await contrastProblems(page)).toEqual([]);
});
