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
    def blocked(s):   # phrase filter + contact-name filter (anonymize mode)
        return phrase_blocked(s) or ctx.name_blocked(s)

    D["words"] = {
        "top": [{"word": k, "n": int(v)} for k, v in word_c.most_common() if not blocked(k)][:60],
        "top_bigrams": [{"bigram": k, "n": int(v)} for k, v in bigram_c.most_common() if not blocked(k)][:30],
    }

    # word clouds (overall + self) as base64 WebP (~6x smaller than PNG inline)
    try:
        from wordcloud import WordCloud
        WC_COLORS = ["#e1306c", "#4f5bd5", "#962fbf", "#fa7e1e", "#262626"]
        def _color_func(word, font_size, position, orientation, random_state=None, **kw):
            return WC_COLORS[int(font_size) % len(WC_COLORS)]
        def wc_png(counter, n=150):
            if not counter: return None
            w = WordCloud(width=1000, height=500, background_color="#ffffff", mode="RGB",
                          color_func=_color_func, max_words=n, prefer_horizontal=0.95,
                          relative_scaling=0.45).generate_from_frequencies(dict(counter.most_common(300)))
            buf = io.BytesIO(); w.to_image().save(buf, format="WEBP", quality=82, method=6)
            return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()
        self_words = Counter()
        for txt, cnt in tx[tx.is_self]["content"].value_counts().items():
            for t in tokenize(txt): self_words[t] += cnt
        wc_all = Counter({k: v for k, v in word_c.items() if not blocked(k)})
        wc_self = Counter({k: v for k, v in self_words.items() if not blocked(k)})
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
            top = [t for t in terms[H[i].argsort()[::-1]].tolist() if not ctx.name_blocked(t)][:10]
            topics.append({"id": i, "terms": top, "size": int((sizes == i).sum())})
        topics.sort(key=lambda t: t["size"], reverse=True)
        D["topics"] = topics
        print(f"  {k} topics over {len(docs):,} docs")

        # 3D word/topic clusters: each term is a point in topic-loading space
        # (its column of H), projected to 3D via PCA and coloured by the topic
        # it loads on most strongly. Words near each other are used in the
        # same contexts — a semantic "vocabulary galaxy".
        try:
            from sklearn.decomposition import PCA
            V = H.T                                   # (n_terms, k) topic loadings
            keep = [j for j in range(len(terms))
                    if V[j].sum() > 0 and not blocked(terms[j])]
            # most salient terms by peak topic loading, capped for a legible scene
            keep.sort(key=lambda j: V[j].max(), reverse=True)
            keep = keep[:240]
            if len(keep) >= 12:
                Vk = V[keep]
                dom = Vk.argmax(1)
                Vn = Vk / np.linalg.norm(Vk, axis=1, keepdims=True)  # direction only
                ncomp = min(3, Vn.shape[1])
                proj = PCA(n_components=ncomp, random_state=42).fit_transform(Vn)
                pts = [{"word": terms[keep[i]],
                        "x": float(proj[i, 0]), "y": float(proj[i, 1]),
                        "z": float(proj[i, 2]) if ncomp > 2 else 0.0,
                        "topic": int(dom[i]),
                        "weight": float(Vk[i].max())}
                       for i in range(len(keep))]
                # one representative top term per topic, for legend labels
                labels = [t["terms"][0] if t["terms"] else f"topic {t['id']}"
                          for t in sorted(topics, key=lambda t: t["id"])]
                D["word_clusters"] = {"k": k, "points": pts, "labels": labels}
                print(f"  word/topic 3D clusters: {len(pts)} terms")
        except Exception as e:
            print("  word clustering failed:", e)
    except Exception as e:
        print("  topic modelling failed:", e)
