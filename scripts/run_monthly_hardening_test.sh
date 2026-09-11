#!/usr/bin/env bash
set -euo pipefail

FEATURE_ROOT="${GITHUB_WORKSPACE:-$(pwd)}"
INTEGRATED=/tmp/monthly-integrated
MONTH=2026-08
AS_OF=2026-09-11

cd "$FEATURE_ROOT"
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
  scripts/check_monthly_readiness.py
  scripts/validate_monthly_source_guards.py
  scripts/write_monthly_receipt.py
  scripts/audit_epci_monthly.py
  scripts/audit_monthly_territorial_coverage.py
  scripts/validate_monthly_widget_contract.py
  scripts/browser_smoke_monthly_widget.mjs
  widgets/bilan-territorial/index.html
)
tar cf - "${monthly_files[@]}" | tar xf - -C "$INTEGRATED"

cd "$INTEGRATED"
python -m pip install --disable-pip-version-check -r requirements.lock.txt
python -m unittest tests.test_ci_supply_chain_contracts -v

# Consume a real successful C2 publication receipt and prove that it still matches current
# repository data + current public Pages. We intentionally do not require receipt.commit == HEAD:
# the existing verifier proves content by SHA-256 and Pages identity, which is stronger when main
# has advanced without changing data.json/homepage-summary.json.
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

# Negative readiness cases: incomplete calendar month, stale/tampered C2 state, valid final receipt,
# and corrupt final receipt must all block generation.
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

# All scripts below run in this disposable main-based worktree. Production helper files may mutate
# here, but only explicitly approved monthly outputs are copied back to the feature branch.
cp config/bdr_station_brands.json /tmp/monthly-bdr-registry.json
python scripts/validate_monthly_source_guards.py \
  --month "$MONTH" --c2-data data.json \
  --output outputs/monthly-source-guards-2026-08.json
cp /tmp/monthly-bdr-registry.json config/bdr_station_brands.json
rm -rf outputs/ufip outputs/c1

PYTHONPATH=. python scripts/build_monthly_territorial.py \
  --month "$MONTH" --c2-data data.json \
  --output outputs/monthly-territories-2026-08.json
python scripts/validate_monthly_widget_contract.py \
  --data outputs/monthly-territories-2026-08.json \
  --widget widgets/bilan-territorial/index.html

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
m=d['meta']
lines=['# Contrôle territorial C2 V2 — août 2026','',
       f"Moteur : {m['c2_engine']} ; C2 main : {m['c2_main_sha_runtime']}.",
       f"Release C1 : {m['c1_release_tag']}.",
       f"Registre géographique : {m['geography_rows']} stations ; {m['epci_count_registry']} EPCI.",'']
for fuel in ('Gazole','SP95'):
    rows=[r for r in d['epci'] if r['fuel']==fuel]
    rank=[r for r in rows if r['rankable']]
    lines += [f'## {fuel}', f'EPCI présents : {len(rows)} ; classables : {len(rank)} ; hors classement : {len(rows)-len(rank)}.', '']
Path('outputs/monthly-territories-2026-08-summary.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
PY

mkdir -p /tmp/monthly-final-receipts
FINAL_RECEIPT=/tmp/monthly-final-receipts/2026-08.json
python scripts/write_monthly_receipt.py \
  --month "$MONTH" \
  --dataset outputs/monthly-territories-2026-08.json \
  --readiness outputs/monthly-readiness-2026-08.json \
  --source-guards outputs/monthly-source-guards-2026-08.json \
  --browser-smoke outputs/monthly-widget-browser-smoke-2026-08.json \
  --widget widgets/bilan-territorial/index.html \
  --geography config/corse_station_geography_2026.csv \
  --c2-business-receipt "$BUSINESS_RECEIPT" \
  --output "$FINAL_RECEIPT"
if python scripts/write_monthly_receipt.py \
  --month "$MONTH" \
  --dataset outputs/monthly-territories-2026-08.json \
  --readiness outputs/monthly-readiness-2026-08.json \
  --source-guards outputs/monthly-source-guards-2026-08.json \
  --browser-smoke outputs/monthly-widget-browser-smoke-2026-08.json \
  --widget widgets/bilan-territorial/index.html \
  --geography config/corse_station_geography_2026.csv \
  --c2-business-receipt "$BUSINESS_RECEIPT" \
  --output "$FINAL_RECEIPT"; then
  echo 'Second receipt write unexpectedly succeeded' >&2
  exit 1
fi
cp "$FINAL_RECEIPT" outputs/monthly-final-receipt-test-2026-08.json

# Copy only controlled test evidence back. Mutable C2 helper inputs and node_modules stay disposable.
mkdir -p "$FEATURE_ROOT/outputs"
approved=(
  monthly-readiness-2026-08.json
  monthly-source-guards-2026-08.json
  monthly-territories-2026-08.json
  monthly-territories-2026-08-summary.md
  monthly-widget-browser-smoke-2026-08.json
  monthly-final-receipt-test-2026-08.json
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
  git commit -m "Revalidate hardened August monthly prototype"
  git push origin HEAD:add-corse-station-geography-2026
fi
