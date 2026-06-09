#!/usr/bin/env python3
"""
03_analysis.py — orchestrator for the modular EDA + ML pipeline.

Thin entry point: it builds the shared analysis context and runs every registered
section module (see scripts/analysis/), then writes output/data.json for the dashboard.

The actual computations live in scripts/analysis/sections/*.py — one module per
section, each a `compute(ctx, D)` function. Add an analysis by dropping a module
there and registering it in scripts/analysis/__init__.py:SECTIONS.
"""
import sys, os, json, warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # make scripts/ importable

from analysis import run
from analysis.text_utils import jnum

OUT = "output"


def main():
    os.makedirs(OUT, exist_ok=True)
    ctx, D = run()
    out_path = f"{OUT}/data.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(D, fh, ensure_ascii=False, default=jnum)
    print(f"\nwrote {out_path}  ({os.path.getsize(out_path)/1024:.0f} KB)")
    print("sections:", list(D.keys()))


if __name__ == "__main__":
    main()
