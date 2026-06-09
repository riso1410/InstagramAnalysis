"""Modular analysis pipeline.

`run()` builds the shared AnalysisContext, then executes each registered section
module in order, accumulating results into a single dict (-> output/data.json).

Adding an analysis = add a `sections/<name>.py` with `compute(ctx, D)` and list it
in SECTIONS below. Order matters only where a section reads another's shared output
(people -> ctx.chats; dynamics -> ctx.per_chat_resp).
"""
from .context import AnalysisContext
from .sections import (overview, temporal, people, examples, length, dynamics,
                       emoji, language, slang, clusters, sentiment, activity, interests)

SECTIONS = [
    ("overview", overview.compute),
    ("temporal", temporal.compute),
    ("people", people.compute),       # -> ctx.chats, ctx.title_map
    ("examples", examples.compute),
    ("length", length.compute),
    ("dynamics", dynamics.compute),   # -> ctx.per_chat_resp
    ("emoji", emoji.compute),
    ("language", language.compute),
    ("slang", slang.compute),
    ("clusters", clusters.compute),   # uses ctx.chats + ctx.per_chat_resp
    ("sentiment", sentiment.compute), # uses ctx.chats
    ("activity", activity.compute),
    ("interests", interests.compute),
]


def run(ctx=None):
    ctx = ctx or AnalysisContext()
    D = {}
    for name, fn in SECTIONS:
        fn(ctx, D)
    return ctx, D
