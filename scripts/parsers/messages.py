"""Messages parser: inbox + message_requests -> messages/reactions/threads tables
plus meta.json (self identity, date range). This is the heart of the dataset.
"""
import glob, json, os
from collections import Counter, defaultdict
import numpy as np
import pandas as pd

from .common import fix, add_time

META = {
    "key": "messages",
    "outputs": ["messages.parquet", "reactions.parquet", "threads.parquet", "meta.json"],
}


def _message_files(raw):
    inbox = glob.glob(f"{raw}/**/messages/inbox/*/message_*.json", recursive=True)
    reqs = glob.glob(f"{raw}/**/messages/message_requests/*/message_*.json", recursive=True)
    return inbox, reqs


def _thread_id(path):
    # .../inbox/<thread_dir>/message_N.json  -> <thread_dir>
    return os.path.basename(os.path.dirname(path))


def parse(env):
    raw, out, tz = env["RAW"], env["OUT"], env["TZ"]
    inbox, reqs = _message_files(raw)
    rows, react_rows = [], []
    thread_meta = {}
    file_groups = defaultdict(list)
    for f in inbox:
        file_groups[("inbox", _thread_id(f))].append(f)
    for f in reqs:
        file_groups[("request", _thread_id(f))].append(f)

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
            rows.append({
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
            })
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

    if not rows:
        print("  no message files found — skipping message tables")
        return {}

    df = pd.DataFrame(rows)
    rx = pd.DataFrame(react_rows)
    tm = pd.DataFrame(list(thread_meta.values()))

    # self = the participant present in the most threads (the account owner)
    self_name = participant_counter.most_common(1)[0][0]

    df = df[df["timestamp_ms"].notna()].copy()
    df = add_time(df, "timestamp_ms", tz)
    df["is_self"] = df["sender"] == self_name
    df["direction"] = np.where(df["is_self"], "sent", "received")
    df = df.sort_values("dt").reset_index(drop=True)

    if not rx.empty:
        rx = rx[rx["react_ts"].notna()].copy()
        rdt = pd.to_datetime(rx["react_ts"], unit="s", utc=True).dt.tz_convert(tz)
        rx["dt"] = rdt
        rx["ym"] = rdt.dt.strftime("%Y-%m")
        rx["reactor_is_self"] = rx["reactor"] == self_name

    df.to_parquet(f"{out}/messages.parquet", index=False)
    rx.to_parquet(f"{out}/reactions.parquet", index=False)
    tm.to_parquet(f"{out}/threads.parquet", index=False)

    meta = {
        "self_name": self_name,
        "n_messages": int(len(df)),
        "n_text_messages": int(df["has_text"].sum()),
        "n_threads": int(df["thread_id"].nunique()),
        "date_min": str(df["dt"].min()),
        "date_max": str(df["dt"].max()),
        "timezone": tz,
    }
    with open(f"{out}/meta.json", "w") as fh:
        json.dump(meta, fh, indent=2)

    print(f"  messages : {len(df):,} rows -> messages.parquet")
    print(f"  reactions: {len(rx):,} rows -> reactions.parquet")
    print(f"  threads  : {len(tm):,} rows -> threads.parquet")
    print(f"  self     : {self_name!r}")
    print(f"  date range: {df['dt'].min()}  ->  {df['dt'].max()}")
    return meta
