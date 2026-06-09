#!/usr/bin/env python3
"""
00_extract.py — extract message & activity JSON from Instagram export ZIP(s).

Auto-detects any Instagram export archives so anyone can drop in their own data:
  - explicit paths:   python scripts/00_extract.py path/to/a.zip path/to/b.zip
  - a folder:         python scripts/00_extract.py --dir ~/Downloads
  - nothing (default): every *.zip in the project root

Extracts only *.json (skips gigabytes of media) into data/raw/, replacing any prior export.
Cross-platform (uses the stdlib zipfile, not the `unzip` binary).
"""
import sys, os, glob, zipfile, shutil, argparse

RAW = "data/raw"

def find_zips(args):
    if args.paths:
        zips = []
        for p in args.paths:
            if os.path.isdir(p):
                zips += glob.glob(os.path.join(p, "*.zip"))
            else:
                zips.append(p)
        return zips
    if args.dir:
        return sorted(glob.glob(os.path.join(args.dir, "*.zip")))
    # default: any zip in cwd, preferring instagram-named ones
    z = sorted(glob.glob("*.zip"))
    ig = [p for p in z if "instagram" in os.path.basename(p).lower()]
    return ig or z

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="zip files or folders")
    ap.add_argument("--dir", help="folder to scan for *.zip")
    ap.add_argument("--keep", action="store_true", help="do not wipe data/raw first")
    args = ap.parse_args()

    zips = [p for p in find_zips(args) if p.lower().endswith(".zip") and os.path.exists(p)]
    if not zips:
        sys.exit("No Instagram export .zip found. Pass paths, --dir, or place zips in the project root.")

    if not args.keep and os.path.isdir(RAW):
        shutil.rmtree(RAW)
    os.makedirs(RAW, exist_ok=True)

    total = 0
    for zp in zips:
        print(f"extracting JSON from {os.path.basename(zp)} ...")
        n = 0
        with zipfile.ZipFile(zp) as z:
            for info in z.infolist():
                if info.filename.endswith(".json") and not info.is_dir():
                    z.extract(info, RAW)
                    n += 1
        print(f"  {n:,} json files")
        total += n
    has_msgs = len(glob.glob(f"{RAW}/**/messages/inbox/*/message_*.json", recursive=True))
    print(f"done: {total:,} json files in {RAW}/  ({has_msgs} message files)")
    if has_msgs == 0:
        sys.exit("WARNING: no message files found — is this an Instagram export?")

if __name__ == "__main__":
    main()
