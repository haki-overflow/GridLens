// Title readouts, status bar, Messages panel and Properties panel, all
// drawn from the project state.
import { mountOutput } from "./output";
import { paintProps } from "./props";
import { getState, isStale, subscribe, type State } from "./state";

const esc = (s: unknown) => String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] ?? c);

export function solution(s: State): [string, string] {
  if (!s.results) return ["NOT SOLVED", "bad"];
  if (isStale(s)) return ["STALE", "stale"];
  return s.results.ok ? ["SOLVED", "ok"] : ["NOT SOLVED", "bad"];
}

export function mountChrome(read: HTMLElement, status: HTMLElement, outTabs: HTMLElement,
  out: HTMLElement, props: HTMLElement): void {
  mountOutput(outTabs, out);

  const paint = (s: State) => {
    const c = s.case;
    const st = c?.settings;
    const [sol, cls] = solution(s);
    read.innerHTML = [
      ["Case", esc(c?.name ?? "-")],
      ["Buses / Branches", c ? `${c.bus.length} / ${c.lines.length}` : "- / -"],
      ["Base", st ? `${st.base} MVA` : "-"],
      ["Limits", st ? `${st.vmin.toFixed(2)}-${st.vmax.toFixed(2)} pu` : "-"],
    ].map(([k, v]) => `<div><span>${k}</span>${v}</div>`).join("") +
      `<div><span>Solution</span><b class="${cls}">${sol}</b></div>`;

    const r = s.results;
    status.innerHTML =
      `<div><b>Solver</b>${esc(r?.method ?? st?.method ?? "-")}</div>` +
      `<div><b>Iterations</b>${r ? r.its : "-"}</div>` +
      `<div><b>Tolerance</b>${r ? r.tol : st?.tol ?? "-"}</div>` +
      `<div class="fill"><b>Status</b>${sol === "SOLVED" ? "Converged" : sol === "STALE"
        ? "Stale: press Run (F5)" : r ? "Not converged" : "Ready"}</div>` +
      `<div class="file">${esc(s.fileName)}</div>`;

    paintProps(props, s);
  };
  subscribe(paint);
  paint(getState());
}
