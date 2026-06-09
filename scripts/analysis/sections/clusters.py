"""K-means behavioural clustering of chats, projected to 3D via PCA.

Reads ctx.chats (people module) and ctx.per_chat_resp (dynamics module).
"""


def compute(ctx, D):
    print("behavioural clustering of chats ...")
    chats, per_chat_resp = ctx.chats, ctx.per_chat_resp or {}
    try:
        from sklearn.preprocessing import StandardScaler
        from sklearn.cluster import KMeans
        from sklearn.decomposition import PCA
        from sklearn.metrics import silhouette_score
        feat = chats[chats["n"] >= 200].copy()
        if len(feat) >= 8:
            _m = feat["thread_id"].map(per_chat_resp)
            feat["resp_med"] = _m.fillna(_m.median())
            feat["msgs_per_active_day"] = feat["n"] / feat["active_days"].clip(lower=1)
            cols = ["my_share", "avg_len_chars", "msgs_per_active_day", "resp_med"]
            if "sent_compound" in feat: cols.append("sent_compound")
            feat[cols] = feat[cols].fillna(feat[cols].median())
            Xf = StandardScaler().fit_transform(feat[cols].values)
            best_k, best_s = 3, -1
            for kk in range(3, min(7, len(feat) - 1)):
                lab = KMeans(n_clusters=kk, n_init=10, random_state=0).fit_predict(Xf)
                try:
                    s = silhouette_score(Xf, lab)
                    if s > best_s: best_s, best_k = s, kk
                except Exception: pass
            km = KMeans(n_clusters=best_k, n_init=10, random_state=0).fit(Xf)
            ncomp = min(3, Xf.shape[1])
            proj = PCA(n_components=ncomp, random_state=0).fit_transform(Xf)
            D["clusters"] = {
                "k": int(best_k), "silhouette": round(float(best_s), 3), "features": cols,
                "points": [{"title": t, "x": float(proj[i, 0]), "y": float(proj[i, 1]),
                            "z": float(proj[i, 2]) if ncomp > 2 else 0.0,
                            "cluster": int(km.labels_[i]), "n": int(feat.iloc[i]["n"]),
                            "is_group": bool(feat.iloc[i]["is_group"])}
                           for i, t in enumerate(feat["title"].tolist())],
            }
            print(f"  k={best_k} silhouette={best_s:.3f} over {len(feat)} chats")
    except Exception as e:
        print("  clustering failed:", e)
