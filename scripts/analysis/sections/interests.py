"""Interests & discovery: hashtags + creators mined from liked/watched posts & reels."""
import os, json, re
from collections import Counter
import pandas as pd
import ftfy

HASH = re.compile(r"#(\w+)", re.UNICODE)
MENT = re.compile(r"@([A-Za-z0-9_.]{2,30})")
SOURCES = [("your_instagram_activity/likes/liked_posts.json", "liked"),
           ("ads_information/ads_and_topics/videos_watched.json", "watched"),
           ("ads_information/ads_and_topics/posts_viewed.json", "viewed")]


def _find_name(obj):
    if isinstance(obj, dict):
        if obj.get("label") == "Name" and obj.get("value"):
            return obj["value"]
        for v in obj.values():
            r = _find_name(v)
            if r: return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find_name(v)
            if r: return r
    return None


def _harvest(path, kind):
    if not os.path.exists(path): return []
    try: d = json.load(open(path, encoding="utf-8"))
    except Exception: return []
    entries = d if isinstance(d, list) else next((v for v in d.values() if isinstance(v, list)), [])
    rows = []
    for e in entries:
        if not isinstance(e, dict): continue
        cap = url = None
        for it in e.get("label_values", []):
            if it.get("label") == "Caption": cap = it.get("value")
            elif it.get("label") == "URL": url = it.get("value")
        cap = ftfy.fix_text(cap) if cap else ""
        rows.append({"ts": e.get("timestamp"), "kind": kind, "is_reel": bool(url and "/reel/" in url),
                     "tags": [t.lower() for t in HASH.findall(cap)],
                     "creator": _find_name(e),
                     "mentions": [m.lower() for m in MENT.findall(cap)]})
    return rows


def compute(ctx, D):
    print("interests & discovery (hashtags / creators from liked & watched content) ...")
    try:
        eng = []
        for rel, kind in SOURCES:
            eng += _harvest(os.path.join(ctx.RAW, rel), kind)
        if not eng:
            return
        tag_c, creator_c, reel_tag_c, month_c = Counter(), Counter(), Counter(), Counter()
        n_reel = n_post = 0
        for r in eng:
            for t in r["tags"]:
                if len(t) > 1:
                    tag_c[t] += 1
                    if r["is_reel"]: reel_tag_c[t] += 1
            if r["creator"]: creator_c[r["creator"].lower()] += 1
            for m in r["mentions"]: creator_c[m] += 1
            if r["is_reel"]: n_reel += 1
            else: n_post += 1
            if r["ts"]:
                month_c[pd.Timestamp(r["ts"], unit="s", tz="UTC").tz_convert(ctx.TZ).strftime("%Y-%m")] += 1
        months = sorted(month_c)
        D["interests"] = {
            "n_engagements": len(eng), "n_reels": n_reel, "n_posts": n_post,
            "top_hashtags": [{"tag": k, "n": int(v)} for k, v in tag_c.most_common(40)],
            "top_reel_hashtags": [{"tag": k, "n": int(v)} for k, v in reel_tag_c.most_common(30)],
            "top_creators": [{"name": k, "n": int(v)} for k, v in creator_c.most_common(25)],
            "by_month": {"ym": months, "n": [int(month_c[m]) for m in months]},
            "n_unique_tags": len(tag_c), "n_unique_creators": len(creator_c),
        }
        print(f"  engagements: {len(eng):,} ({n_reel:,} reels) · {len(tag_c):,} unique tags · {len(creator_c):,} creators")
    except Exception as e:
        print("  interests analysis failed:", e)
