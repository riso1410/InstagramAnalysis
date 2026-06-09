#!/usr/bin/env python3
"""
01_parse.py — Parse the Instagram data export into tidy analysis-ready tables.

Thin orchestrator over the modular `parsers/` package (one module per export
domain — messages, activity, connections, ...). Handles the classic Instagram
mojibake (latin-1/UTF-8 double encoding, repaired with ftfy) and timezone
conversion to the configured local timezone.

Outputs land in data/clean/ — see each parser's META["outputs"].
"""
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _config import load_config
import parsers

if __name__ == "__main__":
    cfg = load_config()
    stats = parsers.run(raw="data/raw", out="data/clean", tz=cfg["timezone"])
    print("\n== parse summary ==")
    print(json.dumps({k: v for k, v in stats.items() if v}, indent=2, default=str))
