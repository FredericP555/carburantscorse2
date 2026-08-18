#!/usr/bin/env python3
"""Safe one-time migrations for the carburantscorse2 dashboard shell.

The legacy embedded DATA and MARGES_GZ objects are deliberately kept as a fallback.
The migration makes them mutable, loads data.json before the first chart render, and
makes the period slider depend on the chart width/history rather than a frozen June-2026
month count. It does not change the underlying chart series or editorial content.
"""
from __future__ import annotations

import argparse
from pathlib import Path

LOADER = r'''
async function loadDashboardData(){
  try{
    const response=await fetch('./data.json',{cache:'no-store'});
    if(!response.ok) throw new Error('HTTP '+response.status);
    const payload=await response.json();
    if(!payload||!payload.DATA||!payload.MARGES_GZ){
      throw new Error('structure data.json invalide');
    }
    DATA=payload.DATA;
    MARGES_GZ=payload.MARGES_GZ;
    window.A4C_DATA_META=payload.meta||{};
  }catch(err){
    // Résilience : si data.json est momentanément indisponible, le tableau de bord
    // continue avec les séries historiques embarquées dans cette page.
    console.warn('A4C: data.json indisponible, repli sur les données embarquées.',err);
  }
}
'''.strip()

RESPONSIVE_HELPERS = r'''
let currentMonths=12;  // 12 derniers mois par défaut quand le graphique est étroit
function usePeriodSlider(){
  const area=document.getElementById('charts-area');
  const width=area&&area.clientWidth?area.clientWidth:window.innerWidth;
  return width<850;
}
function getHistoryMonths(){
  const raw=DATA&&DATA.gazole&&DATA.gazole.sp95&&DATA.gazole.sp95.daily?DATA.gazole.sp95.daily.all:[];
  if(!raw||raw.length<2)return 12;
  const first=new Date(raw[0].date),last=new Date(raw[raw.length-1].date);
  return Math.max(12,(last.getFullYear()-first.getFullYear())*12+(last.getMonth()-first.getMonth())+1);
}
function syncPeriodSliderRange(){
  const sl=document.getElementById('slider-mois');
  if(!sl)return;
  const total=getHistoryMonths();
  sl.max=String(total);
  if(currentMonths>total){currentMonths=total;sl.value=String(total);}
}
'''.strip()


def migrate(text: str) -> tuple[str, bool]:
    original = text

    if 'const DATA=' in text:
        text = text.replace('const DATA=', 'let DATA=', 1)
    elif 'let DATA=' not in text:
        raise RuntimeError('DATA declaration not found')

    if 'const MARGES_GZ=' in text:
        text = text.replace('const MARGES_GZ=', 'let MARGES_GZ=', 1)
    elif 'let MARGES_GZ=' not in text:
        raise RuntimeError('MARGES_GZ declaration not found')

    if 'async function loadDashboardData()' not in text:
        marker = "window.addEventListener('load',function(){"
        if marker not in text:
            raise RuntimeError('window load initializer not found')
        replacement = LOADER + "\n\nwindow.addEventListener('load',async function(){\n  await loadDashboardData();"
        text = text.replace(marker, replacement, 1)
    elif "window.addEventListener('load',async function(){\n  await loadDashboardData();" not in text:
        raise RuntimeError('loader exists but is not wired before initial render')

    old_helpers = (
        "let currentMonths=12;  // nb de mois affichés sur mobile vertical (12 par défaut)\n"
        "function isMobilePortrait(){return window.innerWidth<700 && window.innerHeight>window.innerWidth;}"
    )
    if old_helpers in text:
        text = text.replace(old_helpers, RESPONSIVE_HELPERS, 1)
    elif 'function usePeriodSlider()' not in text or 'function getHistoryMonths()' not in text:
        raise RuntimeError('period slider helper block not found')

    text = text.replace('isMobilePortrait()', 'usePeriodSlider()')
    text = text.replace(
        'const totalMonths=54; // janv 2022 -> juin 2026 ~ 54 mois',
        'const totalMonths=getHistoryMonths();',
        1,
    )

    load_marker = 'await loadDashboardData();\n  updateSliderVisibility();'
    if load_marker in text:
        text = text.replace(
            load_marker,
            'await loadDashboardData();\n  syncPeriodSliderRange();\n  updateSliderVisibility();',
            1,
        )
    elif 'await loadDashboardData();\n  syncPeriodSliderRange();\n  updateSliderVisibility();' not in text:
        raise RuntimeError('period slider range is not synchronized after data load')

    return text, text != original


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('path', nargs='?', default='index.html')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    path = Path(args.path)
    source = path.read_text(encoding='utf-8')
    migrated, changed = migrate(source)

    if migrated.count('let DATA=') != 1:
        raise RuntimeError('expected exactly one let DATA declaration')
    if migrated.count('let MARGES_GZ=') != 1:
        raise RuntimeError('expected exactly one let MARGES_GZ declaration')
    if migrated.count("fetch('./data.json'") != 1:
        raise RuntimeError('expected exactly one data.json fetch')
    if migrated.count('await loadDashboardData();') != 1:
        raise RuntimeError('expected exactly one pre-render loader call')
    if migrated.count('syncPeriodSliderRange();') != 1:
        raise RuntimeError('expected exactly one period-range synchronization call')
    if 'isMobilePortrait()' in migrated or 'const totalMonths=54' in migrated:
        raise RuntimeError('legacy frozen mobile-period logic still present')

    if args.check:
        if changed:
            raise SystemExit('index.html still needs the dashboard-shell migration')
        print('index.html dashboard-shell migration: OK')
        return

    if changed:
        path.write_text(migrated, encoding='utf-8')
        print('index.html migrated: data.json loader + responsive data-driven period slider')
    else:
        print('index.html already migrated; no change')


if __name__ == '__main__':
    main()
