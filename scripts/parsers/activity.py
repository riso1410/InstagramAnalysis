"""Unified activity timeline: bare timestamps of likes, views, story interactions,
saves and searches, for the when-do-you-browse charts.
"""
import pandas as pd

from .common import load_json

META = {"key": "activity", "outputs": ["activity.parquet"]}

SPECS = {
    "liked_posts":     "your_instagram_activity/likes/liked_posts.json",
    "liked_comments":  "your_instagram_activity/likes/liked_comments.json",
    "post_comments":   "your_instagram_activity/comments/post_comments_1.json",
    "reels_comments":  "your_instagram_activity/comments/reels_comments.json",
    "posts_viewed":    "ads_information/ads_and_topics/posts_viewed.json",
    "videos_watched":  "ads_information/ads_and_topics/videos_watched.json",
    "ads_viewed":      "ads_information/ads_and_topics/ads_viewed.json",
    "stories_viewed":  "your_instagram_activity/story_interactions/stories_viewed.json",
    "story_likes":     "your_instagram_activity/story_interactions/story_likes.json",
    "polls":           "your_instagram_activity/story_interactions/polls.json",
    "saved_posts":     "your_instagram_activity/saved/saved_posts.json",
    "own_posts":       "your_instagram_activity/media/posts_1.json",
    "own_stories":     "your_instagram_activity/media/stories.json",
    "searches":        "logged_information/recent_searches/recent_searches.json",
    "profile_searches": "logged_information/recent_searches/profile_searches.json",
}


def _harvest_timestamped(obj, label, fix):
    """Recursively pull (timestamp, title/value) pairs from Instagram activity JSON."""
    out = []

    def walk(o):
        if isinstance(o, dict):
            ts = o.get("timestamp")
            if ts and isinstance(ts, (int, float)):
                title = o.get("title") or o.get("value") or ""
                href = None
                smd = o.get("string_list_data")
                if isinstance(smd, list) and smd:
                    href = smd[0].get("href")
                out.append({"ts": ts, "title": fix(title), "href": href, "kind": label})
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return out


def parse(env):
    from .common import fix
    raw, out, tz = env["RAW"], env["OUT"], env["TZ"]
    all_rows = []
    for label, path in SPECS.items():
        obj = load_json(path, raw)
        if obj is None:
            continue
        rows = _harvest_timestamped(obj, label, fix)
        all_rows.extend(rows)
        print(f"  activity[{label}]: {len(rows):,}")
    if not all_rows:
        print("  no activity timestamps harvested")
        return {}
    a = pd.DataFrame(all_rows)
    a = a[a["ts"] > 0].copy()
    dt = pd.to_datetime(a["ts"], unit="s", utc=True).dt.tz_convert(tz)
    a["dt"] = dt
    a["date"] = dt.dt.date
    a["year"] = dt.dt.year
    a["ym"] = dt.dt.strftime("%Y-%m")
    a["hour"] = dt.dt.hour
    a["weekday"] = dt.dt.weekday
    a = a.sort_values("dt").reset_index(drop=True)
    a.to_parquet(f"{out}/activity.parquet", index=False)
    print(f"  activity timeline: {len(a):,} events -> activity.parquet")
    return {"n_activity_events": int(len(a))}
