from pathlib import Path
p=Path('index.html')
s=p.read_text(encoding='utf-8')
old="return meta&&Array.isArray(meta.ranges)?meta.ranges:(BOUCLIER[ck]||[]);"
new="return meta&&Array.isArray(meta.ranges)?meta.ranges:[];"
if old not in s:
    raise SystemExit('dynamic bouclier fallback anchor not found')
s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
