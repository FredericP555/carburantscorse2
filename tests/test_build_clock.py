from __future__ import annotations

from datetime import datetime, timezone
import unittest

from scripts.build_append_candidate import default_requested_end


class BuildClockTests(unittest.TestCase):
    def test_default_end_uses_paris_date_after_utc_midnight_boundary(self):
        # 18 Aug 23:35 UTC is already 19 Aug 01:35 in Paris (CEST): yesterday is Aug 18.
        now = datetime(2026, 8, 18, 23, 35, tzinfo=timezone.utc)
        self.assertEqual(default_requested_end(now).strftime("%Y-%m-%d"), "2026-08-18")

    def test_default_end_uses_paris_clock_in_winter_too(self):
        # 4 Jan 23:30 UTC is 5 Jan 00:30 in Paris (CET): yesterday is Jan 4.
        now = datetime(2026, 1, 4, 23, 30, tzinfo=timezone.utc)
        self.assertEqual(default_requested_end(now).strftime("%Y-%m-%d"), "2026-01-04")


if __name__ == "__main__":
    unittest.main()
