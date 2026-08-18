#!/usr/bin/env python3
"""One-time safe migration of index.html from embedded data to data.json.

The legacy embedded DATA and MARGES_GZ objects are deliberately kept as a fallback.
The migration only makes them mutable, loads data.json before the first chart render,
and leaves the existing UI/CSS/chart code unchanged.
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

    return text, text != original


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('path', nargs='?', default='index.html')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()

    path = Path(args.path)
    source = path.read_text(encoding='utf-8')
    migrated, changed = migrate(source)

    # Structural invariants: exactly one mutable declaration and one loader call.
    if migrated.count('let DATA=') != 1:
        raise RuntimeError('expected exactly one let DATA declaration')
    if migrated.count('let MARGES_GZ=') != 1:
        raise RuntimeError('expected exactly one let MARGES_GZ declaration')
    if migrated.count("fetch('./data.json'") != 1:
        raise RuntimeError('expected exactly one data.json fetch')
    if migrated.count('await loadDashboardData();') != 1:
        raise RuntimeError('expected exactly one pre-render loader call')

    if args.check:
        if changed:
            raise SystemExit('index.html still needs the data-loader migration')
        print('index.html data-loader migration: OK')
        return

    if changed:
        path.write_text(migrated, encoding='utf-8')
        print('index.html migrated to data.json with embedded fallback')
    else:
        print('index.html already migrated; no change')


if __name__ == '__main__':
    main()
