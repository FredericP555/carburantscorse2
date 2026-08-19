from pathlib import Path

p = Path('index.html')
s = p.read_text(encoding='utf-8')

# 1) Desktop/mobile timeline information blocks, mirroring c1 semantics.
old = '''<div id="periode-slider" style="display:none">'''
new = '''<div id="bouclier-info" style="flex-shrink:0;background:#fff;border-bottom:1px solid #e2e8f0;padding:5px 14px;font-size:0.67rem;color:rgba(180,130,0,0.95);line-height:1.5"></div>\n<div id="periode-slider" style="display:none">'''
if old not in s:
    raise SystemExit('period slider anchor not found')
s = s.replace(old, new, 1)

old = '''</div>\n<div id="stats-bar">'''
new = '''</div>\n<div id="legende-events-mobile" style="display:none;flex-shrink:0;background:#fff;border-top:1px solid #e2e8f0;padding:5px 12px;font-size:0.62rem;color:#64748b;line-height:1.7">\n  <span style="color:rgba(220,38,38,0.85);font-weight:bold">─ ─</span> Invasion Ukraine (fév. 2022) &nbsp;\n  <span style="color:rgba(14,116,144,0.85);font-weight:bold">─ ─</span> Sanctions Autorité concurrence (nov. 2025) &nbsp;\n  <span style="color:rgba(124,58,237,0.85);font-weight:bold">─ ─</span> Guerre d'Iran (fév. 2026)\n</div>\n<div id="stats-bar">'''
if old not in s:
    raise SystemExit('stats anchor not found')
s = s.replace(old, new, 1)

# 2) Mobile event legend, exactly as c1: lines stay on chart, text moves below.
old = '''  #legend{gap:6px}\n}'''
new = '''  #legend{gap:6px}\n}\n@media (max-width:700px){#legende-events-mobile{display:block!important}}'''
if old not in s:
    raise SystemExit('mobile css anchor not found')
s = s.replace(old, new, 1)

# 3) Match c1 event rendering: labels from top down on desktop; line only on mobile.
old = '''    afterDraw(c){\n      const{ctx,chartArea:{top,bottom,left,right},scales:{x}}=c;\n      EVENTS.forEach(ev=>{\n        const et=new Date(ev.date).getTime();\n        if(et<minTs||et>maxTs)return;\n        const xp=x.getPixelForValue(et);\n        ctx.save();ctx.strokeStyle=ev.color;ctx.lineWidth=1.5;ctx.setLineDash([4,3]);\n        ctx.beginPath();ctx.moveTo(xp,top);ctx.lineTo(xp,bottom);ctx.stroke();\n        ctx.fillStyle=ev.color;ctx.font='bold 10px system-ui';ctx.textAlign='left';\n        // Label dans les limites du graphique\n        const maxY=bottom-10;\n        ctx.translate(xp+3, bottom-4);\n        ctx.rotate(-Math.PI/2);ctx.fillText(ev.label,0,0);ctx.restore();\n      });\n    }'''
new = '''    afterDraw(c){\n      const{ctx,chartArea:{top,bottom,left,right},scales:{x}}=c;\n      const isMobile=window.innerWidth<700;\n      EVENTS.forEach(ev=>{\n        const et=new Date(ev.date).getTime();\n        if(et<minTs||et>maxTs)return;\n        const xp=x.getPixelForValue(et);\n        if(xp<left||xp>right)return;\n        ctx.save();\n        ctx.beginPath();ctx.rect(left,top,right-left,bottom-top);ctx.clip();\n        ctx.beginPath();ctx.strokeStyle=ev.color;ctx.lineWidth=1.5;ctx.setLineDash([5,4]);\n        ctx.moveTo(xp,top);ctx.lineTo(xp,bottom);ctx.stroke();ctx.setLineDash([]);\n        if(!isMobile){\n          ctx.fillStyle=ev.color;ctx.font='bold 11px system-ui';ctx.textAlign='left';ctx.textBaseline='top';\n          ctx.translate(xp+3,top+20);ctx.rotate(Math.PI/2);ctx.fillText(ev.label,0,0);\n        }\n        ctx.restore();\n      });\n    }'''
if old not in s:
    raise SystemExit('legacy event draw block not found')
s = s.replace(old, new, 1)

# 4) Annual time markers, same semantic landmarks as c1 (Jan each year;
#    first Monday of Jan for weekly series).
old = '''function setStats(px,raw){'''
new = '''function buildAnnualTicks(minTs,maxTs){\n  const out=[];\n  const y0=new Date(minTs).getFullYear(),y1=new Date(maxTs).getFullYear();\n  const weekly=currentGran==='weekly'||(currentCarbu==='gazole'&&currentVue==='marge');\n  for(let y=y0;y<=y1;y++){\n    const d=new Date(y,0,1);\n    if(weekly){while(d.getDay()!==1)d.setDate(d.getDate()+1);}\n    const v=d.getTime();\n    if(v>=minTs&&v<=maxTs)out.push({value:v});\n  }\n  return out;\n}\nfunction formatAnnualTick(v){\n  const d=new Date(v);\n  return 'jan '+String(d.getFullYear()).slice(2);\n}\n\nfunction setStats(px,raw){'''
if old not in s:
    raise SystemExit('setStats anchor not found')
s = s.replace(old, new, 1)

old = '''        x:{type:'linear',min:minTs,max:maxTs,\n          grid:{color:'rgba(0,0,0,0.04)'},\n          ticks:{color:'#94a3b8',font:{size:9},maxTicksLimit:window.innerWidth<700?6:14,\n            callback:function(v){return new Date(v).toLocaleDateString('fr-FR',{month:'short',year:'numeric'});}\n          }\n        },'''
new = '''        x:{type:'linear',min:minTs,max:maxTs,\n          afterBuildTicks:function(scale){const yrs=buildAnnualTicks(minTs,maxTs);if(yrs.length)scale.ticks=yrs;},\n          grid:{color:'rgba(0,0,0,0.04)'},\n          ticks:{color:'#94a3b8',font:{size:9},autoSkip:false,maxRotation:0,\n            callback:function(v){return formatAnnualTick(v);}\n          }\n        },'''
if old not in s:
    raise SystemExit('x axis block not found')
s = s.replace(old, new, 1)

# 5) Full Total price-cap policy periods (not just active/constraint windows).
old = '''function buildCharts(){'''
new = '''function updateBouclierInfo(){\n  const bi=document.getElementById('bouclier-info');if(!bi)return;\n  if(currentCarbu==='gazole'){\n    bi.innerHTML='■ Bouclier tarifaire TotalEnergies : <b>1,99 €/L TTC</b> d’août 2023 au 19 mars 2026 · <b>2,09 €/L TTC</b> du 20 mars au 7 avr. 2026 · <b>2,25 €/L TTC</b> depuis le 8 avr. 2026 <span style="color:rgba(234,88,12,0.85)">· Promo 2,09 €/L les ponts de mai 2026</span>';\n  }else{\n    bi.innerHTML='■ Bouclier tarifaire TotalEnergies : <b>1,99 €/L TTC</b> depuis mars 2023';\n  }\n}\n\nfunction buildCharts(){'''
if old not in s:
    raise SystemExit('buildCharts anchor not found')
s = s.replace(old, new, 1)

old = '''function buildCharts(){\n  const ref=currentCarbu==='gazole'?'sp95':currentRef;'''
new = '''function buildCharts(){\n  updateBouclierInfo();\n  const ref=currentCarbu==='gazole'?'sp95':currentRef;'''
if old not in s:
    raise SystemExit('buildCharts body anchor not found')
s = s.replace(old, new, 1)

p.write_text(s,encoding='utf-8')
