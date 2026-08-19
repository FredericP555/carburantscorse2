#!/usr/bin/env python3
"""One-shot patch: make c2 editorial copy derive its dates and headline metrics from live DATA.

The dashboard keeps its historical editorial interpretation, but the values that naturally
move as data is appended (period end, full-period means, annual trend, E10 comparison and
margin averages) are computed in the browser from the exact series being displayed.
"""
from pathlib import Path

# This script is idempotent; updating it on main also triggers the targeted deployment workflow.
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
  const p=editorialCommonPeriod(all,net);
  if(!p)return ANALYSES.gazole;
  const meanAll=editorialMean(all,'ecart',p.start,p.end);
  const meanNet=editorialMean(net,'ecart',p.start,p.end);
  const firstYear=new Date(p.start+'T12:00:00').getFullYear();
  const lastFullYear=new Date(p.end+'T12:00:00').getFullYear()-1;
  const trend=lastFullYear>=firstYear?editorialTrend(all,firstYear,lastFullYear):null;
  const discount=editorialMean(all,'ecart','2022-09-01','2022-11-15');
  const trendText=trend?`Sur les années complètes, l'écart passe de <strong>${editorialSigned(trend.first)} c/L en ${firstYear}</strong> à <strong>${editorialSigned(trend.last)} c/L en ${lastFullYear}</strong>, ${editorialEvolutionText(trend.pct)} — indépendamment des fluctuations des cours du pétrole.`:'';
  const discountText=discount==null?'':` La remise TotalEnergies de −20 c/L du 1er septembre au 15 novembre 2022, répercutée par VITO, a ramené l'écart moyen de cette période à <strong>${editorialSigned(discount)} c/L</strong> — preuve que la surcharge corse n'est pas une fatalité liée aux coûts d'insularité.`;
  return `<p style="margin-bottom:8px">Sur la période ${editorialMonthYear(p.start)} – ${editorialMonthYear(p.end)}, l'écart HT Corse/BdR sur le <strong>Gazole</strong> s'établit en moyenne à <strong>${editorialSigned(meanAll)} c/L</strong> toutes stations confondues, et à <strong>${editorialSigned(meanNet)} c/L</strong> réseau vs réseau.</p><p style="margin-bottom:8px">${trendText} L'Autorité de la concurrence a reconnu le caractère anticoncurrentiel de cette politique dans sa décision 25-D-07 du 17 novembre 2025 (sanction de 187,5 M€).${discountText} Les zones jaunes du graphique correspondent aux périodes où le bouclier TotalEnergies est effectivement contraignant selon la règle de l'observatoire.${editorialBouclierStatus('Gazole')}</p><p style="color:#991b1b;font-weight:600">Fait le plus significatif : dans les semaines suivant la sanction du 17 novembre 2025, l'écart Gazole a atteint son niveau record à <strong>+22,7 c/L HT</strong> en décembre 2025. La décision n'a produit aucun effet correctif observable sur les prix.</p>`;
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
function buildMarginAnalysis(){
  const all=MARGES_GZ&&Array.isArray(MARGES_GZ.all)?MARGES_GZ.all:[];
  const net=MARGES_GZ&&Array.isArray(MARGES_GZ.reseau)?MARGES_GZ.reseau:[];
  const p=editorialCommonPeriod(all,net);
  if(!p)return ANALYSE_MARGE_GZ;
  const start23=p.start>'2023-01-01'?p.start:'2023-01-01';
  const corse=editorialMean(all,'corse',start23,p.end);
  const bdr=editorialMean(all,'bdr',start23,p.end);
  const firstYear=new Date(p.start+'T12:00:00').getFullYear();
  const lastFullYear=new Date(p.end+'T12:00:00').getFullYear()-1;
  const firstGap=editorialYearMean(all,firstYear,'ecart');
  const lastGap=lastFullYear>=firstYear?editorialYearMean(all,lastFullYear,'ecart'):null;
  const pct=(firstGap!=null&&lastGap!=null&&firstGap!==0)?(lastGap-firstGap)/Math.abs(firstGap)*100:null;
  const evolution=(firstGap!=null&&lastGap!=null)?`L'écart annuel moyen toutes stations est passé de <strong>${editorialSigned(firstGap)} c/L en ${firstYear}</strong> à <strong>${editorialSigned(lastGap)} c/L en ${lastFullYear}</strong>, ${editorialEvolutionText(pct)}.`:'';
  return `<p style="margin-bottom:8px">La marge de distribution, c'est tout ce qui sépare le prix du carburant à sa sortie du marché de gros (cotation Rotterdam) du prix hors taxes payé à la pompe. C'est la part qui revient à la chaîne de distribution dans son ensemble. Il s'agit d'une marge théorique, car elle part d'un prix de référence : des groupes intégrés spécialisés dans le trading, comme TotalEnergies, ENI ou Rubis, peuvent en réalité s'approvisionner en dessous de ce cours — leur marge réelle est donc probablement supérieure à celle calculée ici.</p><p style="margin-bottom:8px"><em>La marge de distribution est calculée en soustrayant du prix HT à la pompe l'accise sur les carburants (différenciée selon la zone et la période) et la cotation Rotterdam du Gazole publiée par l'UFIP. Ce qui reste représente ce que les distributeurs conservent pour couvrir leurs coûts et dégager un bénéfice.</em></p><p style="margin-bottom:8px">De ${editorialMonthYear(start23)} à ${editorialMonthYear(p.end)}, la marge de distribution en Corse s'établit en moyenne à <strong>${editorialSigned(corse)} c/L</strong>, contre <strong>${editorialSigned(bdr)} c/L</strong> dans les Bouches-du-Rhône (toutes stations). ${evolution} Si les seuls coûts d'insularité expliquaient cet écart, celui-ci devrait rester relativement stable dans le temps. En septembre-octobre 2022, la remise TotalEnergies a comprimé les marges à leur niveau le plus bas de la période analysée, montrant la capacité des opérateurs à absorber des baisses significatives.</p><p style="color:#991b1b;font-weight:600">Fait le plus significatif : dans les semaines suivant la sanction du 17 novembre 2025, non seulement l'écart de marge a atteint son niveau record à <strong>+24 c/L</strong> (semaine du 15 décembre 2025), mais la marge corse elle-même culminait à près de <strong>+49 c/L</strong> — son plus haut niveau depuis 2022. La décision n'a produit aucun effet correctif sur les comportements tarifaires.</p>`;
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

    if "function buildGazolePriceAnalysis()" not in text:
        marker = "function toggleAnalyse(btn){"
        if marker not in text:
            raise SystemExit("toggleAnalyse marker not found")
        text = text.replace(marker, HELPERS + "\n" + marker, 1)

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