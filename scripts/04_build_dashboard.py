#!/usr/bin/env python3
"""
04_build_dashboard.py — assemble the self-contained interactive dashboard.

Inlines plotly.min.js and output/data.json into scripts/dashboard_template.html,
producing output/Instagram_Dashboard.html — a single file that opens offline.
"""
import json, os, glob

TEMPLATE = "scripts/dashboard_template.html"
DATA = "output/data.json"
OUT = "output/Instagram_Dashboard.html"

def find_plotly():
    hits = glob.glob(".venv/**/plotly/package_data/plotly.min.js", recursive=True)
    if not hits:
        raise SystemExit("plotly.min.js not found in venv")
    return hits[0]

def main():
    tpl = open(TEMPLATE, encoding="utf-8").read()
    plotly = open(find_plotly(), encoding="utf-8").read()
    data = open(DATA, encoding="utf-8").read()
    # guard against </script> breaking the inline blocks
    data = data.replace("</", "<\\/")

    html = tpl.replace("/*__PLOTLY__*/", plotly).replace("/*__DATA__*/", data)
    # sanity: no unresolved markers
    assert "/*__PLOTLY__*/" not in html and "/*__DATA__*/" not in html, "marker not replaced"

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"built {OUT}  ({os.path.getsize(OUT)/1024/1024:.2f} MB)")
    print(f"  plotly: {len(plotly)/1024:.0f} KB · data: {len(data)/1024:.0f} KB")

if __name__ == "__main__":
    main()
