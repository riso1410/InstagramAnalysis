"""Your written comments on posts, reels and stories -> comments.parquet.

Sources (your_instagram_activity/comments/):
  post_comments_1.json   bare list of string_map_data records (surface=post)
  reels_comments.json    {comments_reels_comments:[...]}        (surface=reel)
  hype.json              {comments_story_comments:[...]}        (surface=story)

string_map_data keys: Comment.value (may be absent for GIF-only comments),
'Media Owner'.value (username, sometimes missing), Time.timestamp (seconds).
"""
import re
import pandas as pd

from .common import load_json, first_list, smd_value, add_time

META = {"key": "comments", "outputs": ["comments.parquet"]}

MENT = re.compile(r"@([A-Za-z0-9_.]{2,30})")
SOURCES = [
    ("your_instagram_activity/comments/post_comments_1.json", "post"),
    ("your_instagram_activity/comments/reels_comments.json", "reel"),
    ("your_instagram_activity/comments/hype.json", "story"),
]


def parse(env):
    raw, out, tz = env["RAW"], env["OUT"], env["TZ"]
    rows = []
    for path, surface in SOURCES:
        obj = load_json(path, raw)
        if obj is None:
            continue
        n0 = len(rows)
        for e in first_list(obj):
            if not isinstance(e, dict):
                continue
            ts = smd_value(e, "Time")           # -> timestamp (seconds)
            if not isinstance(ts, (int, float)) or ts <= 0:
                continue
            text = smd_value(e, "Comment") or ""        # ftfy-fixed by smd_value
            owner = smd_value(e, "Media Owner") or ""
            rows.append({"ts": int(ts), "surface": surface, "text": text,
                         "media_owner": owner,
                         "mentions": "|".join(dict.fromkeys(MENT.findall(text)))})
        print(f"  comments[{surface}]: {len(rows) - n0:,}")

    if not rows:
        print("  no comments found")
        return {}

    c = pd.DataFrame(rows)
    c = add_time(c, "ts", tz, unit="s")
    c = c.sort_values("dt").reset_index(drop=True)
    c.to_parquet(f"{out}/comments.parquet", index=False)
    print(f"  comments: {len(c):,} -> comments.parquet")
    return {"n_comments": int(len(c))}
