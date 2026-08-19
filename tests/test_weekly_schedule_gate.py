from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "update-weekly.yml").read_text(encoding="utf-8")


class WeeklyScheduleGateTests(unittest.TestCase):
    def test_dst_crons_share_the_same_minute(self):
        crons = re.findall(r"- cron: '(\d+) (\d+) \* \* 1'", WORKFLOW)
        self.assertEqual(len(crons), 2)
        minutes = {int(minute) for minute, _hour in crons}
        hours = {int(hour) for _minute, hour in crons}
        self.assertEqual(len(minutes), 1, "Both DST cron slots must use the same minute")
        self.assertEqual(hours, {5, 6}, "Expected the two UTC hours covering 07:xx Europe/Paris")

        label = re.search(r"name: Select the 07:(\d{2}) Europe/Paris slot", WORKFLOW)
        self.assertIsNotNone(label)
        self.assertEqual(int(label.group(1)), next(iter(minutes)), "Step label and cron minute must stay aligned")

    def test_gate_selects_only_the_matching_utc_hour(self):
        self.assertIn("scheduled_hour = int(parts[1])", WORKFLOW)
        self.assertIn("run = scheduled_hour == expected_utc_hour", WORKFLOW)
        self.assertNotIn("scheduled_minute", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
