// One-line diagram (D3). Positions and branch routes come from
// /api/layout (oneline.layout, the same as the Streamlit diagram); bus
// colours from the last results. Wheel = zoom, drag = pan, Fit (Ctrl+0),
// click a bus or line to select it.
import * as d3 from "d3";
import { post, type Rec } from "./api";
import { report } from "./actions";
import { registerDoc } from "./docs";
import { h } from "./shell";
import { caseSig, getState, setState, subscribe, type CaseData, type State } from "./state";

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
    const xs = L.cx.flatMap((x, i) => [x - L.w[i]! / 2, x + L.w[i]! / 2]);
    grid.attr("x", Math.floor(Math.min(...xs)) - 50).attr("y", Math.floor(Math.min(...L.cy)) - 50)
      .attr("width", 200).attr("height", 200).style("display", s.view.grid ? "inline" : "none");

    const line = d3.line<[number, number]>();
    gBranch.selectAll("*").remove();
    L.routes.forEach((pts, k) => {
      const isSel = sel?.kind === "branch" && sel.index === k;
      gBranch.append("path").attr("class", `branch${isSel ? " sel" : ""}`).attr("d", line(pts));
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
      const res = fresh?.res[i];
      const v = res ? Number(res["V (pu)"]) : NaN;
      const colour = Number.isFinite(v) ? BAND(v, fresh!.vmin, fresh!.vmax) : "var(--muted)";
      const isSel = sel?.kind === "bus" && sel.index === i;
      gBus.append("line").attr("class", "bar-line").attr("x1", x - w / 2).attr("x2", x + w / 2)
        .attr("y1", y).attr("y2", y)
        .style("stroke", isSel ? "var(--accent)" : colour);
      gBus.append("rect").attr("class", "bus-hit").attr("x", x - w / 2).attr("y", y - 0.35)
        .attr("width", w).attr("height", 0.7)
        .on("click", (e: MouseEvent) => {
          e.stopPropagation();
          setState({ selection: { kind: "bus", index: i } });
        })
        .append("title").text(`Bus ${i + 1}`);
      const sx = x + w / 2 - 0.45;
      if (b.Type === "Slack" || b.Type === "PV") {
        gBus.append("line").attr("class", "sym").attr("x1", sx).attr("x2", sx).attr("y1", y).attr("y2", y - 0.9);
        gBus.append("circle").attr("class", "sym").attr("cx", sx).attr("cy", y - 1.2).attr("r", 0.3);
        gText.append("text").attr("class", "bus-label").attr("x", sx).attr("y", y - 1.08)
          .attr("text-anchor", "middle").style("font-size", "0.3px").text("G");
      }
      if (Number(b.Pd) > 0) {
        const lx = x - w / 2 + 0.45;
        gBus.append("line").attr("class", "sym").attr("x1", lx).attr("x2", lx).attr("y1", y).attr("y2", y + 0.75);
        gBus.append("path").attr("class", "sym-load")
          .attr("d", `M${lx - 0.17},${y + 0.75}L${lx + 0.17},${y + 0.75}L${lx},${y + 1.02}Z`);
      }
      gText.append("text").attr("class", "bus-label").attr("x", x - w / 2 + 0.05).attr("y", y - 0.2)
        .text(Number.isFinite(v) ? `${i + 1}  ${v.toFixed(3)}` : `${i + 1}`);
      if (s.view.angles && res) {
        gText.append("text").attr("class", "angle-label").attr("x", x - w / 2 + 1.0).attr("y", y + 0.5)
          .text(`${Number(res["Angle (deg)"]).toFixed(2)}°`);
      }
    });

    if (s.view.flows && fresh) {
      L.routes.forEach((pts, k) => {
        const f = fresh.flows[k] as Rec | undefined;
        if (!f || pts.length < 2) return;
        let best = 0, at: [number, number] = pts[0]!;
        for (let j = 1; j < pts.length; j++) {
          const a = pts[j - 1]!, b = pts[j]!;
          const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
          if (len > best) [best, at] = [len, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]];
        }
        gText.append("text").attr("class", "flow-label").attr("x", at[0] + 0.12).attr("y", at[1])
          .text(`${(Number(f.P_ij) * fresh.base).toFixed(1)} MW`);
      });
    }
  };

  const refresh = async (c: CaseData) => {
    const my = ++token;
    try {
      const L = await post<Layout>("/api/layout", c);
      if (my !== token) return;
      const first = !layout;
      layout = L;
      draw(getState());
      if (first || !fitted) {
        fit(false);
        fitted = wrap.getBoundingClientRect().width > 10;
      }
    } catch (e) {
      report(e, "The diagram layout");
    }
  };

  svg.on("click", () => setState({ selection: null }));
  subscribe((s) => {
    const sig = s.case ? JSON.stringify([s.case.name, s.case.bus.length, s.case.lines.map((l) => [l.From, l.To])]) : null;
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
  layoutSig = s0.case ? JSON.stringify([s0.case.name, s0.case.bus.length, s0.case.lines.map((l) => [l.From, l.To])]) : null;
  if (s0.case) void refresh(s0.case);
});
