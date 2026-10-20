"""Screenshot every workspace view (and the Streamlit pages) at 1366x768
and report any page that scrolls. Needs the servers running:
    ./run_workspace.sh            # workspace on :8000
    streamlit run app.py          # optional fallback on :8501
Set CHROME=/path/to/chrome if Playwright cannot find a browser.
Usage: python tools/shots.py [workspace_url] [streamlit_url|-] [out_dir]
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

WS = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
ST = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8501"
OUT = Path(sys.argv[3] if len(sys.argv) > 3 else "screenshots/1366")
DOCS = ["canvas", "case-tables", "load-flow", "solver-check", "report", "contingency",
        "pv-analysis", "fault-levels", "faults", "ybus", "iterations", "answer",
        "symmetrical", "line", "dispatch"]
TABLE_TABS = ["Buses", "Branches", "Generators", "Loads", "Shunts"]
CASE118 = Path(__file__).resolve().parent.parent / "tests" / "data" / "case118.m"
ST_PAGES = ["", "problem", "network", "solver-check", "ybus", "iterations",
            "answer", "contingency", "pv-analysis", "fault-levels", "faults",
            "dispatch", "symmetrical", "line", "study-report"]


def no_page_scroll(pg):
    return pg.evaluate("document.scrollingElement.scrollHeight <= innerHeight + 1")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bad = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=os.environ.get("CHROME") or None)
        pg = b.new_page(viewport={"width": 1366, "height": 768})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(WS)
        pg.evaluate("localStorage.clear()")
        pg.reload()
        pg.wait_for_selector(".start-card")
        pg.screenshot(path=OUT / "ws-start.png")
        pg.get_by_role("button", name="New case").first.click()
        pg.wait_for_timeout(300)
        pg.screenshot(path=OUT / "ws-new-case.png")
        pg.keyboard.press("Escape")
        pg.get_by_role("button", name="IEEE 14-bus").click()
        pg.wait_for_timeout(500)
        pg.click("[data-testid=run]")
        pg.wait_for_selector("text=SOLVED", timeout=30000)
        pg.locator(".tb-menu button").first.click()
        pg.wait_for_timeout(300)
        pg.screenshot(path=OUT / "ws-file-menu.png")
        pg.keyboard.press("Escape")
        for d in DOCS:
            pg.goto(f"{WS}/#/doc/{d}")
            pg.wait_for_timeout(900)
            pg.screenshot(path=OUT / f"ws-{d}.png")
            if not no_page_scroll(pg):
                bad.append(d)
            if d == "case-tables":
                for t in TABLE_TABS:
                    pg.locator(".subtabs button", has_text=t).first.click()
                    pg.wait_for_timeout(300)
                    pg.screenshot(path=OUT / f"ws-tables-{t.lower()}.png")
        # a large imported case: auto layout of IEEE 118
        pg.goto(f"{WS}/#/doc/canvas")
        pg.locator(".tb-menu button").first.click()
        with pg.expect_file_chooser() as fc:
            pg.get_by_role("menuitem", name="Open or import a file...").click()
        fc.value.set_files(str(CASE118))
        pg.wait_for_timeout(2500)
        pg.screenshot(path=OUT / "ws-case118-diagram.png")
        if ST != "-":
            pg.goto(ST)
            pg.wait_for_selector("text=Run study", timeout=60000)
            pg.get_by_role("button", name="Run study").first.click()
            pg.wait_for_timeout(8000)
            for s in ST_PAGES:
                pg.goto(f"{ST}/{s}")
                pg.wait_for_timeout(4000)
                pg.screenshot(path=OUT / f"st-{s or 'dashboard'}.png")
        b.close()
    print("pages that scroll:", bad or "none")
    print("script errors:", errors or "none")
    return 1 if bad or errors else 0


if __name__ == "__main__":
    sys.exit(main())
