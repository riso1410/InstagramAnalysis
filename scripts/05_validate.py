#!/usr/bin/env python3
"""
05_validate.py — render the dashboard in headless Chromium, capture console
errors and screenshots of each section for visual QA.
"""
import os, sys, time
from playwright.sync_api import sync_playwright

HTML = os.path.abspath("output/Instagram_Dashboard.html")
SHOT_DIR = "figures/qa"
os.makedirs(SHOT_DIR, exist_ok=True)
SECTIONS = ["overview", "timeline", "rhythm", "people", "dynamics",
            "sentiment", "language", "brainrot", "emoji", "clusters", "activity"]

def main():
    errors, warnings = [], []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        pg.on("console", lambda m: (errors if m.type == "error" else warnings).append(m.text) if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: errors.append("PAGEERROR: " + str(e)))
        pg.goto("file://" + HTML, wait_until="networkidle")
        pg.wait_for_timeout(1200)
        # scroll through to trigger lazy chart rendering
        h = pg.evaluate("document.body.scrollHeight")
        step = 700
        y = 0
        while y < h:
            pg.evaluate(f"window.scrollTo(0,{y})")
            pg.wait_for_timeout(220)
            y += step
            h = pg.evaluate("document.body.scrollHeight")
        pg.evaluate("window.scrollTo(0,0)")
        pg.wait_for_timeout(800)

        # count rendered plotly charts
        n_charts = pg.evaluate("document.querySelectorAll('.js-plotly-plot').length")
        n_targets = pg.evaluate("document.querySelectorAll('[data-chart]').length")
        empty = pg.evaluate("[...document.querySelectorAll('[data-chart]')].filter(e=>!e.querySelector('.js-plotly-plot')).map(e=>e.dataset.chart)")
        print(f"charts rendered: {n_charts}/{n_targets}")
        if empty:
            print("  EMPTY chart targets:", empty)

        # hero screenshot
        pg.screenshot(path=f"{SHOT_DIR}/00_hero.png")
        # per-section screenshots
        for s in SECTIONS:
            try:
                el = pg.query_selector(f"#{s}")
                if el:
                    el.scroll_into_view_if_needed()
                    pg.wait_for_timeout(500)
                    el.screenshot(path=f"{SHOT_DIR}/{s}.png")
            except Exception as e:
                print(f"  shot {s} failed: {e}")
        # full page
        pg.screenshot(path=f"{SHOT_DIR}/_full.png", full_page=True)
        b.close()

    print(f"\nconsole errors: {len(errors)}")
    for e in errors[:30]:
        print("  ✗", e[:200])
    print(f"console warnings: {len(warnings)}")
    for w in warnings[:8]:
        print("  ·", w[:160])
    print(f"\nscreenshots -> {SHOT_DIR}/")
    sys.exit(1 if errors else 0)

if __name__ == "__main__":
    main()
