# DESIGN.md — InstagramAnalysis dashboard

Single-file dashboard rendered from `scripts/dashboard_template.html`
(CSS + JS inline; Plotly + data.json injected at build).

## Theme

Instagram-native: white canvas, hairline borders, system sans, the brand
gradient as the signature accent. The dashboard should feel like a part of
Instagram itself reporting on you. Always light; never dark mode.

## Color tokens (CSS `:root`; the JS `C` object derives from these at boot)

- `--bg #fafafa` canvas · `--surface #ffffff` card · `--surface2 #efefef` inset
- `--border #dbdbdb` hairline · `--border2 #c7c7c7` hover
- `--text #262626` ink · `--muted #737373` · `--dim #a8a8a8`
- `--accent #e1306c` Instagram pink — semantic: **You / Sent**
- `--accent2 #4f5bd5` Instagram indigo — semantic: **Them / Received**
- `--cat3 #fa7e1e` orange · `--cat4 #962fbf` purple · `--cat5 #fcaf45` amber
  · `--cat6 #0095f6` action blue (third/fourth/fifth categorical series)
- `--pos #27a35f` · `--neg #ed4956` (IG alert red) · `--neu #8e8e8e` sentiment triad
- `--ig-grad` the brand gradient `#feda75 → #fa7e1e → #d62976 → #962fbf → #4f5bd5`
- heatmap scale INK: `#fafafa → #fa7e1e → #962fbf` (the "sunset" ramp)
- diverging scale: `--neg → --border → --pos` (center = 0, always `cmid:0`)

Color strategy: full palette, used semantically. Pink = the user, indigo =
everyone else, the gradient family fills categorical series. A chart never
recolors these roles. Aggregates of both sides use `--neu` gray.

The gradient (`--ig-grad`) appears ONLY as a signature: the scroll-progress
bar, the brand dot, and gradient-clipped text on the single emphasised
`<em>` word per headline. Nowhere else — especially not on data.

## Typography

System sans everywhere (`--font`: -apple-system / Segoe UI / Roboto …),
exactly like Instagram. Headlines bold 700–800, no italics. Numerals use
`font-variant-numeric: tabular-nums` (`.mono` class — the name is legacy,
it is the same family). Micro-labels: 10–11px uppercase letterspaced.

## Layout

- `--maxw 1180px`, 12-col grid `gap:20px`, cards span `col-3…col-12`;
  everything collapses to span-12 under 980px.
- Cards: white, 1px `--border`, 10px radius, flat (no shadows).
- Section anatomy: `.kicker` (uppercase, numbered) → `h2` (one gradient
  `<em>` word) → `.dek` standfirst (≤720px) → optional `.lead-row` big
  stats → `.grid` of cards.
- Chart heights via class only: `.chart` 330px, `.tall` 420px, `.sm` 260px.
  Never set Plotly `layout.height`.
- Message Explorer renders Instagram-Direct bubbles: own messages on the
  indigo→purple gradient, theirs on `--surface2`, 18px pill radius.

## Chart conventions

- `baseLayout()` for every 2-D chart; `layout3d()` for 3-D. Transparent
  backgrounds, system sans 12, dark hoverlabel.
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

Side-stripe accent borders, dark theme, drop shadows, gradient applied to
data marks or body text (signature spots above are the only exception),
decorative 3-D where a 2-D chart reads better, em dashes in copy (use ·
or commas).
