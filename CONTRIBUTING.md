# Contributing to InstagramAnalysis

Thanks for helping. This document covers the development setup, the extension points (parsers, analysis sections, dashboard cards), the validation workflow, and the privacy checklist every PR must pass.

## Dev setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium        # only needed for scripts/05_validate.py

.venv/bin/python run.py --skip-sentiment     # fast full pipeline on your own export
```

You need your own Instagram export (JSON format) to develop against; there are no bundled fixtures because the data is inherently personal. Keep your ZIPs in the repo root, they are gitignored.

## Pipeline stages

```
run.py
 └─ scripts/00_extract.py        ZIPs -> data/raw/           (stdlib zipfile, JSON only)
 └─ scripts/01_parse.py          data/raw -> data/clean/*.parquet   (scripts/parsers/)
 └─ scripts/02_sentiment.py      messages -> sentiment.parquet      (skippable)
 └─ scripts/03_analysis.py       data/clean -> output/data.json     (scripts/analysis/)
 └─ scripts/04_build_dashboard.py  template + data.json -> output/Instagram_Dashboard.html
 └─ scripts/05_validate.py       headless Chromium QA -> figures/qa/   (optional)
```

Key design rule: **parsers are config-independent** (no filtering), and **all user config (exclude_people, date window, privacy) is applied at analysis time** in `AnalysisContext`. That way a config change never forces a re-parse or a sentiment re-run.

## How to add a parser

One parser module owns one export domain and turns its raw JSON into tidy tables under `data/clean/`.

1. Create `scripts/parsers/<domain>.py`:

```python
META = {"key": "<domain>", "outputs": ["<file>.parquet"]}

def parse(env) -> dict:
    # env = {"RAW": "data/raw", "OUT": "data/clean", "TZ": "Europe/Bratislava"}
    # read JSON under env["RAW"], write parquet under env["OUT"]
    # return summary stats (dict) for the parse log
    ...
```

2. Register it in `scripts/parsers/__init__.py:PARSERS`.

Rules:

- Use the helpers in `parsers/common.py` (ftfy `fix()`, `load_json`, ...) so mojibake repair is consistent.
- Missing source files are normal (exports differ by account and download options): produce nothing, do not raise.
- No config filtering here. No `exclude_people`, no date windows. That happens later.
- Timestamps: convert UTC ms to the `env["TZ"]` timezone, name the column `dt` (the analysis layer's date-window filter keys on it).

## How to add an analysis section

One section module computes one dashboard section's data.

1. Create `scripts/analysis/sections/<name>.py`:

```python
META = {
    "key": "<name>",                 # config toggle key; defaults to module name
    "title": "Human label",          # used in logs
    "requires": ["<file>.parquet"],  # data/clean inputs; section skipped if missing
    "privacy": "low",                # low | medium | high
}

def compute(ctx, D):
    D["<name>"] = {...}              # plain-JSON-serializable dict -> output/data.json
```

2. Register it in `scripts/analysis/__init__.py:SECTIONS` (order only matters if you read another section's shared output, e.g. `ctx.chats` from `people`).

### The ctx contract

`AnalysisContext` (`scripts/analysis/context.py`) is the only way sections see data:

- `ctx.df / ctx.inbox / ctx.tx` message frames, already config-filtered (`tx` = human text only)
- `ctx.rx / ctx.th` reactions / thread metadata, config-filtered
- `ctx.load_clean("x.parquet")` any other cleaned table; returns `None` if the export lacks it; applies the date window when a `dt` column exists
- `ctx.filter_people(df, cols)` drops rows naming an excluded person
- `ctx.disp(name)` / `ctx.disp_title(title, is_group)` display names that respect `privacy.anonymize_names`

**Hard rule: any output that carries a contact name MUST pass through both `ctx.filter_people(...)` (so `exclude_people` works) and `ctx.disp(...)` / `ctx.disp_title(...)` (so anonymization works).** A section that emits a raw name breaks the privacy guarantees of the whole project.

Set `META["privacy"]` honestly: `high` for anything with names lists, locations, message text or login data (these are dropped when `privacy.include_sensitive` is false), `medium` for personal-but-aggregate, `low` for pure aggregates.

A section must never crash the pipeline; the runner catches exceptions, but prefer guarding for empty/missing data yourself and emitting nothing.

## How to add a dashboard card

The dashboard is `scripts/dashboard_template.html` (CSS + JS inline; Plotly and `data.json` injected by `04_build_dashboard.py`). Read **DESIGN.md** first; it defines the color tokens, typography and chart conventions, and they are enforced in review.

1. **Markup**: add a card inside the section's `.grid`:

```html
<div class="card col-6">
  <h3>Chart title</h3>
  <div class="sub">honest caption · label the data window if it is a rolling log</div>
  <div class="chart" data-chart="mychart"></div>
</div>
```

Heights come from the class only (`.chart` 330px, `.tall` 420px, `.sm` 260px). Never set Plotly `layout.height`.

2. **Renderer**: add `R.mychart` in the script block. Charts lazy-render when scrolled into view via the `data-chart` -> `R.<id>` lookup:

```js
R.mychart = el => {
  const t = DATA.<section>.<field>;
  if (!t || !t.x.length) return empty(el, "no data in this export");
  Plotly.newPlot(el, [{
    x: t.x, y: t.y, type: "bar", marker: {color: C.accent},
    hovertemplate: "%{x}<br><b>%{y:,}</b><extra></extra>",
  }], baseLayout({ yaxis: {tickformat: "~s"} }), {displayModeBar: false});
};
```

Non-negotiables (see DESIGN.md for the rest):

- `baseLayout()` for every 2-D chart, `layout3d()` for 3-D.
- Every trace gets an explicit `hovertemplate` with `:,` thousands formatting and `<extra></extra>`.
- Semantic colors: oxblood `C.accent` = You/Sent, slate `C.accent2` = Them/Received, everywhere.
- Month axes are date axes (`tickformat:'%b %Y'`), not category strings.
- Empty data goes through the shared `empty(el, msg)` placeholder, never a silent void.
- No em dashes in copy; use `·` or commas.

## Validation workflow

After any analysis or template change:

```bash
.venv/bin/python scripts/03_analysis.py          # rebuild output/data.json
.venv/bin/python scripts/04_build_dashboard.py   # rebuild the HTML
.venv/bin/python scripts/05_validate.py          # headless-Chromium QA
```

`05_validate.py` opens the dashboard in headless Chromium, scrolls the full page to trigger lazy rendering, fails on console errors, reports `data-chart` targets that rendered empty, and drops per-section screenshots into `figures/qa/` for visual review. A PR that adds charts should pass with zero console errors and zero unexpectedly-empty targets.

## Code style

- Match the existing code. Small modules, module docstrings that state the contract, no new frameworks.
- **Explicit `int()` / `float()` casts on every number that ends up in `D`**: numpy scalars (`int64`, `float64`) are not JSON-serializable and will break `03_analysis.py` at dump time.
- Round floats sensibly (2-3 decimals) to keep `data.json`, and therefore the single-file dashboard, small. Payload size is a design constraint.
- Parsers and sections must tolerate missing files and empty frames; other people's exports vary wildly.
- No exact version pins in `requirements.txt`; light floors only when needed.

## Privacy review checklist for PRs

Every PR is reviewed against this list. Check it yourself first:

- [ ] No real names, usernames, message text, locations or other personal data in code, comments, fixtures, tests, docs or commit messages.
- [ ] Screenshots in the PR description were generated with `privacy.anonymize_names: true` (or contain no name-bearing surfaces).
- [ ] Any new output field that carries a contact name goes through `ctx.filter_people` and `ctx.disp` / `ctx.disp_title`.
- [ ] New sections declare an honest `META["privacy"]` level; anything with name lists, message text, locations or login data is `high`.
- [ ] No new files written outside `data/`, `output/`, `figures/` (everything personal must stay inside gitignored paths).
- [ ] No network calls added anywhere in the pipeline (the sentiment model download is the only sanctioned one).
- [ ] `config.example.yaml` additions contain placeholder values only.
