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
