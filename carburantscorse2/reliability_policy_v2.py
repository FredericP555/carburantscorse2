#!/usr/bin/env python3
"""Prepared, inactive A4C 45-day/shield policy. Not imported by publication.py."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

NORMAL_MAX_AGE_DAYS=45
CAP_TOLERANCE_BELOW_EUR=0.002
CAP_TOLERANCE_ABOVE_EUR=0.001
PRINCIPAL_FUELS=frozenset({'Gazole','SP95'})

@dataclass(frozen=True)
class Decision:
    eligible: bool
    reason: str
    age_days: int|None

def age_days(ts:datetime|None, day:date)->int|None:
    return None if ts is None else (day-ts.date()).days

def normally_fresh(ts:datetime|None, day:date)->bool:
    a=age_days(ts,day); return a is not None and 0<=a<NORMAL_MAX_AGE_DAYS

def at_cap(price:float|None, cap:float|None)->bool:
    return price is not None and cap is not None and cap-CAP_TOLERANCE_BELOW_EUR<=float(price)<=cap+CAP_TOLERANCE_ABOVE_EUR

def recent_liveness(*,region_kind:str,target_fuel:str,activity_by_fuel:Mapping[str,datetime],day:date)->bool:
    if region_kind not in {'corsica','mainland'}: raise ValueError('region_kind')
    for fuel,ts in activity_by_fuel.items():
        if fuel==target_fuel: continue
        if region_kind=='corsica' and fuel not in PRINCIPAL_FUELS: continue
        if normally_fresh(ts,day): return True
    return False

def evaluate(*,day:date,region_kind:str,target_fuel:str,last_declared_at:datetime|None,last_price:float|None,
             latest_price_valid:bool=True,target_rupture_active:bool=False,independently_inactive:bool=False,
             is_total:bool=False,shield_effective:bool=False,applicable_cap:float|None=None,
             eligible_at_cap_entry:bool=False,activity_by_fuel:Mapping[str,datetime]|None=None,
             gazole_price:float|None=None,gazole_cap:float|None=None,sp95_price:float|None=None,sp95_cap:float|None=None,
             rotterdam_gazole_constraining:bool|None=None)->Decision:
    a=age_days(last_declared_at,day)
    if independently_inactive: return Decision(False,'inactive_independant',a)
    if target_rupture_active: return Decision(False,'rupture_active',a)
    if last_declared_at is None or last_price is None or not latest_price_valid: return Decision(False,'prix_absent_ou_invalide',a)
    if normally_fresh(last_declared_at,day): return Decision(True,'normal_45j',a)
    if not(is_total and shield_effective): return Decision(False,'ancien_hors_exception',a)
    if not eligible_at_cap_entry: return Decision(False,'pas_de_resurrection_a_entree_plafond',a)
    if not at_cap(last_price,applicable_cap): return Decision(False,'ancien_pas_au_plafond',a)
    if recent_liveness(region_kind=region_kind,target_fuel=target_fuel,activity_by_fuel=activity_by_fuel or {},day=day):
        return Decision(True,'bouclier_vivacite_croisee',a)
    if at_cap(gazole_price,gazole_cap) and at_cap(sp95_price,sp95_cap) and rotterdam_gazole_constraining is True:
        return Decision(True,'bouclier_double_plafond_rotterdam',a)
    return Decision(False,'bouclier_sans_preuve_vivacite',a)
