// Diagram canvas (D3).
// Sections follow the order of the files this one replaced; search for '// ----'.
import * as d3 from "d3";
import {
  ApiError, NEW_LINE, NEW_TRAFO, addBus, addLine, caseSig, delBus, delLine, editBus, getState, post, report,
  setState, subscribe, type CaseData, type Rec, type Selection, type State,
} from "./app";
import { registerDoc } from "./documents";
import { h, isTyping } from "./ui";

// ---- canvas ------------------------------------------------------------

// One-line diagram (D3). Positions and branch routes come from
// /api/layout (oneline.layout, the same as the Streamlit diagram); bus
// colours from the last results. Wheel = zoom, drag empty space = pan,
// Fit (Ctrl+0). Drawing tools: Select (V), Bus (B), Line (L),
// Transformer (T), Generator (G), Load (D), Delete (Del); Esc = Select.
//
// Semantic zoom: the d3 zoom transform t is NOT put on a <g>. Every point is
// drawn at screen coordinates t.applyX(x), t.applyY(y), so strokes and text
// keep their CSS pixel sizes and stay sharp at every zoom level. Redraws are
// batched with requestAnimationFrame.

type Pt = [number, number];
interface Layout { cx: number[]; cy: number[]; w: number[]; routes: Pt[][] }
interface Geo { cx: number[]; cy: number[]; w: number[]; routes: (Pt[] | null)[] }
interface Drag { i: number; x: number; y: number }
interface Hit { kind: "bus" | "branch" | "gen" | "load"; i: number }
type Tool = "select" | "bus" | "line" | "trafo" | "gen" | "load" | "delete";

const TOOLS: { id: Tool; label: string; key: string; hint: string }[] = [
  { id: "select", label: "Select", key: "V",
    hint: "Click to select, drag a bar to move it, drag empty space to pan, wheel to zoom. Double-click to edit." },
  { id: "bus", label: "Bus", key: "B", hint: "Click empty canvas to add a PQ bus. Esc returns to Select." },
  { id: "line", label: "Line", key: "L", hint: "Press on a bus, drag to another bus and release to add a line." },
  { id: "trafo", label: "Transformer", key: "T",
    hint: "Press on a bus, drag to another bus and release to add a transformer." },
  { id: "gen", label: "Generator", key: "G",
    hint: "Click a bus to add a generator: Slack if the case has none, otherwise PV (Pg 0.5, V 1.0 pu)." },
  { id: "load", label: "Load", key: "D", hint: "Click a bus to add a load (Pd 0.5, Qd 0.2 pu)." },
  { id: "delete", label: "Delete", key: "Del", hint: "Click a bus, line, generator or load to remove it." },
];

const BAND = (v: number, lo: number, hi: number) =>
  v < lo ? "var(--red)" : v > hi ? "var(--violet)"
    : v < lo + 0.02 || v > hi - 0.02 ? "var(--amber)" : "var(--text)";

/** Symbol size in px for one diagram unit: follows the zoom, within limits. */
// symbol size follows the zoom between 8 px (a big network seen whole: small
// markers) and 60 px per diagram unit
const symUnit = (k: number) => Math.max(8, Math.min(k, 60));
const READ_K = 22;   // px per diagram unit at which every label and symbol is drawn
const NAMES_K = 14;  // below this a fitted view would drop the names: open at READ_K instead
const num = (v: unknown) => (v === null || v === undefined || v === "" ? NaN : Number(v));
const hasXY = (b: Rec) => Number.isFinite(num(b.x)) && Number.isFinite(num(b.y));
const snap = (v: number) => Math.round(v * 2) / 2;
/** Stored bar position: raw diagram units on the 0.5 grid, never whole. */
const stored = (v: number) => snap(v) + 0.001;
const isGen = (b: Rec) => b.Type === "Slack" || b.Type === "PV";
const isLoad = (b: Rec) => (Number(b.Pd) || 0) !== 0 || (Number(b.Qd) || 0) !== 0;
const DEFAULT_W = 3;

/** x, y of every bus are usable as raw diagram units (not grid cells). */
const ownXY = (c: CaseData) => c.bus.length > 0 && c.bus.every(hasXY)
  && !c.bus.every((b) => Number.isInteger(num(b.x)) && Number.isInteger(num(b.y)));

/** A simple connector when the server routes are not available: a straight
 *  drop when the bars overlap horizontally, otherwise one elbow. */
function connector(cx: number[], cy: number[], w: number[], a: number, b: number): Pt[] {
  const aL = cx[a]! - w[a]! / 2, aR = cx[a]! + w[a]! / 2;
  const bL = cx[b]! - w[b]! / 2, bR = cx[b]! + w[b]! / 2;
  const lo = Math.max(aL, bL), hi = Math.min(aR, bR);
  if (hi - lo > 0.2) {
    const x = (lo + hi) / 2;
    return [[x, cy[a]!], [x, cy[b]!]];
  }
  const right = cx[b]! > cx[a]!;
  const xa = right ? aR - 0.3 : aL + 0.3;
  return [[xa, cy[a]!], [xa, cy[b]!], [right ? bL : bR, cy[b]!]];
}

/** Bars and routes. The server layout is used as is when it belongs to this
 *  exact case; otherwise (a drawing in progress, or a refused layout) bars
 *  sit at their x, y and branches get simple connectors. */
function geometry(c: CaseData, L: Layout | null, matched: boolean, drag: Drag | null): Geo {
  const n = c.bus.length;
  const fromL = !!L && L.cx.length === n;
  const own = ownXY(c);
  const cx: number[] = [], cy: number[] = [], w: number[] = [];
  c.bus.forEach((b, i) => {
    let p: Pt;
    if (matched && fromL) p = [L!.cx[i]!, L!.cy[i]!];
    else if (own || (hasXY(b) && !fromL)) p = [num(b.x), num(b.y)];
    else if (L && i < L.cx.length) p = [L.cx[i]!, L.cy[i]!];
    else p = [i * 6, 0];
    if (drag?.i === i) p = [drag.x, drag.y];
    cx.push(p[0]);
    cy.push(p[1]);
    w.push(L && i < L.w.length ? L.w[i]! : DEFAULT_W);
  });
  const useRoutes = matched && fromL && L!.routes.length === c.lines.length;
  const routes = c.lines.map((l, k) => {
    const a = num(l.From) - 1, b = num(l.To) - 1;
    if (!Number.isInteger(a) || !Number.isInteger(b) || a < 0 || b < 0 || a >= n || b >= n || a === b) return null;
    if (useRoutes && drag?.i !== a && drag?.i !== b) return L!.routes[k] ?? null;
    return connector(cx, cy, w, a, b);
  });
  return { cx, cy, w, routes };
}

const sigOf = (c: CaseData | null) => c ? JSON.stringify([c.name, c.bus.length,
  c.lines.map((l) => [l.From, l.To]), c.bus.map((b) => [b.x, b.y])]) : null;

function hitOf(el: EventTarget | Element | null): Hit | null {
  const tag = (el as Element | null)?.closest?.("[data-hit]")?.getAttribute("data-hit");
  if (!tag) return null;
  const [kind, i] = tag.split(":");
  return { kind: kind as Hit["kind"], i: Number(i) };
}

registerDoc("canvas", (el) => {
  const wrap = h("div", "canvas-wrap");
  el.append(wrap);
  const svg = d3.select(wrap).append("svg").attr("role", "img")
    .attr("aria-label", "One-line diagram");
  const node = svg.node()!;
  const defs = svg.append("defs");
  const pat = defs.append("pattern").attr("id", "gl-grid").attr("patternUnits", "userSpaceOnUse")
    .attr("class", "gridpat");
  const patH = pat.append("line"), patV = pat.append("line");
  const grid = svg.append("rect").attr("class", "gridrect").attr("width", "100%").attr("height", "100%")
    .attr("fill", "url(#gl-grid)");
  const gBranch = svg.append("g"), gBus = svg.append("g"), gText = svg.append("g"), gOver = svg.append("g");

  let t = d3.zoomIdentity;
  let tool: Tool = "select";
  let drag: Drag | null = null;
  let rubber: { from: number; x0: number; y0: number; x: number; y: number } | null = null;
  let lastClick = { key: "", t: 0 }; // for double-click detection (see the click handler)
  let layout: Layout | null = null;
  let layoutFor: string | null = null; // the case signature the layout belongs to
  let asked: string | null = null;
  let caseName: string | null = null;
  let needFit = true;
  let token = 0;
  let frame = 0;
  const schedule = () => {
    if (!frame) frame = requestAnimationFrame(() => { frame = 0; draw(getState()); });
  };
  const matched = (c: CaseData) => !!layout && layoutFor === sigOf(c);
  const geo = (c: CaseData, d: Drag | null = drag) => geometry(c, layout, matched(c), d);

  /** The case with x, y on every bus (from the current drawing), so the
   *  first edit made on the canvas fixes the layout in place. */
  const placed = (c: CaseData): CaseData => {
    if (ownXY(c)) return c;
    const g = geo(c, null);
    return { ...c, bus: c.bus.map((b, i) => ({ ...b, x: stored(g.cx[i]!), y: stored(g.cy[i]!) })) };
  };

  const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([2, 400])
    .filter((e: MouseEvent) => {
      if (e.type === "wheel") return true;
      if (e.ctrlKey || e.button) return false;
      return !((tool === "line" || tool === "trafo") && hitOf(e.target) && hitOf(e.target)!.kind !== "branch");
    })
    .on("zoom", (e: d3.D3ZoomEvent<SVGSVGElement, unknown>) => { t = e.transform; schedule(); });
  svg.call(zoom).on("dblclick.zoom", null);

  // ---- overlays: tool group, view options, chips, hint ----
  interface OutageData { k: number; sig: string | null; res: Rec[]; flows: Rec[]; cut: number[]; lost: number }
  let outageData: OutageData | null = null;
  let outageAsked = "";
  const tools = h("div", "canvas-tools");
  const toolGroup = h("div", "ctool-group");
  toolGroup.setAttribute("role", "toolbar");
  toolGroup.setAttribute("aria-label", "Drawing tools");
  const optGroup = h("div", "ctool-group");
  tools.append(toolGroup, optGroup);
  const btn = (host: HTMLElement, label: string, title: string, on: () => void, key = "") => {
    const b = h("button", "ctool", label);
    b.type = "button";
    b.title = title;
    if (key) b.append(h("span", "k", key));
    b.addEventListener("click", (e) => { e.stopPropagation(); on(); });
    host.append(b);
    return b;
  };
  const toolBtns = TOOLS.map((x) => [x.id, btn(toolGroup, x.label, `${x.label} (${x.key})`,
    () => setTool(x.id), x.key)] as const);
  const toggle = (k: "grid" | "flows" | "angles") => () => {
    const v = getState().view;
    setState({ view: { ...v, [k]: !v[k] } });
  };
  btn(optGroup, "Fit", "Fit the diagram to the window (Ctrl+0)", () => fit());
  const optBtns: [string, HTMLButtonElement][] = [
    ["grid", btn(optGroup, "Grid", "Show the drawing grid", toggle("grid"))],
    ["flows", btn(optGroup, "Flows", "Show line flows (MW)", toggle("flows"))],
    ["angles", btn(optGroup, "Angles", "Show bus voltage angles", toggle("angles"))],
  ];
  const chips = h("div", "canvas-chips");
  const chip = h("div", "outage-chip");
  chip.hidden = true;
  chip.title = "Click to clear";
  chip.addEventListener("click", () => setState({ outage: null }));
  const warn = h("div", "canvas-warn");
  warn.hidden = true;
  const part = h("button", "part-chip");   // a big network shown in part, at reading size
  part.type = "button";
  part.hidden = true;
  part.title = "Fit the whole network in the window (Ctrl+0)";
  part.addEventListener("click", (e) => { e.stopPropagation(); fit(); });
  chips.append(chip, warn);
  const hint = h("div", "canvas-hint");
  hint.setAttribute("aria-live", "polite");
  wrap.append(tools, chips, hint, part);

  function setTool(id: Tool): void {
    tool = id;
    rubber = null;
    lastClick = { key: "", t: 0 };
    wrap.dataset.tool = id;
    for (const [k, b] of toolBtns) {
      b.classList.toggle("on", k === id);
      b.setAttribute("aria-pressed", String(k === id));
    }
    hint.textContent = TOOLS.find((x) => x.id === id)!.hint;
    schedule();
  }
  setTool("select");
  window.addEventListener("gl:tool", (e) => setTool((e as CustomEvent<Tool>).detail));

  /** Fit the whole drawing in the window. With `readable`, a network too big
   *  to read when fitted opens at reading size (READ_K) around its Slack bus
   *  instead; the user zooms out (wheel) or presses Fit to see all of it. */
  const fit = (animate = true, readable = false): boolean => {
    const c = getState().case;
    const box = wrap.getBoundingClientRect();
    if (!c || !c.bus.length || box.width < 10 || box.height < 10) return false;
    const g = geo(c, null);
    const xs = g.cx.flatMap((x, i) => [x - g.w[i]! / 2, x + g.w[i]! / 2]);
    const x0 = Math.min(...xs) - 1.5, x1 = Math.max(...xs) + 1.5;
    const y0 = Math.min(...g.cy) - 2.4, y1 = Math.max(...g.cy) + 2;
    const top = 44, bottom = 34;   // the tool bar and the hint line sit over the diagram
    const hgt = Math.max(box.height - top - bottom, 40);
    const k = Math.min(box.width / (x1 - x0), hgt / (y1 - y0), 40);
    let z = d3.zoomIdentity.translate(box.width / 2, top + hgt / 2).scale(k)
      .translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    if (readable && k < NAMES_K) {
      // around the Slack bus, the window kept inside the drawing (no empty margin)
      const i = Math.max(c.bus.findIndex((b) => b.Type === "Slack"), 0);
      const hw = box.width / 2 / READ_K, hh = hgt / 2 / READ_K;
      const mid = (v: number, lo: number, hi: number, half: number) =>
        hi - lo <= 2 * half ? (lo + hi) / 2 : Math.min(Math.max(v, lo + half), hi - half);
      z = d3.zoomIdentity.translate(box.width / 2, top + hgt / 2).scale(READ_K)
        .translate(-mid(g.cx[i]!, x0, x1, hw), -mid(g.cy[i]!, y0, y1, hh));
    }
    (animate ? svg.transition().duration(120) : svg).call(zoom.transform as never, z);
    return true;
  };
  const fitIfNeeded = () => {
    // only once real positions exist (the server layout, or x, y on every bus)
    const c = getState().case;
    if (!c || (!matched(c) && !ownXY(c))) return;
    if (needFit && fit(false, true)) needFit = false;
  };
  window.addEventListener("gl:fit", () => fit());
  new ResizeObserver(fitIfNeeded).observe(wrap);

  /** Grid lines stay 1px: the pattern tile is sized in screen pixels. */
  const drawGrid = (on: boolean) => {
    grid.style("display", on ? "inline" : "none");
    if (!on) return;
    let step = 0.5;
    for (const s of [0.5, 1, 2, 5, 10, 20, 50]) {
      step = s;
      if (s * t.k >= 14) break;
    }
    const p = step * t.k;
    pat.attr("width", p).attr("height", p).attr("x", t.x).attr("y", t.y);
    patH.attr("x1", 0).attr("y1", 0.5).attr("x2", p).attr("y2", 0.5);
    patV.attr("x1", 0.5).attr("y1", 0).attr("x2", 0.5).attr("y2", p);
  };

  // ---- draw ----
  const draw = (s: State) => {
    for (const [k, b] of optBtns) {
      const on = s.view[k as "grid" | "flows" | "angles"];
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    }
    drawGrid(s.view.grid);
    gBranch.selectAll("*").remove();
    gBus.selectAll("*").remove();
    gText.selectAll("*").remove();
    gOver.selectAll("*").remove();
    const c = s.case;
    if (!c) return;
    const G = geo(c);
    const X = (x: number) => t.applyX(x), Y = (y: number) => t.applyY(y);
    const u = symUnit(t.k);
    const vw = wrap.clientWidth, vh = wrap.clientHeight;
    const shown = G.cx.filter((x, i) => X(x) > 0 && X(x) < vw && Y(G.cy[i]!) > 30 && Y(G.cy[i]!) < vh - 20).length;
    part.hidden = shown === c.bus.length || c.bus.length <= 24;
    part.textContent = `Showing ${shown} of ${c.bus.length} buses · wheel to zoom out · click to see all`;
    const fresh = s.results && caseSig(c) === s.solvedSig ? s.results : null;
    const sel = s.selection;
    const od = fresh && s.outage !== null && outageData && outageData.k === s.outage
      && outageData.sig === s.solvedSig ? outageData : null;
    const resRows = od ? od.res : fresh?.res;
    const flowRows = od ? od.flows : fresh?.flows;
    if (fresh && s.outage !== null) {
      const l = c.lines[s.outage];
      const cut = od?.cut.length ? ` - bus ${od.cut.join(", ")} cut off (${od.lost.toFixed(1)} MW of load lost)` : "";
      chip.textContent = `Outage: line ${l?.From}-${l?.To} tripped${od ? cut : " (solving...)"} - click to clear`;
      chip.hidden = false;
    } else chip.hidden = true;

    const line = d3.line<Pt>().x((p) => X(p[0])).y((p) => Y(p[1]));
    G.routes.forEach((pts, k) => {
      if (!pts) return;
      const l = c.lines[k]!;
      const isSel = sel?.kind === "branch" && sel.index === k;
      const tripped = !!fresh && s.outage === k;
      gBranch.append("path").attr("class", `branch${isSel ? " sel" : ""}${tripped ? " tripped" : ""}`)
        .attr("d", line(pts));
      const [mid, dir] = longest(pts);
      if (l.Kind === "trafo") {
        const r = Math.max(5, Math.min(0.22 * u, 10));
        for (const sgn of [-1, 1]) {
          gBranch.append("circle").attr("class", `trafo-sym${isSel ? " sel" : ""}`)
            .attr("cx", X(mid[0]) + sgn * 0.65 * r * dir[0]).attr("cy", Y(mid[1]) + sgn * 0.65 * r * dir[1])
            .attr("r", r);
        }
      }
      if (tripped) {
        gText.append("text").attr("class", "trip-x").attr("x", X(mid[0])).attr("y", Y(mid[1]) + 6)
          .attr("text-anchor", "middle").text("✕");
      }
      gBranch.append("path").attr("class", "branch hit").attr("data-hit", `branch:${k}`).attr("d", line(pts))
        .append("title").text(`${l.Kind === "trafo" ? "Transformer" : "Line"} ${l.From}-${l.To}`);
    });

    // zoomed out on a big network, only bus numbers are written; names,
    // voltages, angles and flows come back as you zoom in
    const names = t.k >= NAMES_K, values = t.k >= 9;
    c.bus.forEach((b, i) => {
      const x = G.cx[i]!, y = G.cy[i]!, w = G.w[i]!;
      const xl = X(x - w / 2), xr = X(x + w / 2), yy = Y(y);
      const res = resRows?.[i];
      const v = res && !od?.cut.includes(i + 1) ? Number(res["V (pu)"]) : NaN;   // cut off: grey
      const colour = Number.isFinite(v) ? BAND(v, fresh!.vmin, fresh!.vmax) : "var(--muted)";
      const isSel = sel?.kind === "bus" && sel.index === i;
      gBus.append("line").attr("class", "bar-line").attr("x1", xl).attr("x2", xr)
        .attr("y1", yy).attr("y2", yy)
        .style("stroke", isSel ? "var(--accent)" : colour);
      const hit = gBus.append("rect").attr("class", "bus-hit").attr("data-hit", `bus:${i}`)
        .attr("x", xl - 3).attr("y", yy - 8).attr("width", xr - xl + 6).attr("height", 16);
      hit.append("title").text(tool === "select" ? `Bus ${i + 1} - drag to move` : `Bus ${i + 1}`);
      hit.call(busDrag(i));
      const sx = xr - 0.45 * u;
      if (isGen(b)) {
        gBus.append("line").attr("class", "sym").attr("x1", sx).attr("x2", sx).attr("y1", yy).attr("y2", yy - 0.9 * u);
        gBus.append("circle").attr("class", u < 16 ? "sym dot" : "sym").attr("cx", sx).attr("cy", yy - 1.2 * u)
          .attr("r", Math.max(0.3 * u, 3));
        if (u >= 16) gText.append("text").attr("class", "sym-label").attr("x", sx).attr("y", yy - 1.2 * u)
          .attr("text-anchor", "middle").attr("dominant-baseline", "central").text("G");
        if (names) gText.append("text").attr("class", "angle-label").attr("x", sx + 0.3 * u + 4).attr("y", yy - 1.2 * u)
          .attr("dominant-baseline", "central").text(`G${i + 1}`);
        gBus.append("circle").attr("class", "sym-hit").attr("data-hit", `gen:${i}`)
          .attr("cx", sx).attr("cy", yy - 1.05 * u).attr("r", Math.max(0.45 * u, 10))
          .append("title").text(`Generator at bus ${i + 1} (${String(b.Type)})`);
      }
      if (isLoad(b)) {
        const lx = xl + 0.45 * u;
        gBus.append("line").attr("class", "sym").attr("x1", lx).attr("x2", lx).attr("y1", yy).attr("y2", yy + 0.75 * u);
        gBus.append("path").attr("class", "sym-load")
          .attr("d", `M${lx - 0.17 * u},${yy + 0.75 * u}L${lx + 0.17 * u},${yy + 0.75 * u}L${lx},${yy + 1.02 * u}Z`);
        if (names) gText.append("text").attr("class", "angle-label").attr("x", lx + 0.17 * u + 4).attr("y", yy + 0.9 * u)
          .attr("dominant-baseline", "central").text(`Load ${i + 1}`);
        gBus.append("rect").attr("class", "sym-hit").attr("data-hit", `load:${i}`)
          .attr("x", lx - Math.max(0.25 * u, 6)).attr("y", yy + 8)
          .attr("width", Math.max(0.5 * u, 12)).attr("height", Math.max(1.02 * u - 8, 10))
          .append("title").text(`Load at bus ${i + 1}`);
      }
      gText.append("text").attr("class", "bus-label").attr("x", xl + 2).attr("y", yy - 7)
        .text(Number.isFinite(v) && values ? `${i + 1}  ${v.toFixed(3)}` : `${i + 1}`);
      if (s.view.angles && res && values) {
        gText.append("text").attr("class", "angle-label").attr("x", xl + 0.9 * u).attr("y", yy + 15)
          .text(`${Number(res["Angle (deg)"]).toFixed(2)}°`);
      }
    });

    if (s.view.flows && fresh && flowRows && values) {
      G.routes.forEach((pts, k) => {
        if (!pts || (od && k === s.outage)) return;
        const f = flowRows[od && s.outage !== null && k > s.outage ? k - 1 : k] as Rec | undefined;
        if (!f || pts.length < 2) return;
        const [at, dir] = longest(pts);
        const horiz = Math.abs(dir[0]) > Math.abs(dir[1]);
        gText.append("text").attr("class", "flow-label").attr("x", horiz ? X(at[0]) : X(at[0]) + 5)
          .attr("y", horiz ? Y(at[1]) - 5 : Y(at[1])).attr("text-anchor", horiz ? "middle" : "start")
          .text(`${(Number(f.P_ij) * fresh.base).toFixed(1)} MW`);
      });
    }

    if (rubber) {
      gOver.append("line").attr("class", "rubber").attr("x1", rubber.x0).attr("y1", rubber.y0)
        .attr("x2", rubber.x).attr("y2", rubber.y);
    }
  };

  /** Midpoint and unit direction of the longest segment of a route. */
  function longest(pts: Pt[]): [Pt, Pt] {
    let best = -1, at: Pt = pts[0]!, dir: Pt = [1, 0];
    for (let j = 1; j < pts.length; j++) {
      const a = pts[j - 1]!, b = pts[j]!;
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (len > best) {
        best = len;
        at = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        dir = len > 0 ? [(b[0] - a[0]) / len, (b[1] - a[1]) / len] : [1, 0];
      }
    }
    return [at, dir];
  }

  // ---- interaction ----
  const toUnits = (e: Event): Pt => t.invert(d3.pointer(e, node));

  /** Select tool: drag a bar. Positions change only locally while dragging;
   *  the case (and the undo history) is updated once, on drag end. */
  function busDrag(i: number) {
    let grab: Pt = [0, 0];
    return d3.drag<SVGRectElement, unknown>()
      .filter((e: MouseEvent) => tool === "select" && !e.button && !e.ctrlKey)
      .on("start", (e: d3.D3DragEvent<SVGRectElement, unknown, unknown>) => {
        const c = getState().case;
        if (!c) return;
        const g = geo(c, null);
        const [ux, uy] = toUnits(e.sourceEvent as Event);
        grab = [ux - g.cx[i]!, uy - g.cy[i]!];
      })
      .on("drag", (e: d3.D3DragEvent<SVGRectElement, unknown, unknown>) => {
        const [ux, uy] = toUnits(e.sourceEvent as Event);
        drag = { i, x: snap(ux - grab[0]), y: snap(uy - grab[1]) };
        schedule();
      })
      .on("end", () => {
        const d = drag;
        drag = null;
        const c = getState().case;
        if (!d || !c) return;
        const p = placed(c);
        setState({ case: { ...p, bus: p.bus.map((b, k) => (k === d.i ? { ...b, x: stored(d.x), y: stored(d.y) } : b)) },
          selection: { kind: "bus", index: d.i } });
      });
  }

  const selectHit = (hit: Hit | null) => {
    const selection: Selection | null = !hit ? null
      : hit.kind === "branch" ? { kind: "branch", index: hit.i } : { kind: "bus", index: hit.i };
    setState({ selection });
  };

  const addGen = (c: CaseData, i: number) => {
    const b = c.bus[i]!;
    const selection: Selection = { kind: "bus", index: i };
    if (isGen(b)) return setState({ selection });
    const slack = c.bus.some((x) => x.Type === "Slack");
    editBus(placed(c), i, { Type: slack ? "PV" : "Slack", Pg: 0.5, V: 1.0 }, { selection });
  };

  const remove = (c: CaseData, hit: Hit) => {
    const p = placed(c);
    if (hit.kind === "bus") delBus(p, hit.i);
    else if (hit.kind === "branch") delLine(p, hit.i);
    else if (hit.kind === "gen") editBus(p, hit.i, { Type: "PQ", Pg: 0 });
    else editBus(p, hit.i, { Pd: 0, Qd: 0 });
  };

  svg.on("click", (e: MouseEvent) => {
    const c = getState().case;
    if (!c) return;
    const hit = hitOf(e.target);
    const onBus = hit && hit.kind !== "branch";
    if (tool === "bus" && !hit) {
      const [ux, uy] = toUnits(e);
      addBus(placed(c), { x: stored(ux), y: stored(uy) });
    } else if (tool === "gen") {
      if (onBus) addGen(c, hit.i);
    } else if (tool === "load") {
      if (onBus) editBus(placed(c), hit.i, { Pd: 0.5, Qd: 0.2 }, { selection: { kind: "bus", index: hit.i } });
    } else if (tool === "delete") {
      if (hit) remove(c, hit);
    } else if (tool !== "line" && tool !== "trafo") {
      selectHit(hit);
    }
    // Double-click, detected here: the first click redraws the diagram, so the
    // browser's dblclick (and click count) can be lost with the replaced
    // element. Two clicks on the same bus or line within 500 ms count.
    const key = hit ? `${hit.kind === "branch" ? "branch" : "bus"}:${hit.i}` : "";
    const double = !!key && key === lastClick.key && e.timeStamp - lastClick.t < 500;
    lastClick = double ? { key: "", t: 0 } : { key, t: e.timeStamp };
    if (double && hit && tool !== "delete") {
      selectHit(hit); // the Properties panel repaints synchronously
      document.querySelector<HTMLElement>(".ws-props .pgroup input:not([readonly]), .ws-props .pgroup select")?.focus();
    }
  });

  // Line / Transformer: press on bus A, drag a rubber band, release on bus B.
  node.addEventListener("pointerdown", (e) => {
    if ((tool !== "line" && tool !== "trafo") || e.button !== 0) return;
    const hit = hitOf(e.target);
    if (!hit || hit.kind === "branch") return;
    e.preventDefault();
    const [px, py] = d3.pointer(e, node);
    rubber = { from: hit.i, x0: px, y0: py, x: px, y: py };
    node.setPointerCapture(e.pointerId);
    schedule();
  });
  node.addEventListener("pointermove", (e) => {
    if (!rubber) return;
    [rubber.x, rubber.y] = d3.pointer(e, node);
    schedule();
  });
  node.addEventListener("pointerup", (e) => {
    if (!rubber) return;
    const from = rubber.from;
    rubber = null;
    schedule();
    const hit = hitOf(document.elementFromPoint(e.clientX, e.clientY));
    const c = getState().case;
    if (c && hit && hit.kind !== "branch" && hit.i !== from) {
      addLine(placed(c), from + 1, hit.i + 1, tool === "trafo" ? NEW_TRAFO : NEW_LINE);
    }
  });
  node.addEventListener("pointercancel", () => { rubber = null; schedule(); });

  window.addEventListener("keydown", (e) => {
    const s = getState();
    if (s.activeDoc !== "canvas" || !s.started || isTyping(e) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape") {
      setTool("select");
    } else if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      const sel = s.selection;
      if (!sel || !s.case) setTool("delete");
      else if (sel.kind === "bus") delBus(placed(s.case), sel.index);
      else delLine(placed(s.case), sel.index);
    } else {
      const x = TOOLS.find((k) => k.key.length === 1 && k.key === e.key.toUpperCase());
      if (x) {
        e.preventDefault();
        setTool(x.id);
      }
    }
  });

  // ---- data: layout and the outage view ----
  const wantOutage = (s: State) => {
    if (!s.case || !s.results || s.outage === null || caseSig(s.case) !== s.solvedSig) return;
    if (outageData && outageData.k === s.outage && outageData.sig === s.solvedSig) return;
    const key = `${s.outage}|${s.solvedSig}`;
    if (key === outageAsked) return;
    outageAsked = key;
    const k = s.outage, sig = s.solvedSig;
    post<{ res: Rec[]; flows: Rec[]; cut_off: number[]; lost_load: number }>(`/api/outage/${k}`, s.case).then((o) => {
      outageData = { k, sig, res: o.res, flows: o.flows, cut: o.cut_off ?? [], lost: o.lost_load ?? 0 };
      schedule();
    }).catch((e) => report(e, "The outage case"));
  };

  const showWarn = (problems: string[]) => {
    warn.textContent = `Diagram: ${problems[0] ?? "the network is not finished"}`
      + (problems.length > 1 ? ` (+${problems.length - 1} more)` : "");
    warn.title = [...problems, "Press Run (F5) for the full list."].join("\n");
    warn.hidden = false;
  };

  /** Ask the server for the layout. An unfinished drawing is checked with
   *  /api/validate first (always 200, so the browser logs no failed
   *  request); it keeps the canvas, drawn from the buses' x, y, and a
   *  warning chip says what is missing. */
  const refresh = async (c: CaseData) => {
    const my = ++token;
    const sig = sigOf(c);
    try {
      const v = await post<{ problems: string[] }>("/api/validate", c);
      if (my !== token) return;
      if (v.problems.length) showWarn(v.problems);
      else {
        const L = await post<Layout>("/api/layout", c);
        if (my !== token) return;
        layout = L;
        layoutFor = sig;
        warn.hidden = true;
      }
    } catch (e) {
      if (my !== token) return;
      if (e instanceof ApiError && e.status === 422) showWarn(e.problems);
      else report(e, "The diagram layout");
    }
    fitIfNeeded();
    schedule();
  };

  const onState = (s: State) => {
    wantOutage(s);
    if ((s.case?.name ?? null) !== caseName) {
      caseName = s.case?.name ?? null;
      layout = null;
      layoutFor = null;
      needFit = true;
      warn.hidden = true;
    }
    const sig = sigOf(s.case);
    if (sig !== asked) {
      asked = sig;
      if (s.case) void refresh(s.case);
    }
    schedule();
  };
  subscribe(onState);
  onState(getState());
});
