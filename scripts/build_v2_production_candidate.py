#!/usr/bin/env python3
"""Build the production-shaped A4C V2 candidate from one pinned C1 release.

Initial activation performs the agreed controlled transition only:
- daily history before 2026-07-23 is byte-for-byte preserved at row level;
- the overlapping week 2026-07-20 is preserved;
- complete weekly series and Gazole margins switch from 2026-07-27;
- future runs are append-only once ``meta.v2.active`` is present.

The builder never writes data.json directly. Promotion is a separate guarded step.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import pandas as pd

from a4c_common.corse_brand import TOTAL, classify_registry_entry
from a4c_common.price_math import at_cap
from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2 import r2_guard_v2, reliability_policy_v2, shield_phase_v2
from carburantscorse2.publication import build_gap_series, build_publication_state, load_bdr_categories, unknown_recent_bdr_stations
from carburantscorse2.publication_margin import build_margin_series
from scripts.resolve_new_bdr_station_brands import DEFAULT_REGISTRY as BDR_REGISTRY, load_registry, resolve_from_observations, resolved_categories

ROOT = Path(__file__).resolve().parents[1]
PARIS = ZoneInfo("Europe/Paris")
SWITCH_DAY = date(2026, 7, 23)
WEEKLY_SWITCH = date(2026, 7, 27)
LEGACY_BDR = ROOT / "config" / "bdr_categories_published_2026-06-06.csv"
C1_META = ROOT / "outputs" / "ufip" / "c1_shared_meta.json"
C1_TAG = ROOT / "outputs" / "c1" / "shared_release_tag.txt"
CORSE_REGISTRY = ROOT / "outputs" / "c1" / "corse_station_brands.json"
ROTTERDAM_OBSERVED = ROOT / "outputs" / "ufip" / "rotterdam_gazole_observed.csv"
ROTTERDAM_DAILY = ROOT / "outputs" / "ufip" / "rotterdam_gazole_daily.csv"
PRINCIPAL_FUELS = {"Gazole", "SP95"}
ALL_FUELS = ("Gazole", "SP95", "E10")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--release-tag", required=True)
    p.add_argument("--tag-prefix", default="a4c-preprod-v2-")
    p.add_argument("--end")
    p.add_argument("--output", default="outputs/v2-production-candidate.json")
    p.add_argument("--summary", default="outputs/v2-production-summary.json")
    return p.parse_args()


def _as_datetime(value) -> datetime | None:
    if value is None or pd.isna(value): return None
    return pd.Timestamp(value).to_pydatetime()


def _as_float(value) -> float | None:
    if value is None or pd.isna(value): return None
    try: result = float(value)
    except (TypeError, ValueError): return None
    return result if math.isfinite(result) else None


def _norm_brand(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _is_total_brand(value: str | None) -> bool:
    normalized = _norm_brand(value)
    return normalized == "total" or normalized.startswith("totalenergies") or normalized.startswith("totalaccess")


def _default_end() -> date:
    return datetime.now(PARIS).date() - timedelta(days=1)


def _last_complete_sunday(day: date) -> date:
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _merged_bdr_categories() -> dict[str, str]:
    categories = load_bdr_categories(LEGACY_BDR)
    for sid, category in resolved_categories(load_registry(BDR_REGISTRY)).items():
        categories.setdefault(str(sid), category)
    return categories


def _recent_bdr_observations(observations: list[dict], days: int = 30) -> list[dict]:
    rows = [r for r in observations if str(r.get("department") or "") == "13" and not bool(r.get("is_motorway")) and str(r.get("pop") or "") != "A"]
    if not rows: return []
    latest = max(r["date"] for r in rows)
    cutoff = latest - timedelta(days=days)
    return [r for r in rows if r["date"] >= cutoff]


def _resolve_bdr(observations: list[dict], legacy: dict[str, str]) -> dict:
    recent_summary = resolve_from_observations(_recent_bdr_observations(observations), legacy, registry_path=BDR_REGISTRY)
    return {"recent": {k: v for k, v in recent_summary.items() if k != "categories"}}


def _candidate_stale_bdr_ids(state: pd.DataFrame, bouclier: dict, start: date, end: date) -> set[str]:
    ids: set[str] = set()
    subset = state[(state["department"].astype(str) == "13") & state["fuel"].isin(PRINCIPAL_FUELS) & (state["date"] >= pd.Timestamp(start)) & (state["date"] <= pd.Timestamp(end))]
    for row in subset.itertuples(index=False):
        last = _as_datetime(getattr(row, "source_timestamp", None))
        if last is None or (pd.Timestamp(row.date).date() - last.date()).days < reliability_policy_v2.NORMAL_MAX_AGE_DAYS: continue
        phase = shield_phase_v2.phase_for_day(bouclier, str(row.fuel), pd.Timestamp(row.date).date())
        if phase is not None and at_cap(_as_float(row.price), phase.cap): ids.add(str(row.station_id))
    return ids


def _resolve_stale_bdr_candidates(observations: list[dict], station_ids: set[str], legacy: dict[str, str]) -> dict:
    if not station_ids: return {"candidate_ids": 0, "resolved_this_run": 0, "unresolved_this_run": 0, "unresolved_ids": []}
    rows = [r for r in observations if str(r.get("department") or "") == "13" and str(r.get("station_id") or "") in station_ids]
    summary = resolve_from_observations(rows, legacy, registry_path=BDR_REGISTRY)
    return {"candidate_ids": len(station_ids), **{k: summary[k] for k in ("resolved_this_run", "unresolved_this_run", "unresolved_ids")}}


def _evaluate_v2(state: pd.DataFrame, *, bouclier: dict, event_guards, corse_stations: dict, start: date, end: date) -> tuple[pd.DataFrame, dict]:
    key_rows = {(str(r.station_id), pd.Timestamp(r.date).date(), str(r.fuel)): r for r in state.itertuples(index=False)}
    bdr_entries = (load_registry(BDR_REGISTRY).get("stations") or {})
    reasons = Counter(); reasons_by_territory = Counter(); r2_calls = r2_true = r2_false = r2_unavailable = 0; r2_errors = Counter()
    eligible = []
    phase_cache = {}
    def phase(fuel: str, day: date):
        key=(fuel,day)
        if key not in phase_cache: phase_cache[key]=shield_phase_v2.phase_for_day(bouclier,fuel,day)
        return phase_cache[key]

    for row in state.itertuples(index=False):
        day = pd.Timestamp(row.date).date(); sid=str(row.station_id); fuel=str(row.fuel); current=bool(row.eligible_publication)
        if day < start or day > end:
            eligible.append(current); continue
        last_declared=_as_datetime(getattr(row,"source_timestamp",None))
        activity={}
        for other_fuel in ALL_FUELS:
            other=key_rows.get((sid,day,other_fuel))
            if other is not None:
                ts=_as_datetime(getattr(other,"source_timestamp",None))
                if ts is not None: activity[other_fuel]=ts
        target_phase=phase(fuel,day) if fuel in PRINCIPAL_FUELS else None
        gp=phase("Gazole",day); sp=phase("SP95",day)
        gr=key_rows.get((sid,day,"Gazole")); sr=key_rows.get((sid,day,"SP95"))
        gazole_price=_as_float(getattr(gr,"price",None)) if gr else None; sp95_price=_as_float(getattr(sr,"price",None)) if sr else None
        gazole_cap=gp.cap if gp else None; sp95_cap=sp.cap if sp else None
        department=str(row.department)
        if department == "20":
            region_kind="corsica"; territory_r2="corsica"; is_total=classify_registry_entry(corse_stations.get(sid)) == TOTAL; territory_label="Corse"
        else:
            region_kind="mainland"; territory_r2="bdr"; entry=bdr_entries.get(sid) if isinstance(bdr_entries,dict) else None; is_total=_is_total_brand((entry or {}).get("enseigne") if isinstance(entry,dict) else None); territory_label="BdR"
        r2_verdict=None; age=reliability_policy_v2.age_days(last_declared,day); both_capped=at_cap(gazole_price,gazole_cap) and at_cap(sp95_price,sp95_cap)
        if fuel in PRINCIPAL_FUELS and age is not None and age >= reliability_policy_v2.NORMAL_MAX_AGE_DAYS and both_capped:
            r2_calls += 1
            try:
                r2_verdict=r2_guard_v2.stale_price_admissible(last_declared,day,territory_r2,bouclier_metadata=bouclier)
                if r2_verdict: r2_true += 1
                else: r2_false += 1
            except Exception as exc:
                r2_unavailable += 1; r2_errors[f"{type(exc).__name__}: {exc}"] += 1; r2_verdict=None
        price_aberrant=getattr(row,"price_aberrant",True); latest_price_valid=False if pd.isna(price_aberrant) else not bool(price_aberrant)
        decision=reliability_policy_v2.evaluate(day=day,region_kind=region_kind,target_fuel=fuel,last_declared_at=last_declared,last_price=_as_float(row.price),latest_price_valid=latest_price_valid,target_rupture_active=event_guards.rupture_active(sid,fuel,day),independently_inactive=event_guards.independently_inactive(sid,day),is_total=is_total,shield_effective=target_phase is not None,applicable_cap=target_phase.cap if target_phase else None,phase_started_on=target_phase.started_on if target_phase else None,activity_by_fuel=activity,gazole_price=gazole_price,gazole_cap=gazole_cap,sp95_price=sp95_price,sp95_cap=sp95_cap,rotterdam_stale_price_admissible=r2_verdict)
        eligible.append(bool(decision.eligible)); reasons[decision.reason]+=1; reasons_by_territory[f"{territory_label}/{fuel}/{decision.reason}"]+=1
    out=state.copy(); out["eligible_publication"]=eligible
    return out, {"evaluate_station_days":sum(1 for d in state["date"] if pd.Timestamp(d).date() >= start),"reason_counts":dict(reasons),"reason_counts_by_territory_fuel":dict(reasons_by_territory),"r2_calls":r2_calls,"r2_true":r2_true,"r2_false":r2_false,"r2_unavailable":r2_unavailable,"r2_errors":dict(r2_errors)}


def _merge_rows(existing: list[dict], generated: list[dict], *, boundary: date, append_through: date, allow_transition_rewrite: bool) -> tuple[list[dict], dict]:
    generated_by_date={str(r["date"]):dict(r) for r in generated if date.fromisoformat(str(r["date"])) <= append_through}
    old_last=date.fromisoformat(str(existing[-1]["date"]))
    out=[]; rewrites=0; additions=0; max_delta=0.0; missing=[]
    for old in existing:
        d=date.fromisoformat(str(old["date"]))
        if allow_transition_rewrite and d >= boundary:
            new=generated_by_date.get(str(old["date"]))
            if new is None: missing.append(str(old["date"])); out.append(deepcopy(old)); continue
            out.append(new)
            if new != old:
                rewrites += 1
                if "ecart" in old and "ecart" in new: max_delta=max(max_delta,abs(float(new["ecart"])-float(old["ecart"])))
        else: out.append(deepcopy(old))
    for dstr,new in sorted(generated_by_date.items()):
        d=date.fromisoformat(dstr)
        if d > old_last:
            out.append(new); additions += 1
    dates=[str(r["date"]) for r in out]
    if dates != sorted(dates) or len(dates) != len(set(dates)): raise RuntimeError("Candidate series dates are not strictly ordered/unique")
    return out,{"rewritten_rows":rewrites,"added_rows":additions,"missing_replacements":missing,"max_abs_ecart_delta_c_l":round(max_delta,4)}


def main() -> None:
    args=parse_args(); requested_end=date.fromisoformat(args.end) if args.end else _default_end()
    baseline=json.loads((ROOT/"data.json").read_text(encoding="utf-8")); baseline_meta=dict(baseline.get("meta") or {}); already_active=bool((baseline_meta.get("v2") or {}).get("active"))
    fetch=download_shared_rotterdam_assets(ROOT/"outputs"/"ufip",tag_prefix=args.tag_prefix,release_tag=args.release_tag,registry_output=CORSE_REGISTRY,tag_output=C1_TAG)
    meta=json.loads(C1_META.read_text(encoding="utf-8")); years=sorted(int(y) for y in meta.get("years",[]))
    observations,source=load_shared_observations(years,tag_prefix=args.tag_prefix,release_tag=args.release_tag)
    source_max=date.fromisoformat(str(source.get("shared_source_max_date"))); target_end=min(requested_end,source_max)
    baseline_last=date.fromisoformat(baseline["DATA"]["gazole"]["sp95"]["daily"]["all"][-1]["date"])
    if target_end < baseline_last: raise RuntimeError(f"Pinned C1 source is older than baseline: {target_end} < {baseline_last}")
    weekly_end=_last_complete_sunday(target_end)
    bouclier=source.get("bouclier") or meta.get("bouclier")
    if not isinstance(bouclier,dict): raise RuntimeError("Pinned C1 release has no shield metadata")

    legacy=load_bdr_categories(LEGACY_BDR); resolution=_resolve_bdr(observations,legacy); categories=_merged_bdr_categories()
    state=build_publication_state(pd.DataFrame(observations),global_end=pd.Timestamp(target_end),bdr_categories=categories)
    stale_ids=_candidate_stale_bdr_ids(state,bouclier,SWITCH_DAY,target_end); resolution["stale_total_candidates"]=_resolve_stale_bdr_candidates(observations,stale_ids,legacy)
    categories=_merged_bdr_categories(); state=build_publication_state(pd.DataFrame(observations),global_end=pd.Timestamp(target_end),bdr_categories=categories)

    from scripts.v2_event_guards import EventGuards
    guards=EventGuards.from_release(args.release_tag,metadata=meta)
    corse_payload=json.loads(CORSE_REGISTRY.read_text(encoding="utf-8")); corse_stations=corse_payload.get("stations") or {}
    v2_state,engine=_evaluate_v2(state,bouclier=bouclier,event_guards=guards,corse_stations=corse_stations,start=SWITCH_DAY,end=target_end)

    candidate=deepcopy(baseline); report_series={}; allow_transition=not already_active
    cases=[("gazole","sp95","Gazole","Gazole"),("sp95","sp95","SP95","SP95"),("sp95","e10","SP95","E10")]
    for key,ref,cf,bf in cases:
        for scope,group in (("all","all"),("network","reseau")):
            daily=build_gap_series(v2_state,corsica_fuel=cf,bdr_fuel=bf,bdr_scope=scope,granularity="daily")
            path=f"DATA/{key}/{ref}/daily/{group}"; merged,stats=_merge_rows(baseline["DATA"][key][ref]["daily"][group],daily,boundary=SWITCH_DAY,append_through=target_end,allow_transition_rewrite=allow_transition); candidate["DATA"][key][ref]["daily"][group]=merged; report_series[path]=stats
            weekly=[r for r in build_gap_series(v2_state,corsica_fuel=cf,bdr_fuel=bf,bdr_scope=scope,granularity="weekly") if date.fromisoformat(str(r["date"])) + timedelta(days=6) <= weekly_end]
            path=f"DATA/{key}/{ref}/weekly/{group}"; merged,stats=_merge_rows(baseline["DATA"][key][ref]["weekly"][group],weekly,boundary=WEEKLY_SWITCH,append_through=weekly_end,allow_transition_rewrite=allow_transition); candidate["DATA"][key][ref]["weekly"][group]=merged; report_series[path]=stats

    rotterdam=pd.read_csv(ROTTERDAM_DAILY); rotterdam["date"]=pd.to_datetime(rotterdam["date"]).dt.normalize()
    margin_state=v2_state[(v2_state["date"] >= pd.Timestamp(WEEKLY_SWITCH)) & (v2_state["date"] <= pd.Timestamp(weekly_end))].copy()
    for scope,group in (("all","all"),("network","reseau")):
        margins=build_margin_series(margin_state,rotterdam,bdr_scope=scope)
        path=f"MARGES_GZ/{group}"; merged,stats=_merge_rows(baseline["MARGES_GZ"][group],margins,boundary=WEEKLY_SWITCH,append_through=weekly_end,allow_transition_rewrite=allow_transition); candidate["MARGES_GZ"][group]=merged; report_series[path]=stats

    missing=sum(len(v["missing_replacements"]) for v in report_series.values())
    if missing: raise RuntimeError(f"V2 candidate has {missing} missing replacement date(s)")
    observed=pd.read_csv(ROTTERDAM_OBSERVED); ufip_last=None if observed.empty else str(pd.to_datetime(observed["date"]).max().date())
    unknown=unknown_recent_bdr_stations(v2_state,since=pd.Timestamp(max(SWITCH_DAY,target_end-timedelta(days=30))))
    new_meta=deepcopy(baseline_meta); new_meta.update({"generated_at":pd.Timestamp.now(tz="UTC").isoformat(),"publication_mode":"v2-append-only" if already_active else "v2-controlled-transition","baseline_source":"data.json","previous_daily_cutoff":baseline_last.isoformat(),"requested_daily_target_end":requested_end.isoformat(),"daily_target_end":target_end.isoformat(),"weekly_complete_through":weekly_end.isoformat(),"official_source_max_date":source_max.isoformat(),"official_ingestion_source":source.get("kind"),"official_shared_release_tag":args.release_tag,"official_shared_release_published_at":source.get("release_published_at"),"official_shared_sha256":source.get("sha256"),"official_shared_source_max_date":source.get("shared_source_max_date"),"bouclier":bouclier,"ufip_last_observed_date":ufip_last,"unknown_recent_bdr_stations":unknown,"v2":{"active":True,"version":"A4C-V2-2026-07-23","daily_switch_date":SWITCH_DAY.isoformat(),"weekly_switch_date":WEEKLY_SWITCH.isoformat(),"history_before_switch_preserved":True,"weekly_overlap_2026_07_20_preserved":True,"controlled_transition_applied":not already_active or bool((baseline_meta.get("v2") or {}).get("controlled_transition_applied")),"c1_release_tag":args.release_tag,"event_reopening_rule":"open rupture -> later same-fuel declaration; open closure -> later any-fuel station declaration; explicit end wins"}})
    candidate["meta"]=new_meta
    output=ROOT/args.output; summary_path=ROOT/args.summary; output.parent.mkdir(parents=True,exist_ok=True); summary_path.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(candidate,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
    summary={"status":"v2-production-candidate","production_modified":False,"initial_transition":allow_transition,"daily_switch_date":SWITCH_DAY.isoformat(),"weekly_switch_date":WEEKLY_SWITCH.isoformat(),"target_end":target_end.isoformat(),"weekly_end":weekly_end.isoformat(),"c1_release_tag":args.release_tag,"series":report_series,"rewritten_rows_total":sum(v["rewritten_rows"] for v in report_series.values()),"added_rows_total":sum(v["added_rows"] for v in report_series.values()),"missing_replacements_total":missing,"engine":engine,"official_event_guards":guards.audit(),"bdr_resolution":resolution,"unknown_recent_bdr_stations":unknown}
    summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__ == "__main__": main()
