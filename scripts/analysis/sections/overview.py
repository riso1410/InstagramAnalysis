"""Top-level metadata and headline KPIs."""
import os, json
import pandas as pd


def compute(ctx, D):
    df, inbox, rx, meta = ctx.df, ctx.inbox, ctx.rx, ctx.meta
    self_name, sent = ctx.self_name, ctx.sent

    D["meta"] = {
        "self_name": ctx.disp(self_name),
        "generated_from": "Instagram data export",
        "timezone": meta["timezone"],
        "date_min": meta["date_min"][:10],
        "date_max": meta["date_max"][:10],
        "n_threads_total": int(df["thread_id"].nunique()),
        "n_threads_inbox": int(inbox["thread_id"].nunique()),
        "has_sentiment": bool(sent),
    }

    n_total = len(inbox)
    n_sent = int(inbox["is_self"].sum())
    days_active = inbox["date"].nunique()
    span_days = (inbox["dt"].max() - inbox["dt"].min()).days + 1
    daily = inbox.groupby("date").size()
    # longest active streak
    dseries = pd.Series(1, index=pd.to_datetime(sorted(inbox["date"].unique())))
    streak = best = 0; prev = None
    for d in dseries.index:
        if prev is not None and (d - prev).days == 1: streak += 1
        else: streak = 1
        best = max(best, streak); prev = d

    conn_path = f"{ctx.CLEAN}/connections.json"
    conn = json.load(open(conn_path)) if os.path.exists(conn_path) else {}
    D["kpis"] = {
        "total_messages": n_total,
        "messages_sent": n_sent,
        "messages_received": n_total - n_sent,
        "sent_share": round(n_sent / n_total, 4),
        "text_messages": int(inbox["has_text"].sum()),
        "human_text_messages": int(inbox["is_human_text"].sum()),
        "system_messages": int(inbox["is_system"].sum()),
        "media_messages": int((inbox["has_photo"] | inbox["has_video"] | inbox["has_audio"] | inbox["has_gif"]).sum()),
        "shares": int(inbox["has_share"].sum()),
        "calls": int(inbox["is_call"].sum()),
        "reactions_total": int(len(rx)),
        "reactions_given": int((rx["reactor"] == self_name).sum()) if len(rx) else 0,
        "reactions_received": int((rx["target_sender"] == self_name).sum()) if len(rx) else 0,
        "n_conversations": int(inbox["thread_id"].nunique()),
        "n_group_chats": int(inbox[inbox["is_group"]]["thread_id"].nunique()),
        "n_dm_chats": int(inbox[~inbox["is_group"]]["thread_id"].nunique()),
        "days_active": int(days_active),
        "span_days": int(span_days),
        "active_day_ratio": round(days_active / span_days, 3),
        "avg_msgs_per_active_day": round(n_total / days_active, 1),
        "busiest_day": str(daily.idxmax()),
        "busiest_day_count": int(daily.max()),
        "longest_streak_days": int(best),
        "total_words_sent": int(inbox.loc[inbox.is_self, "n_words"].sum()),
        "total_chars_sent": int(inbox.loc[inbox.is_self, "n_chars"].sum()),
        "n_message_requests": int((df["kind"] == "request").shape[0] and (df["kind"] == "request").sum()),
        "following": conn.get("following"),
        "followers": conn.get("followers"),
    }
