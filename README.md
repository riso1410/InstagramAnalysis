# Instagram — A Data Portrait

A comprehensive, ML-driven exploratory analysis of a personal Instagram data export
(2 ZIP archives → **504,352 messages** across **243 conversations**, 2018–2026), rendered
as a single self-contained interactive HTML dashboard.

## ▶ Open the dashboard

```
open output/Instagram_Dashboard.html
```

One file, ~5 MB, fully offline (Plotly + all data inlined). 11 scrollable sections with
interactive charts, in a calm editorial light theme.

## ⚙ Customize — `config.yaml`

All customization lives in **`config.yaml`** (no code editing). Edit it, then re-run
`scripts/03_analysis.py` + `scripts/04_build_dashboard.py` (~15s — the slow sentiment step is **not**
needed, filters apply at analysis time):

```yaml
exclude_people:        # drop a person completely (DMs removed, their group msgs removed)
  - "BUBEL"
exclude_phrases:       # tag-filter biased tokens out of "Common phrases" / words / clouds
  - "audio call"
  - "started chat"
date_from: null        # "YYYY-MM-DD" window, or null
date_to: null
min_chat_messages: 1   # min messages for a chat to appear
topics_k: 12           # number of NMF topics
top_chats: 60          # chats kept in the ledger
sentiment_model: "cardiffnlp/twitter-xlm-roberta-base-sentiment"
```

Matching is case-insensitive substring (so `BUBEL` matches `⭐️BUBEL🧋`). Everything is optional.

## ▶ Swap in your own data (one command)

Anyone can regenerate the whole dashboard from *their* Instagram export — no code changes,
no hardcoded filenames, account owner auto-detected:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # one-time setup
.venv/bin/python run.py                 # auto-detects *.zip in this folder
# or:
.venv/bin/python run.py a.zip b.zip     # point at your export archives
.venv/bin/python run.py --dir ~/Downloads
.venv/bin/python run.py --skip-sentiment   # skip the transformer (much faster)
```

`run.py` does **extract → parse → sentiment → analysis → build** and writes
`output/Instagram_Dashboard.html`. The extractor (`scripts/00_extract.py`) reads JSON straight
from the ZIPs with the stdlib (cross-platform, no `unzip` needed) and replaces any prior export.

## What's inside the analysis

| Section | Contents |
|---|---|
| **Overview** | Headline KPIs — totals, sent/received split, reactions, streaks, busiest day |
| **Timeline** | Messages per month (sent vs received), per year, daily volume |
| **Rhythms** | Hour-of-day, day-of-week, month-of-year, weekday×hour heatmap, year×month seasonality, **3D weekday×hour surface** |
| **People** | Top conversations, DM vs group split, sortable ledger, **3D conversation galaxy**, **Message Explorer** (real messages, filter by conversation) |
| **Dynamics** | Reply-time distributions, who initiates, message length, outbox composition |
| **Sentiment** | Distribution, sentiment-over-time, per-chat emotional map, by hour/weekday, brightest/heaviest chats |
| **Language** | Word clouds, top words, bigrams, NMF latent topics |
| **Brainrot Index** | Slang/brainrot/vulgarity lexicon — trend over time, flavours, top terms, most "chronically online" chats |
| **Emoji & Reactions** | Most-used emoji (you vs others), reaction palette, who reacts to whom |
| **Clusters** | K-means behavioural clustering of chats, **3D PCA projection** |
| **Activity** | Likes, stories viewed, polls, etc. over time and by hour |

## Pipeline (what `run.py` orchestrates)

```
scripts/00_extract.py        # ZIP -> data/raw/ (JSON only, stdlib zipfile)
scripts/01_parse.py          # -> tidy parquet tables in data/clean/
scripts/02_sentiment.py      # XLM-RoBERTa sentiment on MPS (unique-text dedup)
scripts/03_analysis.py       # EDA + ML feature computation -> output/data.json
scripts/04_build_dashboard.py# inline Plotly + data -> Instagram_Dashboard.html
scripts/05_validate.py       # headless-Chromium render check + screenshots (optional QA)
```

## Architecture (modular & extensible)

The analysis engine is a small package — `03_analysis.py` is just a 34-line orchestrator:

```
scripts/analysis/
├── context.py        # AnalysisContext: loads data once, applies config (exclusions,
│                     #   date window, phrase filter), exposes shared frames (df, inbox, tx,
│                     #   and cross-section results: ctx.chats, ctx.per_chat_resp)
├── text_utils.py     # stopwords, lemmatizer, tokenizer, emoji/URL regexes, JSON helpers
├── __init__.py       # SECTIONS registry + run() — executes each module in order
└── sections/         # one self-contained module per analysis, each: compute(ctx, D)
    ├── overview.py  temporal.py  people.py    examples.py  length.py
    ├── dynamics.py  emoji.py     language.py  slang.py     clusters.py
    └── sentiment.py activity.py  interests.py
```

**Add a new analysis** in two steps: drop `sections/my_thing.py` with a
`def compute(ctx, D): D["my_thing"] = ...` function, then register it in
`analysis/__init__.py:SECTIONS`. It automatically gets the shared, config-filtered
data via `ctx` and its output flows into `data.json` for the dashboard. Order only
matters where a module reads another's shared output (e.g. `clusters` uses `ctx.chats`).

## Libraries do the heavy lifting (no hand-rolled NLP)

| Concern | Library |
|---|---|
| Mojibake / text repair | **ftfy** |
| Lemmatization (Slovak) | **simplemma** |
| Tokenization | **simplemma.simple_tokenizer** |
| Stopwords | **stopwords-iso** (sk + en + cs) |
| Emoji parsing | **emoji** |
| Transliteration / de-accent | **unidecode** |
| Sentiment | **transformers** (XLM-RoBERTa) on **PyTorch** MPS |
| Topics / clustering | **scikit-learn** (TF-IDF, NMF, KMeans, PCA) |
| Word clouds | **wordcloud** · Charts: **Plotly** |

## Methodology & caveats

- **Mojibake repair.** Instagram exports text as Latin-1-encoded UTF-8; every string is fixed
  with the **ftfy** library so Slovak diacritics render correctly.
- **Timezone.** UTC ms timestamps → `Europe/Bratislava` local time.
- **System messages.** ~79k auto-generated lines ("X sent an attachment", "Reacted ❤ to your
  message", group-membership notices) are detected and **excluded** from language & sentiment
  analysis; reactions are counted separately from the reactions table to avoid double-counting.
- **Sentiment.** `cardiffnlp/twitter-xlm-roberta-base-sentiment` (multilingual XLM-RoBERTa,
  social-media fine-tuned), run on Apple-Silicon MPS over ~294k unique texts. `compound = P(pos) − P(neg)`.
  The model leans neutral/negative on terse, ironic Slovak chat, so **read scores comparatively**
  (between chats / across time) rather than as absolute truth.
- **ML.** Topics = TF-IDF + NMF (12 components); chat clustering = K-means on standardized
  behavioural features (your share, msg length, intensity, reply speed, tone) + PCA projection;
  reply-time & initiation from intra-thread turn-taking gaps; slang = accent-insensitive lexicon match.
- **Stack.** Python · pandas · scikit-learn · PyTorch (MPS) · Plotly. (No PySpark — 504k rows fit
  comfortably in memory and parse in seconds; distributed overhead would only slow it down.)

## A few findings

- One conversation (**Barbora Gombitová**) accounts for ~43% of all messages; the top 3 people
  account for ~67%.
- You **receive ~2× more** than you send; the median reply time is well under a minute on both sides.
- Slang/brainrot rate **rose ~37%** from the earliest to the most-recent quarter of the archive.
- Sentiment runs mildly negative in absolute terms (model bias on casual text) but varies
  meaningfully across chats and months.
