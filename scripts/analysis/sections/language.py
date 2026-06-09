"""Word frequencies & n-grams, word clouds (base64 PNG), and NMF topic modelling."""
import base64, io
from collections import Counter
import numpy as np
from ..text_utils import tokenize


def compute(ctx, D):
    print("word frequencies & n-grams ...")
    tx, CFG = ctx.tx, ctx.CFG
    phrase_blocked = ctx.phrase_blocked

    word_c = Counter(); bigram_c = Counter()
    for txt, cnt in tx["content"].value_counts().items():
        toks = tokenize(txt)
        for t in toks: word_c[t] += cnt
        for a, b in zip(toks, toks[1:]): bigram_c[f"{a} {b}"] += cnt
    D["words"] = {
        "top": [{"word": k, "n": int(v)} for k, v in word_c.most_common() if not phrase_blocked(k)][:60],
        "top_bigrams": [{"bigram": k, "n": int(v)} for k, v in bigram_c.most_common() if not phrase_blocked(k)][:30],
    }

    # word clouds (overall + self) as base64 PNG
    try:
        from wordcloud import WordCloud
        WC_COLORS = ["#8a2a2a", "#2f4858", "#1c1a17", "#9c8348", "#5e7a6a"]
        def _color_func(word, font_size, position, orientation, random_state=None, **kw):
            return WC_COLORS[int(font_size) % len(WC_COLORS)]
        def wc_png(counter, n=150):
            if not counter: return None
            w = WordCloud(width=1000, height=500, background_color="#faf8f3", mode="RGB",
                          color_func=_color_func, max_words=n, prefer_horizontal=0.95,
                          relative_scaling=0.45).generate_from_frequencies(dict(counter.most_common(300)))
            buf = io.BytesIO(); w.to_image().save(buf, format="PNG")
            return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        self_words = Counter()
        for txt, cnt in tx[tx.is_self]["content"].value_counts().items():
            for t in tokenize(txt): self_words[t] += cnt
        wc_all = Counter({k: v for k, v in word_c.items() if not phrase_blocked(k)})
        wc_self = Counter({k: v for k, v in self_words.items() if not phrase_blocked(k)})
        D["wordcloud_all"] = wc_png(wc_all)
        D["wordcloud_self"] = wc_png(wc_self)
        print("  word clouds rendered")
    except Exception as e:
        print("  wordcloud failed:", e)

    # topic modelling (TF-IDF + NMF)
    print("topic modelling (TF-IDF + NMF) ...")
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import NMF
        docs = tx["content"].dropna()
        docs = docs[docs.str.split().str.len() >= 4]
        if len(docs) > 120000:
            docs = docs.sample(120000, random_state=42)
        docs = [" ".join(tokenize(d)) for d in docs]
        docs = [d for d in docs if len(d.split()) >= 3]
        vec = TfidfVectorizer(max_features=4000, min_df=20, max_df=0.4,
                              token_pattern=r"[a-záäčďéíĺľňóôŕšťúýž]{3,}")
        X = vec.fit_transform(docs)
        k = int(CFG["topics_k"])
        nmf = NMF(n_components=k, random_state=42, init="nndsvda", max_iter=300)
        W = nmf.fit_transform(X); H = nmf.components_
        terms = np.array(vec.get_feature_names_out())
        sizes = W.argmax(1)
        topics = []
        for i in range(k):
            top = terms[H[i].argsort()[::-1][:10]].tolist()
            topics.append({"id": i, "terms": top, "size": int((sizes == i).sum())})
        topics.sort(key=lambda t: t["size"], reverse=True)
        D["topics"] = topics
        print(f"  {k} topics over {len(docs):,} docs")
    except Exception as e:
        print("  topic modelling failed:", e)
