"""Non-message activity EDA (likes, stories, polls, ...) over time and by hour."""
import os
import pandas as pd
from ..text_utils import series_to_dict


def compute(ctx, D):
    path = f"{ctx.CLEAN}/activity.parquet"
    if not os.path.exists(path):
        return
    print("activity EDA ...")
    act = pd.read_parquet(path)
    act["dt"] = pd.to_datetime(act["dt"])
    D["activity"] = {
        "totals": series_to_dict(act["kind"].value_counts()),
        "by_month": {},
        "by_hour": series_to_dict(act.groupby("hour").size().reindex(range(24), fill_value=0)),
    }
    am = act.groupby(["ym", "kind"]).size().unstack(fill_value=0)
    D["activity"]["by_month"] = {"ym": am.index.tolist(),
                                 "series": {c: [int(x) for x in am[c]] for c in am.columns}}
