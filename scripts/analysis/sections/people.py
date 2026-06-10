"""Per-chat statistics (the conversation ledger) and global top senders.

Stores ctx.chats and ctx.title_map for downstream modules (examples, clusters, sentiment).
"""
import pandas as pd


def compute(ctx, D):
    print("per-chat stats ...")
    inbox, rx, self_name, sent, CFG = ctx.inbox, ctx.rx, ctx.self_name, ctx.sent, ctx.CFG
    chat_rows = []
    title_map = inbox.groupby("thread_id")["thread_title"].first()
    for tid, sub in inbox.groupby("thread_id"):
        n = len(sub); ns = int(sub["is_self"].sum())
        rsub = rx[rx["thread_id"] == tid] if len(rx) else rx
        row = {
            "thread_id": tid,
            "title": title_map.get(tid) or tid,
            "is_group": bool(sub["is_group"].iloc[0]),
            "n": n, "sent": ns, "received": n - ns,
            "my_share": round(ns / n, 3),
            "first": str(sub["dt"].min().date()), "last": str(sub["dt"].max().date()),
            "span_days": int((sub["dt"].max() - sub["dt"].min()).days) + 1,
            "active_days": int(sub["date"].nunique()),
            "avg_len_chars": round(float(sub.loc[sub.is_human_text, "n_chars"].mean() or 0), 1),
            "media": int((sub["has_photo"] | sub["has_video"]).sum()),
            "shares": int(sub["has_share"].sum()),
            "reactions_recv": int((rsub["target_sender"] == self_name).sum()) if len(rsub) else 0,
            "reactions_given": int((rsub["reactor"] == self_name).sum()) if len(rsub) else 0,
        }
        if sent is not None:
            ts = sub[sub["is_human_text"]]
            if len(ts):
                row["sent_compound"] = round(float(ts["compound"].mean()), 4)
                vc = ts["sent_label"].value_counts(normalize=True)
                row["pos_pct"] = round(float(vc.get("positive", 0)), 4)
                row["neg_pct"] = round(float(vc.get("negative", 0)), 4)
                row["neu_pct"] = round(float(vc.get("neutral", 0)), 4)
        chat_rows.append(row)
    chats = pd.DataFrame(chat_rows).sort_values("n", ascending=False).reset_index(drop=True)
    chats = chats[chats["n"] >= CFG["min_chat_messages"]].reset_index(drop=True)
    # anonymize once at the source: ctx.chats feeds clusters/sentiment/galaxy, so a
    # display-safe title here covers every downstream chart
    chats["title"] = [ctx.disp_title(t, g) for t, g in zip(chats["title"], chats["is_group"])]
    out = chats.head(CFG["top_chats"]).to_dict(orient="records")
    for r in out:   # IG thread ids embed usernames — pseudonymize in emitted records
        r["thread_id"] = ctx.disp_tid(r["thread_id"])
    D["chats"] = out
    D["n_chats_analyzed"] = int(len(chats))
    ctx.chats = chats
    ctx.title_map = title_map   # real titles — consumers apply ctx.disp_title themselves

    snd = inbox.groupby("sender").size().sort_values(ascending=False)
    D["top_senders"] = [{"sender": ctx.disp(k), "n": int(v)} for k, v in snd.head(25).items()]
