"""Modular analysis pipeline.

`run()` builds the shared AnalysisContext, then executes each registered section
module in order, accumulating results into a single dict (-> output/data.json).

Adding an analysis = add a `sections/<name>.py` with `compute(ctx, D)` plus an
optional `META` dict, and list it in SECTIONS below. Order matters only where a
section reads another's shared output (people -> ctx.chats; dynamics ->
ctx.per_chat_resp).

Section META contract (every key optional):
    META = {
        "key": "connections",          # config key; defaults to the module name
        "title": "Social graph",       # human label used in logs
        "requires": ["connections.parquet"],  # data/clean files needed, else skipped
        "privacy": "low",              # low|medium|high; high is skipped when
    }                                  #   privacy.include_sensitive is false

Users can switch any section off in config.yaml:   sections: {connections: false}
A section whose input files are missing (different export options, partial
downloads) is skipped with a notice instead of crashing — other people's exports
won't always contain every file this repo can analyze.
"""
import os, traceback
from .context import AnalysisContext
from .sections import (overview, temporal, people, examples, length, dynamics,
                       emoji, language, slang, clusters, sentiment, activity,
                       interests, connections, content, stories, footprint,
                       security)

SECTIONS = [
    overview, temporal,
    people,          # -> ctx.chats, ctx.title_map
    examples, length,
    dynamics,        # -> ctx.per_chat_resp
    emoji, language, slang,
    clusters,        # uses ctx.chats + ctx.per_chat_resp
    sentiment,       # uses ctx.chats
    activity, interests,
    connections,     # social graph (followers/following/blocks/suggestions)
    content,         # own posts/stories/stickers + your comments
    stories,         # story interactions, inner circle, reels log
    footprint,       # advertisers, targeting labels, ad density
    security,        # logins, devices, identity, link trail (privacy: high)
]


def _meta(mod):
    m = dict(getattr(mod, "META", {}))
    m.setdefault("key", mod.__name__.rsplit(".", 1)[-1])
    m.setdefault("title", m["key"])
    m.setdefault("requires", [])
    m.setdefault("privacy", "low")
    return m


def _skip_reason(meta, ctx):
    if ctx.CFG["sections"].get(meta["key"]) is False:
        return "disabled in config (sections)"
    if meta["privacy"] == "high" and not ctx.CFG["privacy"]["include_sensitive"]:
        return "privacy.include_sensitive is false"
    missing = [f for f in meta["requires"] if not os.path.exists(os.path.join(ctx.CLEAN, f))]
    if missing:
        return f"missing input: {', '.join(missing)}"
    return None


def run(ctx=None):
    ctx = ctx or AnalysisContext()
    D = {}
    for mod in SECTIONS:
        meta = _meta(mod)
        reason = _skip_reason(meta, ctx)
        if reason:
            print(f"[skip] {meta['key']}: {reason}")
            continue
        try:
            mod.compute(ctx, D)
        except Exception:
            # a single section must never kill the whole pipeline (foreign exports
            # vary wildly); surface the error and carry on
            print(f"[error] section {meta['key']} failed:")
            traceback.print_exc()
    return ctx, D
