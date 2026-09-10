#!/usr/bin/env node
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import { chromium } from 'playwright-core';

function arg(name, fallback=null){
  const i=process.argv.indexOf(name);
  return i>=0 && i+1<process.argv.length ? process.argv[i+1] : fallback;
}
function check(cond, msg){ if(!cond) throw new Error(msg); }
function browserPath(){
  const candidates=['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium','/usr/bin/chromium-browser'];
  for(const p of candidates){ if(fs.existsSync(p)) return p; }
  for(const cmd of ['google-chrome','google-chrome-stable','chromium','chromium-browser']){
    try { return execFileSync('which',[cmd],{encoding:'utf8'}).trim(); } catch {}
  }
  throw new Error('No Chrome/Chromium executable found on runner');
}

const url=arg('--url');
const output=arg('--output','outputs/monthly-widget-browser-smoke.json');
check(url,'--url is required');

const executablePath=browserPath();
const browser=await chromium.launch({headless:true, executablePath, args:['--no-sandbox','--disable-dev-shm-usage']});
const report={schema:'a4c-monthly-widget-browser-smoke-v1',url,browser:await browser.version(),executablePath,tests:{}};

async function baseChecks(page, mode){
  await page.goto(url,{waitUntil:'networkidle'});
  await page.waitForSelector('#app:not([hidden])',{timeout:15000});
  check((await page.locator('#error').innerText()).trim()==='',`${mode}: error panel is not empty`);
  check((await page.locator('#period').innerText()).toLowerCase().includes('août 2026'),`${mode}: period does not identify August 2026`);
  check(await page.locator('#epci option').count()===19,`${mode}: expected 19 EPCI for Gazole`);
  const overflow=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,innerWidth:window.innerWidth}));
  check(overflow.scrollWidth<=overflow.innerWidth+1,`${mode}: page has horizontal overflow (${overflow.scrollWidth}>${overflow.innerWidth})`);
  return overflow;
}

{
  const context=await browser.newContext({viewport:{width:1365,height:900},locale:'fr-FR'});
  const page=await context.newPage();
  const overflow=await baseChecks(page,'desktop');
  const layout=await page.evaluate(()=>({
    cards:getComputedStyle(document.querySelector('.cards')).gridTemplateColumns.split(' ').filter(Boolean).length,
    controls:getComputedStyle(document.querySelector('.controls')).gridTemplateColumns.split(' ').filter(Boolean).length,
    cardWidth:document.querySelector('.card').getBoundingClientRect().width,
    wrapWidth:document.querySelector('.wrap').getBoundingClientRect().width
  }));
  check(layout.cards===4,'desktop: cards are not in four columns');
  check(layout.controls===2,'desktop: controls are not in two columns');

  await page.click('[data-fuel="SP95"]');
  check(await page.locator('#epci option').count()===19,'desktop: expected 19 EPCI for SP95');
  check(await page.locator('[data-fuel="SP95"]').getAttribute('aria-pressed')==='true','desktop: SP95 aria-pressed not updated');
  await page.selectOption('#epci','242020105');
  check(await page.locator('#limited').isVisible(),'desktop: Calvi Balagne SP95 limited notice is not visible');
  const calviSample=await page.locator('#sample').innerText();
  check(calviSample.includes('2 stations contributrices'),'desktop: Calvi sample count is not 2 contributing stations');
  check(calviSample.includes('62,9 %'),'desktop: Calvi temporal coverage is not 62.9%');
  const calviRange=await page.locator('#range').innerText();
  check(calviRange.includes('1,999'),'desktop: Calvi station monthly-mean range is missing');

  await page.selectOption('#epci','242000354');
  const bastiaSample=await page.locator('#sample').innerText();
  check(bastiaSample.includes('couverture temporelle de l’échantillon'),'desktop: sample wording is not explicit');
  await page.selectOption('#compareA','242000354');
  await page.selectOption('#compareB','242010056');
  const compare=await page.locator('#compareResult').innerText();
  check(compare.includes('CA de Bastia') && compare.includes('CA du Pays Ajaccien') && compare.includes('écart A − B'),'desktop: EPCI comparison did not render');

  await page.fill('#litres','70');
  const calcNetwork=await page.locator('#calcResult').innerText();
  check(calcNetwork.includes('70 L') && calcNetwork.includes('écart TTC'),'desktop: calculator did not render network result');
  check(!calcNetwork.includes('NaN'),'desktop: calculator produced NaN');
  await page.selectOption('#bdrScope','all');
  const calcAll=await page.locator('#calcResult').innerText();
  check(calcAll!==calcNetwork,'desktop: BDR scope change did not change calculator result');

  report.tests.desktop={ok:true,overflow,layout,calviSample,calviRange,compare,calcNetwork,calcAll};
  await context.close();
}

{
  const context=await browser.newContext({viewport:{width:390,height:844},locale:'fr-FR',isMobile:true});
  const page=await context.newPage();
  const overflow=await baseChecks(page,'mobile');
  const layout=await page.evaluate(()=>({
    cards:getComputedStyle(document.querySelector('.cards')).gridTemplateColumns.split(' ').filter(Boolean).length,
    controls:getComputedStyle(document.querySelector('.controls')).gridTemplateColumns.split(' ').filter(Boolean).length,
    bodyWidth:document.body.getBoundingClientRect().width,
    wrapWidth:document.querySelector('.wrap').getBoundingClientRect().width,
    fuelButtonHeights:[...document.querySelectorAll('.fuel-buttons button')].map(el=>el.getBoundingClientRect().height),
    tableViewportWidth:document.querySelector('section div[style*="overflow:auto"]').getBoundingClientRect().width,
    tableScrollWidth:document.querySelector('section div[style*="overflow:auto"]').scrollWidth
  }));
  check(layout.cards===1,'mobile: cards are not stacked in one column');
  check(layout.controls===1,'mobile: controls are not stacked in one column');
  check(layout.wrapWidth<=390,'mobile: wrapper exceeds viewport');
  check(layout.fuelButtonHeights.every(h=>h>=40),'mobile: fuel buttons are too short for touch');

  await page.click('[data-fuel="SP95"]');
  await page.selectOption('#epci','242020105');
  check(await page.locator('#limited').isVisible(),'mobile: Calvi Balagne SP95 limited notice is not visible');
  const mobileSample=await page.locator('#sample').innerText();
  check(mobileSample.includes('62,9 %'),'mobile: Calvi temporal coverage missing');
  const after=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,innerWidth:window.innerWidth}));
  check(after.scrollWidth<=after.innerWidth+1,`mobile: interaction introduced horizontal overflow (${after.scrollWidth}>${after.innerWidth})`);

  report.tests.mobile={ok:true,overflow,layout,mobileSample,after};
  await context.close();
}

await browser.close();
report.ok=true;
fs.mkdirSync(new URL('.',`file://${process.cwd()}/${output}`).pathname,{recursive:true});
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n','utf8');
console.log(JSON.stringify(report,null,2));
