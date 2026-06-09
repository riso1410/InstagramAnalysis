"""Own created content: feed posts, stories, cutout stickers, story reposts and
profile photos -> media.parquet (one row per created item).

Sources (your_instagram_activity/media/):
  posts.json           NEW label_values format, authoritative for feed posts
  posts_1.json         legacy {media:[...]} format, subset of posts.json -> deduped
  archived_posts.json  legacy, overlaps posts.json -> deduped (marks type=archived)
  stories.json         {ig_stories:[...]} bare media dicts
  other_content.json   label_values, Publish mode == cutout_sticker
  reposts.json         SINGLE DICT record (wrapped), story repost
  profile_photos.json  {ig_profile_picture:[...]}
"""
import re
import pandas as pd

from .common import fix, load_json, first_list, label_value, add_time

META = {"key": "media", "outputs": ["media.parquet"]}

BASE = "your_instagram_activity/media"
MENT = re.compile(r"@([A-Za-z0-9_.]{2,30})")


def _mentions(text):
    """Pipe-joined unique @usernames found in a caption."""
    return "|".join(dict.fromkeys(MENT.findall(text or "")))


def _ext(uri):
    if not uri or "." not in str(uri):
        return ""
    return str(uri).rsplit(".", 1)[-1].lower()[:5]


def _lv_media(entry):
    """Media list nested in the new label_values format (label == 'Media')."""
    for it in entry.get("label_values") or []:
        if "label" in it and it.get("label") == "Media" and isinstance(it.get("media"), list):
            return it["media"]
    return []


def _row_new(entry, typ):
    """Row from the new label_values shape (posts.json / other_content.json / reposts.json)."""
    media = _lv_media(entry)
    first = media[0] if media else {}
    ts = entry.get("timestamp") or first.get("creation_timestamp") or 0
    caption = label_value(entry, "Caption") or label_value(entry, "Text") or ""
    if not caption:
        caption = fix(first.get("title") or "")
    src = (first.get("cross_post_source") or {}).get("source_app") or ""
    return {"type": typ, "ts": int(ts), "format": _ext(first.get("uri")),
            "caption": caption, "source_app": fix(src),
            "publish_mode": label_value(entry, "Publish mode") or "",
            "n_media": len(media), "mentions": _mentions(caption)}


def _row_legacy(entry, typ):
    """Row from legacy shapes: {media:[...], title, creation_timestamp} wrappers
    (posts_1 / archived) or bare media dicts (stories / profile photos)."""
    media = entry.get("media") if isinstance(entry.get("media"), list) and entry.get("media") else [entry]
    first = media[0]
    ts = entry.get("creation_timestamp") or first.get("creation_timestamp") or 0
    caption = fix(entry.get("title") or "") or fix(first.get("title") or "")
    src = (first.get("cross_post_source") or {}).get("source_app") or ""
    return {"type": typ, "ts": int(ts), "format": _ext(first.get("uri")),
            "caption": caption, "source_app": fix(src),
            "publish_mode": "", "n_media": len(media), "mentions": _mentions(caption)}


def parse(env):
    raw, out, tz = env["RAW"], env["OUT"], env["TZ"]

    # ---- feed posts: dedupe the 3 overlapping post files by entry timestamp ----
    posts = {}
    for e in first_list(load_json(f"{BASE}/posts_1.json", raw) or []):
        r = _row_legacy(e, "post")
        if r["ts"]:
            posts[r["ts"]] = r
    for e in first_list(load_json(f"{BASE}/posts.json", raw) or []):
        r = _row_new(e, "post")               # new format supersedes legacy
        if r["ts"]:
            posts[r["ts"]] = r
    for e in first_list(load_json(f"{BASE}/archived_posts.json", raw) or []):
        r = _row_legacy(e, "archived")
        if not r["ts"]:
            continue
        if r["ts"] in posts:                  # same post, currently archived
            posts[r["ts"]]["type"] = "archived"
        else:
            posts[r["ts"]] = r

    rows = list(posts.values())

    for e in first_list(load_json(f"{BASE}/stories.json", raw) or []):
        rows.append(_row_legacy(e, "story"))

    for e in first_list(load_json(f"{BASE}/other_content.json", raw) or []):
        rows.append(_row_new(e, "sticker"))

    rp = load_json(f"{BASE}/reposts.json", raw)
    if rp is not None:
        # single-dict record in this export generation -> wrap before iterating
        entries = rp if isinstance(rp, list) else ([rp] if ("label_values" in rp or "timestamp" in rp) else first_list(rp))
        for e in entries:
            rows.append(_row_new(e, "repost"))

    for e in first_list(load_json(f"{BASE}/profile_photos.json", raw) or []):
        rows.append(_row_legacy(e, "profile_photo"))

    rows = [r for r in rows if r["ts"] > 0]
    if not rows:
        print("  no own media found")
        return {}

    m = pd.DataFrame(rows)
    m = add_time(m, "ts", tz, unit="s")
    m = m.sort_values("dt").reset_index(drop=True)
    m.to_parquet(f"{out}/media.parquet", index=False)
    counts = m["type"].value_counts().to_dict()
    print(f"  media: {len(m):,} created items -> media.parquet  {counts}")
    return {"n_media": int(len(m)), **{f"n_{k}": int(v) for k, v in counts.items()}}
