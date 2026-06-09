"""Story interactions + reels-watched log + notes + saved posts.

Turns the story_interactions/* files (polls, quizzes, questions, emoji sliders,
story likes, reaction stickers), instants_interactions, note_and_repost
interactions and saved_posts into one tidy event table, and splits
stories_viewed.json (which is in fact a ~30-day REELS watch log: every URL is
/reel/) into its own table with hashtag features.

Privacy note: question ANSWERS (free text typed by the account owner) are
deliberately NOT extracted — only the story owner's prompt/question text.
"""
import re
import pandas as pd
import ftfy

from .common import fix as _ftfy_fix, load_json, label_value

_MARKERS = ("Ã", "Å", "Â", "ð")


def fix(s):
    """ftfy fix + recovery of cases ftfy declines: (a) ambiguous mixed content
    (validity-gated latin-1 round-trip — only applies when the bytes really are
    double-encoded UTF-8), (b) 'Å ' where Š's NBSP byte (C5 A0) was normalized
    to a plain space by the export, which destroys the round-trip evidence."""
    if not isinstance(s, str):
        return s
    out = _ftfy_fix(s)
    if any(m in out for m in _MARKERS):
        try:
            return out.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        cand = ftfy.fix_text(out.replace("Å ", "Å\xa0"))
        if cand != out and not any(m in cand for m in _MARKERS):
            return cand
    return out

META = {"key": "story_interactions",
        "outputs": ["story_interactions.parquet", "reels_viewed.parquet"]}

HASH = re.compile(r"#(\w+)", re.UNICODE)

# type -> (path, question label?)  ts is SECONDS everywhere here
SOURCES = [
    ("poll",             "your_instagram_activity/story_interactions/polls.json"),
    ("quiz",             "your_instagram_activity/story_interactions/quizzes.json"),
    ("question",         "your_instagram_activity/story_interactions/questions.json"),
    ("emoji_slider",     "your_instagram_activity/story_interactions/emoji_sliders.json"),
    ("story_like",       "your_instagram_activity/story_interactions/story_likes.json"),
    ("reaction_sticker", "your_instagram_activity/story_interactions/story_reaction_sticker_reactions.json"),
    ("instant",          "your_instagram_activity/instants/instants_interactions.json"),
    ("note",             "personal_information/personal_information/note_and_repost_interactions.json"),
    ("saved",            "your_instagram_activity/saved/saved_posts.json"),
]
FALLBACKS = {"instant": "instants/instants_interactions.json"}


def _entries(obj):
    """Entry list out of {key: [...]}, bare list, or a SINGLE-DICT record."""
    if isinstance(obj, dict):
        if "label_values" in obj or "string_map_data" in obj:
            return [obj]
        return next((v for v in obj.values() if isinstance(v, list)), [])
    return obj if isinstance(obj, list) else []


def _owner(entry, titles=("Owner", "Author")):
    """Recursive Owner/Author extraction. Owner blocks nest at varying depth
    (Owner / Media>Owner / Owner>Owner); collect every candidate and prefer the
    one that carries a Username (the innermost real account block)."""
    found = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("title") in titles and isinstance(o.get("dict"), list):
                name = user = ""
                for blk in o["dict"]:
                    if not isinstance(blk, dict):
                        continue
                    for leaf in blk.get("dict") or []:
                        if not isinstance(leaf, dict):
                            continue
                        if leaf.get("label") == "Name" and leaf.get("value"):
                            name = fix(leaf["value"])
                        elif leaf.get("label") == "Username" and leaf.get("value"):
                            user = fix(leaf["value"])
                if name or user:
                    found.append((name, user))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(entry.get("label_values"))
    for n, u in found:
        if u:
            return n, u
    return found[0] if found else ("", "")


def _deep_label(entry, label):
    """First value for `label` anywhere in the label_values tree (top level
    first — quizzes/questions keep Question at top, Caption nests in Media)."""
    top = label_value(entry, label)
    if top:
        return top
    out = []

    def walk(o):
        if out:
            return
        if isinstance(o, dict):
            if o.get("label") == label and o.get("value"):
                out.append(fix(o["value"]))
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(entry.get("label_values"))
    return out[0] if out else ""


def _hashtags(entry):
    """Tags from the nested Hashtags block plus #tags regexed from the caption."""
    tags = []

    def walk(o):
        if isinstance(o, dict):
            if o.get("title") == "Hashtags" and isinstance(o.get("dict"), list):
                for blk in o["dict"]:
                    if not isinstance(blk, dict):
                        continue
                    for leaf in blk.get("dict") or []:
                        if isinstance(leaf, dict) and leaf.get("label") == "Name" and leaf.get("value"):
                            tags.append(fix(leaf["value"]).lower())
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(entry.get("label_values"))
    cap = _deep_label(entry, "Caption")
    seen, out = set(), []
    for t in tags + [t.lower() for t in HASH.findall(cap or "")]:
        if len(t) > 1 and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _calendar(df, tz):
    """add_time clone that tolerates missing timestamps (notes have none)."""
    dt = pd.to_datetime(df["ts"], unit="s", utc=True, errors="coerce").dt.tz_convert(tz)
    df["dt"] = dt
    df["date"] = dt.dt.strftime("%Y-%m-%d")
    df["year"] = dt.dt.year.astype("Int32")
    df["month"] = dt.dt.month.astype("Int32")
    df["ym"] = dt.dt.strftime("%Y-%m")
    df["day"] = dt.dt.day.astype("Int32")
    df["hour"] = dt.dt.hour.astype("Int32")
    df["weekday"] = dt.dt.weekday.astype("Int32")
    df["weekday_name"] = dt.dt.day_name()
    df["is_weekend"] = df["weekday"] >= 5
    return df


def parse(env):
    raw, out, tz = env["RAW"], env["OUT"], env["TZ"]
    stats = {}

    # ---------------- story_interactions.parquet ----------------
    rows = []
    for typ, path in SOURCES:
        obj = load_json(path, raw)
        if obj is None and typ in FALLBACKS:
            obj = load_json(FALLBACKS[typ], raw)
        if obj is None:
            continue
        n = 0
        for e in _entries(obj):
            if not isinstance(e, dict):
                continue
            name, user = _owner(e)
            ts = e.get("timestamp") or None          # notes: no timestamp; 0 = unset
            emoji = ""
            if typ in ("emoji_slider", "reaction_sticker", "instant"):
                emoji = _deep_label(e, "Emoji")
            text = ""
            if typ in ("poll", "quiz", "question", "emoji_slider"):
                text = _deep_label(e, "Question")    # owner's prompt only, never the Answer
            rows.append({"ts": ts, "type": typ, "owner_username": user,
                         "owner_name": name, "emoji": emoji, "text": text})
            n += 1
        stats[f"n_{typ}"] = n
        print(f"  story_interactions[{typ}]: {n:,}")

    if rows:
        si = pd.DataFrame(rows)
        si = _calendar(si, tz)
        si = si.sort_values("dt", na_position="last").reset_index(drop=True)
        si.to_parquet(f"{out}/story_interactions.parquet", index=False)
        print(f"  story interactions: {len(si):,} events -> story_interactions.parquet")
        stats["n_story_interactions"] = int(len(si))

    # ---------------- reels_viewed.parquet ----------------
    obj = load_json("your_instagram_activity/story_interactions/stories_viewed.json", raw)
    reels = []
    for e in _entries(obj) if obj is not None else []:
        if not isinstance(e, dict):
            continue
        ts = e.get("timestamp")
        if not ts:
            continue
        name, user = _owner(e)
        tags = _hashtags(e)
        reels.append({"ts": ts, "owner_username": user, "owner_name": name,
                      "n_hashtags": len(tags), "hashtags": "|".join(tags)})
    if reels:
        rv = pd.DataFrame(reels)
        rv = _calendar(rv, tz)
        rv = rv.sort_values("dt").reset_index(drop=True)
        rv.to_parquet(f"{out}/reels_viewed.parquet", index=False)
        print(f"  reels watch log: {len(rv):,} views -> reels_viewed.parquet")
        stats["n_reels_viewed"] = int(len(rv))

    return stats
