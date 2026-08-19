from pathlib import Path

p=Path('index.html')
s=p.read_text(encoding='utf-8')
old="""const EVENTS=[
  {date:'2022-02-24',label:'Invasion Ukraine',color:'rgba(220,38,38,0.85)'},
  {date:'2025-11-17',label:'Sanctions Autorité',color:'rgba(14,116,144,0.85)'},
  {date:'2026-02-28',label:\"Guerre d'Iran\",color:'rgba(124,58,237,0.85)'},
];"""
new="""const EVENTS=[
  {date:'2022-02-24',label:'Invasion Ukraine',color:'rgba(220,38,38,0.85)'},
  {date:'2025-11-17',label:'Sanctions Autorité',color:'rgba(14,116,144,0.85)'},
  {date:'2026-02-28',label:'Début guerre Iran',color:'rgba(124,58,237,0.85)'},
  {date:'2026-06-17',label:'Accord / cessez-le-feu Iran',color:'rgba(124,58,237,0.85)'},
  {date:'2026-07-07',label:'Reprise frappes Iran',color:'rgba(124,58,237,0.85)'},
];"""
if old not in s:
    raise SystemExit('EVENTS block not found')
s=s.replace(old,new,1)
old_mobile="""  <span style=\"color:rgba(220,38,38,0.85);font-weight:bold\">─ ─</span> Invasion Ukraine (fév. 2022) &nbsp;
  <span style=\"color:rgba(14,116,144,0.85);font-weight:bold\">─ ─</span> Sanctions Autorité concurrence (nov. 2025) &nbsp;
  <span style=\"color:rgba(124,58,237,0.85);font-weight:bold\">─ ─</span> Guerre d'Iran (fév. 2026)"""
new_mobile="""  <span style=\"color:rgba(220,38,38,0.85);font-weight:bold\">─ ─</span> Invasion Ukraine (24 fév. 2022) &nbsp;
  <span style=\"color:rgba(14,116,144,0.85);font-weight:bold\">─ ─</span> Sanctions Autorité concurrence (17 nov. 2025) &nbsp;
  <span style=\"color:rgba(124,58,237,0.85);font-weight:bold\">─ ─</span> Début guerre Iran (28 fév. 2026) &nbsp;
  <span style=\"color:rgba(124,58,237,0.85);font-weight:bold\">─ ─</span> Accord / cessez-le-feu Iran (17 juin 2026) &nbsp;
  <span style=\"color:rgba(124,58,237,0.85);font-weight:bold\">─ ─</span> Reprise frappes Iran (7 juil. 2026)"""
if old_mobile not in s:
    raise SystemExit('mobile legend block not found')
s=s.replace(old_mobile,new_mobile,1)
p.write_text(s,encoding='utf-8')
