from pathlib import Path

p = Path('index.html')
s = p.read_text(encoding='utf-8')

old_constants = '''const PERIODES={Gazole:[{"d1":"2022-09-01","d2":"2022-10-31","color":"rgba(234,179,8,0.13)","border":"#ca8a04"},{"d1":"2022-11-01","d2":"2022-12-31","color":"rgba(234,179,8,0.08)","border":"#ca8a04"},{"d1":"2023-09-05","d2":"2023-11-01","color":"rgba(5,150,105,0.15)","border":"#059669"},{"d1":"2026-03-10","d2":"2026-03-16","color":"rgba(5,150,105,0.15)","border":"#059669"},{"d1":"2026-03-23","d2":"2026-04-07","color":"rgba(245,158,11,0.18)","border":"#d97706"},{"d1":"2026-04-10","d2":"2026-05-13","color":"rgba(239,68,68,0.14)","border":"#dc2626"}],SP95:[{"d1":"2022-09-01","d2":"2022-10-31","color":"rgba(234,179,8,0.13)","border":"#ca8a04"},{"d1":"2022-11-01","d2":"2022-12-31","color":"rgba(234,179,8,0.08)","border":"#ca8a04"},{"d1":"2023-04-01","d2":"2023-04-28","color":"rgba(5,150,105,0.15)","border":"#059669"},{"d1":"2023-07-31","d2":"2023-10-09","color":"rgba(5,150,105,0.15)","border":"#059669"},{"d1":"2024-03-22","d2":"2024-03-28","color":"rgba(5,150,105,0.15)","border":"#059669"},{"d1":"2024-04-06","d2":"2024-06-04","color":"rgba(5,150,105,0.15)","border":"#059669"},{"d1":"2026-03-17","d2":"2026-06-06","color":"rgba(5,150,105,0.15)","border":"#059669"}]};
const EVENTS=[{"date":"2022-03-07","label":"Guerre Ukraine","color":"#dc2626"},{"date":"2025-11-17","label":"Sanction concurrence","color":"#7c3aed"},{"date":"2026-02-28","label":"Guerre Iran","color":"#dc2626"}];'''
new_constants = '''// Contexte temporel : volontairement aligné sur carburantscorse1/app.js.
// ZONES = remises Total 2022 ; BOUCLIER = périodes où le bouclier est effectivement actif dans les données.
const ZONES=[
  {d1:'2022-09-01',d2:'2022-11-15',alpha_fill:0.18},
  {d1:'2022-11-16',d2:'2022-12-31',alpha_fill:0.12},
];
const BOUCLIER={
  Gazole:[
    {d1:'2023-08-31',d2:'2023-10-13'},{d1:'2023-10-24',d2:'2023-10-30'},
    {d1:'2026-03-20',d2:'2026-04-06'},{d1:'2026-04-08',d2:'2026-05-27'},
  ],
  Gazole_promo:[
    {d1:'2026-04-30',d2:'2026-05-03'},{d1:'2026-05-08',d2:'2026-05-10'},
    {d1:'2026-05-14',d2:'2026-05-17'},{d1:'2026-05-23',d2:'2026-05-25'},
  ],
  SP95:[
    {d1:'2023-02-20',d2:'2023-03-19'},{d1:'2023-03-27',d2:'2023-05-02'},
    {d1:'2023-06-09',d2:'2023-06-21'},{d1:'2023-07-25',d2:'2023-10-07'},
    {d1:'2024-02-20',d2:'2024-03-01'},{d1:'2024-03-07',d2:'2024-06-05'},
    {d1:'2024-07-01',d2:'2024-07-16'},{d1:'2026-03-13',d2:'2026-05-28'},
  ],
};
const EVENTS=[
  {date:'2022-02-24',label:'Invasion Ukraine',color:'rgba(220,38,38,0.85)'},
  {date:'2025-11-17',label:'Sanctions Autorité',color:'rgba(14,116,144,0.85)'},
  {date:'2026-02-28',label:"Guerre d'Iran",color:'rgba(124,58,237,0.85)'},
];'''
if old_constants not in s:
    raise SystemExit('old timeline constants not found; refusing broad patch')
s = s.replace(old_constants, new_constants, 1)

old_draw = '''    beforeDraw(c){
      const{ctx,chartArea:{top,bottom,left,right},scales:{x}}=c;
      (PERIODES[ck]||[]).forEach(p=>{
        const x1=Math.max(left,x.getPixelForValue(ts(p.d1)));
        const x2=Math.min(right,x.getPixelForValue(ts(p.d2)));
        if(x2<=left||x1>=right)return;
        ctx.save();ctx.fillStyle=p.color;ctx.fillRect(x1,top,x2-x1,bottom-top);ctx.restore();
      });
    },'''
new_draw = '''    beforeDraw(c){
      const{ctx,chartArea:{top,bottom,left,right},scales:{x}}=c;
      const fillPeriod=(p,color)=>{
        const x1=Math.max(left,x.getPixelForValue(ts(p.d1)));
        const x2=Math.min(right,x.getPixelForValue(ts(p.d2)));
        if(x2<=left||x1>=right)return;
        ctx.save();ctx.fillStyle=color;ctx.fillRect(x1,top,x2-x1,bottom-top);ctx.restore();
      };
      ZONES.forEach(p=>fillPeriod(p,`rgba(34,197,94,${p.alpha_fill})`));
      (BOUCLIER[ck]||[]).forEach(p=>fillPeriod(p,'rgba(251,191,36,0.20)'));
      if(ck==='Gazole'){
        (BOUCLIER.Gazole_promo||[]).forEach(p=>fillPeriod(p,'rgba(234,88,12,0.09)'));
      }
    },'''
if old_draw not in s:
    raise SystemExit('old period drawing block not found')
s = s.replace(old_draw, new_draw, 1)

old_legend = '''  <div id="legend">
    <div class="li"><div class="lb" style="background:#ca8a04"></div>Remise Total</div>
    <div class="li"><div class="lb" style="background:#059669"></div>Bouclier 1,99€ actif</div>
    <div class="li" id="li-209"><div class="lb" style="background:#d97706"></div>2,09€ actif</div>
    <div class="li" id="li-225"><div class="lb" style="background:#dc2626"></div>2,25€ actif</div>
  </div>'''
new_legend = '''  <div id="legend">
    <div class="li"><div class="lb" style="background:rgba(34,197,94,0.38);border:1px solid rgba(34,197,94,0.5)"></div>Remise Total −20 c/L (sept.–15 nov. 2022)</div>
    <div class="li"><div class="lb" style="background:rgba(34,197,94,0.25);border:1px solid rgba(34,197,94,0.4)"></div>Remise Total −10 c/L (16 nov.–déc. 2022)</div>
    <div class="li"><div class="lb" style="background:rgba(251,191,36,0.25);border:1px solid rgba(251,191,36,0.45)"></div>Bouclier TotalEnergies actif</div>
    <div class="li" id="li-promo-gz"><div class="lb" style="background:rgba(234,88,12,0.18);border:1px dashed rgba(234,88,12,0.4)"></div>Promo ponts mai 2026 — diesel 2,09 €/L</div>
  </div>'''
if old_legend not in s:
    raise SystemExit('old timeline legend not found')
s = s.replace(old_legend, new_legend, 1)

old_visibility = '''  document.getElementById('li-209').style.display=currentCarbu==='gazole'?'flex':'none';
  document.getElementById('li-225').style.display=currentCarbu==='gazole'?'flex':'none';'''
new_visibility = '''  document.getElementById('li-promo-gz').style.display=currentCarbu==='gazole'?'flex':'none';'''
if old_visibility not in s:
    raise SystemExit('old legend visibility logic not found')
s = s.replace(old_visibility, new_visibility, 1)

p.write_text(s, encoding='utf-8')
