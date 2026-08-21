from datetime import date, datetime
import unittest
from carburantscorse2 import reliability_policy_v2 as p
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

if __name__=='__main__': unittest.main()
