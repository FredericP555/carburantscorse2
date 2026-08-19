from pathlib import Path
p=Path('index.html')
s=p.read_text(encoding='utf-8')
items=[
("La remise TotalEnergies de septembre–octobre 2022 (−20 c/L)","La remise TotalEnergies de −20 c/L du 1er septembre au 15 novembre 2022"),
("Le bouclier tarifaire Total n'a été réellement contraignant sur le Gazole qu'à partir de la crise iranienne de mars 2026 ; sur 2023–2025, les cours restaient sous le plafond.","Le bouclier tarifaire Total a été effectivement actif sur plusieurs fenêtres en 2023, puis de nouveau à partir de mars 2026 ; les zones jaunes du graphique reprennent ces périodes observées."),
("La remise TotalEnergies de septembre–octobre 2022, suivie par VITO","La remise TotalEnergies de −20 c/L du 1er septembre au 15 novembre 2022, suivie par VITO"),
]
for old,new in items:
    if old not in s: raise SystemExit('expected wording not found')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
