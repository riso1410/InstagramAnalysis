"""Your own content & comment voice: creations (posts/stories/stickers/reposts)
vs consumption, posting habits, and who you comment on / @mention.
No comment text is emitted — only counts, lengths and (filtered) usernames."""
from collections import Counter

import pandas as pd

META = {"key": "content", "title": "Your Content & Comments",
        "requires": ["media.parquet"], "privacy": "medium"}

TYPES = ["story", "post", "sticker", "repost", "profile_photo", "archived"]
SURFACES = ["post", "reel", "story"]
LEN_BINS = [(1, 5), (6, 10), (11, 20), (21, 40), (41, 80), (81, 10**6)]


def _likes_count(ctx):
    """Total likes given: likes.parquet if present, else activity.parquet."""
    lk = ctx.load_clean("likes.parquet")
    if lk is not None and len(lk):
        return int(len(lk))
    act = ctx.load_clean("activity.parquet")
    if act is not None and "kind" in act.columns:
        n = int((act["kind"] == "liked_posts").sum())
        if n:
            return n
    return None


def compute(ctx, D):
    print("content & comments (own media + comment voice) ...")
    media = ctx.load_clean("media.parquet")
    if media is None or media.empty:
        return
    media = ctx.filter_people(media, ["caption", "mentions"])
    com = ctx.load_clean("comments.parquet")
    if com is not None:
        com = ctx.filter_people(com, ["media_owner", "text", "mentions"])

    # ---------------------------------------------------------------- kpis
    tc = media["type"].value_counts()
    n_total = int(len(media))
    n_comments = int(len(com)) if com is not None else 0
    n_likes = _likes_count(ctx)
    ratio = round(n_likes / n_total, 1) if (n_likes and n_total) else None
    D["content"] = {"kpis": {
        "n_total": n_total,
        **{f"n_{t}": int(tc.get(t, 0)) for t in TYPES},
        "n_comments": n_comments,
        "n_likes": n_likes,
        "consumption_ratio": ratio,
        "first_date": str(media["date"].min()),
        "last_date": str(media["date"].max()),
    }}

    # ------------------------------------------- creation timeline (year/type)
    yt = media.pivot_table(index="year", columns="type", values="ts",
                           aggfunc="size", fill_value=0)
    D["content"]["by_year"] = {
        "years": [int(y) for y in yt.index],
        "series": {t: [int(x) for x in yt[t]] for t in TYPES if t in yt.columns},
    }
    rug = media.sort_values("dt")[["date", "type"]]
    if len(rug) > 200:                       # even thinning, keeps full span
        rug = rug.iloc[:: len(rug) // 200 + 1]
    D["content"]["rug"] = [{"d": str(d), "type": str(t)}
                           for d, t in zip(rug["date"], rug["type"])]

    # ---------------------------------------------------------- story habits
    st = media[media["type"] == "story"]
    hr = st.groupby("hour").size().reindex(range(24), fill_value=0)
    wd = st.groupby("weekday").size().reindex(range(7), fill_value=0)
    fm = st.loc[st["format"].astype(str).str.len() > 0, "format"].value_counts()
    D["content"]["story"] = {
        "n": int(len(st)),
        "by_hour": [int(x) for x in hr],
        "by_weekday": [int(x) for x in wd],
        "formats": [{"format": str(k), "n": int(v)} for k, v in fm.head(8).items()],
    }

    # --------------------------------------------------------- comment voice
    if com is not None and not com.empty:
        cy = com.pivot_table(index="year", columns="surface", values="ts",
                             aggfunc="size", fill_value=0)
        owners = com.loc[com["media_owner"].astype(str).str.len() > 0,
                         "media_owner"].value_counts().head(15)
        ment = Counter()
        for s in pd.concat([com["mentions"], media["mentions"]]).fillna(""):
            for u in str(s).split("|"):
                if u and not ctx.is_excluded(u):
                    ment[u] += 1
        lens = com["text"].fillna("").str.len()
        lens = lens[lens > 0]
        labels, counts = [], []
        for lo, hi in LEN_BINS:
            labels.append(f"{lo}-{hi}" if hi < 10**6 else f"{lo}+")
            counts.append(int(((lens >= lo) & (lens <= hi)).sum()))
        D["content"]["comments"] = {
            "n": int(len(com)),
            "by_year": {"years": [int(y) for y in cy.index],
                        "series": {s: [int(x) for x in cy[s]]
                                   for s in SURFACES if s in cy.columns}},
            "top_owners": [{"name": ctx.disp(k), "n": int(v)} for k, v in owners.items()],
            "mentions": [{"name": ctx.disp(u), "n": int(n)} for u, n in ment.most_common(12)],
            "len_hist": {"labels": labels, "counts": counts},
            "median_len": float(lens.median()) if len(lens) else None,
        }
    else:
        D["content"]["comments"] = None

    print(f"  created items: {n_total:,} ({int(tc.get('story', 0))} stories) · "
          f"comments: {n_comments:,} · likes/creation: {ratio}")
