"""Interests & discovery — what the algorithm feeds you, from liked content.

Primary path reads the structured likes.parquet (exact Owner username/name,
per-record hashtag blocks, post/reel/tv format). Hashtag counts are
OWNER-WEIGHTED (a tag counts once per distinct creator) to neutralise
engagement-bait tag walls. A raw-JSON fallback keeps basic interests working
for foreign exports that lack the parsed table.
"""
import os, json, re
from collections import Counter
import pandas as pd
import ftfy

# requires stays empty on purpose: when likes.parquet is absent the module falls
# back to mining the raw export JSONs, so foreign exports still get basic interests
META = {"key": "interests", "title": "Interests & Discovery",
        "requires": [], "privacy": "low"}

TOP_ERA_CREATORS = 8


def compute(ctx, D):
    print("interests & discovery (creators / hashtags / formats from liked content) ...")
    df = ctx.load_clean("likes.parquet")
    if df is None or df.empty:
        _fallback(ctx, D)
        return
    df = ctx.filter_people(df, ["owner_username", "owner_name"])
    if df is None or df.empty:
        _fallback(ctx, D)
        return

    # creator identity: group by exact username, label with display name
    df = df.copy()
    df["ckey"] = df["owner_username"].where(df["owner_username"].fillna("") != "",
                                            df["owner_name"].fillna(""))
    sub = df[df["ckey"] != ""]
    name_by_key = (sub.loc[sub["owner_name"].fillna("") != ""]
                   .groupby("ckey")["owner_name"].agg("first").to_dict())

    def label(key):
        return ctx.disp(name_by_key.get(key) or key)

    months = pd.period_range(df["dt"].min(), df["dt"].max(), freq="M") \
               .strftime("%Y-%m").tolist()
    per_month = df.groupby("ym").size()

    # ---- hashtags, owner-weighted (kill tag-wall bias) ----------------------
    tag_owner, reel_tag_owner = set(), set()
    for tags, owner, fmt in zip(df["hashtags"].fillna(""), df["ckey"], df["format"]):
        if not tags:
            continue
        for t in tags.split("|"):
            if len(t) > 1:
                tag_owner.add((t, owner))
                if fmt == "reel":
                    reel_tag_owner.add((t, owner))
    tag_c = Counter(t for t, _ in tag_owner)
    reel_tag_c = Counter(t for t, _ in reel_tag_owner)

    # ---- creators ------------------------------------------------------------
    cc = sub.groupby("ckey").size().sort_values(ascending=False)
    top_creators = [{"name": label(k), "n": int(v)} for k, v in cc.head(25).items()]

    # creator eras: monthly like share of the long-term top creators
    series = {}
    pv = sub.pivot_table(index="ym", columns="ckey", values="ts",
                         aggfunc="size", fill_value=0)
    for k in cc.head(TOP_ERA_CREATORS).index:
        lbl = label(k)
        if lbl in series:                      # display-name collision -> username
            lbl = ctx.disp(k)
        col = pv[k] if k in pv.columns else pd.Series(dtype=int)
        series[lbl] = [int(col.get(m, 0)) for m in months]
    others = [int(per_month.get(m, 0)) - sum(series[l][i] for l in series)
              for i, m in enumerate(months)]

    # ---- format takeover (post / reel / tv per quarter) -----------------------
    qper = df["dt"].dt.tz_localize(None).dt.to_period("Q")   # local wall-clock quarter
    quarters = pd.period_range(qper.min(), qper.max(), freq="Q")
    fq = df.groupby([qper, "format"]).size().unstack(fill_value=0) \
           .reindex(quarters, fill_value=0)
    format_shift = {"q": [f"{p.year}-Q{p.quarter}" for p in quarters]}
    for fmt in ("post", "reel", "tv"):
        col = fq[fmt] if fmt in fq.columns else pd.Series(0, index=quarters)
        format_shift[fmt] = [int(x) for x in col]

    # ---- diversity: distinct creators liked per month --------------------------
    dv = sub.groupby("ym")["ckey"].nunique()

    # ---- liked comment authors --------------------------------------------------
    authors = []
    lc = ctx.load_clean("liked_comments.parquet")
    if lc is not None and not lc.empty:
        lc = ctx.filter_people(lc, ["author_username"])
        vc = lc["author_username"].value_counts().head(10)
        authors = [{"name": ctx.disp(k), "n": int(v)} for k, v in vc.items()]

    # ---- kpis ---------------------------------------------------------------------
    daily = df.groupby("date").size()
    kpis = {
        "total_likes": int(len(df)),
        "unique_creators": int(sub["ckey"].nunique()),
        "top_creator": label(cc.index[0]) if len(cc) else "",
        "top_creator_share_pct": round(100.0 * int(cc.iloc[0]) / max(len(df), 1), 1)
                                 if len(cc) else 0.0,
        "likes_per_day_peak": int(daily.max()) if len(daily) else 0,
        "likes_per_day_peak_date": str(daily.idxmax()) if len(daily) else "",
    }

    n_reel = int((df["format"] == "reel").sum())
    D["interests"] = {
        # ---- legacy shapes (existing dashboard charts keep working) ----
        "n_engagements": int(len(df)),
        "n_reels": n_reel,
        "n_posts": int(len(df) - n_reel),
        "top_hashtags": [{"tag": k, "n": int(v)} for k, v in tag_c.most_common(40)],
        "top_reel_hashtags": [{"tag": k, "n": int(v)} for k, v in reel_tag_c.most_common(30)],
        "top_creators": top_creators,
        "by_month": {"ym": months, "n": [int(per_month.get(m, 0)) for m in months]},
        "n_unique_tags": int(len(tag_c)),
        "n_unique_creators": int(sub["ckey"].nunique()),
        # ---- new structured views ----
        "creator_eras": {"ym": months, "series": series, "others": others},
        "format_shift": format_shift,
        "diversity": {"ym": months, "n": [int(dv.get(m, 0)) for m in months]},
        "liked_comment_authors": authors,
        "kpis": kpis,
        "source": "structured",
    }
    print(f"  likes: {len(df):,} · creators: {kpis['unique_creators']:,} · "
          f"tags (owner-weighted): {len(tag_c):,} · top: {kpis['top_creator']} "
          f"({kpis['top_creator_share_pct']}%)")


# =============================================================================
# Fallback: raw-JSON caption mining (foreign exports without likes.parquet).
# Emits only the legacy sub-keys; the new charts must None-guard.
# =============================================================================
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


def _fallback(ctx, D):
    print("  likes.parquet missing — falling back to raw-JSON caption mining")
    try:
        eng = []
        for rel, kind in SOURCES:
            eng += _harvest(os.path.join(ctx.RAW, rel), kind)
        if not eng:
            return
        tag_c, creator_c, reel_tag_c, month_c = Counter(), Counter(), Counter(), Counter()
        n_reel = n_post = 0
        for r in eng:
            creator = ftfy.fix_text(r["creator"]) if r["creator"] else None
            if creator and ctx.is_excluded(creator):
                continue
            for t in r["tags"]:
                if len(t) > 1:
                    tag_c[t] += 1
                    if r["is_reel"]: reel_tag_c[t] += 1
            if creator: creator_c[creator.lower()] += 1
            for m in r["mentions"]:
                if not ctx.is_excluded(m):
                    creator_c[m] += 1
            if r["is_reel"]: n_reel += 1
            else: n_post += 1
            if r["ts"]:
                month_c[pd.Timestamp(r["ts"], unit="s", tz="UTC").tz_convert(ctx.TZ).strftime("%Y-%m")] += 1
        months = sorted(month_c)
        D["interests"] = {
            "n_engagements": len(eng), "n_reels": n_reel, "n_posts": n_post,
            "top_hashtags": [{"tag": k, "n": int(v)} for k, v in tag_c.most_common(40)],
            "top_reel_hashtags": [{"tag": k, "n": int(v)} for k, v in reel_tag_c.most_common(30)],
            "top_creators": [{"name": ctx.disp(k), "n": int(v)} for k, v in creator_c.most_common(25)],
            "by_month": {"ym": months, "n": [int(month_c[m]) for m in months]},
            "n_unique_tags": len(tag_c), "n_unique_creators": len(creator_c),
            "source": "fallback",
        }
        print(f"  engagements: {len(eng):,} ({n_reel:,} reels) · {len(tag_c):,} unique tags · {len(creator_c):,} creators")
    except Exception as e:
        print("  interests fallback failed:", e)
