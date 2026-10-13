import { test, expect } from '@playwright/test';
import {contrastProblems} from './support/contrast';
const planning = '/evaluations/planning/20261013T120000Z-development-scripted';
const assessment = '/evaluations/assessment/20261013T130000Z-development-live';
const authoring = '/evaluations/authoring/20261013T140000Z-development-scripted';

test('real API only projects safe evidence and keeps observed zero', async ({request}) => {
  const response = await request.get('/api/evaluations');
  expect(response.ok()).toBeTruthy();
  const text = await response.text();
  expect(text).not.toContain('PRIVATE');
  const data = JSON.parse(text);
  expect(data.runs).toHaveLength(4);
  expect(data.warnings).toHaveLength(1);
  expect(data.runs.find((r:any)=>r.agent==='assessment').summary.efficiency_mean.input_tokens).toBe(0);
  expect((await request.post('/api/evaluations')).status()).toBe(405);
});

test('overview and filters reflect local records without fabricated accuracy', async ({page}) => {
  const errors:string[]=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'See how your agents perform.'})).toBeVisible();
  await expect(page.getByText(/broken-record: summary unavailable/)).toBeVisible();
  await page.goto('/evaluations');
  await page.getByLabel('Filter agent').selectOption('planning');
  await expect(page.locator('tbody tr')).toHaveCount(2);
  await expect(page.locator('tbody')).toContainText('3/4');
  await page.getByLabel('Search evaluations').fill('no-such-run');
  await expect(page.getByRole('heading',{name:'No matching evaluations'})).toBeVisible();
  expect(errors).toEqual([]);
});

test('detail renders hostile case labels as text and unknown differs from zero', async ({page}) => {
  await page.goto(planning);
  await expect(page.getByRole('heading',{name:'planning evaluation'})).toBeVisible();
  await expect(page.getByText('<img src=x onerror=alert(1)>',{exact:true})).toBeVisible();
  expect(await page.locator('img').count()).toBe(0);
  await page.locator('.case summary').click();
  await expect(page.getByText(/contract.*failed assertion/)).toBeVisible();
  await page.goto(assessment);
  await expect(page.locator('.stat').filter({hasText:'Mean input tokens'}).locator('.stat-value')).toHaveText('0');
  await page.goto(authoring);
  await expect(page.locator('.stat').filter({hasText:'Mean input tokens'}).locator('.stat-value')).toHaveText('Unavailable');
  await page.goto('/evaluations/planning/missing');
  await expect(page.getByRole('heading',{name:'Unable to load evidence'})).toBeVisible();
});

test('runtime matrix presents bounded evidence and real cards', async ({page}) => {
  await page.goto('/runtime');
  await expect(page.getByRole('heading',{name:'Runtime readiness',exact:true})).toBeVisible();
  await expect(page.getByText(/Registration is not current availability/)).toBeVisible();
  expect(await page.locator('.runtime-card').count()).toBeGreaterThan(1);
  await page.locator('.runtime-card details summary').first().click();
  await expect(page.locator('.runtime-card details').first()).toHaveAttribute('open','');
});

test('theme, mobile navigation, history and layout remain usable', async ({page},testInfo) => {
  const errors:string[]=[];
  page.on('console', message=>{if(message.type()==='error')errors.push(message.text());});
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/');
  if(testInfo.project.name==='mobile') await page.getByRole('button',{name:'Open navigation'}).click();
  await page.getByLabel('Appearance',{exact:true}).selectOption('dark');
  await expect(page.locator('html')).toHaveClass(/dark/);
  await page.getByRole('navigation',{name:'Main navigation'}).getByRole('link',{name:/Evaluations/}).click();
  await expect(page.getByRole('heading',{name:'Evaluations',exact:true})).toBeVisible();
  await page.locator(`a[href="${planning}"]`).first().click();
  await expect(page.getByRole('heading',{name:'planning evaluation'})).toBeVisible();
  await page.goBack();
  await expect(page.getByRole('heading',{name:'Evaluations',exact:true})).toBeVisible();
  await page.reload();
  await expect(page.locator('html')).toHaveClass(/dark/);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  expect(errors).toEqual([]);
});

test('empty and connection failure states are actionable', async ({page}) => {
  // Fault injection supplements, rather than replaces, the real API integration tests above.
  await page.route('**/api/evaluations',route=>route.fulfill({json:{runs:[],warnings:[]}}));
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Your first evaluation starts here'})).toBeVisible();
  await page.unroute('**/api/evaluations');
  await page.route('**/api/evaluations',route=>route.abort());
  await page.getByRole('button',{name:'Refresh evidence'}).click();
  await expect(page.getByRole('heading',{name:'Unable to load evidence'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Try again'})).toBeVisible();
});

test('visual review captures all primary screens without horizontal overflow', async ({page},testInfo) => {
  for(const [name,url] of [['overview','/'],['evaluations','/evaluations'],['detail',planning],['runtime','/runtime'],['agents','/agents'],['experiments','/experiments']]){
    await page.goto(url);
    await expect(page.locator('h1')).toBeVisible();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
    await page.screenshot({path:testInfo.outputPath(`${name}.png`),fullPage:true});
  }
});


test('agent cards retain separate cohorts, paired token samples and unknowns', async ({page,request}) => {
  const response=await request.get('/api/metrics');expect(response.ok()).toBeTruthy();
  const data=await response.json();
  const planning=data.groups.find((g:any)=>g.agent==='planning' && g.attempts===4 && g.clean_attempts===3);
  expect(planning.latency_seconds).toEqual([0,1,2]);
  expect(planning.total_tokens).toEqual([110,220,330]);
  await page.goto('/agents');
  await expect(page.getByRole('heading',{name:'Agents',exact:true})).toBeVisible();
  await expect(page.locator('.agent-card')).toHaveCount(3);
  const card=page.getByRole('article',{name:'planning performance'});
  await card.getByLabel('planning cohort').selectOption(planning.id);
  await expect(card.getByRole('img',{name:'Task latency: 3 observed samples',exact:true})).toBeVisible();
  await expect(card.locator('.agent-stat').filter({hasText:'Evaluator success'}).locator('strong')).toHaveText('75.0%');
  await expect(card.locator('.chart-frequency')).toHaveCount(2);
  await expect(card.locator('.chart-frequency').first()).toHaveAttribute('d',/^M .* C /);
  await card.locator('.agent-evidence summary').click();
  await expect(card.locator('.agent-usage')).toContainText('600');
  await page.getByLabel('Metrics agent',{exact:true}).selectOption('assessment');
  await expect(page.locator('.agent-card')).toHaveCount(1);
  await page.locator('.agent-evidence summary').click();
  await expect(page.locator('.agent-usage dd').first()).toContainText('0');
  await expect(page.getByRole('img',{name:'Total tokens: 2 observed samples'})).toBeVisible();
  await page.getByLabel('Metrics agent',{exact:true}).selectOption('authoring');
  await expect(page.locator('.agent-stat').filter({hasText:'Evaluator success'}).locator('strong')).toHaveText('Unavailable');
  await expect(page.getByText('No observed samples. Unknown, not zero.')).toHaveCount(2);
  await expect(page.locator('.chart-frequency')).toHaveCount(0);
  await page.goto('/metrics');
  await expect(page.getByRole('heading',{name:'Agents',exact:true})).toBeVisible();
});

test('overview keeps scripted and live resource observations separate',async({page})=>{
  await page.goto('/');
  await expect(page.getByLabel('Overview distribution mode')).toHaveValue('live');
  await expect(page.getByRole('img',{name:'Total tokens: 2 observed samples'})).toBeVisible();
  await page.getByLabel('Overview distribution mode').selectOption('scripted');
  await expect(page.getByRole('img',{name:'Total tokens: 7 observed samples'})).toBeVisible();
  await expect(page.getByText(/Scripted token counts are fixture estimates/)).toBeVisible();
});

test('experiments show descriptive deltas and block incompatible runs',async({page},testInfo)=>{
  await page.goto('/experiments');
  await page.getByLabel('Baseline run',{exact:true}).selectOption('planning/20261013T120000Z-development-scripted');
  await page.getByLabel('Candidate run',{exact:true}).selectOption('planning/20261013T150000Z-development-scripted');
  await expect(page.getByRole('heading',{name:'What changed'})).toBeVisible();
  await expect(page.getByText('+25 pp recorded change',{exact:true}).first()).toBeVisible();
  await page.screenshot({path:testInfo.outputPath('comparison-populated.png'),fullPage:true});
  if(testInfo.project.name!=='mobile')expect(await contrastProblems(page)).toEqual([]);
  await page.getByLabel('Candidate run',{exact:true}).selectOption('assessment/20261013T130000Z-development-live');
  await expect(page.getByText(/different agents/)).toBeVisible();
  await expect(page.locator('.experiment-outcome').first()).toContainText('Comparison unavailable');
});
