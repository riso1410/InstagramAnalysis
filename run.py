#!/usr/bin/env python3
"""
run.py — one command to turn an Instagram export into the interactive dashboard.

    python run.py                       # auto-detect *.zip in this folder
    python run.py a.zip b.zip           # explicit archives
    python run.py --dir ~/Downloads     # scan a folder for the export zips
    python run.py --skip-sentiment      # skip the transformer step (much faster)

Runs: extract -> parse -> sentiment -> analysis -> build dashboard.
Output: output/Instagram_Dashboard.html  (self-contained, opens offline).

Anyone can swap in their own data: just point this at your Instagram export ZIPs.
The account owner is auto-detected, so no per-user configuration is needed.
"""
import sys, os, subprocess, argparse, time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # use the same interpreter (run with .venv/bin/python)

def step(title, cmd):
    print(f"\n\033[1m== {title} ==\033[0m")
    t = time.time()
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        sys.exit(f"step failed: {title}")
    print(f"   ({time.time()-t:.1f}s)")

def main():
    ap = argparse.ArgumentParser(description="Build the Instagram analysis dashboard from an export.")
    ap.add_argument("paths", nargs="*", help="export .zip files (or folders)")
    ap.add_argument("--dir", help="folder to scan for the export zips")
    ap.add_argument("--skip-sentiment", action="store_true",
                    help="skip the XLM-RoBERTa sentiment model (sentiment sections are omitted)")
    args = ap.parse_args()

    extract = [PY, "scripts/00_extract.py"] + args.paths
    if args.dir:
        extract += ["--dir", args.dir]

    step("1/5 extract JSON from export", extract)
    step("2/5 parse & clean", [PY, "scripts/01_parse.py"])
    if args.skip_sentiment:
        # ensure stale sentiment from a previous dataset isn't reused
        sp = os.path.join(HERE, "data/clean/sentiment.parquet")
        if os.path.exists(sp):
            os.remove(sp)
        print("\n== 3/5 sentiment: SKIPPED (--skip-sentiment) ==")
    else:
        step("3/5 sentiment (XLM-RoBERTa)", [PY, "scripts/02_sentiment.py"])
    step("4/5 analysis & ML features", [PY, "scripts/03_analysis.py"])
    step("5/5 build dashboard", [PY, "scripts/04_build_dashboard.py"])

    out = os.path.join(HERE, "output/Instagram_Dashboard.html")
    print(f"\n\033[1m✓ done\033[0m  →  {out}")
    print("  open it with:  open output/Instagram_Dashboard.html")

if __name__ == "__main__":
    main()
