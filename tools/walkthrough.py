"""Walk the workspace like a first-time user: example -> Run -> every view.

Needs the workspace running (./run_workspace.sh). Fails on a console error,
a page that scrolls, or a view that does not open. CHROME env var overrides
the browser path.
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("URL", "http://localhost:8000")
CHROME = os.environ.get("CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
VIEWS = ["Network", "Solve", "Safety check", "Short circuit", "Show working", "Tools"]


def main() -> int:
    bad: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        pg = b.new_page(viewport={"width": 1366, "height": 768})
        pg.on("console", lambda m: bad.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: bad.append(str(e)))
        pg.goto(URL)
        pg.wait_for_selector(".start-card")
        pg.locator(".start-card").first.click()
        pg.get_by_text("Run", exact=True).first.click()
        pg.wait_for_selector("text=SOLVED")
        for v in VIEWS:
            pg.locator(".flow-list > *", has_text=v).first.click()
            pg.wait_for_timeout(700)
            if pg.evaluate("document.documentElement.scrollHeight > innerHeight"):
                bad.append(f"{v}: page scrolls")
            subs = pg.locator(".ws-centre .tabs [role=tab]:visible")
            for i in range(min(subs.count(), 6)):
                subs.nth(i).click()
                pg.wait_for_timeout(500)
            print("ok", v, subs.count(), "sub-tabs")
        b.close()
    print("problems:", bad or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
