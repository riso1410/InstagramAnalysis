"""What Meta knows: advertisers holding your data, ad-targeting categories,
the served-content impression logs and off-Meta tracking."""
from collections import Counter
import pandas as pd

META = {"key": "footprint", "title": "What Meta knows",
        "requires": ["footprint.json"], "privacy": "medium"}

IMPRESSION_KINDS = ["ad", "post", "video"]

_DEMOGRAPHIC = ("birthday", "relationship", "gender", "age ", "live abroad",
                "parents", "expats", "single", "engaged to", "married")
_DEVICE = ("android", "ios", "mobile", "wi-fi", "wifi", "browser", "device",
           "tablet", "smartphone", "network", "facebook access", "360 degree",
           "operating system")


def _bucket(label):
    l = label.lower()
    if l.startswith("friends of"):
        return "social"
    if any(k in l for k in _DEMOGRAPHIC):
        return "demographic"
    if any(k in l for k in _DEVICE):
        return "device"
    return "behavior"


def compute(ctx, D):
    print("footprint (what Meta knows: advertisers / targeting / impressions) ...")
    fp = ctx.load_clean("footprint.json")
    if fp is None:
        print("  footprint.json missing — skipped")
        return

    d = {}
    adv = fp.get("advertisers") or {}

    # ---- impressions (may be absent / date-window filtered) ----------------
    imp = ctx.load_clean("impressions.parquet")
    if imp is not None and not imp.empty:
        imp = ctx.filter_people(imp, ["owner_name", "owner_username"])
    imp3 = imp[imp["kind"].isin(IMPRESSION_KINDS)].copy() if imp is not None and not imp.empty else None
    sugg = imp[imp["kind"] == "suggested_profile"] if imp is not None and not imp.empty else None

    n_ads = int((imp3["kind"] == "ad").sum()) if imp3 is not None else 0
    n_all = int(len(imp3)) if imp3 is not None else 0
    window = {}
    if imp3 is not None and len(imp3):
        window = {"start": str(imp3["date"].min()), "end": str(imp3["date"].max()),
                  "days": int(imp3["date"].nunique())}

    # ---- scorecard ----------------------------------------------------------
    d["kpis"] = {
        "advertisers_union": int(adv.get("union_n", 0)),
        "advertisers_uploaded": int(adv.get("uploaded_n", 0)),
        "advertisers_interaction": int(adv.get("interaction_n", 0)),
        "advertisers_both": int(adv.get("both_n", 0)),
        "targeting_labels_n": len(fp.get("targeting_labels") or []),
        "off_meta_sites": len(fp.get("off_meta") or []),
        "off_meta_events": int(sum(s.get("n_events", 0) for s in fp.get("off_meta") or [])),
        "ad_share_pct": round(100.0 * n_ads / n_all, 1) if n_all else 0.0,
        "impressions_logged": n_all,
        "suggested_profiles_total": int(len(sugg)) if sugg is not None else 0,
        "hidden_ads_n": int(fp.get("hidden_ads_n", 0)),
        "no_ads_subscription": str(fp.get("no_ads_subscription") or ""),
        "profile_association": str(fp.get("profile_association") or ""),
        "window": window,
    }

    # ---- advertiser split + who-buys-you tokens -----------------------------
    both = int(adv.get("both_n", 0))
    d["advertisers"] = {
        "uploaded_only": int(adv.get("uploaded_n", 0)) - both,
        "interaction_only": int(adv.get("interaction_n", 0)) - both,
        "both": both,
        "union": int(adv.get("union_n", 0)),
        "tokens": [{"token": str(t["token"]), "n": int(t["n"])}
                   for t in (adv.get("name_tokens") or [])[:20]],
    }

    # ---- targeting labels in buckets ----------------------------------------
    labels = [{"label": str(l), "bucket": _bucket(str(l))}
              for l in fp.get("targeting_labels") or []]
    bc = Counter(l["bucket"] for l in labels)
    d["targeting"] = {"labels": labels,
                      "bucket_counts": {b: int(bc.get(b, 0))
                                        for b in ["demographic", "behavior", "device", "social"]}}

    # ---- per-day ad density (the short rolling impression window) -----------
    if imp3 is not None and len(imp3):
        piv = imp3.pivot_table(index="date", columns="kind", aggfunc="size", fill_value=0)
        days = pd.date_range(imp3["date"].min(), imp3["date"].max(), freq="D").date
        piv = piv.reindex(days, fill_value=0)
        ads = [int(piv.get("ad", pd.Series(0, piv.index)).loc[x]) for x in days]
        posts = [int(piv.get("post", pd.Series(0, piv.index)).loc[x]) for x in days]
        vids = [int(piv.get("video", pd.Series(0, piv.index)).loc[x]) for x in days]
        tot = [a + p + v for a, p, v in zip(ads, posts, vids)]
        d["ad_density"] = {"dates": [str(x) for x in days], "ads": ads, "posts": posts,
                           "videos": vids,
                           "share": [round(100.0 * a / t, 1) if t else 0.0
                                     for a, t in zip(ads, tot)]}

        # ---- served accounts / repeat advertisers / hashtags ----------------
        w = imp3.copy()
        w["acct"] = w["owner_username"].where(w["owner_username"] != "", w["owner_name"])
        w["disp"] = w["owner_name"].where(w["owner_name"] != "", w["owner_username"])
        w = w[w["acct"] != ""]
        top = (w.pivot_table(index="acct", columns="kind", aggfunc="size", fill_value=0)
                .reindex(columns=IMPRESSION_KINDS, fill_value=0))
        top["total"] = top.sum(axis=1)
        names = w.groupby("acct")["disp"].first()
        top = top.sort_values("total", ascending=False).head(15)
        d["served"] = {
            "top_accounts": [{"name": ctx.disp(str(names.get(a, a))),
                              "ads": int(r["ad"]), "posts": int(r["post"]),
                              "videos": int(r["video"]), "total": int(r["total"])}
                             for a, r in top.iterrows()],
            "repeat_advertisers": [{"name": ctx.disp(str(names.get(a, a))), "n": int(n)}
                                   for a, n in w[w["kind"] == "ad"]["acct"]
                                   .value_counts().head(10).items() if n >= 2],
            "hashtags": [{"tag": str(t), "n": int(n)} for t, n in Counter(
                t for s in w["hashtags"] if s for t in s.split("|")).most_common(20)],
        }

    # ---- suggested profiles per year (historical 2017-2020 log) -------------
    if sugg is not None and len(sugg):
        by = sugg.groupby("year").size().sort_index()
        d["suggested"] = {"years": [int(y) for y in by.index],
                          "counts": [int(n) for n in by.values]}

    # ---- off-Meta sites (tiny list) ------------------------------------------
    d["off_meta"] = [{"domain": str(s["domain"]), "events": int(s["n_events"]),
                      "last": str(pd.Timestamp(s["last_ts"], unit="s", tz="UTC")
                                  .tz_convert(ctx.TZ).date()) if s.get("last_ts") else ""}
                     for s in (fp.get("off_meta") or [])[:10]]

    hy = fp.get("hidden_ads_years") or {}
    d["hidden_ads_years"] = {"years": sorted(hy), "counts": [int(hy[y]) for y in sorted(hy)]}

    D["footprint"] = d
    print(f"  advertisers: {d['kpis']['advertisers_union']:,} · targeting labels: "
          f"{d['kpis']['targeting_labels_n']} · impressions in window: {n_all:,} "
          f"({d['kpis']['ad_share_pct']}% ads) · suggested: {d['kpis']['suggested_profiles_total']:,}")
