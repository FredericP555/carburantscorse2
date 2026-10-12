"""Browser-side C2 margin commentary tested against real published series."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


NODE_TEST = r"""
const fs=require('fs');
const vm=require('vm');
const assert=require('assert');
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
let text=generate();
for (const token of [
  'UN ÉCART DE MARGE QUI S\'EST CREUSÉ',
  '+13,8 c€/L en 2022',
  '+20,9 c€/L en 2025',
  '+16,4 à +20,8 c€/L',
  '+25,4 c€/L',
  '+56,4 c€/L',
  '15 juin 2026',
  '+8,19 c€/L',
  '+6,76 c€/L',
  'en hausse de 2,21 c€/L',
  'en hausse de 2,41 c€/L',
  '28 septembre 2026',
  '2 octobre 2026',
  'bénéfice net'
])assert(text.includes(token),token);
assert(!text.includes('leur marge réelle est donc probablement supérieure'));
assert.strictEqual(JSON.stringify(context.MARGES_GZ),original);
const old=context.MARGES_GZ;
context.MARGES_GZ={all:[],reseau:[]};
assert.strictEqual(generate(),'fallback');
context.MARGES_GZ={
  all:[...old.all,{date:'2026-10-12',ecart:7,corse:37,bdr:30}],
  reseau:[...old.reseau,{date:'2026-10-05',ecart:6.5,corse:37,bdr:30.5}]
};
text=generate();
assert(text.includes('ne permettent pas encore de calculer une évolution hebdomadaire'));
context.MARGES_GZ={all:[...old.all],reseau:[...old.reseau]};
for(let i=0;i<13;i++){
  const date=new Date(Date.UTC(2026,9,5+i*7)).toISOString().slice(0,10);
  for(const key of ['all','reseau'])context.MARGES_GZ[key].push({date,ecart:11,corse:39,bdr:28});
}
context.MARGES_GZ.all.push({date:'2027-01-04',ecart:10,corse:38,bdr:28});
context.MARGES_GZ.reseau.push({date:'2027-01-04',ecart:8,corse:38,bdr:30});
text=generate();
assert(text.includes('+13,8 c€/L en 2022'));
assert(text.includes('+20,9 c€/L en 2025'));
assert(text.includes('En 2026, l\'écart annuel observé'));
assert(text.includes('influencée par le bouclier'));
console.log('C2 margin editorial runtime: live 2026, incomplete weeks, 2027 rollover, source immutability OK');
"""


class MarginEditorialRuntimeTests(unittest.TestCase):
    def test_live_data_and_rollover(self):
        if not shutil.which("node"):
            self.skipTest("Node unavailable")
        result = subprocess.run(
            ["node", "-e", NODE_TEST],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
