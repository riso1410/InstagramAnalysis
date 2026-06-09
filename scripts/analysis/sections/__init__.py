"""Analysis section modules.

Each module exposes `compute(ctx, D)`: it reads frames from the shared
AnalysisContext `ctx` and writes its results into the output dict `D`.
To add a new analysis, drop a module here with a `compute(ctx, D)` function
and register it in `analysis/__init__.py:SECTIONS`.
"""
