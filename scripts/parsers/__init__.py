"""Modular export parsers.

Each parser module owns one data domain of the Instagram export and turns its raw
JSON into tidy tables under data/clean/. `run()` executes every registered parser;
a parser whose source files are missing simply produces nothing (exports differ
between accounts and download options), and one parser crashing never blocks the
rest.

Adding a parser = drop `parsers/<domain>.py` with:

    META = {"key": "<domain>", "outputs": ["<file>.parquet", ...]}
    def parse(env) -> dict:   # env = {"RAW", "OUT", "TZ"}; returns summary stats

and list it in PARSERS below. Keep parsers config-independent (no filtering here) —
user config (exclude_people, date window, privacy) is applied later, at analysis
time, so config changes never force a re-parse.
"""
import os, traceback

from . import messages, activity, connections

PARSERS = [
    messages,      # messages/reactions/threads/meta — must run first (self identity)
    activity,
    connections,
]


def run(raw="data/raw", out="data/clean", tz="Europe/Bratislava"):
    os.makedirs(out, exist_ok=True)
    env = {"RAW": raw, "OUT": out, "TZ": tz}
    stats = {}
    for mod in PARSERS:
        key = getattr(mod, "META", {}).get("key", mod.__name__.rsplit(".", 1)[-1])
        print(f"== parsing {key} ==")
        try:
            stats[key] = mod.parse(env) or {}
        except Exception:
            print(f"[error] parser {key} failed:")
            traceback.print_exc()
    return stats
