"""Message-length distributions (words per message), you vs them."""
import pandas as pd


def compute(ctx, D):
    tx = ctx.tx
    bins = [0, 1, 2, 5, 10, 20, 40, 80, 160, 320, 100000]
    blabels = ["1", "2", "3-5", "6-10", "11-20", "21-40", "41-80", "81-160", "161-320", "320+"]
    wc = pd.cut(tx["n_words"], bins=bins, labels=blabels, right=True, include_lowest=True)
    D["length"] = {
        "word_bins": blabels,
        "word_counts_all": [int(x) for x in wc.value_counts().reindex(blabels, fill_value=0)],
        "word_counts_self": [int(x) for x in pd.cut(tx[tx.is_self]["n_words"], bins=bins, labels=blabels, include_lowest=True).value_counts().reindex(blabels, fill_value=0)],
        "word_counts_other": [int(x) for x in pd.cut(tx[~tx.is_self]["n_words"], bins=bins, labels=blabels, include_lowest=True).value_counts().reindex(blabels, fill_value=0)],
        "avg_words_self": round(float(tx[tx.is_self]["n_words"].mean()), 2),
        "avg_words_other": round(float(tx[~tx.is_self]["n_words"].mean()), 2),
        "median_chars_self": int(tx[tx.is_self]["n_chars"].median()),
        "median_chars_other": int(tx[~tx.is_self]["n_chars"].median()),
    }
