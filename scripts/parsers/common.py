"""Shared helpers for the export parsers: mojibake repair, JSON loading,
Instagram's string_list_data/string_map_data shapes, and datetime engineering.
"""
import json, os
import pandas as pd
import ftfy

RAW = "data/raw"
OUT = "data/clean"


def fix(s):
    """Repair Instagram's Latin-1/UTF-8 double encoding using ftfy."""
    if not isinstance(s, str):
        return s
    return ftfy.fix_text(s)


def load_json(path, raw=RAW):
    """Load a JSON file relative to the raw export root; None when absent/broken."""
    try:
        return json.load(open(os.path.join(raw, path), encoding="utf-8"))
    except Exception:
        return None


def first_list(obj):
    """Instagram wraps most exports as {"some_key": [entries]} or a bare list."""
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        return next((v for v in obj.values() if isinstance(v, list)), [])
    return []


def sld_entries(obj):
    """Yield flattened string_list_data records: {title, value, href, ts}.

    Handles the canonical connections/searches shape:
        {"title": ..., "string_list_data": [{"href", "value", "timestamp"}]}
    """
    for e in first_list(obj):
        if not isinstance(e, dict):
            continue
        title = fix(e.get("title") or "")
        for s in e.get("string_list_data") or [{}]:
            yield {
                "title": title,
                "value": fix(s.get("value") or "") or title,
                "href": s.get("href"),
                "ts": s.get("timestamp") or e.get("timestamp"),
            }


def smd_value(entry, *labels):
    """Pull a value out of a string_map_data dict by label (first match wins)."""
    smd = entry.get("string_map_data") or {}
    for lb in labels:
        v = smd.get(lb)
        if isinstance(v, dict):
            out = v.get("value") or v.get("href") or v.get("timestamp")
            if out not in (None, ""):
                return fix(out) if isinstance(out, str) else out
    return None


def label_value(entry, label):
    """Pull a value from the label_values list shape (ads/likes files)."""
    for it in entry.get("label_values") or []:
        if it.get("label") == label:
            return fix(it.get("value")) if isinstance(it.get("value"), str) else it.get("value")
    return None


def add_time(frame, col, tz, unit="ms"):
    """Standard datetime engineering: local-tz dt + calendar columns."""
    dt = pd.to_datetime(frame[col], unit=unit, utc=True).dt.tz_convert(tz)
    frame["dt"] = dt
    frame["date"] = dt.dt.date
    frame["year"] = dt.dt.year
    frame["month"] = dt.dt.month
    frame["ym"] = dt.dt.strftime("%Y-%m")
    frame["day"] = dt.dt.day
    frame["hour"] = dt.dt.hour
    frame["weekday"] = dt.dt.weekday          # 0=Mon
    frame["weekday_name"] = dt.dt.day_name()
    frame["week"] = dt.dt.isocalendar().week.astype(int)
    frame["is_weekend"] = frame["weekday"] >= 5
    return frame
