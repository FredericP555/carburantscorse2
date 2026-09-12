#!/usr/bin/env bash
set -euo pipefail

FEATURE_ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
INTEGRATED=/tmp/monthly-integrated
MONTH=2026-08
AS_OF=2026-09-11
PREVIOUS_DATA=/tmp/monthly-before-bdr-backfill.json

cd "$FEATURE_ROOT"
if [ -s "outputs/monthly-territories-2026-08.json" ]; then
  cp "outputs/monthly-territories-2026-08.json" "$PREVIOUS_DATA"
else
  rm -f "$PREVIOUS_DATA"
fi

git fetch origin main --depth=1
C2_MAIN_SHA=$(git rev-parse origin/main)
export C2_MAIN_SHA
rm -rf "$INTEGRATED"
git worktree add --detach "$INTEGRATED" origin/main

monthly_files=(
  .github/workflows/monthly-territorial-test.yml
  config/corse_station_geography_2026.csv
  docs/monthly-territorial-spec.md
  scripts/build_monthly_territorial.py
  scripts/build_monthly_territorial_hardened.py
  scripts/check_monthly_readiness.py
  scripts/monthly_bdr_category_backfill.py
  scripts/validate_monthly_source_guards.py
  scripts/validate_monthly_source_guards_hardened.py
  scripts/write_monthly_receipt.py
  scripts/audit_epci_monthly.py
  scripts/audit_monthly_territorial_coverage.py
  scripts/validate_monthly_widget_contract.py
  scripts/browser_smoke_monthly_widget.mjs
  scripts/check_monthly_c2_contract_isolated.sh
  tests/test_monthly_bdr_category_backfill.py
  widgets/bilan-territorial/index.html
)
tar cf - "${monthly_files[@]}" | tar xf - -C "$INTEGRATED"

cd "$INTEGRATED"
python -m pip install --disable-pip-version-check -r requirements.lock.txt
python -m unittest tests.test_ci_supply_chain_contracts -v
PYTHONPATH=. python -m unittest tests.test_monthly_bdr_category_backfill -v

run_id=$(gh run list \
  --repo FredericP555/carburantscorse2 \
  --workflow verify-c2-publication.yml \
  --branch main \
  --status success \
  --limit 20 \
  --json databaseId,createdAt \
  --jq 'sort_by(.createdAt) | reverse | .[0].databaseId // empty')
test -n "$run_id"
rm -rf /tmp/c2-business && mkdir -p /tmp/c2-business
gh run download "$run_id" \
  --repo FredericP555/carburantscorse2 \
  --name c2-business-success-receipt \
  --dir /tmp/c2-business
BUSINESS_RECEIPT=/tmp/c2-business/c2-business-success.json
test -s "$BUSINESS_RECEIPT"
tag=$(python - <<'PY'
import json
print(json.load(open('data.json'))['meta']['v2']['c1_release_tag'])
PY
)
python scripts/validate_current_c2_receipt.py \
  --receipt "$BUSINESS_RECEIPT" \
  --expected-tag "$tag" \
  --current-data data.json \
  --current-summary homepage-summary.json

rm -rf /tmp/monthly-final-receipts
python scripts/check_monthly_readiness.py \
  --month "$MONTH" --as-of "$AS_OF" \
  --c2-data data.json --c2-summary homepage-summary.json \
  --c2-business-receipt "$BUSINESS_RECEIPT" \
  --receipt-dir /tmp/monthly-final-receipts \
  --output outputs/monthly-readiness-2026-08.json \
  --fail-if-not-ready

rm -rf /tmp/readiness && mkdir -p /tmp/readiness
common=(--month "$MONTH" --c2-summary homepage-summary.json --c2-business-receipt "$BUSINESS_RECEIPT")
python scripts/check_monthly_readiness.py "${common[@]}" --as-of 2026-08-31 --c2-data data.json --output /tmp/readiness/incomplete.json
python - <<'PY'
import json
from pathlib import Path
d=json.loads(Path('data.json').read_text())
d['meta']['daily_target_end']='2026-08-31'
d['meta']['official_shared_source_max_date']='2026-08-31'
Path('/tmp/readiness/stale-data.json').write_text(json.dumps(d), encoding='utf-8')
PY
python scripts/check_monthly_readiness.py "${common[@]}" --as-of "$AS_OF" --c2-data /tmp/readiness/stale-data.json --output /tmp/readiness/stale.json
mkdir -p /tmp/readiness/final /tmp/readiness/corrupt
printf '{"schema":"a4c-monthly-final-receipt-v1","status":"final","month":"2026-08"}\n' >/tmp/readiness/final/2026-08.json
python scripts/check_monthly_readiness.py "${common[@]}" --as-of "$AS_OF" --c2-data data.json --receipt-dir /tmp/readiness/final --output /tmp/readiness/finalized.json
printf '{broken\n' >/tmp/readiness/corrupt/2026-08.json
python scripts/check_monthly_readiness.py "${common[@]}" --as-of "$AS_OF" --c2-data data.json --receipt-dir /tmp/readiness/corrupt --output /tmp/readiness/corrupt.json
python - <<'PY'
import json
from pathlib import Path
for name in ('incomplete','stale','finalized','corrupt'):
    d=json.loads((Path('/tmp/readiness')/f'{name}.json').read_text())
    if d['ready']:
        raise SystemExit(f'{name} scenario incorrectly marked ready')
    print(name, 'blocked by', [c['key'] for c in d['checks'] if not c['ok']])
PY

# Source guard: use the monthly-only bounded category backfill. The repository registry is restored
# immediately afterward; no C2 production registry change is promoted.
cp config/bdr_station_brands.json /tmp/monthly-bdr-registry.json
PYTHONPATH=. python scripts/validate_monthly_source_guards_hardened.py \
  --month "$MONTH" --c2-data data.json \
  --output outputs/monthly-source-guards-2026-08.json
python - <<'PY'
import json
from pathlib import Path
d=json.loads(Path('outputs/monthly-source-guards-2026-08.json').read_text())
assert d['schema']=='a4c-monthly-source-guards-v3', d
assert d['status']=='pass', d
assert d['missing_geography']==[], d
assert d['unknown_recent_bdr_stations']==[], d
assert d['unknown_bdr_details']==[], d
a=d['bdr_category_backfill']
assert a['policy']['max_backfill_days']==7, a
assert a['policy']['same_station_id_required'] is True, a
assert a['policy']['price_or_eligibility_modified'] is False, a
assert a['applied_station_days']==6, a
assert a['applied_gms_station_days']==6, a
assert a['applied_network_station_days']==0, a
assert a['rejected_conflicts']==[], a
assert a['applied_ranges']==[{
    'station_id':'13120012', 'from':'2026-08-25', 'through':'2026-08-30',
    'station_days':6, 'category':'gms', 'enseigne':'Carrefour Market',
    'classification_valid_from':'2026-08-31',
    'verified_at':a['applied_ranges'][0]['verified_at'],
}], a
print('Bounded Gardanne backfill validated:', a['applied_ranges'][0])
PY
cp /tmp/monthly-bdr-registry.json config/bdr_station_brands.json
rm -rf outputs/ufip outputs/c1

# Build the dataset with exactly the same bounded category rule. No price or eligibility rule changes.
PYTHONPATH=. python scripts/build_monthly_territorial_hardened.py \
  --month "$MONTH" --c2-data data.json \
  --output outputs/monthly-territories-2026-08.json
python scripts/validate_monthly_widget_contract.py \
  --data outputs/monthly-territories-2026-08.json \
  --widget widgets/bilan-territorial/index.html

# For the August Gardanne case the propagated category is GMS. Therefore it must not alter either
# the all-BdR aggregates or the network aggregates: the station was already excluded from network
# while unknown. Record that empirical before/after proof.
python - <<'PY'
import json
from pathlib import Path
new=json.loads(Path('outputs/monthly-territories-2026-08.json').read_text())
a=new['internal_audit']['bdr_category_backfill']
assert a['applied_station_days']==6, a
assert a['applied_gms_station_days']==6 and a['applied_network_station_days']==0, a
old_path=Path('/tmp/monthly-before-bdr-backfill.json')
impact={
  'schema':'a4c-monthly-bdr-backfill-impact-v1',
  'month':'2026-08',
  'station_id':'13120012',
  'rule':a['policy'],
  'backfill':a['applied_ranges'],
  'after':new['corse_vs_bdr'],
}
if old_path.exists():
    old=json.loads(old_path.read_text())
    impact['before']=old['corse_vs_bdr']
    impact['corse_vs_bdr_unchanged']=old['corse_vs_bdr']==new['corse_vs_bdr']
    if not impact['corse_vs_bdr_unchanged']:
        raise SystemExit('Gardanne GMS backfill unexpectedly changed Corse/BdR aggregates')
else:
    impact['before']=None
    impact['corse_vs_bdr_unchanged']=None
Path('outputs/monthly-bdr-backfill-impact-2026-08.json').write_text(
    json.dumps(impact, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('Gardanne impact proof:', impact['corse_vs_bdr_unchanged'])
PY

npm install --no-save --no-package-lock playwright-core@1.55.0
python -m http.server 8765 --bind 127.0.0.1 >/tmp/a4c-monthly-http.log 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8765/widgets/bilan-territorial/index.html >/dev/null; then break; fi
  sleep 0.5
done
node scripts/browser_smoke_monthly_widget.mjs \
  --url 'http://127.0.0.1:8765/widgets/bilan-territorial/index.html?data=/outputs/monthly-territories-2026-08.json' \
  --output outputs/monthly-widget-browser-smoke-2026-08.json
kill "$server_pid" 2>/dev/null || true
trap - EXIT

cp /tmp/monthly-bdr-registry.json config/bdr_station_brands.json
rm -rf outputs/ufip outputs/c1
PYTHONPATH=. python scripts/audit_epci_monthly.py \
  --month "$MONTH" --epci-siren 242020105 --fuel SP95 --c2-data data.json \
  --output outputs/calvi-balagne-sp95-2026-08-audit.json \
  --markdown outputs/calvi-balagne-sp95-2026-08-audit.md

cp /tmp/monthly-bdr-registry.json config/bdr_station_brands.json
rm -rf outputs/ufip outputs/c1
PYTHONPATH=. python scripts/audit_monthly_territorial_coverage.py \
  --month "$MONTH" --c2-data data.json \
  --output outputs/monthly-territorial-coverage-2026-08-audit.json \
  --markdown outputs/monthly-territorial-coverage-2026-08-audit.md

python - <<'PY'
import json
from pathlib import Path
d=json.loads(Path('outputs/monthly-territories-2026-08.json').read_text())
m=d['meta']; a=d['internal_audit']['bdr_category_backfill']
lines=['# Contrôle territorial C2 V2 — août 2026','',
       '**Statut : VALIDÉ EN TEST sur la branche de travail — aucune promotion vers main/Pages/WordPress.**','',
       f"Moteur : {m['c2_engine']} ; C2 main de référence : {m['c2_main_sha_runtime']}.",
       f"Release C1 : {m['c1_release_tag']}.",
       f"Registre géographique : {m['geography_rows']} stations ; {m['epci_count_registry']} EPCI.",
       f"Rétro-propagation BdR bornée : {a['applied_station_days']} station-jours ; "
       f"{a['applied_ranges'][0]['station_id']} classé GMS du {a['applied_ranges'][0]['from']} au {a['applied_ranges'][0]['through']} "
       f"à partir de la classification vérifiée du {a['applied_ranges'][0]['classification_valid_from']}.",'']
for fuel in ('Gazole','SP95'):
    rows=[r for r in d['epci'] if r['fuel']==fuel]
    rank=[r for r in rows if r['rankable']]
    lines += [f'## {fuel}', f'EPCI présents : {len(rows)} ; classables : {len(rank)} ; hors classement : {len(rows)-len(rank)}.', '']
Path('outputs/monthly-territories-2026-08-summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
PY

# A real-shaped final receipt is created only in /tmp to test finalization and idempotence.
# Nothing under outputs/monthly-receipts is created or committed by this prototype run.
rm -rf /tmp/monthly-final-receipts && mkdir -p /tmp/monthly-final-receipts
TEST_RECEIPT=/tmp/monthly-final-receipts/2026-08.json
python scripts/write_monthly_receipt.py \
  --month "$MONTH" \
  --dataset outputs/monthly-territories-2026-08.json \
  --readiness outputs/monthly-readiness-2026-08.json \
  --source-guards outputs/monthly-source-guards-2026-08.json \
  --browser-smoke outputs/monthly-widget-browser-smoke-2026-08.json \
  --widget widgets/bilan-territorial/index.html \
  --geography config/corse_station_geography_2026.csv \
  --c2-business-receipt "$BUSINESS_RECEIPT" \
  --output "$TEST_RECEIPT"
test -s "$TEST_RECEIPT"
if python scripts/write_monthly_receipt.py \
  --month "$MONTH" \
  --dataset outputs/monthly-territories-2026-08.json \
  --readiness outputs/monthly-readiness-2026-08.json \
  --source-guards outputs/monthly-source-guards-2026-08.json \
  --browser-smoke outputs/monthly-widget-browser-smoke-2026-08.json \
  --widget widgets/bilan-territorial/index.html \
  --geography config/corse_station_geography_2026.csv \
  --c2-business-receipt "$BUSINESS_RECEIPT" \
  --output "$TEST_RECEIPT"; then
  echo 'Second monthly receipt write unexpectedly succeeded' >&2
  exit 1
fi

mkdir -p "$FEATURE_ROOT/outputs"
approved=(
  monthly-readiness-2026-08.json
  monthly-source-guards-2026-08.json
  monthly-territories-2026-08.json
  monthly-territories-2026-08-summary.md
  monthly-bdr-backfill-impact-2026-08.json
  monthly-widget-browser-smoke-2026-08.json
  calvi-balagne-sp95-2026-08-audit.json
  calvi-balagne-sp95-2026-08-audit.md
  monthly-territorial-coverage-2026-08-audit.json
  monthly-territorial-coverage-2026-08-audit.md
)
for f in "${approved[@]}"; do cp "outputs/$f" "$FEATURE_ROOT/outputs/$f"; done

cd "$FEATURE_ROOT"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
for f in "${approved[@]}"; do git add -f "outputs/$f"; done
if ! git diff --cached --quiet; then
  git commit -m "Validate August monthly prototype with bounded BDR backfill"
  git push origin HEAD:add-corse-station-geography-2026
fi
