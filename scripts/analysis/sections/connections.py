"""Social graph: reciprocity split, follow growth, follow-back latency,
suggestion pruning and moderation — from connections.parquet.

Caveat carried into the charts: followers_1.json only lists CURRENT followers,
so the followers growth curve is survivorship-biased (follow dates of people
who still follow you today; everyone who unfollowed has vanished from it).
"""
import pandas as pd

META = {"key": "connections", "title": "Social graph",
        "requires": ["connections.parquet"], "privacy": "high"}

SESSION_GAP_S = 600         # dismissals closer than 10 min = one cleanup session
BUCKET_LABELS = ["same day", "< 1 week", "< 1 month", "< 1 year", "1 year +"]
BUCKET_EDGES = [1, 7, 30, 365]                      # days, abs(delay)


def _bucket(abs_days):
    for i, edge in enumerate(BUCKET_EDGES):
        if abs_days < edge:
            return i
    return len(BUCKET_EDGES)


def _top_named(series_ts, ctx, cap=30):
    """username -> ts series, newest first, anonymized display names."""
    out = series_ts.sort_values(ascending=False).index.tolist()[:cap]
    return [ctx.disp(u) for u in out]


def compute(ctx, D):
    print("social graph (reciprocity / growth / follow-back latency / pruning) ...")
    conn = ctx.load_clean("connections.parquet")
    if conn is None or conn.empty:
        return
    conn = ctx.filter_people(conn, ["username", "name"])
    if conn is None or conn.empty:
        return

    fol = conn[conn["kind"] == "follower"]
    ing = conn[conn["kind"] == "following"]
    # first follow ts per username (dedupe shards / repeat events)
    f_ts = fol.dropna(subset=["username"]).groupby("username")["ts"].min()
    g_ts = ing.dropna(subset=["username"]).groupby("username")["ts"].min()
    fset, gset = set(f_ts.index), set(g_ts.index)
    mutual, fans, idols = fset & gset, fset - gset, gset - fset

    kc = conn["kind"].value_counts()
    pend_out = int((conn["source"] == "pending_follow_requests").sum())
    kpis = {
        "followers": int(len(fol)), "following": int(len(ing)),
        "mutuals": int(len(mutual)),
        "fans_only": int(len(fans)), "idols_only": int(len(idols)),
        "blocked_total": int(kc.get("blocked", 0)),
        "pending_in": int(kc.get("request_received", 0)),
        "pending_out": pend_out,
        "removed_suggestions_total": int(kc.get("removed_suggestion", 0)),
    }

    # ---- reciprocity: 3-way split + capped name lists --------------------
    reciprocity = {
        "counts": {"mutual": kpis["mutuals"], "fans_only": kpis["fans_only"],
                   "idols_only": kpis["idols_only"]},
        "lists": {
            "mutual": _top_named(f_ts[f_ts.index.isin(mutual)], ctx),
            "fans_only": _top_named(f_ts[f_ts.index.isin(fans)], ctx),
            "idols_only": _top_named(g_ts[g_ts.index.isin(idols)], ctx),
        },
    }

    # ---- growth: monthly cumulative + new per year -----------------------
    growth = {}
    fg = conn[conn["kind"].isin(["follower", "following"])].dropna(subset=["ym"])
    if not fg.empty:
        rng = pd.period_range(fg["ym"].min(), fg["ym"].max(), freq="M").strftime("%Y-%m")
        piv = fg.pivot_table(index="ym", columns="kind", aggfunc="size", fill_value=0)\
                .reindex(rng, fill_value=0)
        growth = {
            "ym": list(rng),
            "followers": [int(x) for x in piv.get("follower", pd.Series(0, index=rng)).cumsum()],
            "following": [int(x) for x in piv.get("following", pd.Series(0, index=rng)).cumsum()],
        }
        yp = fg.pivot_table(index="year", columns="kind", aggfunc="size", fill_value=0)
        growth["per_year"] = {
            "years": [int(y) for y in yp.index],
            "followers_new": [int(x) for x in yp.get("follower", pd.Series(0, index=yp.index))],
            "following_new": [int(x) for x in yp.get("following", pd.Series(0, index=yp.index))],
        }

    # ---- follow-back latency for mutuals ---------------------------------
    latency = {}
    common = f_ts.index.intersection(g_ts.index)
    if len(common):
        diff_days = (g_ts[common] - f_ts[common]) / 86400.0   # you_ts - them_ts
        you_first = [0] * len(BUCKET_LABELS)                   # you followed earlier
        they_first = [0] * len(BUCKET_LABELS)
        for d in diff_days:
            (you_first if d < 0 else they_first)[_bucket(abs(d))] += 1
        latency = {
            "buckets": BUCKET_LABELS,
            "you_first": you_first, "they_first": they_first,
            "totals": {"you_first": int((diff_days < 0).sum()),
                       "they_first": int((diff_days >= 0).sum()),
                       "n_matched": int(len(diff_days))},
            "median_abs_days": float(diff_days.abs().median()),
        }

    # ---- pruning: dismissed suggestions + recent unfollows ----------------
    pruning = {}
    rs = conn[conn["kind"] == "removed_suggestion"]
    if not rs.empty:
        bm = rs.dropna(subset=["ym"]).groupby("ym").size().sort_index()
        rs_users = set(rs["username"].dropna())
        ts_sorted = sorted(rs["ts"].dropna().tolist())
        sessions = []                                          # (start_ts, n)
        for t in ts_sorted:
            if sessions and t - sessions[-1][1] < SESSION_GAP_S:
                s0, _, n = sessions[-1]
                sessions[-1] = (s0, t, n + 1)
            else:
                sessions.append((t, t, 1))
        top = sorted(sessions, key=lambda s: -s[2])[:5]
        pruning = {
            "by_month": {"ym": list(bm.index), "n": [int(x) for x in bm.values]},
            "total": int(len(rs)),
            "became_followers": int(len(rs_users & fset)),
            "you_followed": int(len(rs_users & gset)),
            "sessions": {
                "n_sessions": int(len(sessions)),
                "max_session": int(max((s[2] for s in sessions), default=0)),
                "top_sessions": [
                    {"date": str(pd.Timestamp(s0, unit="s", tz="UTC")
                                 .tz_convert(ctx.TZ).date()), "n": int(n)}
                    for s0, _, n in top],
            },
        }
    uf = conn[conn["kind"] == "unfollowed"]
    if not uf.empty:
        pruning["unfollowed"] = {
            "total": int(len(uf)),
            "still_follow_you": int(len(set(uf["username"].dropna()) & fset)),
        }

    # ---- moderation: blocks per year, requests, restricted ----------------
    blocks = conn[conn["kind"] == "blocked"].dropna(subset=["year"])
    by = blocks.groupby("year").size().sort_index()
    recent = conn[conn["source"] == "recent_follow_requests"]
    moderation = {
        "blocks": {"years": [int(y) for y in by.index], "n": [int(x) for x in by.values]},
        "restricted_total": int(kc.get("restricted", 0)),
        "requests": {
            "pending_in": kpis["pending_in"], "pending_out": pend_out,
            "recent_sent": int(len(recent)),
            "recent_approved": int(len(set(recent["username"].dropna()) & gset)),
        },
    }

    D["connections"] = {"kpis": kpis, "reciprocity": reciprocity, "growth": growth,
                        "latency": latency, "pruning": pruning, "moderation": moderation}
    print(f"  social graph: {kpis['followers']} followers / {kpis['following']} following "
          f"· {kpis['mutuals']} mutual · {pruning.get('total', 0)} suggestions dismissed")
