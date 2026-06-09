"""Message Explorer sample: the chronological opening of each top conversation."""

META = {"key": "examples", "title": "Message Explorer", "privacy": "high"}


def compute(ctx, D):
    CFG, self_name, sent = ctx.CFG, ctx.self_name, ctx.sent
    chats, title_map = ctx.chats, ctx.title_map
    ex, order = {}, []
    if not CFG["privacy"]["include_examples"]:
        print("sampling example messages ... skipped (privacy.include_examples=false)")
    else:
        print("sampling example messages (first messages of each chat) ...")
        exdf = ctx.inbox[ctx.inbox["is_human_text"]]
        for tid in chats.head(40)["thread_id"].tolist():
            sub = exdf[exdf["thread_id"] == tid]
            if len(sub) < 5:
                continue
            msgs = sub.sort_values("dt").head(40)
            is_group = bool(sub["is_group"].iloc[0])
            order.append(tid)
            ex[tid] = {
                "title": ctx.disp_title(title_map.get(tid) or tid, is_group),
                "is_group": is_group,
                "messages": [{"self": bool(r.is_self),
                              # first name only — unless anonymized ("Person 01" must stay whole)
                              "sender": (lambda d: d if ctx.anonymize else d.split()[0])(
                                  ctx.disp(self_name if r.is_self else r.sender)),
                              "date": str(r.dt)[:16],
                              "text": str(r.content)[:260],
                              "label": (r.sent_label if sent is not None else None),
                              "react": int(r.n_reactions)} for r in msgs.itertuples()],
            }
    D["examples"] = ex
    D["examples_order"] = order
