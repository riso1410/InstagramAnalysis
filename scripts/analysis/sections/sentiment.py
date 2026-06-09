"""Sentiment aggregates: distribution, over-time, by hour/weekday, brightest/heaviest chats."""
import pandas as pd
from ..text_utils import WEEKDAYS, series_to_dict


def compute(ctx, D):
    if ctx.sent is None:
        return
    print("sentiment aggregates ...")
    st = ctx.inbox[ctx.inbox["is_human_text"]].copy()
    chats = ctx.chats
    D["sentiment"] = {
        "distribution": series_to_dict(st["sent_label"].value_counts()),
        "overall_compound": round(float(st["compound"].mean()), 4),
        "self_compound": round(float(st[st.is_self]["compound"].mean()), 4),
        "other_compound": round(float(st[~st.is_self]["compound"].mean()), 4),
    }
    sm = st.groupby("ym").agg(compound=("compound", "mean"), pos=("pos", "mean"),
                              neg=("neg", "mean"), neu=("neu", "mean"), n=("compound", "size")).reset_index()
    D["sentiment"]["by_month"] = {
        "ym": sm["ym"].tolist(),
        "compound": [round(x, 4) for x in sm["compound"]],
        "pos": [round(x, 4) for x in sm["pos"]],
        "neg": [round(x, 4) for x in sm["neg"]],
        "n": [int(x) for x in sm["n"]],
    }
    sh = st.groupby("hour")["compound"].mean().reindex(range(24))
    D["sentiment"]["by_hour"] = {"hours": list(range(24)), "compound": [round(float(x), 4) if pd.notna(x) else None for x in sh]}
    sw = st.groupby("weekday")["compound"].mean().reindex(range(7))
    D["sentiment"]["by_weekday"] = {"labels": WEEKDAYS, "compound": [round(float(x), 4) if pd.notna(x) else None for x in sw]}
    cc = chats[chats["n"] >= 300].dropna(subset=["sent_compound"]) if "sent_compound" in chats else pd.DataFrame()
    if len(cc):
        D["sentiment"]["most_positive_chats"] = cc.nlargest(10, "sent_compound")[["title", "sent_compound", "n", "pos_pct", "neg_pct"]].to_dict("records")
        D["sentiment"]["most_negative_chats"] = cc.nsmallest(10, "sent_compound")[["title", "sent_compound", "n", "pos_pct", "neg_pct"]].to_dict("records")
