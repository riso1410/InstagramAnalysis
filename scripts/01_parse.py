#!/usr/bin/env python3
"""
01_parse.py — Parse Instagram data export into tidy analysis-ready tables.

Handles the classic Instagram mojibake (latin-1 / UTF-8 double-encoding),
timezone conversion to Europe/Bratislava, and extracts messages, reactions,
shares, media flags, and the rich activity data (likes, comments, follows...).

Outputs (data/clean/):
  messages.parquet      one row per message (inbox + message_requests)
  reactions.parquet     one row per reaction event
  threads.parquet       one row per conversation thread (metadata)
  activity_*.parquet     various activity timelines
  meta.json             top-level summary + self identity
"""
import json, glob, os, re, sys
from collections import Counter, defaultdict
import pandas as pd
import numpy as np

RAW = "data/raw"
OUT = "data/clean"
TZ = "Europe/Bratislava"
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- mojibake fix
import ftfy

def fix(s):
    """Repair Instagram's Latin-1/UTF-8 double encoding using ftfy."""
    if not isinstance(s, str):
        return s
    return ftfy.fix_text(s)

# ---------------------------------------------------------------- message parse
def message_files():
    inbox = glob.glob(f"{RAW}/**/messages/inbox/*/message_*.json", recursive=True)
    reqs  = glob.glob(f"{RAW}/**/messages/message_requests/*/message_*.json", recursive=True)
    return inbox, reqs

def thread_id_from_path(path):
    # .../inbox/<thread_dir>/message_N.json  -> <thread_dir>
    return os.path.basename(os.path.dirname(path))

def parse_messages():
    inbox, reqs = message_files()
    rows = []
    react_rows = []
    thread_meta = {}
    file_groups = defaultdict(list)
    for f in inbox: file_groups[("inbox", thread_id_from_path(f))].append(f)
    for f in reqs:  file_groups[("request", thread_id_from_path(f))].append(f)

    participant_counter = Counter()

    for (kind, tid), files in file_groups.items():
        msgs = []
        title = None
        participants = None
        is_still = None
        for f in sorted(files):
            try:
                d = json.load(open(f))
            except Exception:
                continue
            if title is None:
                title = fix(d.get("title"))
            if participants is None:
                participants = [fix(p.get("name", "")) for p in d.get("participants", [])]
            if is_still is None:
                is_still = d.get("is_still_participant")
            msgs.extend(d.get("messages", []))

        participants = participants or []
        n_part = len(participants)
        is_group = n_part > 2 or (kind == "request")  # treat request threads explicitly
        for p in participants:
            participant_counter[p] += 1

        thread_meta[(kind, tid)] = {
            "thread_id": tid,
            "kind": kind,
            "title": title,
            "n_participants": n_part,
            "is_group": n_part > 2,
            "participants": "|".join(participants),
            "n_messages": len(msgs),
            "is_still_participant": is_still,
        }

        for m in msgs:
            sender = fix(m.get("sender_name", ""))
            content = fix(m.get("content")) if m.get("content") is not None else None
            ts = m.get("timestamp_ms")
            reacts = m.get("reactions") or []
            share = m.get("share") or {}
            row = {
                "thread_id": tid,
                "thread_title": title,
                "kind": kind,
                "is_group": n_part > 2,
                "n_participants": n_part,
                "sender": sender,
                "timestamp_ms": ts,
                "content": content,
                "has_text": bool(content and content.strip()),
                "n_chars": len(content) if content else 0,
                "n_words": len(content.split()) if content else 0,
                "has_photo": "photos" in m,
                "n_photos": len(m.get("photos", [])) if "photos" in m else 0,
                "has_video": "videos" in m,
                "has_audio": "audio_files" in m,
                "has_gif": "gifs" in m,
                "has_file": "files" in m,
                "has_share": bool(share),
                "share_link": fix(share.get("link")) if share else None,
                "share_owner": fix(share.get("original_content_owner")) if share else None,
                "is_call": m.get("call_duration") is not None,
                "call_duration": m.get("call_duration"),
                "is_unsent": bool(m.get("is_unsent")),
                "n_reactions": len(reacts),
            }
            rows.append(row)
            for r in reacts:
                react_rows.append({
                    "thread_id": tid,
                    "thread_title": title,
                    "kind": kind,
                    "is_group": n_part > 2,
                    "reactor": fix(r.get("actor", "")),
                    "emoji": fix(r.get("reaction", "")),
                    "target_sender": sender,
                    "react_ts": r.get("timestamp"),
                    "msg_ts_ms": ts,
                })

    df = pd.DataFrame(rows)
    rx = pd.DataFrame(react_rows)
    tm = pd.DataFrame(list(thread_meta.values()))

    # self = the participant present in the most threads (the account owner)
    self_name = participant_counter.most_common(1)[0][0]

    # ---- datetime engineering (UTC ms -> Europe/Bratislava local) ----
    def add_time(frame, col):
        dt = pd.to_datetime(frame[col], unit="ms", utc=True).dt.tz_convert(TZ)
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

    df = df[df["timestamp_ms"].notna()].copy()
    df = add_time(df, "timestamp_ms")
    df["is_self"] = df["sender"] == self_name
    df["direction"] = np.where(df["is_self"], "sent", "received")
    df = df.sort_values("dt").reset_index(drop=True)

    if not rx.empty:
        rx = rx[rx["react_ts"].notna()].copy()
        rdt = pd.to_datetime(rx["react_ts"], unit="s", utc=True).dt.tz_convert(TZ)
        rx["dt"] = rdt
        rx["ym"] = rdt.dt.strftime("%Y-%m")
        rx["reactor_is_self"] = rx["reactor"] == self_name

    df.to_parquet(f"{OUT}/messages.parquet", index=False)
    rx.to_parquet(f"{OUT}/reactions.parquet", index=False)
    tm.to_parquet(f"{OUT}/threads.parquet", index=False)

    print(f"  messages : {len(df):,} rows -> messages.parquet")
    print(f"  reactions: {len(rx):,} rows -> reactions.parquet")
    print(f"  threads  : {len(tm):,} rows -> threads.parquet")
    print(f"  self     : {self_name!r}")
    print(f"  date range: {df['dt'].min()}  ->  {df['dt'].max()}")
    return df, self_name

# ---------------------------------------------------------------- activity data
def load_json(path):
    try:
        return json.load(open(os.path.join(RAW, path)))
    except Exception:
        return None

def harvest_timestamped(obj, label):
    """Recursively pull (timestamp, title/value) pairs from Instagram activity JSON."""
    out = []
    def walk(o):
        if isinstance(o, dict):
            ts = o.get("timestamp")
            if ts and isinstance(ts, (int, float)):
                title = o.get("title") or o.get("value") or ""
                # string_map_data style
                href = None
                smd = o.get("string_list_data")
                if isinstance(smd, list) and smd:
                    href = smd[0].get("href")
                    if not ts:
                        ts = smd[0].get("timestamp")
                out.append({"ts": ts, "title": fix(title), "href": href, "kind": label})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    return out

def parse_activity():
    """Build a unified activity timeline + a few specific tables."""
    specs = {
        "liked_posts":   "your_instagram_activity/likes/liked_posts.json",
        "liked_comments":"your_instagram_activity/likes/liked_comments.json",
        "post_comments": "your_instagram_activity/comments/post_comments_1.json",
        "reels_comments":"your_instagram_activity/comments/reels_comments.json",
        "posts_viewed":  "ads_information/ads_and_topics/posts_viewed.json",
        "videos_watched":"ads_information/ads_and_topics/videos_watched.json",
        "ads_viewed":    "ads_information/ads_and_topics/ads_viewed.json",
        "stories_viewed":"your_instagram_activity/story_interactions/stories_viewed.json",
        "story_likes":   "your_instagram_activity/story_interactions/story_likes.json",
        "polls":         "your_instagram_activity/story_interactions/polls.json",
        "saved_posts":   "your_instagram_activity/saved/saved_posts.json",
        "own_posts":     "your_instagram_activity/media/posts_1.json",
        "own_stories":   "your_instagram_activity/media/stories.json",
        "searches":      "logged_information/recent_searches/recent_searches.json",
        "profile_searches":"logged_information/recent_searches/profile_searches.json",
    }
    all_rows = []
    for label, path in specs.items():
        obj = load_json(path)
        if obj is None:
            continue
        rows = harvest_timestamped(obj, label)
        all_rows.extend(rows)
        print(f"  activity[{label}]: {len(rows):,}")
    if not all_rows:
        print("  no activity timestamps harvested")
        return
    a = pd.DataFrame(all_rows)
    a = a[a["ts"] > 0].copy()
    dt = pd.to_datetime(a["ts"], unit="s", utc=True).dt.tz_convert(TZ)
    a["dt"] = dt
    a["date"] = dt.dt.date
    a["year"] = dt.dt.year
    a["ym"] = dt.dt.strftime("%Y-%m")
    a["hour"] = dt.dt.hour
    a["weekday"] = dt.dt.weekday
    a = a.sort_values("dt").reset_index(drop=True)
    a.to_parquet(f"{OUT}/activity.parquet", index=False)
    print(f"  activity timeline: {len(a):,} events -> activity.parquet")

    # followers / following counts
    foll = {}
    fobj = load_json("connections/followers_and_following/following.json")
    fwr  = load_json("connections/followers_and_following/followers_1.json")
    def count_conn(o):
        if o is None: return 0
        n = 0
        def walk(x):
            nonlocal n
            if isinstance(x, dict):
                if "string_list_data" in x: n += 1
                for v in x.values(): walk(v)
            elif isinstance(x, list):
                for v in x: walk(v)
        walk(o); return n
    foll["following"] = count_conn(fobj)
    foll["followers"] = count_conn(fwr)
    with open(f"{OUT}/connections.json", "w") as fh:
        json.dump(foll, fh)
    print(f"  connections: {foll}")

# ---------------------------------------------------------------- main
if __name__ == "__main__":
    print("== parsing messages ==")
    df, self_name = parse_messages()
    print("== parsing activity ==")
    parse_activity()

    meta = {
        "self_name": self_name,
        "n_messages": int(len(df)),
        "n_text_messages": int(df["has_text"].sum()),
        "n_threads": int(df["thread_id"].nunique()),
        "date_min": str(df["dt"].min()),
        "date_max": str(df["dt"].max()),
        "timezone": TZ,
    }
    with open(f"{OUT}/meta.json", "w") as fh:
        json.dump(meta, fh, indent=2)
    print("\n== meta ==")
    print(json.dumps(meta, indent=2))
