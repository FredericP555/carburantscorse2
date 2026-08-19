#!/usr/bin/env python3
"""Build an append-only carburantscorse2 candidate from the live public sources.

Historical values already published are immutable. If ``data.json`` exists it is the
baseline; otherwise the first migration bootstraps from the DATA/MARGES_GZ constants in
``index.html``. Current annual government files may contain retrospective corrections,
but those corrections are never allowed to rewrite a date already present in the baseline.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import pandas as pd

from a4c_common.official_prices import download_annual_zip, iter_observations_from_zip
from a4c_common.shared_release import load_shared_observations
from a4c_common.ufip import expand_daily, fetch_rotterdam_gazole
from carburantscorse2.publication import (
    build_gap_series,
    build_publication_state,
    load_bdr_categories,
    unknown_recent_bdr_stations,
)
from carburantscorse2.publication_margin import build_margin_series

ROOT = Path(__file__).resolve().parents[1]
INITIAL_LEGACY_DAILY_CUTOFF = "2026-06-06"
PARIS_TZ = ZoneInfo("Europe/Paris")


def parse_js_object(name: str, html: str) -> dict:
    # ``index.html`` used const historically and now uses let so it can be replaced by
    # data.json at runtime. Accept both to keep the bootstrap path recoverable.
    match = re.search(rf"(?:const|let)\s+{re.escape(name)}=(.*?);\n", html, flags=re.S)
    if not match:
        raise RuntimeError(f"Cannot find {name} in index.html")
    raw = match.group(1)
    quoted = re.sub(r"([{,])\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', raw)
    return json.loads(quoted)


def load_baseline() -> tuple[dict, dict, dict, str]:
    data_path = ROOT / "data.json"
    if data_path.exists():
        obj = json.loads(data_path.read_text(encoding="utf-8"))
        if "DATA" not in obj or "MARGES_GZ" not in obj:
            raise RuntimeError("data.json must contain DATA and MARGES_GZ")
        return deepcopy(obj["DATA"]), deepcopy(obj["MARGES_GZ"]), dict(obj.get("meta", {})), "data.json"

    html = (ROOT / "index.html").read_text(encoding="utf-8")
    return parse_js_object("DATA", html), parse_js_object("MARGES_GZ", html), {}, "index.html"


def max_date(rows: list[dict]) -> pd.Timestamp:
    return pd.Timestamp(max(row["date"] for row in rows))


def append_new(existing: list[dict], generated: list[dict], *, complete_through: pd.Timestamp | None = None) -> tuple[list[dict], int]:
    last = max_date(existing)
    additions = []
    for row in generated:
        stamp = pd.Timestamp(row["date"])
        if stamp <= last:
            continue
        if complete_through is not None and stamp + pd.Timedelta(6, unit="D") > complete_through:
            continue
        additions.append(row)
    combined = existing + additions
    dates = [row["date"] for row in combined]
    if dates != sorted(dates) or len(dates) != len(set(dates)):
        raise AssertionError("Candidate series is not strictly chronological and unique")
    return combined, len(additions)


def last_complete_sunday(day: pd.Timestamp) -> pd.Timestamp:
    day = day.normalize()
    offset_days = int((day.weekday() + 1) % 7)
    return day - pd.Timedelta(offset_days, unit="D")


def default_requested_end(now: datetime | None = None) -> pd.Timestamp:
    """Return yesterday using the observatory's Europe/Paris publication clock."""
    if now is None:
        paris_now = datetime.now(PARIS_TZ)
    elif now.tzinfo is None:
        paris_now = now.replace(tzinfo=PARIS_TZ)
    else:
        paris_now = now.astimezone(PARIS_TZ)
    return pd.Timestamp(paris_now.date() - timedelta(days=1))


def official_year_window(
    requested_end: pd.Timestamp,
    *,
    run_day: pd.Timestamp | None = None,
) -> tuple[int, int]:
    """Return the two annual slices needed for publication around a year boundary.

    Normally this is requested-end N-1/N. On 1 January the scheduled run publishes through
    31 December of the previous year while c1 already exposes previous/current run years;
    use those two years so the shared snapshot remains compatible without downloading a
    third national archive.
    """
    day = pd.Timestamp(requested_end).normalize()
    if run_day is not None:
        run = pd.Timestamp(run_day).normalize()
        if run.year == day.year + 1 and run.month == 1 and run.day == 1:
            return day.year, run.year
    return day.year - 1, day.year


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--end", help="Requested last daily date YYYY-MM-DD; default yesterday in Europe/Paris. Publication is capped at source freshness.")
    parser.add_argument("--output", default="outputs/candidate-data.json")
    parser.add_argument("--summary", default="outputs/candidate-summary.json")
    parser.add_argument(
        "--official-source",
        choices=("auto", "shared", "direct"),
        default="shared",
        help=(
            "Official-price ingestion source. shared is the production default and fails closed; "
            "auto/direct are retained only for explicit diagnostic use."
        ),
    )
    return parser.parse_args()


def load_official_observations(years: tuple[int, int], mode: str) -> tuple[list[dict], dict]:
    """Load official observations without changing any c2 reliability/publication rule."""
    if mode in ("auto", "shared"):
        try:
            rows, source = load_shared_observations(years)
            print(
                "Using shared official snapshot "
                f"{source.get('release_tag')} ({source.get('shared_rows')} source rows; "
                f"max={source.get('shared_source_max_date')})"
            )
            return rows, source
        except Exception as exc:
            if mode == "shared":
                raise RuntimeError(f"Required shared official source is unavailable: {exc}") from exc
            print(f"Shared official source unavailable ({exc}); falling back to direct government ZIPs")

    observations: list[dict] = []
    for year in years:
        path = download_annual_zip(year)
        observations.extend(
            iter_observations_from_zip(
                path,
                source_year=year,
                departments=("13", "20"),
                fuels=("Gazole", "SP95", "E10"),
            )
        )
    return observations, {
        "kind": "direct-government",
        "years": list(years),
    }


def main() -> None:
    args = parse_args()
    if args.end:
        requested_end = pd.Timestamp(args.end).normalize()
        run_day = None
    else:
        paris_now = datetime.now(PARIS_TZ)
        requested_end = default_requested_end(paris_now)
        run_day = pd.Timestamp(paris_now.date())

    candidate_data, candidate_margins, baseline_meta, baseline_source = load_baseline()
    previous_daily_cutoff = max_date(candidate_data["gazole"]["sp95"]["daily"]["all"])
    initial_legacy_cutoff = baseline_meta.get("legacy_daily_cutoff", INITIAL_LEGACY_DAILY_CUTOFF)

    years = official_year_window(requested_end, run_day=run_day)
    observations, official_source = load_official_observations(years, args.official_source)
    obs = pd.DataFrame(observations)
    if obs.empty:
        raise RuntimeError("No official observations were parsed")
    source_max = pd.to_datetime(obs["date"]).max().normalize()

    # Never manufacture a publication day beyond the freshness of the official stock.
    target_end = min(requested_end, source_max)
    weekly_end = last_complete_sunday(target_end)
    if target_end < previous_daily_cutoff:
        raise RuntimeError(
            f"Official source is older than current publication baseline: source={target_end.date()} baseline={previous_daily_cutoff.date()}"
        )

    categories = load_bdr_categories(ROOT / "config" / "bdr_categories_published_2026-06-06.csv")
    state = build_publication_state(obs, global_end=target_end, bdr_categories=categories)
    first_unpublished = previous_daily_cutoff + pd.Timedelta(1, unit="D")
    unknown = unknown_recent_bdr_stations(state, since=first_unpublished)

    cases = [
        ("gazole", "sp95", "Gazole", "Gazole"),
        ("sp95", "sp95", "SP95", "SP95"),
        ("sp95", "e10", "SP95", "E10"),
    ]
    additions: dict[str, int] = {}
    for key, ref, corsica_fuel, bdr_fuel in cases:
        for scope, group in (("all", "all"), ("network", "reseau")):
            generated_daily = build_gap_series(
                state,
                corsica_fuel=corsica_fuel,
                bdr_fuel=bdr_fuel,
                bdr_scope=scope,
                granularity="daily",
            )
            path_key = f"{key}/{ref}/daily/{group}"
            combined, count = append_new(candidate_data[key][ref]["daily"][group], generated_daily)
            candidate_data[key][ref]["daily"][group] = combined
            additions[path_key] = count

            generated_weekly = build_gap_series(
                state,
                corsica_fuel=corsica_fuel,
                bdr_fuel=bdr_fuel,
                bdr_scope=scope,
                granularity="weekly",
            )
            path_key = f"{key}/{ref}/weekly/{group}"
            combined, count = append_new(
                candidate_data[key][ref]["weekly"][group],
                generated_weekly,
                complete_through=weekly_end,
            )
            candidate_data[key][ref]["weekly"][group] = combined
            additions[path_key] = count

    last_margin_period = max(max_date(candidate_margins["all"]), max_date(candidate_margins["reseau"]))
    first_new_margin_week = last_margin_period + pd.Timedelta(7, unit="D")
    if first_new_margin_week <= weekly_end:
        ufip_fetch_start = (first_new_margin_week - pd.Timedelta(14, unit="D")).date()
        ufip_fetch_end = weekly_end.date()
        observed_rotterdam = fetch_rotterdam_gazole(ufip_fetch_start, ufip_fetch_end)
        rotterdam = expand_daily(observed_rotterdam, ufip_fetch_start, ufip_fetch_end)
        margin_state = state[
            (state["date"] >= first_new_margin_week)
            & (state["date"] <= weekly_end)
        ].copy()
        for scope, group in (("all", "all"), ("network", "reseau")):
            generated = build_margin_series(margin_state, rotterdam, bdr_scope=scope)
            combined, count = append_new(candidate_margins[group], generated, complete_through=weekly_end)
            candidate_margins[group] = combined
            additions[f"margins/{group}"] = count
        ufip_last = None if observed_rotterdam.empty else str(pd.to_datetime(observed_rotterdam["date"]).max().date())
    else:
        additions["margins/all"] = additions["margins/reseau"] = 0
        ufip_last = baseline_meta.get("ufip_last_observed_date")

    output = {
        "meta": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "publication_mode": "append-only",
            "baseline_source": baseline_source,
            "previous_daily_cutoff": previous_daily_cutoff.strftime("%Y-%m-%d"),
            "requested_daily_target_end": requested_end.strftime("%Y-%m-%d"),
            "daily_target_end": target_end.strftime("%Y-%m-%d"),
            "weekly_complete_through": weekly_end.strftime("%Y-%m-%d"),
            "official_source_max_date": source_max.strftime("%Y-%m-%d"),
            "official_ingestion_source": official_source.get("kind"),
            "official_shared_release_tag": official_source.get("release_tag"),
            "official_shared_release_published_at": official_source.get("release_published_at"),
            "official_shared_sha256": official_source.get("sha256"),
            "official_shared_source_max_date": official_source.get("shared_source_max_date"),
            "bouclier": official_source.get("bouclier") or baseline_meta.get("bouclier"),
            "ufip_last_observed_date": ufip_last,
            "legacy_daily_cutoff": initial_legacy_cutoff,
            "unknown_recent_bdr_stations": unknown,
        },
        "DATA": candidate_data,
        "MARGES_GZ": candidate_margins,
    }

    summary = {
        **output["meta"],
        "additions": additions,
        "blocking_unknown_bdr_station_count": len(unknown),
        "last_dates": {
            "gazole_daily_all": candidate_data["gazole"]["sp95"]["daily"]["all"][-1]["date"],
            "gazole_weekly_all": candidate_data["gazole"]["sp95"]["weekly"]["all"][-1]["date"],
            "sp95_daily_all": candidate_data["sp95"]["sp95"]["daily"]["all"][-1]["date"],
            "margin_all": candidate_margins["all"][-1]["date"],
        },
    }

    out_path = ROOT / args.output
    summary_path = ROOT / args.summary
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if unknown:
        raise SystemExit(f"Unclassified recent BDR stations: {', '.join(unknown)}")


if __name__ == "__main__":
    main()
