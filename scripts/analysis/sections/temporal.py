"""Temporal histograms: by year/month/weekday/hour, daily series, heatmaps."""
import pandas as pd
from ..text_utils import WEEKDAYS, MONTHS


def compute(ctx, D):
    inbox = ctx.inbox
    by_year = inbox.pivot_table(index="year", columns="direction", values="content", aggfunc="size", fill_value=0)
    D["temporal"] = {
        "by_year": {"years": [int(y) for y in by_year.index],
                    "sent": [int(x) for x in by_year.get("sent", pd.Series(0, by_year.index))],
                    "received": [int(x) for x in by_year.get("received", pd.Series(0, by_year.index))]},
    }
    ym = inbox.groupby("ym").agg(total=("content", "size"), sent=("is_self", "sum")).reset_index()
    ym["received"] = ym["total"] - ym["sent"]
    D["temporal"]["by_month"] = {
        "ym": ym["ym"].tolist(),
        "total": ym["total"].astype(int).tolist(),
        "sent": ym["sent"].astype(int).tolist(),
        "received": ym["received"].astype(int).tolist(),
    }
    moy = inbox.groupby("month").size().reindex(range(1, 13), fill_value=0)
    D["temporal"]["by_month_of_year"] = {"labels": MONTHS, "counts": [int(x) for x in moy]}
    wd = inbox.pivot_table(index="weekday", columns="direction", values="content", aggfunc="size", fill_value=0).reindex(range(7), fill_value=0)
    D["temporal"]["by_weekday"] = {"labels": WEEKDAYS,
                                   "sent": [int(wd.get("sent", pd.Series(0, index=range(7))).get(i, 0)) for i in range(7)],
                                   "received": [int(wd.get("received", pd.Series(0, index=range(7))).get(i, 0)) for i in range(7)]}
    hr = inbox.pivot_table(index="hour", columns="direction", values="content", aggfunc="size", fill_value=0).reindex(range(24), fill_value=0)
    D["temporal"]["by_hour"] = {"hours": list(range(24)),
                                "sent": [int(hr.get("sent", pd.Series(0, index=range(24))).get(i, 0)) for i in range(24)],
                                "received": [int(hr.get("received", pd.Series(0, index=range(24))).get(i, 0)) for i in range(24)]}
    dd = inbox.groupby("date").size()
    D["temporal"]["daily"] = {"dates": [str(d) for d in dd.index], "counts": [int(x) for x in dd.values]}
    hm = inbox.pivot_table(index="weekday", columns="hour", values="content", aggfunc="size", fill_value=0).reindex(index=range(7), columns=range(24), fill_value=0)
    D["temporal"]["heatmap_weekday_hour"] = {"weekdays": WEEKDAYS, "hours": list(range(24)),
                                             "z": [[int(hm.loc[w, h]) for h in range(24)] for w in range(7)]}
    ym_hm = inbox.pivot_table(index="year", columns="month", values="content", aggfunc="size", fill_value=0)
    yrs = sorted(inbox["year"].unique())
    D["temporal"]["heatmap_year_month"] = {"years": [int(y) for y in yrs], "months": MONTHS,
                                           "z": [[int(ym_hm.loc[y, m]) if (y in ym_hm.index and m in ym_hm.columns) else 0 for m in range(1, 13)] for y in yrs]}
