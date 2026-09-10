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
const report={schema:'a4c-monthly-widget-browser-smoke-v2',url,browser:await browser.version(),executablePath,tests:{}};

async function noPageOverflow(page, label){
  const x=await page.evaluate(()=>({scrollWidth:document.documentElement.scrollWidth,innerWidth:window.innerWidth}));
  check(x.scrollWidth<=x.innerWidth+1,`${label}: page has horizontal overflow (${x.scrollWidth}>${x.innerWidth})`);
  return x;
}

async function baseChecks(page, mode){
  await page.goto(url,{waitUntil:'networkidle'});
  await page.waitForSelector('#app:not([hidden])',{timeout:15000});
  check((await page.locator('#error').innerText()).trim()==='',`${mode}: error panel is not empty`);
  check((await page.locator('#period').innerText()).toLowerCase().includes('août 2026'),`${mode}: period does not identify August 2026`);
  check(await page.locator('#epci option').count()===19,`${mode}: expected 19 EPCI for Gazole`);
  return await noPageOverflow(page,mode);
}

async function exerciseAllEpci(page, mode){
  const out={};
  for(const fuelName of ['Gazole','SP95']){
    await page.click(`[data-fuel="${fuelName}"]`);
    const options=await page.locator('#epci option').evaluateAll(els=>els.map(e=>({value:e.value,label:e.textContent||''})));
    check(options.length===19,`${mode}/${fuelName}: expected 19 EPCI options`);
    let limited=0;
    for(const option of options){
      await page.selectOption('#epci',option.value);
      const texts=await Promise.all(['mean','change','vsCorse','range','sample'].map(id=>page.locator(`#${id}`).innerText()));
      check(!texts[0].includes('—') && !texts[0].includes('NaN'),`${mode}/${fuelName}/${option.label}: invalid monthly mean`);
      check(!texts[1].includes('NaN') && !texts[2].includes('NaN') && !texts[3].includes('NaN'),`${mode}/${fuelName}/${option.label}: NaN in indicator`);
      check(texts[4].includes('station-jours') && texts[4].includes('couverture temporelle de l’échantillon'),`${mode}/${fuelName}/${option.label}: sample note incomplete`);
      check(await page.locator('#localities tr').count()>0,`${mode}/${fuelName}/${option.label}: locality table is empty`);
      if(await page.locator('#limited').isVisible()) limited++;
      await noPageOverflow(page,`${mode}/${fuelName}/${option.label}`);
    }
    const expectedLimited=fuelName==='Gazole'?2:3;
    check(limited===expectedLimited,`${mode}/${fuelName}: expected ${expectedLimited} hors-classement EPCI, got ${limited}`);
    out[fuelName]={epciTested:options.length,horsClassement:limited};
  }
  return out;
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

  const exhaustive=await exerciseAllEpci(page,'desktop');

  await page.click('[data-fuel="SP95"]');
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

  report.tests.desktop={ok:true,overflow,layout,exhaustive,calviSample,calviRange,compare,calcNetwork,calcAll};
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
  check(layout.fuelButtonHeights.every(h=>h>=44),'mobile: fuel buttons are below 44px touch target');

  await page.click('[data-fuel="SP95"]');
  await page.selectOption('#epci','242020105');
  check(await page.locator('#limited').isVisible(),'mobile: Calvi Balagne SP95 limited notice is not visible');
  const mobileSample=await page.locator('#sample').innerText();
  check(mobileSample.includes('62,9 %'),'mobile: Calvi temporal coverage missing');

  await page.selectOption('#compareA','200038958');
  await page.selectOption('#compareB','200073104');
  const longCompare=await page.locator('#compareResult').innerText();
  check(longCompare.includes("CC de la Pieve de l'Ornano et du Taravo"),'mobile: long EPCI comparison did not render');
  await page.fill('#litres','70');
  const mobileCalc=await page.locator('#calcResult').innerText();
  check(mobileCalc.includes('70 L') && !mobileCalc.includes('NaN'),'mobile: calculator did not render cleanly');
  const after=await noPageOverflow(page,'mobile after long labels and calculator');

  report.tests.mobile={ok:true,overflow,layout,mobileSample,longCompare,mobileCalc,after};
  await context.close();
}

await browser.close();
report.ok=true;
const parent=output.includes('/')?output.slice(0,output.lastIndexOf('/')):'.';
fs.mkdirSync(parent,{recursive:true});
fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n','utf8');
console.log(JSON.stringify(report,null,2));
