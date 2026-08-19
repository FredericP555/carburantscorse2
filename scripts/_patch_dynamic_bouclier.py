from pathlib import Path

# 1) Carry c1 detector metadata from the shared release manifest.
p=Path('a4c_common/shared_release.py')
s=p.read_text(encoding='utf-8')
needle='''        "shared_rows": metadata.get("rows"),\n'''
repl='''        "shared_rows": metadata.get("rows"),\n        "bouclier": metadata.get("bouclier"),\n'''
if needle not in s:
    raise SystemExit('shared release source anchor not found')
s=s.replace(needle,repl,1)
p.write_text(s,encoding='utf-8')

# 2) Persist the detector metadata in c2 data.json without touching DATA/MARGES_GZ.
p=Path('scripts/build_append_candidate.py')
s=p.read_text(encoding='utf-8')
needle='''            "official_shared_source_max_date": official_source.get("shared_source_max_date"),\n            "ufip_last_observed_date": ufip_last,\n'''
repl='''            "official_shared_source_max_date": official_source.get("shared_source_max_date"),\n            "bouclier": official_source.get("bouclier") or baseline_meta.get("bouclier"),\n            "ufip_last_observed_date": ufip_last,\n'''
if needle not in s:
    raise SystemExit('candidate metadata anchor not found')
s=s.replace(needle,repl,1)
p.write_text(s,encoding='utf-8')

# 3) Draw authoritative dynamic ranges when present; fall back to frozen static history.
p=Path('index.html')
s=p.read_text(encoding='utf-8')
needle='''function makePlugin(minTs,maxTs,ck){\n'''
repl='''function getBouclierMeta(ck){\n  const root=window.A4C_DATA_META&&window.A4C_DATA_META.bouclier;\n  return root&&root[ck]?root[ck]:null;\n}\nfunction getBouclierRanges(ck){\n  const meta=getBouclierMeta(ck);\n  return meta&&Array.isArray(meta.ranges)?meta.ranges:(BOUCLIER[ck]||[]);\n}\nfunction makePlugin(minTs,maxTs,ck){\n'''
if needle not in s:
    raise SystemExit('makePlugin anchor not found')
s=s.replace(needle,repl,1)
s=s.replace("(BOUCLIER[ck]||[]).forEach(p=>fillPeriod(p,'rgba(251,191,36,0.20)'));","getBouclierRanges(ck).forEach(p=>fillPeriod(p,'rgba(251,191,36,0.20)'));",1)

old='''function updateBouclierInfo(){\n  const bi=document.getElementById('bouclier-info');if(!bi)return;\n  if(currentCarbu==='gazole'){\n    bi.innerHTML='■ Bouclier tarifaire TotalEnergies : <b>1,99 €/L TTC</b> d’août 2023 au 19 mars 2026 · <b>2,09 €/L TTC</b> du 20 mars au 7 avr. 2026 · <b>2,25 €/L TTC</b> depuis le 8 avr. 2026 <span style="color:rgba(234,88,12,0.85)">· Promo 2,09 €/L les ponts de mai 2026</span>';\n  }else{\n    bi.innerHTML='■ Bouclier tarifaire TotalEnergies : <b>1,99 €/L TTC</b> depuis mars 2023';\n  }\n}\n'''
new='''function updateBouclierInfo(){\n  const bi=document.getElementById('bouclier-info');if(!bi)return;\n  const ck=currentCarbu==='gazole'?'Gazole':'SP95';\n  const meta=getBouclierMeta(ck);\n  let base;\n  if(currentCarbu==='gazole'){\n    base='■ Bouclier tarifaire TotalEnergies : <b>1,99 €/L TTC</b> d’août 2023 au 19 mars 2026 · <b>2,09 €/L TTC</b> du 20 mars au 7 avr. 2026 · <b>2,25 €/L TTC</b> depuis le 8 avr. 2026 <span style="color:rgba(234,88,12,0.85)">· Promo 2,09 €/L les ponts de mai 2026</span>';\n  }else{\n    base='■ Bouclier tarifaire TotalEnergies : <b>1,99 €/L TTC</b> depuis mars 2023';\n  }\n  if(meta&&meta.current_active&&meta.current_active_since){\n    const d=new Date(meta.current_active_since+'T12:00:00');\n    base+=' · <b>Actuellement contraignant depuis le '+d.toLocaleDateString('fr-FR',{day:'numeric',month:'long',year:'numeric'})+'</b>';\n  }\n  bi.innerHTML=base;\n}\n'''
if old not in s:
    raise SystemExit('bouclier info block not found')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
