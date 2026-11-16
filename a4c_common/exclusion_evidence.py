"""Observe production decisions without changing eligibility or published data.

Rows describe this run's calculation, NOT necessarily immutable historical rows in
its append-only candidate. Compare to the published series before interpreting a
replay as a publication audit. Missing declarations are outside this denominator.
"""
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import warnings

FIELDS = ('date', 'territory', 'station_id', 'fuel', 'brand', 'category',
          'source_timestamp', 'price', 'age_days', 'eligible', 'reason')


def decision_row(day, territory, sid, fuel, brand, category, timestamp, price, decision, age):
    return dict(zip(FIELDS, (day.isoformat(), territory, str(sid), fuel,
        brand or 'UNKNOWN', category, timestamp.isoformat() if timestamp else None,
        price if price is not None and math.isfinite(price) else None,
        age, bool(decision.eligible), decision.reason)))


def summarize(rows):
    groups = defaultdict(list)
    seen = set()
    for row in rows:
        key = tuple(row[k] for k in ('date', 'territory', 'station_id', 'fuel'))
        if key in seen:
            raise ValueError(f'Duplicate station-fuel-day: {key}')
        seen.add(key)
        if row['eligible'] and row['price'] is None:
            raise ValueError(f'Eligible row without price: {key}')
        for scope in ('all', 'network') if row['category'] == 'network' else ('all',):
            groups[(row['date'], row['territory'], row['fuel'], scope)].append(row)
    result = []
    for key, members in sorted(groups.items()):
        retained = [r for r in members if r['eligible']]
        excluded = [r for r in members if not r['eligible']]
        result.append(dict(zip(('date', 'territory', 'fuel', 'scope'), key),
            candidates=len(members), retained=len(retained), excluded=len(excluded),
            excluded_pct=100*len(excluded)/len(members),
            excluded_by_brand=dict(Counter(r['brand'] for r in excluded)),
            excluded_by_reason=dict(Counter(r['reason'] for r in excluded)),
            calculated_mean_ttc=sum(r['price'] for r in retained)/len(retained) if retained else None))
    return result


def _sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write_evidence(root, project, rows, *, source_files, release_tag=None):
    """Optional evidence must never interrupt production; errors remain explicit."""
    root = Path(root)
    csv_path = root/'outputs'/f'{project}-exclusions.csv.gz'
    json_path = root/'outputs'/f'{project}-exclusions.json'
    try:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove stale sidecars before attempting a new export.
        csv_path.unlink(missing_ok=True)
        json_path.unlink(missing_ok=True)
        totals = summarize(rows)
        with gzip.open(csv_path, 'wt', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(sorted(rows, key=lambda r: (r['date'], r['territory'], r['fuel'], r['station_id'])))
        sources = {str(Path(p).relative_to(root)): _sha(Path(p)) for p in source_files if Path(p).is_file()}
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        report = dict(schema='a4c-exclusion-evidence-v1', status='ok' if rows else 'empty',
            project=project, code_commit=commit, run_id=os.getenv('GITHUB_RUN_ID'),
            run_attempt=os.getenv('GITHUB_RUN_ATTEMPT'), c1_release_tag=release_tag,
            source_sha256=sources, rows=len(rows), csv_sha256=_sha(csv_path),
            scope='Observed station-fuel pairs after structural exclusions; last eight calculated days. Missing declarations are not candidates. Network is a separate subset, not a reliability exclusion.',
            publication_reconciled=False,
            publication_note='Calculation evidence only: append-only publication may preserve older values. Reconcile dates, populations and means with the published candidate before certifying an exclusion audit.',
            totals=totals)
        json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return dict(status=report['status'], rows=len(rows), csv=str(csv_path.relative_to(root)),
                    manifest=str(json_path.relative_to(root)), publication_reconciled=False)
    except Exception as exc:
        # A partial CSV must never masquerade as a completed audit.
        for path in (csv_path, json_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        warnings.warn(f'Exclusion evidence unavailable: {type(exc).__name__}: {exc}', RuntimeWarning)
        return dict(status='error', error=f'{type(exc).__name__}: {exc}', publication_reconciled=False)
