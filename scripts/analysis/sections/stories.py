"""Stories & reels: who you tap back to (story likes, polls, quizzes, notes),
the poll/quiz era vs the story-like era, and the 30-day reels watch log
(sessions, repeat creators, hashtags). One of the most personal sections —
every name passes ctx.disp, every frame ctx.filter_people. privacy: high.
"""
from collections import Counter
import pandas as pd

META = {"key": "stories", "title": "Stories & reels",
        "requires": ["story_interactions.parquet"], "privacy": "high"}

TYPES = ["poll", "quiz", "question", "emoji_slider", "story_like",
         "reaction_sticker", "instant", "note", "saved"]
SESSION_GAP_S = 300          # <5 min between views = same binge session


def _person_rows(df):
    """(key, display) per row: key on username when present, display prefers
    the real name. Empty-owner rows are dropped."""
    out = []
    for user, name in zip(df["owner_username"].fillna(""), df["owner_name"].fillna("")):
        key = (user or name).strip().lower()
        if key:
            out.append((key, name.strip() or user.strip()))
    return out


def _col_of(df, candidates):
    return next((c for c in candidates if df is not None and c in df.columns), None)


def compute(ctx, D):
    print("stories & reels (interactions, inner circle, watch log) ...")
    si = ctx.load_clean("story_interactions.parquet")
    rv = ctx.load_clean("reels_viewed.parquet")
    if (si is None or si.empty) and (rv is None or rv.empty):
        return
    S = {"kpis": {}}
    self_lower = str(ctx.self_name).lower()

    # ------------------------------------------------ story interactions
    if si is not None and not si.empty:
        si = ctx.filter_people(si, ["owner_username", "owner_name"])
    if si is not None and not si.empty:
        totals = si["type"].value_counts()
        S["kpis"].update({f"n_{t}": int(totals.get(t, 0)) for t in TYPES})
        S["kpis"]["n_interactions"] = int(len(si))
        S["totals"] = {t: int(totals.get(t, 0)) for t in TYPES if totals.get(t, 0)}

        # --- top people: who you answer / like / note back, stacked by type
        per = Counter()                                  # (key, type) -> n
        disp_name = {}                                   # key -> best display
        for (key, name), typ in zip(_person_rows(si), si["type"]):
            if key == self_lower or name.lower() == self_lower:
                continue
            per[(key, typ)] += 1
            if name and (key not in disp_name or disp_name[key] == key):
                disp_name[key] = name
        tot = Counter()
        for (key, _t), n in per.items():
            tot[key] += n
        top = [k for k, _ in tot.most_common(20)]
        types_present = [t for t in TYPES if any(per.get((k, t)) for k in top)]
        S["top_people"] = {
            "names": [ctx.disp(disp_name.get(k, k)) for k in top],
            "total": [int(tot[k]) for k in top],
            "types": types_present,
            "series": {t: [int(per.get((k, t), 0)) for k in top] for t in types_present},
        }
        S["kpis"]["n_people"] = int(len(tot))

        # --- eras: interaction mix per year (notes have no timestamp -> excluded)
        dated = si[si["year"].notna()]
        if not dated.empty:
            years = list(range(int(dated["year"].min()), int(dated["year"].max()) + 1))
            piv = dated.groupby(["year", "type"]).size().unstack(fill_value=0)
            era_types = [t for t in TYPES if t in piv.columns]
            S["eras"] = {"years": years,
                         "series": {t: [int(piv.loc[y, t]) if y in piv.index else 0
                                        for y in years] for t in era_types}}

        # --- emoji palette: sliders + reaction stickers + instants
        em = si.loc[si["type"].isin(["emoji_slider", "reaction_sticker", "instant"]), "emoji"]
        emc = Counter(e for e in em.fillna("") if e)
        S["emoji_palette"] = [{"emoji": e, "n": int(n)} for e, n in emc.most_common(15)]

        # --- inner circle: cross-surface closeness score
        signals = {}                                     # signal -> Counter(key)
        for sig, typ in [("story_likes", "story_like"), ("notes", "note")]:
            c = Counter()
            for key, name in _person_rows(si[si["type"] == typ]):
                if key != self_lower and name.lower() != self_lower:
                    c[key] += 1
                    if name and (key not in disp_name or disp_name[key] == key):
                        disp_name[key] = name
            if c:
                signals[sig] = c
        cm = ctx.load_clean("comments.parquet")
        col = _col_of(cm, ["media_owner", "owner_username", "owner", "to_owner", "owner_name"])
        if col:
            cm = ctx.filter_people(cm, [col])
            c = Counter(str(v).strip().lower() for v in cm[col].dropna()
                        if str(v).strip() and str(v).strip().lower() != self_lower)
            if c:
                signals["comments"] = c
        lc = ctx.load_clean("likes_comments.parquet")
        col = _col_of(lc, ["author", "owner_username", "owner", "username", "owner_name", "title"])
        if col:
            lc = ctx.filter_people(lc, [col])
            c = Counter(str(v).strip().lower() for v in lc[col].dropna()
                        if str(v).strip() and str(v).strip().lower() != self_lower)
            if c:
                signals["liked_comments"] = c
        if signals:
            total = Counter()
            n_surface = Counter()
            for c in signals.values():
                total.update(c)
                for k in c:
                    n_surface[k] += 1
            # rank by surfaces touched first, then volume — brands rack volume,
            # friends span surfaces
            ranked = sorted(total, key=lambda k: (-n_surface[k], -total[k]))[:15]
            sig_names = list(signals)
            S["inner_circle"] = {
                "names": [ctx.disp(disp_name.get(k, k)) for k in ranked],
                "signals": sig_names,
                "series": {s: [int(signals[s].get(k, 0)) for k in ranked] for s in sig_names},
                "n_surfaces": [int(n_surface[k]) for k in ranked],
            }

    # ------------------------------------------------ reels watch log
    if rv is not None and not rv.empty:
        rv = ctx.filter_people(rv, ["owner_username", "owner_name"])
    if rv is not None and not rv.empty:
        rv = rv.sort_values("ts")
        daily = rv.groupby("date").size()
        R = {"daily": {"dates": [str(d) for d in daily.index],
                       "n": [int(x) for x in daily.values]},
             "by_hour": [int(x) for x in
                         rv.groupby("hour").size().reindex(range(24), fill_value=0)],
             "window": [str(daily.index.min()), str(daily.index.max())]}
        gaps = rv["ts"].diff()
        sess_id = (gaps > SESSION_GAP_S).cumsum()
        lens = rv.groupby(sess_id).size()
        R["sessions"] = {"n_sessions": int(len(lens)),
                         "median_views": float(lens.median()),
                         "max_views": int(lens.max()),
                         "p90_views": float(lens.quantile(0.9))}
        creators = Counter()
        cd = {}
        for key, name in _person_rows(rv):
            creators[key] += 1
            if name and (key not in cd or cd[key] == key):
                cd[key] = name
        one_off = sum(1 for n in creators.values() if n == 1)
        R["unique_creators"] = int(len(creators))
        R["one_off_share"] = round(one_off / max(len(creators), 1), 3)
        R["repeat_creators"] = [{"name": ctx.disp(cd.get(k, k)), "n": int(n)}
                                for k, n in creators.most_common(12) if n >= 10]
        tags = Counter()
        for h in rv["hashtags"].fillna(""):
            for t in h.split("|"):
                if len(t) > 1:
                    tags[t] += 1
        R["top_hashtags"] = [{"tag": t, "n": int(n)} for t, n in tags.most_common(20)]
        S["reels"] = R
        S["kpis"]["reels_views"] = int(len(rv))
        S["kpis"]["reels_per_day"] = round(len(rv) / max(daily.index.nunique(), 1), 1)
        S["kpis"]["reels_unique_creators"] = int(len(creators))
        S["kpis"]["reels_sessions"] = int(len(lens))

    D["stories"] = S
    print(f"  story interactions: {S['kpis'].get('n_interactions', 0):,} · "
          f"reels views: {S['kpis'].get('reels_views', 0):,}")
