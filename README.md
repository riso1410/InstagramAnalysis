# InstagramAnalysis

Turn your entire Instagram data export into a single offline, interactive HTML dashboard.

One command reads the ZIP archives Meta sends you and renders a data portrait of your digital life: half a million messages, your social graph, your story habits, the advertisers who hold your data, and the security trail of every device you ever logged in from. Everything runs locally on your machine. Nothing is uploaded anywhere.

```bash
python run.py            # ZIPs in this folder -> output/Instagram_Dashboard.html
```

The result is one self-contained HTML file (Plotly and all data inlined, ~5 MB) that opens offline in any browser: 18 analysis sections, interactive charts, a calm editorial light theme.

Some things one real export surfaced (anonymized):

- One conversation accounted for 43% of half a million messages; the top three people for two thirds.
- The "stories viewed" file was actually a 30-day reels watch log: ~225 reels a day across 600 binge sessions, median 5 reels per sitting, worst binge 133 in one go.
- 3,402 distinct advertisers held the account's data; in the only impression window the export covers, 13.4% of logged feed items were paid ads.
- The login log doubled as a decade-long phone biography, and the algorithm's dismissed follow suggestions turned out to be right about 9% of the time.

## Prerequisites: get your Instagram data dump

This tool runs on the official Instagram data export, a set of ZIP archives full of JSON files. Request it first:

1. Instagram app or web: **Settings** -> **Accounts Center** -> **Your information and permissions** -> **Download your information** (or go directly to <https://accountscenter.instagram.com/info_and_permissions/dyi/>).
2. Choose **Download or transfer information**, select your Instagram account, then **All available information**.
3. **Format: JSON. This is required.** The default HTML format cannot be parsed; double-check this option before submitting. Date range: **All time**. Media quality does not matter (media files are ignored).
4. Wait for Meta's email. It can take from minutes up to a couple of days for large accounts. Download the ZIP(s); large archives arrive split into several ZIPs, keep them all.

You also need **Python 3.10+**. That is it. No accounts, no API keys.

## Quick start

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # one-time setup

.venv/bin/python run.py                    # auto-detects *.zip in this folder
.venv/bin/python run.py a.zip b.zip        # or point at your export archives
.venv/bin/python run.py --dir ~/Downloads  # or scan a folder for them
.venv/bin/python run.py --skip-sentiment   # skip the transformer model (much faster, no torch needed at runtime)

open output/Instagram_Dashboard.html
```

`run.py` orchestrates the whole pipeline: extract -> parse -> sentiment -> analysis -> build. The account owner is auto-detected from the export, so there is no per-user setup. Re-running after a config change only needs the last two stages (about 15 seconds):

```bash
.venv/bin/python scripts/03_analysis.py && .venv/bin/python scripts/04_build_dashboard.py
```

## What's analyzed

Every section is a self-contained module. Sections whose source files are missing from your export are skipped automatically; any section can be switched off in config (key in parentheses).

### Messages suite

| Section | Contents |
|---|---|
| Overview (`overview`) | Headline KPIs: totals, sent/received split, reactions, streaks, busiest day |
| Timeline & Rhythms (`temporal`) | Per month/year/day volume, hour-of-day, weekday, weekday x hour heatmap, seasonality, 3D surface |
| People (`people`) | Top conversations, DM vs group split, sortable ledger, 3D conversation galaxy |
| Message Explorer (`examples`) | Browse real messages, filtered by conversation (privacy: high) |
| Length (`length`) | Message length distributions, outbox composition |
| Dynamics (`dynamics`) | Reply-time distributions, who initiates, turn-taking |
| Sentiment (`sentiment`) | XLM-RoBERTa sentiment: distribution, over time, per chat, by hour and weekday |
| Language (`language`) | Word clouds, top words, bigrams, NMF latent topics |
| Brainrot Index (`slang`) | Slang/vulgarity lexicon: trend over time, flavours, most chronically online chats |
| Emoji & Reactions (`emoji`) | Most-used emoji (you vs others), reaction palette, who reacts to whom |
| Clusters (`clusters`) | K-means behavioural clustering of chats, 3D PCA projection |

### Beyond messages

| Section | Contents |
|---|---|
| Activity (`activity`) | Likes, polls, story interactions over time and by hour |
| Interests & Discovery (`interests`) | What you like: creators, hashtags (owner-weighted to defuse tag-wall bait), reel takeover over time, caption language mix |
| Social graph (`connections`) | Follower/following reciprocity, who followed first and how fast follow-backs close, blocks, unfollows, dismissed "suggested for you" accounts and the algorithm's hit rate (privacy: high) |
| Your Content & Comments (`content`) | Your posts, stories and stickers over the years, posting hours, your comment voice: where, how long, who you tag (privacy: medium) |
| Stories & Reels (`stories`) | Story engagement eras (polls/quizzes vs story likes), your inner circle of story interactions, the 30-day reels watch log with binge-session analysis (privacy: high) |
| What Meta Knows (`footprint`) | Advertiser counts (contact-list uploads vs activity matching), third-party targeting categories, ad density in the logged impression window, off-app websites reporting your visits (privacy: medium) |
| Security & Identity (`security`) | Login history as a device biography, login cities, password changes, profile/bio/privacy-flip history, in-app browser link trail (privacy: high) |

## Configuration

All customization lives in YAML, no code editing. `config.example.yaml` is the committed template; copy it to `config.yaml` for your personal settings (gitignored, never pushed). The two are deep-merged with your `config.yaml` winning, and every key is optional. The pipeline runs fine with no config at all.

```bash
cp config.example.yaml config.yaml
```

```yaml
# Remove a person from EVERY surface of the analysis. Case-insensitive
# substring match against chat titles, participants, senders, reactors,
# story owners, followers, search results. DMs with a matched person are
# dropped entirely; in groups only their messages are removed.
exclude_people:
  - "some name"
  - "@username"

# Phrases filtered out of "Common phrases", top words and word clouds.
# The template ships defaults that strip Instagram call/system boilerplate.
exclude_phrases:
  - "audio call"

# Privacy controls for sharing the generated dashboard
privacy:
  include_examples: true     # Message Explorer embeds real message text in the HTML
  anonymize_names: false     # every contact becomes a stable "Person 01", groups "Group 01"
  include_sensitive: true    # sections marked privacy=high (logins, message explorer, name lists)

# Switch any section off by key; the dashboard hides it automatically
sections: {}
#  slang: false
#  security: false

date_from: null              # "YYYY-MM-DD" analysis window, or null
date_to: null
timezone: "Europe/Bratislava"  # IANA name; all charts use your local time
min_chat_messages: 1         # min messages for a chat to appear in per-chat charts
topics_k: 12                 # number of NMF latent topics
top_chats: 60                # chats kept in the ledger
sentiment_model: "cardiffnlp/twitter-xlm-roberta-base-sentiment"
```

Filters apply at analysis time, so config changes never force a re-parse or a sentiment re-run.

### Share the dashboard safely

The dashboard is a single HTML file, so it is tempting to send to friends. Before sharing, set:

```yaml
privacy:
  anonymize_names: true      # contacts -> "Person 01", you -> "Me", groups -> "Group 01"
  include_sensitive: false   # drops logins, identity history, message explorer, name lists
  include_examples: false    # no real message text embedded
```

then re-run `03_analysis.py` + `04_build_dashboard.py`. Pseudonyms are stable within a build, so charts stay readable, but no real name, message or login appears in the file.

## Architecture (for contributors)

The pipeline is five small scripts orchestrated by `run.py`:

```
scripts/00_extract.py         # ZIPs -> data/raw/ (JSON only, stdlib zipfile, cross-platform)
scripts/01_parse.py           # -> tidy parquet tables in data/clean/   (scripts/parsers/)
scripts/02_sentiment.py       # XLM-RoBERTa sentiment, unique-text dedup (skippable)
scripts/03_analysis.py        # EDA + ML features -> output/data.json   (scripts/analysis/)
scripts/04_build_dashboard.py # inline Plotly + data into one HTML
scripts/05_validate.py        # headless-Chromium render check + screenshots (optional QA)
```

Two registries make it modular:

- **Parsers** (`scripts/parsers/`): one module per export domain (messages, connections, ads, security, ...). Each declares `META = {"key", "outputs"}` and a `parse(env)` function, and is listed in `parsers/__init__.py:PARSERS`. Parsers are config-independent; a parser whose source files are missing produces nothing, and one crashing never blocks the rest.
- **Sections** (`scripts/analysis/sections/`): one module per analysis. Each declares an optional `META = {"key", "title", "requires", "privacy"}` and a `compute(ctx, D)` function, and is listed in `analysis/__init__.py:SECTIONS`. The shared `AnalysisContext` (`ctx`) loads the cleaned data once, applies all config filters, and exposes helpers (`ctx.load_clean`, `ctx.filter_people`, `ctx.disp`, `ctx.disp_title`) so every section automatically respects exclusions and anonymization.

Adding an analysis is two steps: drop `sections/my_thing.py` with `def compute(ctx, D): D["my_thing"] = ...`, then register it in `SECTIONS`. Its output flows into `data.json` for the dashboard. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contracts, including how to add the dashboard card, and [DESIGN.md](DESIGN.md) for the visual rules.

## Methodology & caveats

- **Mojibake repair.** Instagram exports text as Latin-1-encoded UTF-8; every string is repaired with **ftfy** (plus targeted recovery for short ambiguous strings ftfy abstains on) so diacritics render correctly.
- **Timezone.** UTC millisecond timestamps are converted to your configured IANA timezone before any hour/weekday analysis.
- **System messages.** Auto-generated lines ("X sent an attachment", "Reacted to your message", group-membership notices) are detected and excluded from language and sentiment analysis; reactions are counted from the reactions table to avoid double-counting.
- **Sentiment.** `cardiffnlp/twitter-xlm-roberta-base-sentiment` (multilingual, social-media fine-tuned); `compound = P(pos) - P(neg)`. The model leans neutral/negative on terse, ironic chat in smaller languages, so read scores comparatively (between chats, across time) rather than as absolute truth.
- **Rolling-window logs.** Several export files only cover a recent window (typically ~30 days): feed impressions, the reels watch log, the in-app link history. Charts built from them label the window explicitly; do not extrapolate them to all time.
- **Survivorship bias.** The followers list only contains people who follow you *now*, with their original follow dates. Anyone who unfollowed has vanished from history, so "follower growth" curves systematically understate early churn.
- **ML.** Topics = TF-IDF + NMF; chat clustering = K-means on standardized behavioural features plus a PCA projection; reply time and initiation from intra-thread turn-taking gaps; slang = accent-insensitive lexicon match.

## Libraries do the heavy lifting

| Concern | Library |
|---|---|
| Mojibake / text repair | **ftfy** |
| Lemmatization (multilingual) | **simplemma** |
| Tokenization | **simplemma.simple_tokenizer** |
| Stopwords | **stopwords-iso** |
| Emoji parsing | **emoji** |
| Transliteration / de-accent | **unidecode** |
| Sentiment | **transformers** (XLM-RoBERTa) on **PyTorch** (MPS/CUDA/CPU) |
| Topics / clustering | **scikit-learn** (TF-IDF, NMF, KMeans, PCA) |
| Word clouds | **wordcloud** · Charts: **Plotly** |

## Privacy & data safety

- **Nothing leaves your machine.** The pipeline reads local ZIPs and writes local files. The only network access is the one-time download of the sentiment model from Hugging Face; use `--skip-sentiment` to avoid even that.
- **The repository is designed so personal data cannot be committed.** `.gitignore` covers your export ZIPs, all extracted and derived data (`data/`, `output/`, `figures/`), model caches, and your personal `config.yaml`. Only code and the example config are tracked.
- **Anonymization is built in.** `privacy.anonymize_names` replaces every contact with a stable pseudonym across the whole dashboard, and `privacy.include_sensitive: false` drops the high-sensitivity sections entirely, so a shared dashboard does not have to expose anyone.
- **You stay in control of scope.** `exclude_people` removes a person from every analysis surface, and per-section toggles let you keep whole domains out of the build.

## License

MIT. See [LICENSE](LICENSE).
