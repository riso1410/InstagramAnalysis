"""Account security, identity & digital trail: logins, devices, cities, profile
history, in-app browser link trail. Everything here is privacy-sensitive (high)."""
import pandas as pd

META = {"key": "security", "title": "Security & identity", "privacy": "high",
        "requires": ["security_events.parquet"]}

DUR_BINS = [(-1, 5, "<5s"), (5, 30, "5–30s"), (30, 120, "30s–2m"), (120, float("inf"), ">2m")]


def compute(ctx, D):
    print("security & identity (logins, devices, cities, profile history, link trail) ...")
    ev = ctx.load_clean("security_events.parquet")
    identity = ctx.load_clean("identity.json") or {}
    links = ctx.load_clean("links.parquet")
    if ev is None and not identity and links is None:
        return

    sec = {}

    # ------------------------------------------------------------------ kpis
    now = pd.Timestamp.now(tz=ctx.TZ)
    signup = (identity.get("signup") or {})
    age_days = None
    if signup.get("ts"):
        age_days = int((now - pd.Timestamp(signup["ts"], unit="s", tz="UTC")).days)
    sec["kpis"] = {
        "account_age_days": age_days,
        "n_logins": int((ev["type"] == "Login").sum()) if ev is not None else 0,
        "n_devices": int(ev["device"].dropna().nunique()) if ev is not None else 0,
        "n_cities": int(ev["city"].dropna().nunique()) if ev is not None else 0,
        "password_changes": int((ev["type"] == "Password changed").sum()) if ev is not None else 0,
    }

    # ------------------------------------------------ event timeline & splits
    if ev is not None and not ev.empty:
        e = ev.sort_values("ts")
        sec["events"] = [{"date": str(r.date), "type": str(r.type),
                          "device": str(r.device) if pd.notna(r.device) else None,
                          "city": str(r.city) if pd.notna(r.city) else None}
                         for r in e.tail(150).itertuples()]

        dv = e.dropna(subset=["device"]).groupby("device").agg(
            first=("date", "min"), last=("date", "max"), n=("ts", "size"))
        sec["device_bands"] = [{"device": str(d), "first": str(r["first"]),
                                "last": str(r["last"]), "n": int(r["n"])}
                               for d, r in dv.sort_values("first").iterrows()]

        years = sorted(e["year"].unique())
        yt = e.pivot_table(index="year", columns="type", values="ts", aggfunc="size", fill_value=0)
        sec["by_year_type"] = {
            "years": [int(y) for y in years],
            "series": [{"type": str(t), "n": [int(yt.loc[y, t]) if y in yt.index else 0 for y in years]}
                       for t in yt.columns],
        }
        sec["apps"] = [{"app": str(k), "n": int(v)}
                       for k, v in e["app"].dropna().value_counts().items()]
        sec["languages"] = [{"lang": str(k), "n": int(v)}
                            for k, v in e["language"].dropna().value_counts().items()]
        sec["cities"] = [{"city": str(k), "n": int(v)}
                         for k, v in e["city"].dropna().value_counts().head(15).items()]

    # -------------------------------------------------------------- identity
    # all masking (emails/phones/profile names -> •••, IPs -> a.b.x.x) done at parse
    sec["identity"] = {
        "signup": {"date": signup.get("date"), "device": signup.get("device")} if signup else None,
        "milestones": [{"label": str(m["label"]), "date": str(m["date"])}
                       for m in identity.get("milestones") or []],
        "profile_changes": [{"date": c.get("date"), "field": str(c["field"]),
                             "prev": str(c.get("prev") or ""), "new": str(c.get("new") or "")}
                            for c in identity.get("profile_changes") or []],
        "privacy_toggles": [{"date": str(t["date"]), "to": str(t["to"])}
                            for t in identity.get("privacy_toggles") or []],
        "based_in": identity.get("based_in"),
        "locations_of_interest": [str(x) for x in identity.get("locations_of_interest") or []],
    }

    # ------------------------------------------------------------ link trail
    if links is not None and not links.empty:
        lk = links
        dom = lk.dropna(subset=["domain"]).groupby("domain").agg(
            n=("ts", "size"), total_s=("duration_s", "sum"))
        dom = dom.sort_values("n", ascending=False).head(12)
        per_day = lk.groupby("date").size()
        dur = lk["duration_s"].dropna()
        sec["links"] = {
            "n_visits": int(len(lk)),
            "n_domains": int(lk["domain"].dropna().nunique()),
            "median_s": float(dur.median()) if len(dur) else None,
            "span_days": int((lk["dt"].max() - lk["dt"].min()).days) + 1,
            "top_domains": [{"domain": str(d), "n": int(r["n"]), "total_s": float(r["total_s"] or 0)}
                            for d, r in dom.iterrows()],
            "per_day": {"dates": [str(d) for d in per_day.index],
                        "n": [int(x) for x in per_day.values]},
            "duration_bins": {"labels": [lb for _, _, lb in DUR_BINS],
                              "n": [int(((dur > lo) & (dur <= hi)).sum()) for lo, hi, _ in DUR_BINS]},
            "utm": [{"medium": str(k) if k is not None else "none", "n": int(v)}
                    for k, v in lk["utm_medium"].fillna("none").value_counts().items()],
        }

    D["security"] = sec
    print(f"  events: {sec['kpis']['n_logins']} logins · {sec['kpis']['n_devices']} devices · "
          f"{sec['kpis']['n_cities']} cities · {len((sec.get('links') or {}).get('top_domains', []))} link domains")
