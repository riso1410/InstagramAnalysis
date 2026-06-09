"""Liked content: likes/liked_posts.json (42k records, structured Owner /
Hashtags / Caption blocks in the new label_values format) and
likes/liked_comments.json -> tidy tables for the interests section.

Privacy/size: caption TEXT is never stored — only derived features
(length, language hint, hashtag list, mention count).
"""
import re, time
import pandas as pd

from .common import fix, load_json, first_list, sld_entries, add_time

META = {"key": "likes", "outputs": ["likes.parquet", "liked_comments.parquet"]}

MENT = re.compile(r"@([A-Za-z0-9_.]{2,30})")
WORD = re.compile(r"[a-záäčďéíľĺňóôŕšťúýž]+")
SK_DIA = set("áäčďéíľĺňóôŕšťúýžěřůč")
# ascii-only stopwords that are distinctive per language (no en/sk homographs)
EN_STOP = {"the", "and", "you", "your", "this", "that", "with", "for", "are",
           "what", "when", "have", "from", "just", "about", "it", "is", "of",
           "not", "but", "can", "all", "get", "out", "how", "will", "more"}
SK_STOP = {"je", "sa", "som", "ako", "ale", "aj", "si", "pre", "nie", "ked",
           "aby", "lebo", "ktore", "ktory", "este", "vsetko", "len", "uz",
           "tak", "nas", "vam", "bude", "byt", "mam", "co", "ze"}


def _lang_hint(cap_lower):
    """Cheap sk/en/other guess: Slovak diacritics, then stopword vote."""
    if not cap_lower:
        return ""
    if any(ch in SK_DIA for ch in cap_lower):
        return "sk"
    toks = WORD.findall(cap_lower)
    en = sum(1 for t in toks if t in EN_STOP)
    sk = sum(1 for t in toks if t in SK_STOP)
    if en >= 2 and en > sk:
        return "en"
    if sk >= 2 and sk > en:
        return "sk"
    return "other"


def _leaves(items):
    """Yield {label, value} leaves from a dict-block list at any depth."""
    for b in items or []:
        if not isinstance(b, dict):
            continue
        if "label" in b:
            yield b
        elif isinstance(b.get("dict"), list):
            yield from _leaves(b["dict"])


def _find_block(label_values, title):
    """Locate a label-less {title: ..., dict: [...]} block at any nesting depth
    (Owner blocks appear as Owner / Media>Owner / Owner>Owner across exports)."""
    stack = list(label_values or [])
    while stack:
        it = stack.pop()
        if not isinstance(it, dict):
            continue
        if it.get("title") == title:
            return it
        if isinstance(it.get("dict"), list):
            stack.extend(it["dict"])
    return None


def _fmt_from_url(url):
    if "/reel" in url:
        return "reel"
    if "/tv" in url:
        return "tv"
    return "post"


def _parse_liked_posts(raw, out, tz):
    obj = load_json("your_instagram_activity/likes/liked_posts.json", raw)
    if obj is None:
        return None
    rows = []
    for e in first_list(obj):
        if not isinstance(e, dict):
            continue
        ts = e.get("timestamp") or 0
        if not isinstance(ts, (int, float)) or ts <= 0:
            continue
        lv = e.get("label_values") or []

        url = next((it.get("value") or it.get("href") or ""
                    for it in lv if it.get("label") == "URL"), "")
        # captions can be DUPLICATED within one record — first non-empty wins
        cap = next((it.get("value") for it in lv
                    if it.get("label") == "Caption" and it.get("value")), "")
        cap = fix(cap) if cap else ""

        ob = _find_block(lv, "Owner")
        owner_username = owner_name = ""
        for leaf in _leaves(ob.get("dict") if ob else None):
            if leaf.get("label") == "Username" and leaf.get("value"):
                owner_username = fix(leaf["value"])
            elif leaf.get("label") == "Name" and leaf.get("value"):
                owner_name = fix(leaf["value"])

        hb = _find_block(lv, "Hashtags")
        tags, seen = [], set()
        for leaf in _leaves(hb.get("dict") if hb else None):
            if leaf.get("label") == "Name" and leaf.get("value"):
                t = fix(leaf["value"]).lower().strip("#")
                if t and t not in seen:          # dedupe tag walls per record
                    seen.add(t)
                    tags.append(t)

        rows.append({
            "ts": int(ts),
            "owner_username": owner_username,
            "owner_name": owner_name,
            "format": _fmt_from_url(url),
            "n_hashtags": len(tags),
            "hashtags": "|".join(tags),
            "caption_len": len(cap),
            "n_mentions": len(MENT.findall(cap)),
            "lang_hint": _lang_hint(cap.lower()),
        })
    if not rows:
        return None
    df = pd.DataFrame(rows)
    add_time(df, "ts", tz, unit="s")
    df = df.sort_values("dt").reset_index(drop=True)
    df.to_parquet(f"{out}/likes.parquet", index=False)
    return df


def _parse_liked_comments(raw, out, tz):
    obj = load_json("your_instagram_activity/likes/liked_comments.json", raw)
    if obj is None:
        return None
    rows = [{"ts": int(r["ts"]), "author_username": r["title"]}
            for r in sld_entries(obj)
            if r.get("ts") and r["ts"] > 0 and r.get("title")]
    if not rows:
        return None
    df = pd.DataFrame(rows)
    add_time(df, "ts", tz, unit="s")
    df = df.sort_values("dt").reset_index(drop=True)
    df.to_parquet(f"{out}/liked_comments.parquet", index=False)
    return df


def parse(env):
    raw, out, tz = env["RAW"], env["OUT"], env["TZ"]
    t0 = time.perf_counter()
    stats = {}

    lp = _parse_liked_posts(raw, out, tz)
    if lp is not None:
        stats["n_liked_posts"] = int(len(lp))
        stats["n_creators"] = int(lp.loc[lp["owner_username"] != "", "owner_username"].nunique())
        print(f"  liked posts: {len(lp):,} ({stats['n_creators']:,} creators) -> likes.parquet")
    else:
        print("  liked_posts.json missing/empty — skipped")

    lc = _parse_liked_comments(raw, out, tz)
    if lc is not None:
        stats["n_liked_comments"] = int(len(lc))
        print(f"  liked comments: {len(lc):,} -> liked_comments.parquet")
    else:
        print("  liked_comments.json missing/empty — skipped")

    stats["parse_seconds"] = round(time.perf_counter() - t0, 2)
    print(f"  likes parser finished in {stats['parse_seconds']}s")
    return stats
