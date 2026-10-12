#!/usr/bin/env python3
"""Keep c2 editorial copy derived from the live dashboard series.

Dates, headline averages, trends and record wording are computed in the browser from the
exact DATA/MARGES series being displayed, while the historical interpretation remains
editorial copy.
"""
from pathlib import Path

PATH = Path("index.html")

HELPERS = r'''
// ── Texte éditorial dynamique ────────────────────────────────────────────────
// Les chiffres ci-dessous sont calculés à partir des séries chargées dans data.json.
// Les constantes ANALYSES restent uniquement comme repli si les séries sont absentes.
function editorialMean(rows,field,start,end){
  const vals=(rows||[])
    .filter(r=>(!start||r.date>=start)&&(!end||r.date<=end))
    .map(r=>Number(r[field||'ecart']))
    .filter(v=>Number.isFinite(v));
  return vals.length?vals.reduce((a,b)=>a+b,0)/vals.length:null;
}
function editorialYearMean(rows,year,field){
  return editorialMean(rows,field||'ecart',year+'-01-01',year+'-12-31');
}
function editorialMax(rows,field,start,end){
  const f=field||'ecart';
  const vals=(rows||[]).filter(r=>(!start||r.date>=start)&&(!end||r.date<=end)&&Number.isFinite(Number(r[f])));
  return vals.length?vals.reduce((best,r)=>Number(r[f])>Number(best[f])?r:best):null;
}
function editorialCommonPeriod(){
  const lists=[...arguments].filter(r=>Array.isArray(r)&&r.length);
  if(!lists.length)return null;
  const starts=lists.map(r=>r[0].date).sort();
  const ends=lists.map(r=>r[r.length-1].date).sort();
  const start=starts[starts.length-1],end=ends[0];
  return start<=end?{start,end}:null;
}
function editorialSigned(v,digits){
  if(v==null||!Number.isFinite(v))return '—';
  const d=digits==null?1:digits;
  return (v>=0?'+':'−')+Math.abs(v).toFixed(d).replace('.',',');
}
function editorialPlain(v,digits){
  if(v==null||!Number.isFinite(v))return '—';
  const d=digits==null?1:digits;
  return v.toFixed(d).replace('.',',');
}
function editorialMonthYear(dateStr){
  if(!dateStr)return '';
  return new Date(dateStr+'T12:00:00').toLocaleDateString('fr-FR',{month:'long',year:'numeric'});
}
function editorialLongDate(dateStr){
  if(!dateStr)return '';
  return new Date(dateStr+'T12:00:00').toLocaleDateString('fr-FR',{day:'numeric',month:'long',year:'numeric'});
}
function getLatestDataYear(){
  const rows=DATA&&DATA.gazole&&DATA.gazole.sp95&&DATA.gazole.sp95.daily?DATA.gazole.sp95.daily.all:[];
  if(!rows||!rows.length)return 2026;
  return new Date(rows[rows.length-1].date+'T12:00:00').getFullYear();
}
function editorialTrend(all,startYear,lastFullYear){
  const first=editorialYearMean(all,startYear,'ecart');
  const last=editorialYearMean(all,lastFullYear,'ecart');
  if(first==null||last==null)return null;
  const pct=first===0?null:(last-first)/Math.abs(first)*100;
  return {first,last,pct};
}
function editorialEvolutionText(pct){
  if(pct==null||!Number.isFinite(pct))return '';
  const n=Math.abs(pct).toFixed(0).replace('.',',');
  return pct>=0?`soit une hausse d’environ <strong>+${n}%</strong>`:`soit une baisse d’environ <strong>−${n}%</strong>`;
}
function editorialBouclierStatus(fuel){
  const meta=getBouclierMeta(fuel);
  if(meta&&meta.current_active&&meta.current_active_since){
    return ` Il est actuellement contraignant depuis le <strong>${editorialLongDate(meta.current_active_since)}</strong>.`;
  }
  return '';
}
function buildGazolePriceAnalysis(){
  const all=DATA&&DATA.gazole&&DATA.gazole.sp95&&DATA.gazole.sp95.daily?DATA.gazole.sp95.daily.all:[];
  const net=DATA&&DATA.gazole&&DATA.gazole.sp95&&DATA.gazole.sp95.daily?DATA.gazole.sp95.daily.reseau:[];
  const weekly=DATA&&DATA.gazole&&DATA.gazole.sp95&&DATA.gazole.sp95.weekly?DATA.gazole.sp95.weekly.all:[];
  const p=editorialCommonPeriod(all,net);
  if(!p)return ANALYSES.gazole;
  const meanAll=editorialMean(all,'ecart',p.start,p.end);
  const meanNet=editorialMean(net,'ecart',p.start,p.end);
  const firstYear=new Date(p.start+'T12:00:00').getFullYear();
  const lastFullYear=new Date(p.end+'T12:00:00').getFullYear()-1;
  const trend=lastFullYear>=firstYear?editorialTrend(all,firstYear,lastFullYear):null;
  const discount=editorialMean(all,'ecart','2022-09-01','2022-11-15');
  const sanctionPeak=editorialMax(weekly,'ecart','2025-11-17','2025-12-31');
  const through2025Peak=editorialMax(weekly,'ecart',null,'2025-12-31');
  const overallPeak=editorialMax(weekly,'ecart');
  const wasRecord=!!(sanctionPeak&&through2025Peak&&sanctionPeak.date===through2025Peak.date&&Number(sanctionPeak.ecart)===Number(through2025Peak.ecart));
  let recordText='';
  if(sanctionPeak){
    recordText=`Fait le plus significatif : après la sanction de l’Autorité de la concurrence du 17 novembre 2025, l’écart Gazole a atteint <strong>${editorialSigned(Number(sanctionPeak.ecart))} c/L HT</strong> la semaine du <strong>${editorialLongDate(sanctionPeak.date)}</strong>${wasRecord?', alors un record depuis 2022':''}.`;
    if(overallPeak&&Number(overallPeak.ecart)>Number(sanctionPeak.ecart)){
      recordText+=` Il a depuis été dépassé : <strong>${editorialSigned(Number(overallPeak.ecart))} c/L HT</strong> la semaine du <strong>${editorialLongDate(overallPeak.date)}</strong>.`;
    }
  }
  const trendText=trend?`Sur les années complètes, l'écart passe de <strong>${editorialSigned(trend.first)} c/L en ${firstYear}</strong> à <strong>${editorialSigned(trend.last)} c/L en ${lastFullYear}</strong>, ${editorialEvolutionText(trend.pct)} — indépendamment des fluctuations des cours du pétrole.`:'';
  const discountText=discount==null?'':` La remise TotalEnergies de −20 c/L du 1er septembre au 15 novembre 2022, répercutée par VITO, a ramené l'écart moyen de cette période à <strong>${editorialSigned(discount)} c/L</strong> — preuve que la surcharge corse n'est pas une fatalité liée aux coûts d'insularité.`;
  return `<p style="margin-bottom:8px">Sur la période ${editorialMonthYear(p.start)} – ${editorialMonthYear(p.end)}, l'écart HT Corse/BdR sur le <strong>Gazole</strong> s'établit en moyenne à <strong>${editorialSigned(meanAll)} c/L</strong> toutes stations confondues, et à <strong>${editorialSigned(meanNet)} c/L</strong> réseau vs réseau.</p><p style="margin-bottom:8px">${trendText}${discountText} Les zones jaunes du graphique correspondent aux périodes où le bouclier TotalEnergies est effectivement contraignant selon la règle de l'observatoire.${editorialBouclierStatus('Gazole')}</p>${recordText?`<p style="color:#991b1b;font-weight:600">${recordText}</p>`:''}`;
}
function buildSp95PriceAnalysis(){
  const spAll=DATA&&DATA.sp95&&DATA.sp95.sp95&&DATA.sp95.sp95.daily?DATA.sp95.sp95.daily.all:[];
  const spNet=DATA&&DATA.sp95&&DATA.sp95.sp95&&DATA.sp95.sp95.daily?DATA.sp95.sp95.daily.reseau:[];
  const e10All=DATA&&DATA.sp95&&DATA.sp95.e10&&DATA.sp95.e10.daily?DATA.sp95.e10.daily.all:[];
  const e10Net=DATA&&DATA.sp95&&DATA.sp95.e10&&DATA.sp95.e10.daily?DATA.sp95.e10.daily.reseau:[];
  const p=editorialCommonPeriod(spAll,spNet,e10All,e10Net);
  if(!p)return ANALYSES.sp95;
  const spMeanAll=editorialMean(spAll,'ecart',p.start,p.end);
  const spMeanNet=editorialMean(spNet,'ecart',p.start,p.end);
  const e10MeanAll=editorialMean(e10All,'ecart',p.start,p.end);
  const e10MeanNet=editorialMean(e10Net,'ecart',p.start,p.end);
  const e10Adv=(e10MeanAll!=null&&spMeanAll!=null)?e10MeanAll-spMeanAll:null;
  const gmsEffect=(spMeanAll!=null&&spMeanNet!=null)?spMeanAll-spMeanNet:null;
  const firstYear=new Date(p.start+'T12:00:00').getFullYear();
  const lastFullYear=new Date(p.end+'T12:00:00').getFullYear()-1;
  const trend=lastFullYear>=firstYear?editorialTrend(spAll,firstYear,lastFullYear):null;
  const discount=editorialMean(spAll,'ecart','2022-09-01','2022-11-15');
  const trendText=trend?`Sur les années complètes, l'écart SP95 passe de <strong>${editorialSigned(trend.first)} c/L en ${firstYear}</strong> à <strong>${editorialSigned(trend.last)} c/L en ${lastFullYear}</strong>, ${editorialEvolutionText(trend.pct)}.`:'';
  const e10Text=e10Adv==null?'':` Sur la même période, prendre l'E10 comme référence continentale porte l'écart à <strong>${editorialSigned(e10MeanAll)} c/L</strong> toutes stations et <strong>${editorialSigned(e10MeanNet)} c/L</strong> réseau vs réseau ; cela correspond à un E10 BdR en moyenne <strong>${editorialPlain(e10Adv)} c/L moins cher</strong> que le SP95 BdR.`;
  const gmsText=gmsEffect==null?'':` L'inclusion des GMS dans la référence BdR accroît à elle seule l'écart moyen observé de <strong>${editorialSigned(gmsEffect)} c/L</strong> par rapport au seul réseau traditionnel.`;
  const discountText=discount==null?'':` La remise TotalEnergies de −20 c/L du 1er septembre au 15 novembre 2022, suivie par VITO, a ramené l'écart moyen de cette période à <strong>${editorialSigned(discount)} c/L</strong> — preuve que la surcharge n'est pas une fatalité.`;
  return `<p style="margin-bottom:8px">Sur la période ${editorialMonthYear(p.start)} – ${editorialMonthYear(p.end)}, l'écart HT Corse/BdR sur le <strong>SP95</strong> s'établit en moyenne à <strong>${editorialSigned(spMeanAll)} c/L</strong> toutes stations confondues et à <strong>${editorialSigned(spMeanNet)} c/L</strong> réseau vs réseau. La Corse ne commercialise pas d'E10, alors que ce carburant a largement pris la place du SP95 sur le continent.${e10Text}</p><p style="margin-bottom:8px">Les grandes surfaces des Bouches-du-Rhône tirent la référence « toutes stations » vers le bas, tandis que la Corse n'en compte aucune.${gmsText} En 2022, quand TotalEnergies a baissé ses prix, VITO a immédiatement suivi sur toute l'île : un acteur pratiquant des prix plus bas peut donc entraîner le marché corse.</p><p style="margin-bottom:8px">${trendText} Les zones jaunes correspondent aux périodes où le bouclier TotalEnergies est effectivement contraignant.${editorialBouclierStatus('SP95')}${discountText}</p><p style="color:#991b1b;font-weight:600">Comme pour le Gazole, la sanction du 17 novembre 2025 n'a produit aucun effet correctif : l'écart SP95 a atteint <strong>+19,6 c/L HT</strong> en décembre 2025 — son niveau le plus élevé depuis 2022 — dans les semaines suivant immédiatement la publication de la décision.</p>`;
}
(s)=>Date.parse(s+"T00:00:00Z")

function editorialMarginFullYear(rows,year){
  const vals=rows.filter(r=>r.date>=`${year}-01-01`&&r.date<=`${year}-12-31`);
  return vals.length>=48 && vals[0].date<=`${year}-01-15` && vals[vals.length-1].date>=`${year}-12-15`;
}

function editorialMarginWeekly(all,net,end){
  const a=all.filter(r=>r.date<=end);
  const n=net.filter(r=>r.date<=end);
  if(a.length<2||n.length<2) return null;
  const latest=a[a.length-1],previous=a[a.length-2],latestNet=n[n.length-1],previousNet=n[n.length-2];
  if(latest.date!==latestNet.date || previous.date!==previousNet.date ||
      periodUtc(latest.date)-periodUtc(previous.date)!==7*86400000 ||
      periodUtc(latestNet.date)-periodUtc(previousNet.date)!==7*86400000) return null;
  const nums=[latest.ecart,previous.ecart,latestNet.ecart,previousNet.ecart].map(Number);
  if(!nums.every(Number.isFinite))return null;
  return {date:latest.date,all:nums[0],net:nums[2],allChange:nums[0]-nums[1],netChange:nums[2]-nums[3]};
}

function editorialMarginVariation(v){
  if(Math.abs(v)<0.005)return 'stable';
  return v>0?`en hausse de ${editorialPlain(v,2)} c€/L`:`en baisse de ${editorialPlain(-v,2)} c€/L`;
}

function buildMarginAnalysis(){
  const all=MARGES_GZ&&Array.isArray(MARGES_GZ.all)?MARGES_GZ.all:[];
  const net=MARGES_GZ&&Array.isArray(MARGES_GZ.reseau)?MARGES_GZ.reseau:[];
  const p=editorialCommonPeriod(all,net);
  if(!p)return ANALYSE_MARGE_GZ;

  // A stable 2022–2025 historical comparison prevents the commercial 2026 cap
  // from silently replacing the reference used to document the earlier widening.
  const start23=p.start>'2023-01-01'?p.start:'2023-01-01';
  const corse=editorialMean(all,'corse',start23,p.end);
  const bdr=editorialMean(all,'bdr',start23,p.end);
  const baseReady=editorialMarginFullYear(all,2022)&&editorialMarginFullYear(all,2025);
  const firstGap=baseReady?editorialYearMean(all,2022,'ecart'):null;
  const lastGap=baseReady?editorialYearMean(all,2025,'ecart'):null;
  const change=firstGap!=null&&lastGap!=null?lastGap-firstGap:null;
  const pct=firstGap?change/Math.abs(firstGap)*100:null;
  const historic=baseReady
    ? `L'écart annuel moyen toutes stations est passé de <strong>${editorialSigned(firstGap)} c€/L en 2022</strong> à <strong>${editorialSigned(lastGap)} c€/L en 2025</strong>, soit ${change>=0?'une aggravation':'une réduction'} de <strong>${editorialPlain(Math.abs(change))} c€/L (${editorialPlain(Math.abs(pct),0)} %)</strong>.`
    : 'Les données ne couvrent pas encore deux années complètes permettant une comparaison historique fiable.';
  const janAug2022=editorialMean(all,'ecart','2022-01-01','2022-08-31');
  const janAug2025=editorialMean(all,'ecart','2025-01-01','2025-08-31');
  const preDiscount=(baseReady&&janAug2022!=null&&janAug2025!=null)
    ? `Sur les seuls mois de janvier à août, avant les remises de fin 2022, l'écart passe de <strong>${editorialSigned(janAug2022)} à ${editorialSigned(janAug2025)} c€/L</strong> entre 2022 et 2025, soit <strong>${editorialPlain(Math.abs(janAug2025-janAug2022))} c€/L ${janAug2025>=janAug2022?'de plus':'de moins'}</strong>.`
    : '';
  const lastFullYear=Number(p.end.slice(0,4))-1;
  const extraYear=lastFullYear>2025&&editorialMarginFullYear(all,lastFullYear)
    ? lastFullYear:null;
  const shieldRanges=getBouclierRanges('Gazole');
  const affected=extraYear!=null&&shieldRanges.some(r=>r.d1<=`${extraYear}-12-31`&&r.d2>=`${extraYear}-01-01`);
  const recentAnnual=extraYear!=null
    ? ` En ${extraYear}, l'écart annuel observé est de <strong>${editorialSigned(editorialYearMean(all,extraYear,'ecart'))} c€/L</strong>${affected?', sur une année influencée par le bouclier tarifaire':''}.`
    : '';

  const gapRecord=editorialMax(all,'ecart');
  const corseRecord=editorialMax(all,'corse');
  const afterSanction=gapRecord?.date>='2025-11-17'&&corseRecord?.date>='2025-11-17';
  const records=gapRecord&&corseRecord
    ? `Les records relevés depuis 2022 ${afterSanction?'ont même été établis après la sanction du 17 novembre 2025 :':'sont :'} <strong>${editorialSigned(Number(gapRecord.ecart))} c€/L</strong> d'écart la semaine du <strong>${editorialLongDate(gapRecord.date)}</strong> et <strong>${editorialSigned(Number(corseRecord.corse))} c€/L</strong> de marge apparente corse la semaine du <strong>${editorialLongDate(corseRecord.date)}</strong>.`
    : '';
  const w=editorialMarginWeekly(all,net,p.end);
  const weekly=w
    ? `À la semaine du <strong>${editorialLongDate(w.date)}</strong>, l'écart atteint <strong>${editorialSigned(w.all,2)} c€/L</strong> toutes stations BdR (${editorialMarginVariation(w.allChange)}) et <strong>${editorialSigned(w.net,2)} c€/L</strong> face au réseau traditionnel (${editorialMarginVariation(w.netChange)}).`
    : `Les dernières semaines ne permettent pas encore de calculer une évolution hebdomadaire sur deux relevés comparables.`;
  const ufip=window.A4C_DATA_META?.ufip_last_observed_date;
  const source=`Dernière semaine de marge disponible : ${editorialLongDate(p.end)}${ufip?` · Dernière cotation UFIP observée : ${editorialLongDate(ufip)}`:''}.`;
  return `<p style="margin-bottom:8px">La <strong>marge apparente</strong> du gazole correspond au prix à la pompe hors TVA et accise, diminué de la cotation Rotterdam (UFIP). Elle couvre les coûts et la rémunération de la distribution : <strong>ce n'est pas un bénéfice net</strong>.</p><p style="margin-bottom:8px"><strong>1 — UN ÉCART DE MARGE QUI S'EST CREUSÉ</strong> De ${editorialMonthYear(start23)} à ${editorialMonthYear(p.end)}, la marge apparente moyenne s'établit à <strong>${editorialSigned(corse)} c€/L en Corse</strong>, contre <strong>${editorialSigned(bdr)} c€/L dans les Bouches-du-Rhône</strong>. ${historic} ${preDiscount}${recentAnnual} <strong>L'insularité ne suffit pas à expliquer cette évolution sans chiffrage des coûts supplémentaires.</strong></p><p style="margin-bottom:6px"><strong>2 — LE BOUCLIER ATTÉNUE L'ÉCART SANS EN EFFACER LES CAUSES</strong> ${records} ${weekly} <strong>Une baisse conjoncturelle sous plafonnement commercial ne démontre pas que les causes de l'aggravation historique ont disparu.</strong></p><p style="font-size:0.75em;color:#64748b">${source}</p>`;
}
function syncDynamicPeriodLabels(){
  const y=getLatestDataYear();
  const h=document.querySelector('#header h1');
  if(h)h.textContent=`Écart de prix HT — Corse vs Bouches-du-Rhône — 2022–${y}`;
  const src=document.querySelector('#credits span');
  if(src)src.innerHTML=`Source&nbsp;: prix-carburants.gouv.fr 2022–${y} &middot; Cotations UFIP`;
  document.title=`Écart HT Corse / BdR 2022–${y}`;
}
'''

OLD_UPDATE = '''function updateAnalyse(c,vue){
  vue=vue||currentVue;
  const panel=document.getElementById('analyse-panel');
  const ls=document.getElementById('lire-suite');
  if(panel){panel.classList.remove('expanded');}
  if(ls){ls.setAttribute('aria-expanded','false');ls.textContent='▾ Lire la suite';}
  if(c==='gazole'&&vue==='marge'){
    document.getElementById('analyse-panel').innerHTML=ANALYSE_MARGE_GZ;
  } else {
    document.getElementById('analyse-panel').innerHTML=ANALYSES[c];
  }
}'''

NEW_UPDATE = '''function updateAnalyse(c,vue){
  vue=vue||currentVue;
  const panel=document.getElementById('analyse-panel');
  const ls=document.getElementById('lire-suite');
  if(panel){panel.classList.remove('expanded');}
  if(ls){ls.setAttribute('aria-expanded','false');ls.textContent='▾ Lire la suite';}
  if(c==='gazole'&&vue==='marge'){
    panel.innerHTML=buildMarginAnalysis();
  } else if(c==='gazole'){
    panel.innerHTML=buildGazolePriceAnalysis();
  } else {
    panel.innerHTML=buildSp95PriceAnalysis();
  }
}'''


def main():
    text = PATH.read_text(encoding="utf-8")

    marker = "function toggleAnalyse(btn){"
    helper_marker = "// ── Texte éditorial dynamique"
    if marker not in text:
        raise SystemExit("toggleAnalyse marker not found")
    helper_block = HELPERS.strip("\n")
    if helper_marker in text:
        marker_start = text.index(helper_marker)
        start = len(text[:marker_start].rstrip("\n"))
        end = text.index(marker, marker_start)
        prefix = text[:start].rstrip("\n")
        suffix = text[end:].lstrip("\n")
        text = prefix + "\n\n" + helper_block + "\n\n" + suffix
    else:
        text = text.replace(marker, helper_block + "\n\n" + marker, 1)

    if OLD_UPDATE in text:
        text = text.replace(OLD_UPDATE, NEW_UPDATE, 1)
    elif NEW_UPDATE not in text:
        raise SystemExit("updateAnalyse block not found")

    text = text.replace(
        "lbl.textContent='Toute la période (2022–2026)';",
        "lbl.textContent='Toute la période (2022–'+getLatestDataYear()+')';",
        1,
    )
    text = text.replace(
        "  await loadDashboardData();\n  syncPeriodSliderRange();",
        "  await loadDashboardData();\n  syncDynamicPeriodLabels();\n  syncPeriodSliderRange();",
        1,
    )

    PATH.write_text(text, encoding="utf-8")
    print("Dynamic editorial patch applied to index.html")


if __name__ == "__main__":
    main()