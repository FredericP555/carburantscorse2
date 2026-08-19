(function(){
  'use strict';

  const DAY_MS=86400000;

  function parseIso(s){
    if(!s||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(s)) return null;
    const [y,m,d]=s.split('-').map(Number);
    return new Date(Date.UTC(y,m-1,d));
  }
  function isoFromDate(d){
    return d?d.toISOString().slice(0,10):null;
  }
  function addDays(iso,n){
    const d=parseIso(iso); if(!d)return null;
    d.setUTCDate(d.getUTCDate()+n);
    return isoFromDate(d);
  }
  function frDate(iso){
    const d=parseIso(iso); if(!d)return '—';
    return new Intl.DateTimeFormat('fr-FR',{day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(d);
  }
  function parisTodayIso(){
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Paris',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
    const o={}; parts.forEach(p=>{if(p.type!=='literal')o[p.type]=p.value;});
    return `${o.year}-${o.month}-${o.day}`;
  }
  function ageDays(iso){
    const d=parseIso(iso),t=parseIso(parisTodayIso());
    return d&&t?Math.max(0,Math.floor((t-d)/DAY_MS)):null;
  }
  function lastValidC1(res){
    if(typeof DATA==='undefined'||!DATA||!DATA.G)return null;
    const ck=(typeof carbu!=='undefined'&&carbu==='SP95')?'S':'G';
    const rows=DATA[ck]&&DATA[ck].corse&&DATA[ck].corse[res];
    if(!Array.isArray(rows)||!rows.length)return null;
    for(let i=rows.length-1;i>=0;i--){
      if(rows[i]&&rows[i][1]!=null){
        if(typeof offsetToDate==='function')return offsetToDate(rows[i][0]);
        return addDays('2022-01-01',Number(rows[i][0]));
      }
    }
    return null;
  }
  function c2Rows(gran){
    if(typeof DATA==='undefined'||!DATA||!DATA.gazole)return [];
    if(typeof currentCarbu!=='undefined'&&currentCarbu==='gazole'&&typeof currentVue!=='undefined'&&currentVue==='marge'){
      return (typeof MARGES_GZ!=='undefined'&&MARGES_GZ&&Array.isArray(MARGES_GZ.all))?MARGES_GZ.all:[];
    }
    const car=(typeof currentCarbu!=='undefined')?currentCarbu:'gazole';
    const ref=car==='sp95'&&typeof currentRef!=='undefined'?currentRef:'sp95';
    const node=DATA[car]&&DATA[car][ref]&&DATA[car][ref][gran];
    return node&&Array.isArray(node.all)?node.all:[];
  }
  function lastC2(gran){
    const rows=c2Rows(gran);
    for(let i=rows.length-1;i>=0;i--){if(rows[i]&&rows[i].date)return rows[i].date;}
    return null;
  }
  function sourceMaxDate(){
    if(typeof DATA!=='undefined'&&DATA&&DATA.gazole){
      const meta=(typeof window!=='undefined'&&window.A4C_DATA_META)||{};
      if(typeof currentCarbu!=='undefined'&&currentCarbu==='gazole'&&typeof currentVue!=='undefined'&&currentVue==='marge'){
        return meta.ufip_last_observed_date||lastC2('weekly');
      }
      return meta.official_source_max_date||meta.daily_target_end||lastC2('daily');
    }
    return lastValidC1('d');
  }
  function weeklyStartDate(){
    if(typeof DATA!=='undefined'&&DATA&&DATA.gazole)return lastC2('weekly');
    return lastValidC1('w');
  }
  function isWeeklyView(){
    if(typeof DATA!=='undefined'&&DATA&&DATA.gazole){
      if(typeof currentCarbu!=='undefined'&&currentCarbu==='gazole'&&typeof currentVue!=='undefined'&&currentVue==='marge')return true;
      return typeof currentGran!=='undefined'&&currentGran==='weekly';
    }
    return typeof resolution!=='undefined'&&resolution==='w';
  }
  function ensureBadge(){
    let badge=document.getElementById('a4c-freshness-badge');
    if(badge)return badge;
    const header=document.querySelector('header')||document.getElementById('header');
    if(!header)return null;
    const style=document.createElement('style');
    style.id='a4c-freshness-style';
    style.textContent=`
      header,#header{position:relative}
      #a4c-freshness-badge{position:absolute;right:18px;top:9px;z-index:5;display:inline-flex;align-items:center;gap:7px;padding:5px 10px;border-radius:999px;border:1px solid #cbd5e1;background:#fff;font:600 11px/1.2 system-ui,sans-serif;white-space:nowrap;box-shadow:0 1px 2px rgba(15,23,42,.05)}
      #a4c-freshness-badge::before{content:'';width:8px;height:8px;border-radius:50%;background:#16a34a;flex:0 0 auto}
      #a4c-freshness-badge.fresh{color:#166534;border-color:#bbf7d0;background:#f0fdf4}
      #a4c-freshness-badge.warn{color:#9a3412;border-color:#fed7aa;background:#fff7ed}
      #a4c-freshness-badge.warn::before{background:#f59e0b}
      #a4c-freshness-badge.stale{color:#991b1b;border-color:#fecaca;background:#fef2f2}
      #a4c-freshness-badge.stale::before{background:#dc2626}
      @media(min-width:701px){header h1,#header h1{padding-right:330px}}
      @media(max-width:700px){#a4c-freshness-badge{position:static;margin:5px 0 1px;max-width:100%;white-space:normal;font-size:10px}header h1,#header h1{padding-right:0}}
    `;
    document.head.appendChild(style);
    badge=document.createElement('div');
    badge.id='a4c-freshness-badge';
    badge.className='fresh';
    badge.setAttribute('role','status');
    badge.setAttribute('aria-live','polite');
    badge.title='Fraîcheur des données : vert ≤ 3 jours, orange 4–7 jours, rouge > 7 jours.';
    const h1=header.querySelector('h1');
    if(h1)h1.insertAdjacentElement('afterend',badge); else header.appendChild(badge);
    return badge;
  }
  function updateFreshnessBadge(){
    const badge=ensureBadge(); if(!badge)return;
    const sourceMax=sourceMaxDate();
    if(!sourceMax){badge.textContent='Fraîcheur indisponible';badge.className='warn';return;}
    let freshnessDate=sourceMax;
    if(isWeeklyView()){
      const start=weeklyStartDate();
      if(start){
        const end=addDays(start,6);
        if(end&&sourceMax>=end){
          badge.textContent=`Hebdo · semaine complète au ${frDate(end)}`;
          freshnessDate=end;
        }else{
          badge.textContent=`Hebdo · semaine du ${frDate(start)} · partielle au ${frDate(sourceMax)}`;
          freshnessDate=sourceMax;
        }
      }else{
        badge.textContent=`Hebdo · données au ${frDate(sourceMax)}`;
      }
    }else{
      badge.textContent=`Données au ${frDate(sourceMax)}`;
    }
    const age=ageDays(freshnessDate);
    badge.className=age==null?'warn':age<=3?'fresh':age<=7?'warn':'stale';
  }

  window.A4C_updateFreshnessBadge=updateFreshnessBadge;
  document.addEventListener('click',function(e){
    const t=e.target&&e.target.closest&&e.target.closest('[data-res],[data-carbu],#btn-daily,#btn-weekly,#btn-prix,#btn-marge,#btn-gz,#btn-sp,#btn-sp95ref,#btn-e10ref');
    if(t)setTimeout(updateFreshnessBadge,0);
  });
  window.addEventListener('load',function(){
    let tries=0;
    const timer=setInterval(function(){
      tries++;
      updateFreshnessBadge();
      if(sourceMaxDate()||tries>30)clearInterval(timer);
    },100);
  });
})();
