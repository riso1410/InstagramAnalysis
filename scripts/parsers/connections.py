"""Social graph parser: every edge/event under connections/followers_and_following/
becomes one tidy row in connections.parquet (kind, username, name, ts, dt, href, ...).
Also keeps writing connections.json {followers, following} for the overview KPIs.

Two schema families are normalised here:
  * string_list_data lists (followers_N.json: username in value, title empty;
    following.json: username in the TITLE, no value key)
  * label_values event records (URL / Name / Username labels + top-level epoch-s
    timestamp) — blocked, unfollowed, removed suggestions, follow requests,
    restricted. restricted_profiles.json is a SINGLE dict record, not a list.
"""
import json, os
import pandas as pd

from .common import fix, load_json, first_list, add_time

META = {"key": "connections", "outputs": ["connections.parquet", "connections.json"]}

BASE = "connections/followers_and_following"

_MOJI = ("Ã", "Å¡", "Å½", "â€", "Ä\x8d", "ð\x9f")


def _fix(s):
    """ftfy first; if telltale mojibake survives (ftfy abstains on short ambiguous
    strings like 'Å¡.f.'), force the latin-1→utf-8 roundtrip — it only succeeds
    when the bytes really are valid UTF-8, so genuine 'Å'/'ð' names are safe."""
    s = fix(s)
    if isinstance(s, str) and any(t in s for t in _MOJI):
        try:
            s = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return s

# label_values-shaped files -> edge kind (source column keeps the file identity,
# e.g. to tell pending (still open) from recent (mostly approved) sent requests)
LV_FILES = [
    ("blocked_profiles.json", "blocked"),
    ("recently_unfollowed_profiles.json", "unfollowed"),
    ("removed_suggestions.json", "removed_suggestion"),
    ("follow_requests_you've_received.json", "request_received"),
    ("pending_follow_requests.json", "request_sent"),
    ("recent_follow_requests.json", "request_sent"),
    ("restricted_profiles.json", "restricted"),
]


def _records(obj):
    """Entry list whether the file is a bare list, a wrapped dict, or ONE record."""
    if obj is None:
        return []
    if isinstance(obj, dict) and ("label_values" in obj or "string_list_data" in obj):
        return [obj]                       # single-record file (restricted_profiles)
    return first_list(obj)


def _lv_rows(obj, kind, source):
    rows = []
    for e in _records(obj):
        if not isinstance(e, dict):
            continue
        name = username = href = None
        for it in e.get("label_values") or []:
            lb, v = it.get("label"), it.get("value")
            if not isinstance(v, str) or not v:
                continue
            if lb == "Name":
                name = _fix(v)
            elif lb == "Username":
                username = _fix(v)
            elif lb == "URL":
                href = fix(v)
        rows.append({"kind": kind, "source": source, "username": username,
                     "name": name, "ts": e.get("timestamp"), "href": href})
    return rows


def _sld_rows(obj, kind, source):
    rows = []
    for e in _records(obj):
        if not isinstance(e, dict):
            continue
        title = _fix(e.get("title") or "")
        for s in e.get("string_list_data") or [{}]:
            username = _fix(s.get("value") or "") or title or None
            rows.append({"kind": kind, "source": source, "username": username,
                         "name": None, "ts": s.get("timestamp") or e.get("timestamp"),
                         "href": s.get("href")})
    return rows


def parse(env):
    raw, out, tz = env["RAW"], env["OUT"], env["TZ"]
    rows = []

    # followers can be sharded into followers_1.json, followers_2.json, ...
    fdir = os.path.join(raw, BASE)
    shards = sorted(f for f in os.listdir(fdir)) if os.path.isdir(fdir) else []
    for fname in shards:
        if fname.startswith("followers_") and fname.endswith(".json"):
            rows += _sld_rows(load_json(f"{BASE}/{fname}", raw), "follower", fname[:-5])
    rows += _sld_rows(load_json(f"{BASE}/following.json", raw), "following", "following")
    for fname, kind in LV_FILES:
        rows += _lv_rows(load_json(f"{BASE}/{fname}", raw), kind, fname[:-5])
    if not rows:
        print("  connections: no files found")
        return {}

    df = pd.DataFrame(rows)
    df["ts"] = pd.to_numeric(df["ts"], errors="coerce")
    df.loc[df["ts"] == 0, "ts"] = float("nan")     # timestamp 0 == unset
    if df["ts"].notna().all():
        df = add_time(df, "ts", tz, unit="s")      # epoch SECONDS here (messages are ms)
    else:                                          # null-safe replica of add_time
        dt = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce").dt.tz_convert(tz)
        df["dt"] = dt
        df["date"] = dt.dt.date
        df["year"] = dt.dt.year.astype("Int64")
        df["month"] = dt.dt.month.astype("Int64")
        df["ym"] = dt.dt.strftime("%Y-%m")
        df["day"] = dt.dt.day.astype("Int64")
        df["hour"] = dt.dt.hour.astype("Int64")
        df["weekday"] = dt.dt.weekday.astype("Int64")
        df["weekday_name"] = dt.dt.day_name()
        df["week"] = dt.dt.isocalendar().week.astype("Int64")
        df["is_weekend"] = df["weekday"] >= 5

    df.to_parquet(f"{out}/connections.parquet", index=False)

    counts = df["kind"].value_counts().to_dict()
    foll = {"followers": int(counts.get("follower", 0)),
            "following": int(counts.get("following", 0))}
    with open(f"{out}/connections.json", "w") as fh:
        json.dump(foll, fh)

    stats = {**foll, "edges": int(len(df)),
             **{k: int(v) for k, v in sorted(counts.items()) if k not in ("follower", "following")}}
    print(f"  connections: {stats}")
    return stats
