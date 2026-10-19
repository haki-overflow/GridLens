// Diagram canvas (D3).
// Sections follow the order of the files this one replaced; search for '// ----'.
import * as d3 from "d3";
import { caseSig, getState, post, report, setState, subscribe, type CaseData, type Rec, type State } from "./app";
import { registerDoc } from "./documents";
import { h } from "./ui";

// ---- canvas ------------------------------------------------------------

// One-line diagram (D3). Positions and branch routes come from
// /api/layout (oneline.layout, the same as the Streamlit diagram); bus
// colours from the last results. Wheel = zoom, drag = pan, Fit (Ctrl+0),
// click a bus or line to select it.

interface Layout { cx: number[]; cy: number[]; w: number[]; routes: [number, number][][] }

const BAND = (v: number, lo: number, hi: number) =>
  v < lo ? "var(--red)" : v > hi ? "var(--violet)"
    : v < lo + 0.02 || v > hi - 0.02 ? "var(--amber)" : "var(--text)";

registerDoc("canvas", (el) => {
  const wrap = h("div", "canvas-wrap");
  el.append(wrap);
  const svg = d3.select(wrap).append("svg").attr("role", "img")
    .attr("aria-label", "One-line diagram");
  const defs = svg.append("defs");
  const pat = defs.append("pattern").attr("id", "gl-grid").attr("width", 1).attr("height", 1)
    .attr("patternUnits", "userSpaceOnUse").attr("class", "gridpat");
  pat.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 1).attr("y2", 0);
  pat.append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 1);
  const world = svg.append("g");
  const grid = world.append("rect").attr("fill", "url(#gl-grid)");
  const gBranch = world.append("g"), gBus = world.append("g"), gText = world.append("g");
  const zoom = d3.zoom<SVGSVGElement, unknown>().scaleExtent([2, 400])
    .on("zoom", (e: d3.D3ZoomEvent<SVGSVGElement, unknown>) => world.attr("transform", e.transform.toString()));
  svg.call(zoom).on("dblclick.zoom", null);

  interface OutageData { k: number; sig: string | null; res: Rec[]; flows: Rec[] }
  let outageData: OutageData | null = null;
  let outageAsked = "";
  const tools = h("div", "canvas-tools");
  const opt = (label: string, title: string, on: () => void) => {
    const b = h("button", "ctool", label);
    b.type = "button";
    b.title = title;
    b.addEventListener("click", (e) => { e.stopPropagation(); on(); });
    tools.append(b);
    return b;
  };
  const toggle = (k: "grid" | "flows" | "angles") => () => {
    const v = getState().view;
    setState({ view: { ...v, [k]: !v[k] } });
  };
  opt("Fit", "Fit the diagram to the window (Ctrl+0)", () => window.dispatchEvent(new CustomEvent("gl:fit")));
  const optBtns: [string, HTMLButtonElement][] = [
    ["grid", opt("Grid", "Show the drawing grid", toggle("grid"))],
    ["flows", opt("Flows", "Show line flows (MW)", toggle("flows"))],
    ["angles", opt("Angles", "Show bus voltage angles", toggle("angles"))],
  ];
  wrap.append(tools);
  const chip = h("div", "outage-chip");
  chip.hidden = true;
  chip.title = "Click to clear";
  chip.addEventListener("click", () => setState({ outage: null }));
  wrap.append(chip);

  let caseKey = "";
  let layout: Layout | null = null;
  let layoutSig: string | null = null;
  let token = 0;
  let fitted = false;

  const fit = (animate = true) => {
    if (!layout) return;
    const box = wrap.getBoundingClientRect();
    if (box.width < 10 || box.height < 10) return;
    const xs = layout.cx.flatMap((c, i) => [c - layout!.w[i]! / 2, c + layout!.w[i]! / 2]);
    const ys = layout.cy;
    const x0 = Math.min(...xs) - 1.5, x1 = Math.max(...xs) + 1.5;
    const y0 = Math.min(...ys) - 2.4, y1 = Math.max(...ys) + 2;
    const k = Math.min(box.width / (x1 - x0), box.height / (y1 - y0));
    const t = d3.zoomIdentity.translate(box.width / 2, box.height / 2).scale(k)
      .translate(-(x0 + x1) / 2, -(y0 + y1) / 2);
    (animate ? svg.transition().duration(120) : svg).call(zoom.transform as never, t);
  };
  window.addEventListener("gl:fit", () => fit());
  new ResizeObserver(() => {
    if (!fitted && layout) {
      fit(false);
      fitted = true;
    }
  }).observe(wrap);

  const draw = (s: State) => {
    for (const [k, b] of optBtns) {
      const on = s.view[k as "grid" | "flows" | "angles"];
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", String(on));
    }
    if (!layout || !s.case) {
      gBranch.selectAll("*").remove();
      gBus.selectAll("*").remove();
      gText.selectAll("*").remove();
      return;
    }
    const c = s.case;
    const L = layout;
    const fresh = s.results && caseSig(s.case) === s.solvedSig ? s.results : null;
    const sel = s.selection;
    const od = fresh && s.outage !== null && outageData && outageData.k === s.outage
      && outageData.sig === s.solvedSig ? outageData : null;
    const resRows = od ? od.res : fresh?.res;
    const flowRows = od ? od.flows : fresh?.flows;
    if (fresh && s.outage !== null) {
      const l = c.lines[s.outage];
      chip.textContent = `Outage: line ${l?.From}-${l?.To} tripped${od ? "" : " (solving...)"} - click to clear`;
      chip.hidden = false;
    } else chip.hidden = true;
    const xs = L.cx.flatMap((x, i) => [x - L.w[i]! / 2, x + L.w[i]! / 2]);
    grid.attr("x", Math.floor(Math.min(...xs)) - 50).attr("y", Math.floor(Math.min(...L.cy)) - 50)
      .attr("width", 200).attr("height", 200).style("display", s.view.grid ? "inline" : "none");

    const line = d3.line<[number, number]>();
    gBranch.selectAll("*").remove();
    L.routes.forEach((pts, k) => {
      const isSel = sel?.kind === "branch" && sel.index === k;
      const tripped = !!fresh && s.outage === k;
      gBranch.append("path").attr("class", `branch${isSel ? " sel" : ""}${tripped ? " tripped" : ""}`)
        .attr("d", line(pts));
      if (tripped) {
        const m = pts[Math.floor((pts.length - 1) / 2)]!, n2 = pts[Math.floor((pts.length - 1) / 2) + 1] ?? m;
        gText.append("text").attr("class", "trip-x").attr("x", (m[0] + n2[0]) / 2).attr("y", (m[1] + n2[1]) / 2 + 0.2)
          .attr("text-anchor", "middle").text("✕");
      }
      gBranch.append("path").attr("class", "branch hit").attr("d", line(pts))
        .on("click", (e: MouseEvent) => {
          e.stopPropagation();
          setState({ selection: { kind: "branch", index: k } });
        })
        .append("title").text(`Line ${c.lines[k]?.From}-${c.lines[k]?.To}`);
    });

    gBus.selectAll("*").remove();
    gText.selectAll("*").remove();
    c.bus.forEach((b, i) => {
      const x = L.cx[i]!, y = L.cy[i]!, w = L.w[i]!;
      const res = resRows?.[i];
      const v = res ? Number(res["V (pu)"]) : NaN;
      const colour = Number.isFinite(v) ? BAND(v, fresh!.vmin, fresh!.vmax) : "var(--muted)";
      const isSel = sel?.kind === "bus" && sel.index === i;
      gBus.append("line").attr("class", "bar-line").attr("x1", x - w / 2).attr("x2", x + w / 2)
        .attr("y1", y).attr("y2", y)
        .style("stroke", isSel ? "var(--accent)" : colour);
      const hit = gBus.append("rect").attr("class", "bus-hit").attr("x", x - w / 2).attr("y", y - 0.35)
        .attr("width", w).attr("height", 0.7)
        .on("click", (e: MouseEvent) => {
          e.stopPropagation();
          setState({ selection: { kind: "bus", index: i } });
        })

      hit.append("title").text(`Bus ${i + 1} - drag to move`);
      hit.call(d3.drag<SVGRectElement, unknown>()
        .on("start", () => setState({ selection: { kind: "bus", index: i } }))
        .on("drag", (e: d3.D3DragEvent<SVGRectElement, unknown, unknown>) => {
          const [px, py] = d3.pointer(e.sourceEvent as MouseEvent, world.node());
          L.cx[i] = Math.round(px * 2) / 2;
          L.cy[i] = Math.round(py * 2) / 2;
          draw(getState());
        })
        .on("end", () => commitPositions()));
      const sx = x + w / 2 - 0.45;
      if (b.Type === "Slack" || b.Type === "PV") {
        gBus.append("line").attr("class", "sym").attr("x1", sx).attr("x2", sx).attr("y1", y).attr("y2", y - 0.9);
        gBus.append("circle").attr("class", "sym").attr("cx", sx).attr("cy", y - 1.2).attr("r", 0.3);
        gText.append("text").attr("class", "bus-label").attr("x", sx).attr("y", y - 1.08)
          .attr("text-anchor", "middle").style("font-size", "0.3px").text("G");
        gText.append("text").attr("class", "angle-label").attr("x", sx + 0.42).attr("y", y - 1.1).text(`G${i + 1}`);
      }
      if (Number(b.Pd) > 0) {
        const lx = x - w / 2 + 0.45;
        gBus.append("line").attr("class", "sym").attr("x1", lx).attr("x2", lx).attr("y1", y).attr("y2", y + 0.75);
        gBus.append("path").attr("class", "sym-load")
          .attr("d", `M${lx - 0.17},${y + 0.75}L${lx + 0.17},${y + 0.75}L${lx},${y + 1.02}Z`);
        gText.append("text").attr("class", "angle-label").attr("x", lx + 0.28).attr("y", y + 1.0).text(`Load ${i + 1}`);
      }
      gText.append("text").attr("class", "bus-label").attr("x", x - w / 2 + 0.05).attr("y", y - 0.2)
        .text(Number.isFinite(v) ? `${i + 1}  ${v.toFixed(3)}` : `${i + 1}`);
      if (s.view.angles && res) {
        gText.append("text").attr("class", "angle-label").attr("x", x - w / 2 + 1.0).attr("y", y + 0.5)
          .text(`${Number(res["Angle (deg)"]).toFixed(2)}°`);
      }
    });

    if (s.view.flows && fresh && flowRows) {
      L.routes.forEach((pts, k) => {
        if (od && k === s.outage) return;
        const f = flowRows[od && s.outage !== null && k > s.outage ? k - 1 : k] as Rec | undefined;
        if (!f || pts.length < 2) return;
        let best = 0, at: [number, number] = pts[0]!, horiz = false;
        for (let j = 1; j < pts.length; j++) {
          const a = pts[j - 1]!, b = pts[j]!;
          const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
          if (len > best) [best, at, horiz] = [len, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
            Math.abs(b[0] - a[0]) > Math.abs(b[1] - a[1])];
        }
        gText.append("text").attr("class", "flow-label").attr("x", horiz ? at[0] : at[0] + 0.12)
          .attr("y", horiz ? at[1] - 0.18 : at[1]).attr("text-anchor", horiz ? "middle" : "start")
          .text(`${(Number(f.P_ij) * fresh.base).toFixed(1)} MW`);
      });
    }
  };

  /** Save the bar positions into the case (raw diagram units, never all whole
   *  numbers, so oneline.layout does not read them as grid cells). */
  const commitPositions = () => {
    const s = getState();
    if (!layout || !s.case) return;
    const L = layout;
    setState({ case: { ...s.case, bus: s.case.bus.map((b, i) => (
      { ...b, x: Math.round(L.cx[i]! * 2) / 2 + 0.001, y: Math.round(L.cy[i]! * 2) / 2 + 0.001 })) } });
  };

  const sigOf = (c: CaseData | null) => c ? JSON.stringify([c.name, c.bus.length,
    c.lines.map((l) => [l.From, l.To]), c.bus.map((b) => [b.x, b.y])]) : null;

  const wantOutage = (s: State) => {
    if (!s.case || !s.results || s.outage === null || caseSig(s.case) !== s.solvedSig) return;
    if (outageData && outageData.k === s.outage && outageData.sig === s.solvedSig) return;
    const key = `${s.outage}|${s.solvedSig}`;
    if (key === outageAsked) return;
    outageAsked = key;
    const k = s.outage, sig = s.solvedSig;
    post<{ res: Rec[]; flows: Rec[] }>(`/api/outage/${k}`, s.case).then((o) => {
      outageData = { k, sig, res: o.res, flows: o.flows };
      draw(getState());
    }).catch((e) => report(e, "The outage case"));
  };

  const refresh = async (c: CaseData) => {
    const my = ++token;
    try {
      const L = await post<Layout>("/api/layout", c);
      if (my !== token) return;
      const first = !layout;
      const key = `${c.name}|${c.bus.length}|${c.lines.length}`;
      const newCase = key !== caseKey;
      caseKey = key;
      layout = L;
      draw(getState());
      if (newCase) {
        fit(false);
        fitted = wrap.getBoundingClientRect().width > 10;
      } else if (first || !fitted) {
        fit(false);
        fitted = wrap.getBoundingClientRect().width > 10;
      }
    } catch (e) {
      report(e, "The diagram layout");
    }
  };

  svg.on("click", () => setState({ selection: null }));
  subscribe((s) => {
    wantOutage(s);
    const sig = sigOf(s.case);
    if (sig !== layoutSig) {
      layoutSig = sig;
      if (s.case) void refresh(s.case);
      else {
        layout = null;
        draw(s);
      }
    } else {
      draw(s);
    }
  });
  const s0 = getState();
  layoutSig = sigOf(s0.case);
  wantOutage(s0);
  if (s0.case) void refresh(s0.case);
});
