"""Personalized writing patterns — your style fingerprint, signature words,
go-to lines, and your longest messages.

Aggregate style metrics are always emitted (safe to share). Verbatim message
text (longest messages, go-to lines) is gated behind privacy.include_examples,
exactly like the Message Explorer, and scrubbed of contact names when anonymizing.
"""
import re
from collections import Counter
import emoji as emojilib
from ..text_utils import tokenize

# laughter across the languages in this archive (sk/cs/en) plus the usual emoji
LAUGH_RE = re.compile(r"(hah(a|e)|haha|hihi|hehe|\bxd+\b|\blol+\b|😂|🤣|😅|😆)", re.IGNORECASE)


def _style(df):
    """Writing-style rates for a message frame, as percentages of messages."""
    n = len(df)
    if not n:
        return {}
    c = df["content"].fillna("").astype(str)
    lc = c.str.lower()
    letters = c.str.count(r"[^\W\d_]")  # unicode letters only
    out = {
        "n": int(n),
        "avg_words": round(float(df["n_words"].mean()), 1),
        "avg_chars": round(float(df["n_chars"].mean()), 1),
        "q_rate": round(100 * float(c.str.contains(r"\?", regex=True).mean()), 1),
        "excl_rate": round(100 * float(c.str.contains("!", regex=False).mean()), 1),
        "ellipsis_rate": round(100 * float(c.str.contains(r"\.\.", regex=True).mean()), 1),
        "laugh_rate": round(100 * float(lc.str.contains(LAUGH_RE).mean()), 1),
        "caps_rate": round(100 * float(((c.str.upper() == c) & (letters >= 3)).mean()), 1),
    }
    # emoji rate — the lib call is the slow part, so dedup over unique texts first
    emoji_hits = 0
    for txt, cnt in c.value_counts().items():
        if emojilib.emoji_count(txt):
            emoji_hits += cnt
    out["emoji_rate"] = round(100 * emoji_hits / n, 1)
    return out


def compute(ctx, D):
    print("writing patterns ...")
    tx, CFG = ctx.tx, ctx.CFG
    self_df = tx[tx.is_self]
    other_df = tx[~tx.is_self]
    if self_df.empty:
        print("  no outgoing text messages — skipped")
        return
    include_text = CFG["privacy"]["include_examples"]
    title_map = ctx.title_map if ctx.title_map is not None else {}

    def blocked(s):
        return ctx.phrase_blocked(s) or ctx.name_blocked(s)

    res = {
        "self": _style(self_df),
        "other": _style(other_df),
        "include_text": include_text,
    }

    # --- signature words: lemmas you use far more than everyone else ----------
    sc, oc = Counter(), Counter()
    for txt, cnt in self_df["content"].value_counts().items():
        for t in tokenize(txt):
            sc[t] += cnt
    for txt, cnt in other_df["content"].value_counts().items():
        for t in tokenize(txt):
            oc[t] += cnt
    st, ot = max(sum(sc.values()), 1), max(sum(oc.values()), 1)
    sig = []
    for w, sn in sc.items():
        if sn < 30 or blocked(w):
            continue
        self_rate = sn / st
        other_rate = (oc.get(w, 0) + 1) / (ot + 1)   # +1 smoothing for rare words
        lift = self_rate / other_rate
        if lift > 1.3:
            sig.append({"word": w, "n": int(sn), "lift": round(float(lift), 1)})
    sig.sort(key=lambda x: x["lift"], reverse=True)
    res["signature"] = sig[:15]

    # --- top 5 longest messages you sent --------------------------------------
    longest = []
    for r in self_df.nlargest(5, "n_chars").itertuples():
        is_group = bool(getattr(r, "is_group", False))
        longest.append({
            "chars": int(r.n_chars), "words": int(r.n_words),
            "date": str(r.dt)[:10],
            "chat": ctx.disp_title(title_map.get(r.thread_id) or r.thread_id, is_group),
            "react": int(r.n_reactions),
            "text": ctx.scrub_names(str(r.content)[:700]) if include_text else None,
        })
    res["longest"] = longest

    # --- go-to lines: your most-repeated exact messages -----------------------
    goto = []
    if include_text:
        for txt, cnt in self_df["content"].value_counts().items():
            s = str(txt).strip()
            if not s or blocked(s):
                continue
            goto.append({"text": ctx.scrub_names(s[:60]), "n": int(cnt)})
            if len(goto) >= 10:
                break
    res["go_to"] = goto

    D["writing"] = res
    print(f"  fingerprint over {len(self_df):,} of your messages · "
          f"{len(res['signature'])} signature words · {len(longest)} longest")
