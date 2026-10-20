"""Walk the workspace like a first-time user.

1. Tour: example -> Run -> every view and sub-tab.
2. Draw: "New case" (draw on the diagram) -> add 2 buses with the Bus tool -> draw a line
   between them (the warning chip says the network is disconnected) -> a line
   from the Slack bus -> a load -> Run (F5) -> SOLVED. Then Network > Data
   tables: change Pd, Run again and check the result changed. Zoom the
   diagram with the mouse wheel and check the labels keep their pixel size.

Needs the workspace running (./run_workspace.sh). Fails on a console error,
a page that scrolls, or a step that does not happen. CHROME env var
overrides the browser path, URL the address.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("URL", "http://localhost:8000")
CHROME = os.environ.get("CHROME", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
VIEWS = ["Network", "Solve", "Safety check", "Short circuit", "Show working", "Tools"]
SOLVED = ".ws-title .read b.ok"  # the SOLUTION readout when it says SOLVED
STATE = "JSON.parse(localStorage.getItem('gridlens.project'))"


def watch(pg, bad):
    pg.on("console", lambda m: bad.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: bad.append(str(e)))


def scrolls(pg):
    return pg.evaluate("document.documentElement.scrollHeight > innerHeight")


def tour(b, bad):
    pg = b.new_page(viewport={"width": 1366, "height": 768})
    watch(pg, bad)
    pg.goto(URL)
    pg.wait_for_selector(".start-card")
    pg.get_by_role("button", name="5-bus (demo)").click()
    pg.get_by_text("Run", exact=True).first.click()
    pg.wait_for_selector(SOLVED)
    for v in VIEWS:
        pg.locator(".flow-list > *", has_text=v).first.click()
        pg.wait_for_timeout(700)
        if scrolls(pg):
            bad.append(f"{v}: page scrolls")
        subs = pg.locator(".ws-centre .tabs [role=tab]:visible")
        for i in range(min(subs.count(), 6)):
            subs.nth(i).click()
            pg.wait_for_timeout(500)
        print("ok", v, subs.count(), "sub-tabs")
    pg.close()


def centre(pg, sel):
    # one evaluate: the canvas redraws its elements, so a locator could go stale
    return pg.evaluate("""s => { const r = document.querySelector(s).getBoundingClientRect();
                                 return [r.x + r.width / 2, r.y + r.height / 2]; }""", sel)


def state(pg, path):
    pg.wait_for_timeout(300)  # the project is saved 150 ms after a change
    return pg.evaluate(f"{STATE}.{path}")


def need(cond, what, bad):
    print("ok" if cond else "FAIL", what)
    if not cond:
        bad.append(what)


def draw(b, bad):
    ctx = b.new_context(viewport={"width": 1366, "height": 768})  # fresh localStorage
    pg = ctx.new_page()
    watch(pg, bad)
    pg.goto(URL)
    pg.get_by_role("button", name="New case").first.click()
    pg.get_by_role("button", name="Create").click()
    pg.wait_for_selector(".bar-line", state="attached")
    need(pg.locator("[role=toolbar] .ctool.on").inner_text().startswith("Bus"), "Draw a new network: Bus tool active", bad)
    box = pg.locator(".canvas-wrap").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    pg.mouse.click(cx - 220, cy + 180)  # bus 2
    pg.mouse.click(cx + 220, cy + 180)  # bus 3
    try:  # the canvas redraws on the next animation frame
        pg.wait_for_function("document.querySelectorAll('.bar-line').length === 3", timeout=3000)
    except Exception:
        pass
    need(pg.locator(".bar-line").count() == 3, "Bus tool: 2 buses added", bad)

    def line(a, z):
        x0, y0 = centre(pg, f'[data-hit="bus:{a}"]')
        x1, y1 = centre(pg, f'[data-hit="bus:{z}"]')
        pg.mouse.move(x0, y0)
        pg.mouse.down()
        pg.mouse.move(x1, y1, steps=8)
        pg.mouse.up()

    pg.keyboard.press("l")
    line(1, 2)
    pg.wait_for_function("!document.querySelector('.canvas-warn').hidden")
    need("disconnected" in pg.locator(".canvas-warn").inner_text(),
         "line between them; chip: " + pg.locator(".canvas-warn").inner_text(), bad)
    line(0, 1)
    pg.wait_for_function("document.querySelector('.canvas-warn').hidden")
    need(len(state(pg, "case.lines")) == 2, "Line tool: 2 lines, network connected", bad)
    pg.keyboard.press("d")
    pg.mouse.click(*centre(pg, '[data-hit="bus:2"]'))
    need(state(pg, "case.bus[2].Pd") == 0.5, "Load tool: Pd 0.5 on bus 3", bad)
    need("Press Run (F5) to solve" in pg.locator(".nexthint").inner_text(), "hint: Press Run (F5) to solve", bad)
    pg.keyboard.press("F5")
    pg.wait_for_selector(SOLVED)
    loss = state(pg, "results.loss")
    print("ok drawn case SOLVED, losses", round(loss, 4), "MW")

    pg.locator(".ws-centre .tabs [role=tab]", has_text="Data tables").click()
    pd = pg.locator('[data-t="bus"][data-r="2"][data-c="Pd"]')
    pd.fill("0.8")
    pd.press("Tab")
    need(state(pg, "case.bus[2].Pd") == 0.8, "Data tables: Pd changed to 0.8", bad)
    pg.keyboard.press("F5")
    pg.wait_for_function(f"{STATE}.results && {STATE}.results.loss !== {json.dumps(loss)}")
    pg.wait_for_selector(SOLVED)
    need(state(pg, "results.loss") > loss, "Run again: losses went up with the load", bad)

    pg.locator(".ws-centre .tabs [role=tab]", has_text="Diagram").click()
    pg.mouse.move(cx, cy)
    for dy in [-120] * 6 + [120] * 9:
        pg.mouse.wheel(0, dy)
        pg.wait_for_timeout(40)
    size = pg.evaluate("getComputedStyle(document.querySelector('.bus-label')).fontSize")
    need(size == "12px", f"wheel zoom: bus labels stay {size}", bad)
    need(not scrolls(pg), "page does not scroll", bad)
    ctx.close()


def main() -> int:
    bad: list[str] = []
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME)
        tour(b, bad)
        draw(b, bad)
        b.close()
    print("problems:", bad or "none")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
