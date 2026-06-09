"""Emoji usage (you vs others) and tap-back reaction analysis."""
from collections import Counter
import emoji as emojilib


def _emoji_counts(text_series):
    c = Counter()
    for txt, cnt in text_series.value_counts().items():
        for e in emojilib.distinct_emoji_list(str(txt)):
            c[e] += cnt
    return c


def compute(ctx, D):
    print("emoji analysis ...")
    tx, rx, self_name = ctx.tx, ctx.rx, ctx.self_name
    em_self = _emoji_counts(tx[tx.is_self]["content"])
    em_other = _emoji_counts(tx[~tx.is_self]["content"])
    em_all = em_self + em_other
    D["emoji"] = {
        "top_all": [{"emoji": k, "n": int(v)} for k, v in em_all.most_common(30)],
        "top_self": [{"emoji": k, "n": int(v)} for k, v in em_self.most_common(20)],
        "top_other": [{"emoji": k, "n": int(v)} for k, v in em_other.most_common(20)],
        "total_self": int(sum(em_self.values())),
        "total_other": int(sum(em_other.values())),
    }
    if len(rx):
        rc = Counter()
        for e, cnt in rx["emoji"].value_counts().items():
            for ch in emojilib.distinct_emoji_list(str(e)):
                rc[ch] += cnt
        D["emoji"]["top_reactions"] = [{"emoji": k, "n": int(v)} for k, v in rc.most_common(20)]
        to_me = rx[rx["target_sender"] == self_name]["reactor"].value_counts().head(12)
        by_me = rx[rx["reactor"] == self_name]["target_sender"].value_counts().head(12)
        D["reactions"] = {
            "who_reacts_to_me": [{"name": ctx.disp(k), "n": int(v)} for k, v in to_me.items()],
            "whom_i_react_to": [{"name": ctx.disp(k), "n": int(v)} for k, v in by_me.items()],
        }
