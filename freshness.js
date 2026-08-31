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
  function isMarginView(){
    return typeof DATA!=='undefined'&&DATA&&DATA.gazole&&
      typeof currentCarbu!=='undefined'&&currentCarbu==='gazole'&&
      typeof currentVue!=='undefined'&&currentVue==='marge';
  }
  function c2Rows(gran){
    if(typeof DATA==='undefined'||!DATA||!DATA.gazole)return [];
    if(isMarginView()){
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
      if(isMarginView()){
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
      if(isMarginView())return true;
      return typeof currentGran!=='undefined'&&currentGran==='weekly';
    }
    return typeof resolution!=='undefined'&&resolution==='w';
  }
  function hasCurrentC2Metadata(){
    const meta=(typeof window!=='undefined'&&window.A4C_DATA_META)||{};
    return !!(meta.official_source_max_date||meta.daily_target_end);
  }

  function enableC2PeriodSliderEverywhere(){
    const slider=document.getElementById('periode-slider');
    if(!slider||typeof window.onSliderPeriode!=='function')return false;
    window.usePeriodSlider=function(){return true;};
    window.updateSliderVisibility=function(){
      const panel=document.getElementById('periode-slider');
      if(!panel)return;
      panel.style.display=window.innerWidth<=700?'block':'flex';
    };
    if(!document.getElementById('a4c-c2-desktop-period-style')){
      const style=document.createElement('style');
      style.id='a4c-c2-desktop-period-style';
      style.textContent=`
        @media(min-width:701px){
          #periode-slider{align-items:center;gap:12px;padding:5px 14px 6px!important}
          #periode-slider label{margin:0;white-space:nowrap;flex:0 0 auto}
          #periode-slider input[type=range]{width:min(360px,40vw);height:20px;flex:0 1 360px}
        }
      `;
      document.head.appendChild(style);
    }
    window.updateSliderVisibility();
    return true;
  }

  function installC2AdaptiveAxis(){
    if(typeof buildAnnualTicks!=='function'||typeof formatAnnualTick!=='function')return false;
    buildAnnualTicks=function(minTs,maxTs){
      const spanMonths=Math.max(1,(maxTs-minTs)/(30.44*DAY_MS));
      const step=spanMonths<=15?2:spanMonths<=30?3:12;
      const weekly=(typeof currentGran!=='undefined'&&currentGran==='weekly')||isMarginView();
      const out=[];
      if(step===12){
        const y0=new Date(minTs).getFullYear(),y1=new Date(maxTs).getFullYear();
        for(let y=y0;y<=y1;y++){
          const d=new Date(y,0,1);
          if(weekly){while(d.getDay()!==1)d.setDate(d.getDate()+1);}
          const v=d.getTime();
          if(v>=minTs&&v<=maxTs)out.push({value:v});
        }
        return out;
      }
      const start=new Date(minTs);
      let d=new Date(start.getFullYear(),start.getMonth(),1);
      if(d.getTime()<minTs)d.setMonth(d.getMonth()+1);
      while(d.getTime()<=maxTs){
        const tick=new Date(d.getTime());
        if(weekly){while(tick.getDay()!==1)tick.setDate(tick.getDate()+1);}
        const v=tick.getTime();
        if(v>=minTs&&v<=maxTs)out.push({value:v});
        d.setMonth(d.getMonth()+step);
      }
      return out;
    };
    formatAnnualTick=function(v){
      const d=new Date(v);
      const months=['jan','fév','mar','avr','mai','jun','jul','aoû','sep','oct','nov','déc'];
      return months[d.getMonth()]+' '+String(d.getFullYear()).slice(2);
    };
    return true;
  }

  function installDynamicMarginRecord(){
    if(typeof window.buildMarginAnalysis!=='function')return false;
    if(window.buildMarginAnalysis.__a4cDynamicMarginRecord)return true;

    const base=window.buildMarginAnalysis;
    const marker='<p style="color:#991b1b;font-weight:600">';

    function maxRow(rows,field,start,end){
      const vals=(rows||[]).filter(r=>
        (!start||r.date>=start)&&(!end||r.date<=end)&&Number.isFinite(Number(r[field]))
      );
      return vals.length?vals.reduce((best,r)=>Number(r[field])>Number(best[field])?r:best):null;
    }
    function samePeak(a,b,field){
      return !!(a&&b&&a.date===b.date&&Math.abs(Number(a[field])-Number(b[field]))<1e-9);
    }
    function signed(v){
      if(v==null||!Number.isFinite(Number(v)))return '—';
      const n=Math.abs(Number(v));
      const s=n.toFixed(1).replace('.',',').replace(/,0$/,'');
      return (Number(v)>=0?'+':'−')+s;
    }
    function longDate(iso){
      return frDate(iso);
    }
    function joinFr(parts){
      if(!parts.length)return '';
      if(parts.length===1)return parts[0];
      return parts.slice(0,-1).join(', ')+' et '+parts[parts.length-1];
    }

    function patchedMarginAnalysis(){
      const html=base();
      const rows=(typeof MARGES_GZ!=='undefined'&&MARGES_GZ&&Array.isArray(MARGES_GZ.all))?MARGES_GZ.all:[];
      if(!rows.length)return html;

      const sanctionStart='2025-11-17';
      const sanctionEnd='2025-12-31';
      const gapAfter=maxRow(rows,'ecart',sanctionStart,sanctionEnd);
      const corseAfter=maxRow(rows,'corse',sanctionStart,sanctionEnd);
      if(!gapAfter||!corseAfter)return html;

      const gapThrough=maxRow(rows,'ecart',null,sanctionEnd);
      const corseThrough=maxRow(rows,'corse',null,sanctionEnd);
      const gapOverall=maxRow(rows,'ecart');
      const corseOverall=maxRow(rows,'corse');
      const gapWasRecord=samePeak(gapAfter,gapThrough,'ecart');
      const corseWasRecord=samePeak(corseAfter,corseThrough,'corse');

      let recordText='Fait le plus significatif : dans les semaines suivant la sanction du 17 novembre 2025, ';
      if(gapAfter.date===corseAfter.date){
        recordText+=`l'écart de marge a atteint <strong>${signed(gapAfter.ecart)} c/L</strong> et la marge corse <strong>${signed(corseAfter.corse)} c/L</strong> au cours de la semaine du <strong>${longDate(gapAfter.date)}</strong>.`;
      }else{
        recordText+=`l'écart de marge a atteint <strong>${signed(gapAfter.ecart)} c/L</strong> la semaine du <strong>${longDate(gapAfter.date)}</strong>, tandis que la marge corse a culminé à <strong>${signed(corseAfter.corse)} c/L</strong> la semaine du <strong>${longDate(corseAfter.date)}</strong>.`;
      }

      if(gapWasRecord&&corseWasRecord){
        recordText+=' Ces deux niveaux constituaient alors des records depuis 2022.';
      }else if(gapWasRecord){
        recordText+=' L’écart de marge constituait alors un record depuis 2022.';
      }else if(corseWasRecord){
        recordText+=' La marge corse constituait alors un record depuis 2022.';
      }

      const later=[];
      if(gapOverall&&Number(gapOverall.ecart)>Number(gapAfter.ecart)+1e-9){
        later.push(`le record d'écart de marge a depuis été porté à <strong>${signed(gapOverall.ecart)} c/L</strong> la semaine du <strong>${longDate(gapOverall.date)}</strong>`);
      }
      if(corseOverall&&Number(corseOverall.corse)>Number(corseAfter.corse)+1e-9){
        later.push(`le record de marge corse à <strong>${signed(corseOverall.corse)} c/L</strong> la semaine du <strong>${longDate(corseOverall.date)}</strong>`);
      }
      if(later.length){
        recordText+=` Depuis, ${joinFr(later)}.`;
      }else if(gapWasRecord&&corseWasRecord){
        recordText+=' Ces records n’ont pas été dépassés depuis.';
      }

      recordText+=' Les données observées dans les semaines suivant la décision ne montrent donc aucun effet correctif immédiat sur les comportements tarifaires.';

      const paragraph=`${marker}${recordText}</p>`;
      const pos=html.lastIndexOf(marker);
      return pos>=0?html.slice(0,pos)+paragraph:html+paragraph;
    }

    patchedMarginAnalysis.__a4cDynamicMarginRecord=true;
    window.buildMarginAnalysis=patchedMarginAnalysis;
    return true;
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
        if(isMarginView()&&end){
          // Align the margin badge with the price view: once a guarded weekly
          // margin exists, display the covered end date in the same compact form.
          badge.textContent=`Données au ${frDate(end)}`;
          freshnessDate=end;
        }else if(end&&sourceMax>=end){
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

  // La vue marge est nécessairement hebdomadaire. Mémoriser la granularité
  // choisie pour la vue prix afin de la restaurer quand on quitte la marge.
  let lastPriceGran=(typeof currentGran!=='undefined'&&currentGran==='weekly')?'weekly':'daily';
  document.addEventListener('click',function(e){
    const t=e.target&&e.target.closest&&e.target.closest('#btn-daily,#btn-weekly,#btn-prix,#btn-marge,#btn-sp');
    if(!t)return;
    if(t.id==='btn-marge'){
      if(typeof currentVue==='undefined'||currentVue!=='marge'){
        if(typeof currentGran!=='undefined')lastPriceGran=currentGran;
      }
      return;
    }
    if((t.id==='btn-prix'||t.id==='btn-sp')&&typeof currentVue!=='undefined'&&currentVue==='marge'){
      if(typeof currentGran!=='undefined')currentGran=lastPriceGran;
      return;
    }
    if((t.id==='btn-daily'||t.id==='btn-weekly')&&!(typeof currentVue!=='undefined'&&currentVue==='marge')){
      lastPriceGran=t.id==='btn-weekly'?'weekly':'daily';
    }
  },true);

  enableC2PeriodSliderEverywhere();
  installC2AdaptiveAxis();
  installDynamicMarginRecord();
  window.A4C_updateFreshnessBadge=updateFreshnessBadge;
  document.addEventListener('click',function(e){
    const t=e.target&&e.target.closest&&e.target.closest('[data-res],[data-carbu],#btn-daily,#btn-weekly,#btn-prix,#btn-marge,#btn-gz,#btn-sp,#btn-sp95ref,#btn-e10ref');
    if(t)setTimeout(updateFreshnessBadge,0);
  });
  window.addEventListener('load',function(){
    enableC2PeriodSliderEverywhere();
    installC2AdaptiveAxis();
    installDynamicMarginRecord();
    let tries=0;
    const timer=setInterval(function(){
      tries++;
      updateFreshnessBadge();
      // Les séries historiques embarquées peuvent s'arrêter au 6 juin 2026.
      // Attendre les métadonnées de data.json avant de considérer le badge à jour.
      if(hasCurrentC2Metadata()||tries>300)clearInterval(timer);
    },100);
  });
})();
