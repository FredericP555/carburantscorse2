#!/usr/bin/env python3
"""Targeted diagnostic of monthly station-day eligibility for one Corsican EPCI.

This is an internal audit tool only. It rebuilds the same C2 V2 station-day state used by
``build_monthly_territorial.py`` and records, station by station, the exact V2 eligibility
reason returned by the production reliability policy. It does not modify C2 data.json.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2 import reliability_policy_v2
from carburantscorse2.publication import build_publication_state, load_bdr_categories
from scripts.build_monthly_territorial import load_c2_reference, load_geography, month_bounds
from scripts.build_v2_production_candidate import (
    BDR_REGISTRY,
    C1_META,
    C1_TAG,
    CORSE_REGISTRY,
    LEGACY_BDR,
    SWITCH_DAY,
    _bdr_category_resolver,
    _candidate_stale_bdr_ids,
    _evaluate_v2,
    _resolve_bdr,
    _resolve_stale_bdr_candidates,
)
from scripts.resolve_new_bdr_station_brands import load_registry
from scripts.v2_event_guards import EventGuards

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--month", required=True)
    p.add_argument("--epci-siren", required=True)
    p.add_argument("--fuel", choices=("Gazole", "SP95"), required=True)
    p.add_argument("--geography", default="config/corse_station_geography_2026.csv")
    p.add_argument("--c2-data", default="data.json")
    p.add_argument("--release-tag")
    p.add_argument("--tag-prefix", default="a4c-v2-shared-")
    p.add_argument("--output", required=True)
    p.add_argument("--markdown")
    return p.parse_args()


def _compress_days(rows: list[dict]) -> list[dict]:
    if not rows:
        return []
    rows = sorted(rows, key=lambda r: r["date"])
    out: list[dict] = []
    current = {
        "start": rows[0]["date"],
        "end": rows[0]["date"],
        "eligible": rows[0]["eligible"],
        "reason": rows[0]["reason"],
    }
    previous = date.fromisoformat(rows[0]["date"])
    for row in rows[1:]:
        day = date.fromisoformat(row["date"])
        contiguous = (day - previous).days == 1
        same = row["eligible"] == current["eligible"] and row["reason"] == current["reason"]
        if contiguous and same:
            current["end"] = row["date"]
        else:
            out.append(current)
            current = {
                "start": row["date"],
                "end": row["date"],
                "eligible": row["eligible"],
                "reason": row["reason"],
            }
        previous = day
    out.append(current)
    return out


def main() -> None:
    args = parse_args()
    start, end = month_bounds(args.month)
    if end >= pd.Timestamp(date.today()):
        raise RuntimeError("Requested month is not complete")
    if start.date() < SWITCH_DAY:
        raise RuntimeError("This diagnostic is intended for C2 V2 months from 2026-07-23 onward")

    geo = load_geography(ROOT / args.geography)
    target_geo = geo[geo["epci_siren"].astype(str) == str(args.epci_siren)].copy()
    if target_geo.empty:
        raise RuntimeError(f"No geography rows for EPCI {args.epci_siren}")

    c2_path = Path(args.c2_data)
    if not c2_path.is_absolute():
        c2_path = ROOT / c2_path
    c2_meta, c2_release_tag = load_c2_reference(c2_path, end)
    release_tag = args.release_tag or c2_release_tag
    if release_tag != c2_release_tag:
        raise RuntimeError("Explicit C1 release does not match the release pinned by C2")

    download_shared_rotterdam_assets(
        ROOT / "outputs" / "ufip",
        tag_prefix=args.tag_prefix,
        release_tag=release_tag,
        registry_output=CORSE_REGISTRY,
        tag_output=C1_TAG,
    )
    c1_meta = json.loads(C1_META.read_text(encoding="utf-8"))
    years = sorted(int(y) for y in c1_meta.get("years", []))
    observations, source = load_shared_observations(
        years,
        tag_prefix=args.tag_prefix,
        release_tag=release_tag,
    )
    bouclier = source.get("bouclier") or c1_meta.get("bouclier")
    if not isinstance(bouclier, dict):
        raise RuntimeError("Pinned C1 release has no shield metadata")

    legacy = load_bdr_categories(LEGACY_BDR)
    _resolve_bdr(observations, legacy)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    base_state = build_publication_state(
        pd.DataFrame(observations), global_end=end, bdr_category_resolver=resolver
    )
    stale_ids = _candidate_stale_bdr_ids(base_state, bouclier, SWITCH_DAY, end.date())
    _resolve_stale_bdr_candidates(observations, stale_ids, legacy)
    registry = load_registry(BDR_REGISTRY)
    resolver = _bdr_category_resolver(legacy, registry)
    base_state = build_publication_state(
        pd.DataFrame(observations), global_end=end, bdr_category_resolver=resolver
    )

    guards = EventGuards.from_release(release_tag, metadata=c1_meta)
    corse_payload = json.loads(CORSE_REGISTRY.read_text(encoding="utf-8"))
    corse_stations = corse_payload.get("stations") or {}

    obs_df = pd.DataFrame(observations)
    obs_df["station_id"] = obs_df["station_id"].astype(str)
    obs_df["fuel"] = obs_df["fuel"].astype(str)
    obs_df["date"] = pd.to_datetime(obs_df["date"]).dt.normalize()

    station_results: list[dict] = []
    for geo_row in target_geo.sort_values(["commune", "localite", "station_id"]).itertuples(index=False):
        sid = str(geo_row.station_id)
        station_state = base_state[
            (base_state["station_id"].astype(str) == sid)
            & (base_state["date"] >= start)
            & (base_state["date"] <= end)
        ].copy()

        captured: list[dict] = []
        original_evaluate = reliability_policy_v2.evaluate

        def recording_evaluate(**kwargs):
            decision = original_evaluate(**kwargs)
            captured.append({
                "date": kwargs["day"].isoformat(),
                "fuel": str(kwargs["target_fuel"]),
                "eligible": bool(decision.eligible),
                "reason": str(decision.reason),
                "age_days": decision.age_days,
                "last_declared_at": None if kwargs.get("last_declared_at") is None else kwargs["last_declared_at"].isoformat(),
                "price_eur_l": None if kwargs.get("last_price") is None else float(kwargs["last_price"]),
                "is_total": bool(kwargs.get("is_total")),
                "shield_effective": bool(kwargs.get("shield_effective")),
                "applicable_cap": kwargs.get("applicable_cap"),
            })
            return decision

        if not station_state.empty:
            with patch.object(reliability_policy_v2, "evaluate", side_effect=recording_evaluate):
                evaluated, _ = _evaluate_v2(
                    station_state,
                    bouclier=bouclier,
                    event_guards=guards,
                    corse_stations=corse_stations,
                    start=start.date(),
                    end=end.date(),
                )
        else:
            evaluated = station_state

        decisions = [r for r in captured if r["fuel"] == args.fuel]
        eligible_days = sum(1 for r in decisions if r["eligible"])
        reason_counts = Counter(r["reason"] for r in decisions)
        month_decls = obs_df[
            (obs_df["station_id"] == sid)
            & (obs_df["fuel"] == args.fuel)
            & (obs_df["date"] >= start)
            & (obs_df["date"] <= end)
        ]
        all_fuel_obs = obs_df[(obs_df["station_id"] == sid) & (obs_df["fuel"] == args.fuel)]
        ever_sells = not all_fuel_obs.empty
        first_decl = None if all_fuel_obs.empty else all_fuel_obs["date"].min().strftime("%Y-%m-%d")
        last_decl = None if all_fuel_obs.empty else all_fuel_obs["date"].max().strftime("%Y-%m-%d")

        final_rows = evaluated[(evaluated["fuel"] == args.fuel)].copy() if not evaluated.empty else evaluated
        if not final_rows.empty and len(final_rows) != len(decisions):
            raise RuntimeError(f"Decision capture mismatch for station {sid}")
        if not final_rows.empty:
            expected = [bool(v) for v in final_rows.sort_values("date")["eligible_publication"].tolist()]
            actual = [bool(r["eligible"]) for r in sorted(decisions, key=lambda r: r["date"])]
            if expected != actual:
                raise RuntimeError(f"Eligibility audit mismatch for station {sid}")

        station_results.append({
            "station_id": sid,
            "localite": str(geo_row.localite),
            "commune": str(geo_row.commune),
            "address": str(geo_row.adresse_source),
            "fuel_present_in_source": ever_sells,
            "first_source_declaration": first_decl,
            "last_source_declaration": last_decl,
            "declarations_in_month": int(len(month_decls)),
            "days_evaluated": len(decisions),
            "eligible_days": eligible_days,
            "excluded_days": len(decisions) - eligible_days,
            "eligibility_ratio": None if not decisions else round(eligible_days / len(decisions), 4),
            "reason_counts": dict(sorted(reason_counts.items())),
            "intervals": _compress_days(decisions),
            "daily": decisions,
        })

    output = {
        "meta": {
            "schema": "a4c-monthly-epci-station-audit-v1",
            "month": args.month,
            "fuel": args.fuel,
            "epci_siren": str(args.epci_siren),
            "epci_nom": str(target_geo.iloc[0]["epci_nom"]),
            "c1_release_tag": release_tag,
            "c2_reference_daily_target_end": c2_meta.get("daily_target_end"),
            "c2_engine": "A4C-V2-2026-07-23",
            "source_max_date": str(source.get("shared_source_max_date")),
            "station_count_registry": int(len(target_geo)),
        },
        "stations": station_results,
    }
    output_path = ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# Audit {output['meta']['epci_nom']} — {args.fuel} — {args.month}",
        "",
        f"Moteur : {output['meta']['c2_engine']} ; C1 : {release_tag}.",
        "",
        "| Station | Localité | Vend ce carburant | Déclarations dans le mois | Jours retenus | Jours exclus | Motifs |",
        "|---|---|:---:|---:|---:|---:|---|",
    ]
    for row in station_results:
        reasons = ", ".join(f"{k}: {v}" for k, v in row["reason_counts"].items()) or "—"
        lines.append(
            f"| {row['station_id']} | {row['localite']} | {'oui' if row['fuel_present_in_source'] else 'non'} | "
            f"{row['declarations_in_month']} | {row['eligible_days']} | {row['excluded_days']} | {reasons} |"
        )
        for interval in row["intervals"]:
            status = "retenu" if interval["eligible"] else "exclu"
            lines.append(
                f"<!-- {row['station_id']} {interval['start']}..{interval['end']} {status}: {interval['reason']} -->"
            )
    markdown = "\n".join(lines) + "\n"
    if args.markdown:
        md_path = ROOT / args.markdown
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
