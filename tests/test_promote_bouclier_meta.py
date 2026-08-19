from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def payload(bouclier):
    rows=[{"date":"2026-08-18","ecart":1.0}]
    return {
        "meta": {
            "publication_mode":"append-only",
            "official_source_max_date":"2026-08-18",
            "daily_target_end":"2026-08-18",
            "weekly_complete_through":"2026-08-16",
            "bouclier":bouclier,
        },
        "DATA":{"gazole":{"sp95":{"daily":{"all":rows,"reseau":rows},"weekly":{"all":rows,"reseau":rows}}}},
        "MARGES_GZ":{"all":rows,"reseau":rows},
    }


class PromoteBouclierMetaTests(unittest.TestCase):
    def run_promote(self, baseline, candidate, summary):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            target=td/'data.json'; cand=td/'candidate.json'; summ=td/'summary.json'
            target.write_text(json.dumps(baseline),encoding='utf-8')
            cand.write_text(json.dumps(candidate),encoding='utf-8')
            summ.write_text(json.dumps(summary),encoding='utf-8')
            proc=subprocess.run([
                sys.executable,'-m','scripts.promote_candidate',
                '--candidate',str(cand),'--summary',str(summ),'--target',str(target)
            ],capture_output=True,text=True,check=True)
            return json.loads(target.read_text(encoding='utf-8')),proc.stdout

    def test_promotes_bouclier_only_when_public_series_are_identical(self):
        old=payload(None)
        new=payload({"Gazole":{"current_active":True,"current_active_since":"2026-07-23"}})
        result,out=self.run_promote(old,new,{"blocking_unknown_bdr_station_count":0,"additions":{}})
        self.assertEqual(result['DATA'],old['DATA'])
        self.assertEqual(result['MARGES_GZ'],old['MARGES_GZ'])
        self.assertEqual(result['meta']['bouclier'],new['meta']['bouclier'])
        self.assertIn('bouclier metadata changed',out)

    def test_noop_when_neither_series_nor_bouclier_changed(self):
        old=payload({"Gazole":{"current_active":True}})
        new=payload({"Gazole":{"current_active":True}})
        result,out=self.run_promote(old,new,{"blocking_unknown_bdr_station_count":0,"additions":{}})
        self.assertEqual(result,old)
        self.assertIn('stays unchanged',out)


if __name__=='__main__':
    unittest.main()
