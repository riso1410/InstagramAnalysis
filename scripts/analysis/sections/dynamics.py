"""Reply-time distributions and conversation initiation (DMs).

Stores ctx.per_chat_resp (median self reply time per chat) for the clusters module.
"""
from collections import Counter
import numpy as np
import pandas as pd


def compute(ctx, D):
    print("response times & conversation dynamics ...")
    inbox = ctx.inbox
    GAP_NEW_CONV = pd.Timedelta(hours=6)
    resp_self, resp_other = [], []
    init_counter = Counter()
    per_chat_resp = {}
    for tid, sub in inbox[~inbox["is_group"]].sort_values("dt").groupby("thread_id"):
        s = sub[["dt", "is_self", "sender"]].reset_index(drop=True)
        prev_self = None; prev_dt = None
        chat_self_rt = []
        for dt, is_self in zip(s["dt"], s["is_self"]):
            if prev_dt is not None:
                gap = (dt - prev_dt).total_seconds()
                if gap > GAP_NEW_CONV.total_seconds():
                    init_counter[("self" if is_self else "other", tid)] += 1
                elif is_self != prev_self and gap < 6 * 3600:
                    if is_self: resp_self.append(gap); chat_self_rt.append(gap)
                    else: resp_other.append(gap)
            else:
                init_counter[("self" if is_self else "other", tid)] += 1
            prev_self = is_self; prev_dt = dt
        if chat_self_rt:
            per_chat_resp[tid] = float(np.median(chat_self_rt))
    ctx.per_chat_resp = per_chat_resp

    def rt_hist(vals):
        vals = np.array(vals)
        edges = [0, 60, 300, 900, 1800, 3600, 7200, 21600]
        lbl = ["<1m", "1-5m", "5-15m", "15-30m", "30-60m", "1-2h", "2-6h"]
        h = np.histogram(vals, bins=edges)[0]
        return lbl, [int(x) for x in h]
    lbl, hs = rt_hist(resp_self); _, ho = rt_hist(resp_other)
    D["response"] = {
        "bins": lbl, "self": hs, "other": ho,
        "median_self_sec": int(np.median(resp_self)) if resp_self else None,
        "median_other_sec": int(np.median(resp_other)) if resp_other else None,
        "mean_self_sec": int(np.mean(resp_self)) if resp_self else None,
        "mean_other_sec": int(np.mean(resp_other)) if resp_other else None,
    }
    init_self = sum(v for (who, _), v in init_counter.items() if who == "self")
    init_other = sum(v for (who, _), v in init_counter.items() if who == "other")
    D["initiation"] = {"self": int(init_self), "other": int(init_other),
                       "self_share": round(init_self / max(init_self + init_other, 1), 3)}
