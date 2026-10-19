// D3 line chart (P-V curves). Colours from the token palette.
import * as d3 from "d3";

export interface Series { name: string; y: number[] }
const PALETTE = ["--c1", "--c2", "--c3", "--c4", "--c5", "--c6"];

export function lineChart(x: number[], series: Series[], o: {
  xLabel: string; yLabel: string; hline?: { y: number; label: string };
  width?: number; height?: number;
}): HTMLElement {
  const W = o.width ?? 760, H = o.height ?? 380;
  const m = { t: 14, r: 16, b: 40, l: 54 };
  const svg = d3.create("svg").attr("class", "chart").attr("viewBox", `0 0 ${W} ${H}`)
    .attr("width", W).attr("height", H).attr("role", "img").attr("aria-label", o.yLabel);
  const all = series.flatMap((s) => s.y).filter(Number.isFinite);
  if (o.hline) all.push(o.hline.y);
  const xs = d3.scaleLinear().domain(d3.extent(x) as [number, number]).nice().range([m.l, W - m.r]);
  const ys = d3.scaleLinear().domain(d3.extent(all) as [number, number]).nice().range([H - m.b, m.t]);
  svg.append("g").attr("class", "gridline").attr("transform", `translate(${m.l},0)`)
    .call(d3.axisLeft(ys).tickSize(-(W - m.l - m.r)).tickFormat(() => ""))
    .call((g) => g.select(".domain").remove());
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`).call(d3.axisBottom(xs));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(ys));
  svg.append("text").attr("x", (m.l + W - m.r) / 2).attr("y", H - 6).attr("text-anchor", "middle").text(o.xLabel);
  svg.append("text").attr("transform", `translate(14,${(m.t + H - m.b) / 2}) rotate(-90)`)
    .attr("text-anchor", "middle").text(o.yLabel);
  if (o.hline) {
    const y = ys(o.hline.y);
    svg.append("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y).attr("y2", y)
      .style("stroke", "var(--red)").style("stroke-dasharray", "5 4");
    svg.append("text").attr("x", W - m.r - 4).attr("y", y - 4).attr("text-anchor", "end")
      .style("fill", "var(--red)").text(o.hline.label);
  }
  const line = d3.line<number>().x((_, i) => xs(x[i]!)).y((v) => ys(v)).defined(Number.isFinite);
  series.forEach((s, i) => {
    svg.append("path").attr("d", line(s.y)).style("fill", "none")
      .style("stroke", `var(${PALETTE[i % PALETTE.length]})`).style("stroke-width", 1.6);
  });
  const wrap = document.createElement("div");
  wrap.append(svg.node()!);
  const legend = document.createElement("div");
  legend.className = "legend";
  legend.innerHTML = series.map((s, i) =>
    `<span><i style="background: var(${PALETTE[i % PALETTE.length]})"></i>${s.name}</span>`).join("");
  wrap.append(legend);
  return wrap;
}

// ---- stacked panels, shared x axis, crosshair (PSCAD graph frame style) -----
export interface PSeries { name: string; y: number[]; dim?: boolean; colour?: string }
export interface Panel {
  yLabel: string; series: PSeries[]; log?: boolean;
  hline?: { y: number; label: string }; digits?: number;
}

export function stackedPlot(x: number[], panels: Panel[], o: {
  xLabel: string; panelHeight?: number; vline?: { x: number; label: string };
}): HTMLElement {
  const W = 860, PH = o.panelHeight ?? 170;
  const m = { t: 8, r: 14, b: 8, l: 58 };
  const wrap = document.createElement("div");
  wrap.className = "stack";
  const xs = d3.scaleLinear().domain(d3.extent(x) as [number, number]).range([m.l, W - m.r]);
  const cross: { line: d3.Selection<SVGLineElement, undefined, null, undefined>; read: d3.Selection<SVGTextElement, undefined, null, undefined>; p: Panel }[] = [];
  let colourIx = 0;
  const colours = new Map<string, string>();
  const colourOf = (s: PSeries) => {
    if (s.dim) return "var(--axis)";
    if (s.colour) return s.colour;
    if (!colours.has(s.name)) colours.set(s.name, `var(${PALETTE[colourIx++ % PALETTE.length]})`);
    return colours.get(s.name)!;
  };

  panels.forEach((p, pi) => {
    const last = pi === panels.length - 1;
    const H = PH + (last ? 34 : 0);
    const svg = d3.create("svg").attr("class", "chart").attr("viewBox", `0 0 ${W} ${H}`)
      .attr("width", "100%").attr("role", "img").attr("aria-label", p.yLabel);
    const vals = p.series.flatMap((s) => s.y).filter((v) => Number.isFinite(v) && (!p.log || v > 0));
    if (p.hline) vals.push(p.hline.y);
    const ext = d3.extent(vals) as [number, number];
    const ys = (p.log ? d3.scaleLog() : d3.scaleLinear()).domain(ext).nice().range([PH - m.b, m.t]);
    svg.append("rect").attr("class", "frame").attr("x", m.l).attr("y", m.t)
      .attr("width", W - m.l - m.r).attr("height", PH - m.b - m.t);
    svg.append("g").attr("class", "gridline").attr("transform", `translate(${m.l},0)`)
      .call(d3.axisLeft(ys as d3.AxisScale<number>).ticks(5).tickSize(-(W - m.l - m.r)).tickFormat(() => ""))
      .call((g) => g.select(".domain").remove());
    svg.append("g").attr("class", "gridline").attr("transform", `translate(0,${PH - m.b})`)
      .call(d3.axisBottom(xs).ticks(10).tickSize(-(PH - m.b - m.t)).tickFormat(() => ""))
      .call((g) => g.select(".domain").remove());
    svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`)
      .call(d3.axisLeft(ys as d3.AxisScale<number>).ticks(5, p.log ? ".0e" : undefined));
    const bottom = svg.append("g").attr("class", "axis").attr("transform", `translate(0,${PH - m.b})`)
      .call(d3.axisBottom(xs).ticks(10));
    if (!last) bottom.selectAll("text").remove();
    svg.append("text").attr("class", "ylab").attr("transform", `translate(12,${(m.t + PH - m.b) / 2}) rotate(-90)`)
      .attr("text-anchor", "middle").text(p.yLabel);
    if (last) svg.append("text").attr("x", (m.l + W - m.r) / 2).attr("y", H - 6)
      .attr("text-anchor", "middle").text(o.xLabel);
    if (p.hline) {
      const y = ys(p.hline.y);
      svg.append("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y).attr("y2", y)
        .style("stroke", "var(--red)").style("stroke-dasharray", "5 4");
      svg.append("text").attr("x", m.l + 6).attr("y", y - 4).style("fill", "var(--red)").text(p.hline.label);
    }
    if (o.vline) {
      const vx = xs(o.vline.x);
      svg.append("line").attr("x1", vx).attr("x2", vx).attr("y1", m.t).attr("y2", PH - m.b)
        .style("stroke", "var(--red)").style("stroke-dasharray", "4 4");
      if (pi === 0) svg.append("text").attr("x", vx - 4).attr("y", PH - m.b - 6).attr("text-anchor", "end")
        .style("fill", "var(--red)").text(o.vline.label);
    }
    const line = d3.line<number>().x((_, i) => xs(x[i]!)).y((v) => ys(v)).defined((v) => Number.isFinite(v) && (!p.log || v > 0));
    [...p.series].sort((a, b) => Number(!!b.dim) - Number(!!a.dim)).forEach((s) => {
      svg.append("path").attr("d", line(s.y)).style("fill", "none")
        .style("stroke", colourOf(s)).style("stroke-width", s.dim ? 1 : 1.8);
    });
    // legend, top right (named series only)
    const named = p.series.filter((s) => !s.dim).slice(0, 6);
    named.forEach((s, i) => {
      const gy = m.t + 12 + i * 13, gx = W - m.r - 70;
      svg.append("line").attr("x1", gx).attr("x2", gx + 14).attr("y1", gy - 3).attr("y2", gy - 3)
        .style("stroke", colourOf(s)).style("stroke-width", 2);
      svg.append("text").attr("x", gx + 18).attr("y", gy).text(s.name);
    });
    const line1 = svg.append("line").attr("class", "cross").attr("y1", m.t).attr("y2", PH - m.b).style("display", "none");
    const read = svg.append("text").attr("class", "cross-read").attr("x", m.l + 6).attr("y", m.t + 12)
      .style("display", "none");
    cross.push({ line: line1, read, p });
    wrap.append(svg.node()!);
    svg.on("pointermove", (e: PointerEvent) => {
      const box = (svg.node() as SVGSVGElement).getBoundingClientRect();
      const px = ((e.clientX - box.left) / box.width) * W;
      const xv = xs.invert(Math.min(Math.max(px, m.l), W - m.r));
      const i = Math.min(Math.max(d3.bisectCenter(x, xv), 0), x.length - 1);
      for (const c of cross) {
        c.line.attr("x1", xs(x[i]!)).attr("x2", xs(x[i]!)).style("display", null);
        const dg = c.p.digits ?? 3;
        const top = c.p.series.filter((s) => !s.dim).slice(0, 3)
          .map((s) => `${s.name} ${Number.isFinite(s.y[i]!) ? s.y[i]!.toFixed(dg) : "-"}`).join("   ");
        c.read.style("display", null).text(`x=${x[i]!.toFixed(2)}   ${top}`);
      }
    }).on("pointerleave", () => {
      for (const c of cross) { c.line.style("display", "none"); c.read.style("display", "none"); }
    });
  });
  return wrap;
}
