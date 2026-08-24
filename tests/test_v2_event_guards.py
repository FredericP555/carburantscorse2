from datetime import date
import unittest

from scripts.v2_event_guards import EventGuards


META = {"schema": "a4c-official-13-20-events-v1", "asset": "official_13_20_events.csv.gz"}


def event(kind, *, sid="1", fuel="Gazole", start="2026-01-01T08:00:00", end=""):
    return {
        "station_id": sid,
        "department": "20",
        "event_kind": kind,
        "fuel": fuel if kind == "rupture" else "",
        "event_type": "temporaire",
        "started_at": start,
        "ended_at": end,
        "start_date": start[:10],
        "end_date": end[:10] if end else "",
    }


def obs(sid="1", fuel="Gazole", ts="2026-01-03T10:00:00"):
    return {"station_id": sid, "fuel": fuel, "timestamp": ts}


class EventGuardReopeningTest(unittest.TestCase):
    def guards(self, rows):
        return EventGuards(rows, release_tag="test", metadata=META)

    def test_open_rupture_closes_on_later_same_fuel_price(self):
        g = self.guards([event("rupture")])
        g.bind_observations([obs(ts="2026-01-03T10:00:00")])
        self.assertTrue(g.rupture_active("1", "Gazole", date(2026, 1, 2)))
        self.assertFalse(g.rupture_active("1", "Gazole", date(2026, 1, 3)))
        self.assertEqual(g.audit()["reopening_stats"]["rupture_open_closed_by_declaration"], 1)

    def test_other_fuel_does_not_close_open_rupture(self):
        g = self.guards([event("rupture")])
        g.bind_observations([obs(fuel="SP95", ts="2026-01-03T10:00:00")])
        self.assertTrue(g.rupture_active("1", "Gazole", date(2026, 1, 4)))

    def test_open_closure_closes_on_any_later_price(self):
        g = self.guards([event("fermeture")])
        g.bind_observations([obs(fuel="SP95", ts="2026-01-03T10:00:00")])
        self.assertTrue(g.independently_inactive("1", date(2026, 1, 2)))
        self.assertFalse(g.independently_inactive("1", date(2026, 1, 3)))
        self.assertEqual(g.audit()["reopening_stats"]["closure_open_closed_by_declaration"], 1)

    def test_explicit_end_has_priority_over_price_declaration(self):
        g = self.guards([event("rupture", end="2026-01-05T23:59:00")])
        g.bind_observations([obs(ts="2026-01-03T10:00:00")])
        self.assertTrue(g.rupture_active("1", "Gazole", date(2026, 1, 4)))
        self.assertFalse(g.rupture_active("1", "Gazole", date(2026, 1, 6)))
        self.assertEqual(g.audit()["reopening_stats"]["rupture_explicit_end"], 1)

    def test_same_day_later_declaration_reopens_for_daily_state(self):
        g = self.guards([event("rupture", start="2026-01-03T08:00:00")])
        g.bind_observations([obs(ts="2026-01-03T10:00:00")])
        self.assertFalse(g.rupture_active("1", "Gazole", date(2026, 1, 3)))
        stats = g.audit()["reopening_stats"]
        self.assertEqual(stats["rupture_same_day_reopen"], 1)
        self.assertEqual(stats["rupture_effectively_empty_after_reopen"], 1)


if __name__ == "__main__":
    unittest.main()
