#!/usr/bin/env python3
"""Recompute October ENI-vs-ENI gap from pinned official station declarations.
Read-only, no use of external brand sources or published data writes.
"""
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd
from a4c_common.shared_release import download_shared_rotterdam_assets, load_shared_observations
from carburantscorse2.publication import build_publication_state, load_bdr_categories
from scripts.build_v2_production_candidate import (
    _bdr_category_resolver, _evaluate_v2, C1_META, CORSE_REGISTRY, LEGACY_BDR, BDR_REGISTRY
)
from scripts.resolve_new_bdr_station_brands import load_registry, _entry_for_day
from scripts.v2_event_guards import EventGuards

TAG = "a4c-v2-shared-20261026T162416Z-40357791719"
TARGET_END = date(2026, 10, 25)
SOURCE_ONLY = "prix-carburants.gouv.fr via immutable C1 official archive"

def main():
    download_shared_rotterdam_assets(
        "outputs/ufip", tag_prefix="a4c-v2-shared-", release_tag=TAG,
        registry_output=CORSE_REGISTRY, tag_output="outputs/c1/shared_release_tag.txt"
    )
    meta = json.loads(Path(C1_META).read_text())
    rows, source = load_shared_observations(
        [2025,2026], tag_prefix="a4c-v2-shared-", release_tag=TAG
    )
    registry = load_registry(BDR_REGISTRY)
    bdr_stations = registry["stations"]
    corse = json.loads(Path(CORSE_REGISTRY).read_text())["stations"]
    bdr_classifier = _bdr_category_resolver(load_bdr_categories(LEGACY_BDR),registry)
    state = build_publication_state(
        pd.DataFrame(rows),global_end=pd.Timestamp(TARGET_END),bdr_category_resolver=bdr_classifier
    )
    guards = EventGuards.from_release(TAG,metadata=meta)
    checked, audit = _evaluate_v2(
        state, bouclier=source["bouclier"], event_guards=guards, corse_stations=corse,
        start=date(2026, 10, 1), end=TARGET_END
    )
    checked = checked[
        (checked["date"] >= pd.Timestamp("2026-10-01")) &
        (checked["date"] <= pd.Timestamp(TARGET_END)) &
        (checked["eligible_publication"])
    ].copy()
    def is_eni(r):
        sid = str(r.station_id)
        if r.territory == "Corse":
            entry = corse.get(sid) or {}
        else:
            entry = _entry_for_day(bdr_stations.get(sid), pd.Timestamp(r.date).date()) or {}
        return str(entry.get("enseigne","")).casefold() == "eni"
    eni = checked[checked.apply(is_eni,axis=1)]
    output={"source":SOURCE_ONLY,"release_tag":TAG,"end":str(TARGET_END),"fuels":{}}
    for fuel in ("Gazole","SP95","E10"):
        sub=eni[eni["fuel"]==fuel]
        pts=[]
        for d,day in sub.groupby("date"):
            territories={}
            for side in ("Corse","Bouches-du-Rhone"):
                v=day[day["territory"]==side]
                territories[side]={
                    "n":int(v["station_id"].nunique()),
                    "ids":sorted(v["station_id"].astype(str).unique().tolist()),
                    "mean_ht":round(float(v["price_ht"].mean()),6) if len(v) else None,
                    "mean_ttc":round(float(v["price"].mean()),6) if len(v) else None,
                }
            if territories["Corse"]["n"] and territories["Bouches-du-Rhone"]["n"]:
                pts.append({"day":str(d.date()),
                    "gap_ht_c":round(100*(territories["Corse"]["mean_ht"]-territories["Bouches-du-Rhone"]["mean_ht"]),2),
                    "sides":territories})
        output["fuels"][fuel]={
           "count_days":len(pts),
           "daily":[{ "day":p["day"],"gap_ht_c":p["gap_ht_c"],"n_corse":p["sides"]["Corse"]["n"],"n_bdr":p["sides"]["Bouches-du-Rhone"]["n"]} for p in pts],
           "last_day_detail":pts[-1] if pts else None
        }
    print("A4C_ENI_OFFICIAL_CHECK_START",flush=True)
    print(json.dumps(output,ensure_ascii=False,indent=2),flush=True)
    print("A4C_ENI_OFFICIAL_CHECK_END",flush=True)

if __name__=="__main__":
    main()
