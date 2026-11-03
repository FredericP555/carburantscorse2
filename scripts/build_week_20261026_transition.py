#!/usr/bin/env python3
"""One-time offline candidate builder. Never writes production data or calls a network.
Run from repository root: python scripts/build_week_20261026_transition.py
Baseline and replay trace are hash-pinned. Output is audits/.../candidate*.json.
"""
from pathlib import Path
from datetime import date, timedelta
from copy import deepcopy
import argparse
import hashlib
import json
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'audits/2026-11-03-total-transition'
START, END = '2026-10-26', '2026-11-01'
ID = 'total-below-cap-week-20261026'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def diffs(a, b, path=()):
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), path
        for k in a:
            yield from diffs(a[k], b[k], path+(k,))
    elif isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b), path
        for i, (x, y) in enumerate(zip(a,b)):
            yield from diffs(x,y,path+(i,))
    elif a != b:
        yield {'path':list(path),'old':a,'new':b}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--baseline', type=Path, default=ROOT/'data.json')
    ap.add_argument('--summary-baseline', type=Path, default=ROOT/'homepage-summary.json')
    args=ap.parse_args()
    source = json.loads((OUT/'source.json').read_text())
    assert digest(args.baseline) == source['baseline_sha256'], 'Published baseline moved'
    assert digest(OUT/'corsica-station-days.csv') == source['station_days_sha256']
    base = json.loads(args.baseline.read_text()); candidate = deepcopy(base)
    s = pd.read_csv(OUT/'corsica-station-days.csv',dtype={'station_id':str})
    assert set(s.date) == {(date.fromisoformat(START)+timedelta(days=n)).isoformat() for n in range(7)}
    assert not (s.old_eligible & ~s.eligible_publication).any()
    assert set(s.fuel) == {'Gazole','SP95'}
    assert not s[['price','price_ht','rotterdam_eur_l']].isna().any().any()
    deltas = {}
    for fuel in ('Gazole','SP95'):
        for gran in ('daily','weekly'):
            frame=s[s.fuel.eq(fuel)].copy();frame['period']=frame.date if gran=='daily' else START
            for period,g in frame.groupby('period'):
                old=g[g.old_eligible];new=g[g.eligible_publication]
                assert old.station_id.nunique()>=5
                d={c:float(new[c].mean()-old[c].mean()) for c in ['price','price_ht','rotterdam_eur_l']}
                d['n_delta']=int(new.station_id.nunique()-old.station_id.nunique())
                # Excise is constant across this week, so it cancels. Rotterdam does
                # NOT cancel: station-day weighting changes with eligibility.
                d['margin_delta_c_l']=100*(d['price_ht']-d['rotterdam_eur_l'])
                deltas[(fuel,gran,period)]=d
    kind='C1' if 'origin' in base else 'C2'
    if kind=='C1':
        origin=date.fromisoformat(base['origin']);off=lambda x:(date.fromisoformat(x)-origin).days
        lo,hi=off(START),off(END)
        for fuel,key in [('Gazole','G'),('SP95','S')]:
            series=candidate[key]['corse']
            for row in series['d']:
                if lo<=row[0]<=hi:
                    delta=deltas[(fuel,'daily',(origin+timedelta(days=row[0])).isoformat())]['price']
                    row[1]=round(row[1]+delta+1e-12,3)
                    row[2]=round(row[2]+delta/1.13+1e-12,3)
            for gran,periods in [('w',[lo]),('m',['2026-10','2026-11'])]:
                for row in series[gran]:
                    if row[0] not in periods:continue
                    days=[p for p in series['d'] if (row[0]<=p[0]<=row[0]+6 if gran=='w' else (origin+timedelta(days=p[0])).isoformat()[:7]==row[0])]
                    for col in (1,2):
                        vals=[p[col] for p in days if p[col] is not None]
                        row[col]=round(sum(vals)/len(vals)+1e-12,3)
        changes=list(diffs(base,candidate))
        for x in changes:
            key,region,gran,i,col=x['path'];period=base[key][region][gran][i][0]
            assert region=='corse' and col in (1,2)
            assert (gran=='d' and lo<=period<=hi) or (gran=='w' and period==lo) or (gran=='m' and period in ('2026-10','2026-11'))
    else:
        for key,fuel in [('gazole','Gazole'),('sp95','SP95')]:
            for ref,grans in candidate['DATA'][key].items():
                for gran,groups in grans.items():
                    for group,rows in groups.items():
                        for row in rows:
                            if (fuel,gran,row['date']) in deltas:
                                row['ecart']=round(row['ecart']+100*deltas[(fuel,gran,row['date'])]['price_ht'],2)
        md=deltas[('Gazole','weekly',START)]['margin_delta_c_l']
        for rows in candidate['MARGES_GZ'].values():
            for row in rows:
                if row['date']==START:
                    row['corse']=round(row['corse']+md,2);row['ecart']=round(row['ecart']+md,2)
        changes=list(diffs(base,candidate))
        for x in changes:
            p=x['path']
            if p[0]=='DATA':
                _,key,ref,gran,group,i,field=p
                assert field=='ecart' and (('Gazole' if key=='gazole' else 'SP95'),gran,base['DATA'][key][ref][gran][group][i]['date']) in deltas
            else:
                _,group,i,field=p
                assert p[0]=='MARGES_GZ' and field in ('corse','ecart') and base['MARGES_GZ'][group][i]['date']==START
        assert digest(args.summary_baseline)==source['summary_sha256']
        summary=json.loads(args.summary_baseline.read_text()); old_summary=deepcopy(summary)
        for fuel,scopes in summary['fuels'].items():
            for scope,grans in scopes.items():
                key='gazole' if fuel=='Gazole' else 'sp95';group='all' if scope=='all' else 'reseau'
                for gran,metrics in grans.items():
                    canonical={r['date']:r['ecart'] for r in candidate['DATA'][key]['sp95'][gran][group]}
                    for name in ('latest','previous','four_weeks_ago','year_ago','recent'):
                        rows=metrics[name] if isinstance(metrics[name],list) else [metrics[name]]
                        for row in rows:
                            if not row or (fuel,gran,row['date']) not in deltas:continue
                            d=deltas[(fuel,gran,row['date'])]
                            row['gap_ht_c_l']=canonical[row['date']]
                            row['corse_ht_eur_l']=round(row['corse_ht_eur_l']+d['price_ht'],4)
                            row['corse_ttc_eur_l']=round(row['corse_ttc_eur_l']+d['price'],4)
                            row['n_corse']+=d['n_delta']
                    for metric,name in [('gap_change_wow_c_l','previous'),('gap_change_4w_c_l','four_weeks_ago'),('gap_change_yoy_c_l','year_ago')]:
                        if metrics[name]:metrics[metric]=round(metrics['latest']['gap_ht_c_l']-metrics[name]['gap_ht_c_l'],2)
        for fuel,key in [('Gazole','gazole'),('SP95','sp95')]:
            m=summary['fuels'][fuel]['network']['weekly']
            summary['homepage_default'][key]={'gap_ht_c_l':m['latest']['gap_ht_c_l'],'gap_change_wow_c_l':m['gap_change_wow_c_l']}
        for scope,group in [('all','all'),('network','reseau')]:
            rows=candidate['MARGES_GZ'][group]
            summary['margin_gazole'][scope]={'latest':deepcopy(rows[-1]),'previous':deepcopy(rows[-2]),'recent':deepcopy(rows[-8:])}
        summary_changes=list(diffs(old_summary,summary))
        assert all(x['path'][0] in ('fuels','homepage_default','margin_gazole') for x in summary_changes)
        (OUT/'candidate-homepage-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    (OUT/'candidate.json').write_text(json.dumps(candidate,ensure_ascii=False,separators=(',',':')))
    report={'id':ID,'kind':kind,'window':[START,END],'baseline_sha256':source['baseline_sha256'],'candidate_sha256':digest(OUT/'candidate.json'),'production_modified':False,'protected_history_verified':True,'automation_changed':False,'reintroduced_station_days':int((s.eligible_publication & ~s.old_eligible).sum()),'changes':changes,'deltas':[dict(fuel=f,granularity=g,date=p,**d) for (f,g,p),d in deltas.items()]}
    if kind=='C2':report.update(summary_changes=summary_changes,summary_candidate_sha256=digest(OUT/'candidate-homepage-summary.json'))
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    assert digest(args.baseline)==source['baseline_sha256']
    print(json.dumps({k:v for k,v in report.items() if k not in ('changes','deltas','summary_changes')},indent=2))

if __name__=='__main__':main()
