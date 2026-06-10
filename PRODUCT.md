# PRODUCT.md — InstagramAnalysis

## What it is

An open-source, local-only pipeline that turns a personal Instagram data export
(ZIP of JSON) into a single self-contained interactive HTML dashboard: a
data-portrait of one person's digital life. Messages, social graph, story
engagement, ad surveillance, security trail.

## Users

People curious about their own data: data-literate Instagram users, privacy
researchers, quantified-self hobbyists, developers extending the pipeline.
They read it like a long-form magazine feature about themselves, scrolling
top to bottom on a laptop, occasionally sharing a screenshot or the whole
file with friends.

## Register

product

## Tone

Instagram-native data essay. The dashboard borrows Instagram's own visual
language (white canvas, hairlines, system sans, the brand gradient as a
signature accent) so it reads like Instagram reporting on itself, with dry
wit in the copy ("The physics of a reply"). Charts are the prose; the UI
never shouts over them.

## Anti-references

- SaaS dashboard chrome: glassmorphism, dark "command center" themes,
  neon data-viz palettes, gradients smeared over data marks.
- Social-media-report kitsch: emoji confetti, "Wrapped" hype slides,
  the gradient smeared over everything instead of used as a signature.
- Generic admin-template look: identical card grids, icon+heading+text rows.

## Strategic principles

1. Privacy first: the dashboard may be shared, so every name can be
   anonymized and sensitive sections can be dropped via config.
2. Honest charts: label windows and biases (rolling 30-day logs,
   survivorship-biased follower lists); never imply more data than exists.
3. One file, offline: everything inlines into a single HTML; payload size is
   a design constraint.
4. The data is the personality: color and type stay constant; the numbers
   provide the drama.
