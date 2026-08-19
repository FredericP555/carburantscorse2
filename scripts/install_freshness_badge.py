#!/usr/bin/env python3
"""Install the shared freshness badge script in the dashboard HTML, idempotently."""
from __future__ import annotations

import argparse
from pathlib import Path

TAG = '<script src="freshness.js"></script>'


def install(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if TAG in text:
        return False
    marker = "</body>"
    if marker not in text:
        raise SystemExit(f"{path}: </body> marker not found")
    text = text.replace(marker, f"{TAG}\n{marker}", 1)
    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="index.html")
    args = parser.parse_args()
    changed = install(Path(args.path))
    print("freshness badge installed" if changed else "freshness badge already installed")


if __name__ == "__main__":
    main()
