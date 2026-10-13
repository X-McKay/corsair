import {test,expect} from '@playwright/test';
import {contrastProblems} from './support/contrast';
for(const path of ['/','/evaluations','/runtime','/agents','/experiments','/system','/runs','/evaluations/planning/20261013T120000Z-development-scripted']){
  test(`text contrast ${path}`,async({page},info)=>{
    test.skip(info.project.name==='mobile','Same palette covered by desktop and dark');
    await page.goto(path);await expect(page.locator('h1')).toBeVisible();
    await page.waitForLoadState('networkidle');
    const problems=await contrastProblems(page);
    expect(problems).toEqual([]);
  });
}
