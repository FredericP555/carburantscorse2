from datetime import date, datetime
from pathlib import Path
import json
import tempfile
import unittest
from carburantscorse2 import reliability_policy_v2 as p
from carburantscorse2 import rotterdam_calibration_v2 as rc
D=date(2026,8,19)

class T(unittest.TestCase):
 def ev(self, **k):
  a=dict(day=D,region_kind='corsica',target_fuel='SP95',last_declared_at=datetime(2026,3,1),last_price=1.99)
  a.update(k); return p.evaluate(**a)
 def test_45(self):
  self.assertTrue(self.ev(last_declared_at=datetime(2026,7,6)).eligible)
  self.assertFalse(self.ev(last_declared_at=datetime(2026,7,5)).eligible)
 def test_corse_cross_liveness(self):
  self.assertTrue(self.ev(is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=True,activity_by_fuel={'Gazole':datetime(2026,8,10)}).eligible)
 def test_mainland_any_fuel(self):
  self.assertTrue(self.ev(region_kind='mainland',is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=True,activity_by_fuel={'E10':datetime(2026,8,18)}).eligible)
 def test_double_cap_rotterdam(self):
  self.assertTrue(self.ev(is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=True,gazole_price=2.25,gazole_cap=2.25,sp95_price=1.99,sp95_cap=1.99,rotterdam_gazole_constraining=True).eligible)
 def test_no_resurrection(self):
  self.assertFalse(self.ev(is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=False,activity_by_fuel={'Gazole':datetime(2026,8,18)}).eligible)
 def test_inactive_overrides(self):
  self.assertFalse(self.ev(independently_inactive=True,is_total=True,shield_effective=True,applicable_cap=1.99,eligible_at_cap_entry=True,gazole_price=2.25,gazole_cap=2.25,sp95_price=1.99,sp95_cap=1.99,rotterdam_gazole_constraining=True).eligible)

class RotterdamCalibrationT(unittest.TestCase):
 def observed_file(self):
  rows=[('2026-04-03',1.037),('2026-04-06',1.048),('2026-04-07',1.061),('2026-05-20',0.868),('2026-05-21',0.865),('2026-05-22',0.859)]
  tmp=tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='',delete=False,suffix='.csv')
  tmp.write('date,rotterdam_eur_l\n')
  for d,v in rows: tmp.write(f'{d},{v}\n')
  tmp.close(); self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True)); return tmp.name
 def meta_file(self):
  payload={'rotterdam':{'corsica_calibration':{'territory':'corsica','entry_date':'2026-04-08','r1_observation_count':3,'r1':1.0486666666666666,'k':0.7329942783728567,'r2':0.7686666666666667,'r1_source_dates':['2026-04-03','2026-04-06','2026-04-07'],'exit_source_dates':['2026-05-29','2026-06-01','2026-06-02']}}}
  tmp=tempfile.NamedTemporaryFile('w',encoding='utf-8',delete=False,suffix='.json')
  json.dump(payload,tmp); tmp.close(); self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True)); return tmp.name
 def test_corse_is_consumed_from_c1_metadata(self):
  c=rc.calibrate_2026('corsica',self.observed_file(),self.meta_file())
  self.assertEqual(c.r1_source_dates,(date(2026,4,3),date(2026,4,6),date(2026,4,7)))
  self.assertAlmostEqual(c.k,0.7329942784,places=9)
  self.assertAlmostEqual(c.r2,0.7686666667,places=9)
 def test_bdr_is_derived_from_shared_observed_csv(self):
  bdr=rc.calibrate_2026('bdr',self.observed_file(),self.meta_file())
  self.assertAlmostEqual(bdr.r1,1.0486666667,places=9)
  self.assertAlmostEqual(bdr.k,0.8239033694,places=9)
 def test_missing_c1_corse_metadata_fails_closed(self):
  tmp=tempfile.NamedTemporaryFile('w',encoding='utf-8',delete=False,suffix='.json')
  json.dump({},tmp); tmp.close(); self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
  with self.assertRaises(ValueError): rc.calibrate_2026('corsica',self.observed_file(),tmp.name)

if __name__=='__main__': unittest.main()
