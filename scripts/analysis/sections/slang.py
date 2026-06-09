"""Brainrot / slang / vulgarity lexicon mining and the monthly 'brainrot index'."""
import re
from collections import Counter
import numpy as np
from ..text_utils import deacc

# categorised lexicon (single tokens, matched accent-insensitively / lowercase)
LEX = {
    "Gen-Z brainrot": ["skibidi", "rizz", "gyat", "gyatt", "sigma", "ohio", "mewing", "aura", "npc",
        "delulu", "based", "sus", "cringe", "gigachad", "chad", "sheesh", "pov", "slay", "ratio", "mid",
        "goat", "goated", "bussin", "yeet", "simp", "cope", "mald", "pog", "poggers", "drip", "lowkey",
        "highkey", "finna", "deadass", "cooked", "cooking", "peak", "washed", "clutch", "glaze", "mog",
        "mogged", "looksmaxxing", "fanum", "opp", "cap", "nocap", "sybau", "edging", "rizzler", "skibid",
        "gyatt", "fr", "frfr", "ick", "yap", "yapping", "menty", "huzz", "bop", "diddy", "grimace"],
    "Chat acronym": ["lol", "lel", "lmao", "lmfao", "rofl", "omg", "omfg", "wtf", "wtff", "idk", "idc",
        "ngl", "tbh", "imo", "imho", "smh", "fyp", "gg", "ggs", "ez", "wp", "afk", "brb", "nvm", "rip",
        "xd", "xdd", "xddd", "xdddd", "wbu", "hbu", "btw", "asap", "irl", "dm", "pls", "plz", "thx",
        "ily", "wyd", "hmu", "tldr", "ootd"],
    "Slovak slang": ["kamo", "bracho", "vole", "digga", "cao", "joj", "kokso", "debo", "hejt",
        "hype", "ban", "kek", "jaj", "cavo", "typek", "dako", "daco", "hento", "ziju", "boomer",
        "cringe", "sus", "vibe", "vibes", "chill", "random", "trapko", "respekt", "kemo", "bro",
        "brasko", "dabest", "mega", "fullka", "sigma", "rizz", "based", "kapo", "synak"],
    "Vulgar (SK)": ["kurva", "kokot", "pica", "debil", "srac", "hovno", "doriti", "dopici", "curak",
        "mrdka", "zmrd", "jebo", "jebnute", "skurvene", "kktko", "pico", "nasrat", "blbec", "idiot",
        "sracka", "hajzel", "kokotina", "picovina", "dojebane", "vyjebane", "skurveny", "mrdat",
        "chuj", "buzerant", "sviniar", "kktk", "nasrany", "vyserie"],
}
PHRASES = ["no cap", "touch grass", "fanum tax", "ty kokot", "co kelo", "do pice", "do riti",
           "ty kokso", "let him cook", "real ones", "on god", "fell off", "no shot", "what the sigma"]


def compute(ctx, D):
    print("brainrot & slang lexicon mining ...")
    tx = ctx.tx
    tok2cat = {}
    for cat, toks in LEX.items():
        for t in toks:
            tok2cat.setdefault(deacc(t), cat)
    SLANG_STOP_OK = set(tok2cat)
    phrase_keys = [p.replace(" ", "_") for p in PHRASES]

    def slang_hits(text):
        d = deacc(str(text).lower())
        hits = [w for w in re.findall(r"[a-z]+", d) if w in SLANG_STOP_OK]
        hits += [p.replace(" ", "_") for p in PHRASES if p in d]
        return hits

    term_c = Counter(); cat_c = Counter(); self_c = Counter(); other_c = Counter()
    for is_self_flag, ser in [(True, tx[tx.is_self]["content"]), (False, tx[~tx.is_self]["content"])]:
        for txt, cnt in ser.value_counts().items():
            for h in slang_hits(txt):
                term_c[h] += cnt
                cat_c[tok2cat.get(h, "Gen-Z brainrot")] += cnt
                (self_c if is_self_flag else other_c)[h] += cnt

    uniq_hits = {t: len(slang_hits(t)) for t in tx["content"].dropna().unique()}
    tx_h = tx.assign(sh=tx["content"].map(uniq_hits).fillna(0))
    msgs_with = int((tx_h["sh"] > 0).sum())
    monthly = tx_h.groupby("ym").agg(hits=("sh", "sum"), n=("sh", "size")).reset_index()
    monthly["rate"] = (monthly["hits"] / monthly["n"] * 1000).round(2)
    chat_rate = (tx_h.groupby("thread_id")
                 .agg(hits=("sh", "sum"), n=("sh", "size"), title=("thread_title", "first")).reset_index())
    chat_rate = chat_rate[chat_rate["n"] >= 300].copy()
    chat_rate["rate"] = (chat_rate["hits"] / chat_rate["n"] * 1000).round(2)
    chat_rate = chat_rate.sort_values("rate", ascending=False)
    qparts = np.array_split(tx_h.sort_values("dt"), 4)
    q_rates = [round(float(p["sh"].sum() / max(len(p), 1) * 1000), 2) for p in qparts]
    growth_pct = round((q_rates[3] / q_rates[0] - 1) * 100) if q_rates[0] > 0 else None

    def split_for(term):
        return {"term": term, "n": int(term_c[term]),
                "self": int(self_c.get(term, 0)), "other": int(other_c.get(term, 0)),
                "cat": tok2cat.get(term, "Phrase")}
    D["slang"] = {
        "top_terms": [split_for(k) for k, _ in term_c.most_common(35)],
        "by_category": {k: int(v) for k, v in cat_c.most_common()},
        "total_hits": int(sum(term_c.values())),
        "msgs_with_slang": msgs_with,
        "msgs_scanned": int(len(tx_h)),
        "share_msgs": round(msgs_with / max(len(tx_h), 1), 4),
        "monthly": {"ym": monthly["ym"].tolist(),
                    "rate": [float(x) for x in monthly["rate"]],
                    "hits": [int(x) for x in monthly["hits"]]},
        "top_chats": [{"title": r.title, "rate": float(r.rate), "n": int(r.n)}
                      for r in chat_rate.head(12).itertuples()],
        "self_total": int(sum(self_c.values())),
        "other_total": int(sum(other_c.values())),
        "quartile_rates": q_rates,
        "growth_pct": growth_pct,
    }
    print(f"  slang hits: {D['slang']['total_hits']:,} across {msgs_with:,} msgs "
          f"({D['slang']['share_msgs']:.1%}); categories: {dict(cat_c)}")
