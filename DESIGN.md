# DESIGN.md — InstagramAnalysis dashboard

Single-file dashboard rendered from `scripts/dashboard_template.html`
(CSS + JS inline; Plotly + data.json injected at build).

## Theme

Light, warm paper. Scene: someone reading their own data-portrait like a
weekend longread, laptop on a couch, daylight. Never dark mode.

## Color tokens (CSS `:root`, mirrored in JS `C`)

- `--bg #f3f0e9` parchment page
- `--surface #faf8f3` card · `--surface2 #ece8df` inset
- `--border #d8d2c5` · `--border2 #c4bdae` hover
- `--text #1c1a17` ink · `--muted #5c574e` · `--dim #8a847a`
- `--accent #8a2a2a` oxblood — semantic: **You / Sent**
- `--accent2 #2f4858` slate — semantic: **Them / Received**
- `--pos #3f6b4a` · `--neg #9a3324` · `--neu #6f6a60` sentiment triad
- categorical seq: `#8a2a2a #2f4858 #9c8348 #5e7a6a #6f6a60 #b07a4a`
- heatmap scale INK: `#f3f0e9 → #b8a08c → #1c1a17`
- diverging scale: `#9a3324 → #d8d2c5 → #3f6b4a` (center = 0, always `cmid:0`)

Color strategy: full palette, used semantically. Oxblood = the user,
slate = everyone else, gold/sage = third/fourth series. A chart never
recolors these roles.

## Typography

- Newsreader (serif, 360–500): h1–h4, hero lede, callouts. One `<em>`
  italic word per headline, set in oxblood.
- Archivo (sans): body, UI, chart labels (12px).
- IBM Plex Mono: every numeral (KPI values, table cells, axis ticks,
  kickers), `tabular-nums`.

## Layout

- `--maxw 1180px`, 12-col grid `gap:20px`, cards span `col-3…col-12`;
  everything collapses to span-12 under 980px.
- Section anatomy: `.kicker` (mono uppercase, numbered) → `h2` → `.dek`
  standfirst (≤720px) → optional `.lead-row` big stats → `.grid` of cards.
- Chart heights via class only: `.chart` 330px, `.tall` 420px, `.sm` 260px.
  Never set Plotly `layout.height`.

## Chart conventions

- `baseLayout()` for every 2-D chart; `layout3d()` for 3-D. Transparent
  backgrounds, Archivo 12, dark mono hoverlabel.
- Every trace gets an explicit `hovertemplate` with `:,` thousands
  formatting and `<extra></extra>`; truncated labels carry full text in
  `text` for hover.
- Stack/legend order is fixed: "You" first, "Them" second, everywhere.
- Y axes use `tickformat:'~s'` past 4 digits. Month axes are date axes
  with `tickformat:'%b %Y'`, not category strings.
- Donuts only for 3+ meaningful shares; binary splits are split bars.
- Every chart honestly labels its data window (e.g. "rolling 30-day log")
  in the `.sub` caption.
- Empty data: shared `empty(el,msg)` placeholder, never a silent void.

## Banned here

Side-stripe accent borders, gradient text, glassmorphism, dark theme,
neon palettes, decorative 3-D where a 2-D chart reads better, em dashes
in copy (use · or commas).
