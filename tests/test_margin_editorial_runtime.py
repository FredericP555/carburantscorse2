"""C2 margin editorial regression: expectations follow the actual published series."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]

NODE_TEST = r"""
const fs=require('fs');
const vm=require('vm');
const assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
const start=html.indexOf('function editorialMean(rows,field,start,end)');
const end=html.indexOf('function syncDynamicPeriodLabels(){',start);
assert(start>0 && end>start);
const block=html.slice(start,end);
const data=JSON.parse(fs.readFileSync('data.json','utf8'));

const context={
  MARGES_GZ:data.MARGES_GZ,
  ANALYSE_MARGE_GZ:'fallback',
  window:{A4C_DATA_META:data.meta},
  getBouclierRanges:(fuel)=>data.meta?.bouclier?.[fuel]?.ranges||[]
};
vm.createContext(context);
vm.runInContext(block,context);
const generate=()=>vm.runInContext('buildMarginAnalysis()',context);
const original=JSON.stringify(context.MARGES_GZ);

const signed=(v,digits=1)=>(v>=0?'+':'−')+Math.abs(v).toFixed(digits).replace('.',',');
const plain=(v,digits=1)=>Math.abs(v).toFixed(digits).replace('.',',');
const mean=(rows,field,from,to)=>{
  const vals=rows.filter(r=>r.date>=from&&r.date<=to).map(r=>Number(r[field]));
  assert(vals.length>0,'missing source observations '+from+' to '+to);
  assert(vals.every(Number.isFinite));
  return vals.reduce((acc,v)=>acc+v,0)/vals.length;
};
const maxRow=(rows,field)=>rows.reduce((best,row)=>
  Number(row[field])>Number(best[field])?row:best);
const longDate=(iso)=>new Date(iso+'T12:00:00').toLocaleDateString(
  'fr-FR',{day:'numeric',month:'long',year:'numeric'});
const shiftWeek=(iso)=>new Date(Date.parse(iso+'T00:00:00Z')+7*86400000).toISOString().slice(0,10);
const changeText=(value)=>{
  if(Math.abs(value)<0.005)return 'stable';
  return value>0?'en hausse de '+plain(value,2)+' c€/L':'en baisse de '+plain(value,2)+' c€/L';
};

const all=data.MARGES_GZ.all,net=data.MARGES_GZ.reseau;
assert(all.length>100 && net.length>100,'real margin history must be available');
const latest=all.at(-1),previous=all.at(-2);
const netLatest=net.at(-1),netPrevious=net.at(-2);
assert.equal(latest.date,netLatest.date,'both populations must align');
assert.equal(previous.date,netPrevious.date,'preceding weeks must align');
assert.equal(shiftWeek(previous.date),latest.date,'weekly cadence must be consecutive');

let text=generate();
const dynamicChecks=[
  'UN ÉCART DE MARGE QUI S\'EST CREUSÉ',
  signed(mean(all,'ecart','2022-01-01','2022-12-31'))+' c€/L en 2022',
  signed(mean(all,'ecart','2025-01-01','2025-12-31'))+' c€/L en 2025',
  signed(mean(all,'ecart','2022-01-01','2022-08-31'))+
    ' à '+signed(mean(all,'ecart','2025-01-01','2025-08-31'))+' c€/L',
  signed(maxRow(all,'ecart').ecart)+' c€/L',
  signed(maxRow(all,'corse').corse)+' c€/L',
  longDate(maxRow(all,'ecart').date),
  longDate(maxRow(all,'corse').date),
  signed(latest.ecart,2)+' c€/L',
  signed(netLatest.ecart,2)+' c€/L',
  changeText(latest.ecart-previous.ecart),
  changeText(netLatest.ecart-netPrevious.ecart),
  longDate(latest.date),
  'bénéfice net'
];
if(data.meta?.ufip_last_observed_date){
  dynamicChecks.push(longDate(data.meta.ufip_last_observed_date));
}
for(const token of dynamicChecks)assert(text.includes(token),token);
assert(!text.includes('leur marge réelle est donc probablement supérieure'));
assert.equal(JSON.stringify(context.MARGES_GZ),original,'rendering changed the source');

// A normal weekly publication changes the commentary, not the test assertions.
const modified=JSON.parse(original);
modified.all.at(-1).ecart+=1.37;
modified.reseau.at(-1).ecart+=1.37;
context.MARGES_GZ=modified;
text=generate();
assert(text.includes(signed(latest.ecart+1.37,2)+' c€/L'));
assert(text.includes(signed(netLatest.ecart+1.37,2)+' c€/L'));
assert.equal(JSON.stringify(data.MARGES_GZ),original,'mutated the loaded source');

// Divergent weeks do not yield invented weekly variations.
context.MARGES_GZ={
  all:[...all],
  reseau:[...net.slice(0,-1),{...netLatest,date:shiftWeek(netLatest.date)}]
};
text=generate();
assert(text.includes('ne permettent pas encore de calculer une évolution hebdomadaire'));

// Missing margins use the safe fallback.
context.MARGES_GZ={all:[],reseau:[]};
assert.equal(generate(),'fallback');

// Synthetic complete 2026 followed by Jan 2027; historical 2022–2025 unaffected.
const rollover={
  all:all.filter(r=>r.date<'2026-01-01').map(r=>({...r})),
  reseau:net.filter(r=>r.date<'2026-01-01').map(r=>({...r}))
};
for(let i=0;i<52;i++){
  const date=new Date(Date.UTC(2026,0,5+7*i)).toISOString().slice(0,10);
  rollover.all.push({date,ecart:11,corse:39,bdr:28});
  rollover.reseau.push({date,ecart:9,corse:39,bdr:30});
}
rollover.all.push({date:'2027-01-04',ecart:10,corse:38,bdr:28});
rollover.reseau.push({date:'2027-01-04',ecart:8,corse:38,bdr:30});
context.MARGES_GZ=rollover;
text=generate();
assert(text.includes(signed(mean(all,'ecart','2022-01-01','2022-12-31'))+' c€/L en 2022'));
assert(text.includes(signed(mean(all,'ecart','2025-01-01','2025-12-31'))+' c€/L en 2025'));
assert(text.includes('En 2026, l\'écart annuel observé'));
assert(text.includes('influencée par le bouclier'));
assert.equal(JSON.stringify(data.MARGES_GZ),original,'rollover scenario changed the source');
console.log('C2 margin editorial: live weeks/records, incomplete weeks, immutability, 2027 OK');
"""

class MarginEditorialRuntimeTests(unittest.TestCase):
    def test_live_data_and_rollover(self):
        if not shutil.which("node"):
            self.skipTest("Node unavailable")
        result=subprocess.run(
            ["node","-e",NODE_TEST],
            cwd=ROOT,capture_output=True,text=True,check=False,timeout=20,
        )
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

if __name__=="__main__":
    unittest.main()
