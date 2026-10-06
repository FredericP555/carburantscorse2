from datetime import date
from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]


class MonthlyUfipReadinessTests(unittest.TestCase):
    def test_last_weekday_same_day_for_weekday_month_end(self):
        from scripts.check_monthly_readiness import last_weekday_on_or_before

        self.assertEqual(last_weekday_on_or_before(date(2026, 9, 30)), date(2026, 9, 30))

    def test_last_weekday_moves_weekend_month_end_back_to_friday(self):
        from scripts.check_monthly_readiness import last_weekday_on_or_before

        self.assertEqual(last_weekday_on_or_before(date(2026, 10, 31)), date(2026, 10, 30))
        self.assertEqual(last_weekday_on_or_before(date(2026, 5, 31)), date(2026, 5, 29))

    def test_current_summary_covers_september_2026(self):
        from scripts.check_monthly_readiness import last_weekday_on_or_before

        summary = json.loads((ROOT / "homepage-summary.json").read_text(encoding="utf-8"))
        observed = date.fromisoformat(summary["source"]["ufip_last_observed_date"])
        required = last_weekday_on_or_before(date(2026, 9, 30))
        self.assertGreaterEqual(observed, required)

    def test_readiness_contract_contains_explicit_ufip_guard(self):
        source = (ROOT / "scripts" / "check_monthly_readiness.py").read_text(encoding="utf-8")
        self.assertIn('"ufip_covers_month_end"', source)
        self.assertIn('"ufip_last_observed_date"', source)
        self.assertIn('"ufip_required_through"', source)
        self.assertIn('source.get("ufip_last_observed_date")', source)


if __name__ == "__main__":
    unittest.main()
