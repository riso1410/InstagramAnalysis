"""Non-message activity EDA (likes, stories, polls, ...) over time and by hour."""
import pandas as pd
from ..text_utils import series_to_dict

META = {"key": "activity", "title": "Activity timeline", "requires": ["activity.parquet"]}


def compute(ctx, D):
    print("activity EDA ...")
    act = ctx.load_clean("activity.parquet")
    if act is None or act.empty:
        return
    # stories_viewed/story_likes titles are account names -> honour exclude_people
    act = ctx.filter_people(act, ["title"])
    D["activity"] = {
        "totals": series_to_dict(act["kind"].value_counts()),
        "by_month": {},
        "by_hour": series_to_dict(act.groupby("hour").size().reindex(range(24), fill_value=0)),
    }
    am = act.groupby(["ym", "kind"]).size().unstack(fill_value=0)
    D["activity"]["by_month"] = {"ym": am.index.tolist(),
                                 "series": {c: [int(x) for x in am[c]] for c in am.columns}}
