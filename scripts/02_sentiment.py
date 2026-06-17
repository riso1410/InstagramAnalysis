#!/usr/bin/env python3
"""
02_sentiment.py — Sentiment scoring of all text messages.

Model: kinit/slovakbert-sentiment-twitter (default; configurable via config.yaml)
  - SlovakBERT fine-tuned on the Slovak part of the Multilingual Twitter
    Sentiment dataset (~50k manually annotated Slovak tweets), 3-class:
    Negative / Neutral / Positive. Tuned for short informal Slovak social text.
  - Any 3-class HF sequence-classification model works: labels are read from
    the model config and remapped to (neg, neu, pos), handling both word labels
    (negative/neutral/positive) and numeric ones (-1/0/1).

DS optimisation: score only UNIQUE normalised texts (294k of 483k), then map back.
Runs on Apple MPS, length-sorted batching to minimise padding waste.

Output: data/clean/sentiment.parquet  (one row per ORIGINAL message, aligned)
        columns: neg, neu, pos, compound (pos-neg), sent_label
"""
import time, sys
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

try:
    from _config import load_config
    MODEL = load_config(verbose=False)["sentiment_model"]
except Exception:
    MODEL = "kinit/slovakbert-sentiment-twitter"
OUT = "data/clean/sentiment.parquet"
BATCH = 128
MAXLEN = 128

def main():
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device: {dev}")

    df = pd.read_parquet("data/clean/messages.parquet", columns=["content", "has_text"])
    df["norm"] = df["content"].where(df["has_text"], None)
    df.loc[df["norm"].notna(), "norm"] = df.loc[df["norm"].notna(), "norm"].str.strip()
    df.loc[df["norm"] == "", "norm"] = None

    uniq = df.loc[df["norm"].notna(), "norm"].drop_duplicates().tolist()
    print(f"unique texts to score: {len(uniq):,}")

    print("loading model ...")
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(MODEL).to(dev).eval()
    # Map model output ids -> our fixed (neg, neu, pos) order. Handles both word
    # labels (negative/neutral/positive, e.g. cardiffnlp) and numeric labels
    # (-1/0/1, e.g. SlovakBERT-based models).
    id2label = model.config.id2label
    order = [None, None, None]
    for i, lab in id2label.items():
        l = str(lab).strip().lower()
        if "neg" in l or l in ("-1", "-1.0"):
            order[0] = i
        elif "pos" in l or l in ("1", "1.0", "+1"):
            order[2] = i
        elif "neu" in l or l in ("0", "0.0"):
            order[1] = i
    if None in order:
        # Unrecognised label names: fall back to the conventional id ordering
        # (0=neg, 1=neu, 2=pos), which most 3-class sentiment models follow.
        print(f"warning: could not map labels {id2label}; assuming 0/1/2 = neg/neu/pos")
        order = [0, 1, 2]
    print("label order (neg,neu,pos) -> ids:", order)

    # length-sorted for efficient padding; remember original positions
    idx_sorted = sorted(range(len(uniq)), key=lambda i: len(uniq[i]))
    scores = np.zeros((len(uniq), 3), dtype=np.float32)

    t0 = time.time()
    done = 0
    with torch.no_grad():
        for b in range(0, len(idx_sorted), BATCH):
            chunk_idx = idx_sorted[b:b + BATCH]
            texts = [uniq[i] for i in chunk_idx]
            enc = tok(texts, padding=True, truncation=True, max_length=MAXLEN,
                      return_tensors="pt").to(dev)
            logits = model(**enc).logits
            probs = torch.softmax(logits, dim=-1).float().cpu().numpy()
            for j, i in enumerate(chunk_idx):
                scores[i, 0] = probs[j, order[0]]
                scores[i, 1] = probs[j, order[1]]
                scores[i, 2] = probs[j, order[2]]
            done += len(texts)
            if b % (BATCH * 50) == 0:
                el = time.time() - t0
                rate = done / max(el, 1e-9)
                eta = (len(uniq) - done) / max(rate, 1e-9)
                print(f"  {done:,}/{len(uniq):,}  {rate:,.0f}/s  eta {eta/60:.1f}m", flush=True)

    print(f"scored in {(time.time()-t0)/60:.1f} min")

    su = pd.DataFrame({"norm": uniq,
                       "neg": scores[:, 0], "neu": scores[:, 1], "pos": scores[:, 2]})
    su["compound"] = su["pos"] - su["neg"]
    su["sent_label"] = su[["neg", "neu", "pos"]].values.argmax(1)
    su["sent_label"] = su["sent_label"].map({0: "negative", 1: "neutral", 2: "positive"})

    out = df[["norm"]].merge(su, on="norm", how="left")
    out = out.drop(columns=["norm"])
    out.to_parquet(OUT, index=False)
    print(f"saved {OUT}: {len(out):,} rows, {out['neg'].notna().sum():,} scored")
    print(out["sent_label"].value_counts(dropna=False))

if __name__ == "__main__":
    main()
