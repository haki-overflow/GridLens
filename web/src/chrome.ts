// Title readouts, status bar, Messages panel and Properties panel, all
// drawn from the project state.
import { h } from "./shell";
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
  const msgTab = h("div", "tab active", "Messages");
  msgTab.setAttribute("role", "tab");
  outTabs.append(msgTab);
  let shown = -1;

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

    if (s.messages.length !== shown) {
      shown = s.messages.length;
      out.replaceChildren(...(s.messages.length ? s.messages.map((m) => {
        const d = h("div", `msg ${m.level}`);
        d.append(h("span", "t", m.t), document.createTextNode(m.text));
        return d;
      }) : [h("div", "empty", "No messages yet.")]));
      out.scrollTop = out.scrollHeight;
    }
    paintProps(props, s);
  };
  subscribe(paint);
  paint(getState());
}

function rows(pairs: [string, string][]): HTMLTableElement {
  const t = h("table");
  t.innerHTML = pairs.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("");
  return t;
}

const num = (v: unknown, d = 4) => (typeof v === "number" ? v.toFixed(d) : v == null ? "-" : String(v));

function paintProps(el: HTMLElement, s: State): void {
  const sel = s.selection;
  const c = s.case;
  const box = h("div", "props");
  if (!sel || !c) {
    box.append(h("div", "empty", "Nothing selected. Click a bus or branch in the diagram or the project tree."));
    el.replaceChildren(box);
    return;
  }
  const r = s.results && !isStale(s) ? s.results : null;
  if (sel.kind === "bus") {
    const b = c.bus[sel.index] ?? {};
    box.append(h("div", "sec", `Bus ${sel.index + 1}`),
      rows([["Id", `bus:${sel.index + 1}`], ["Type", String(b.Type ?? "-")],
        ["V set (pu)", num(b.V)], ["Pg (pu)", num(b.Pg)], ["Qg (pu)", num(b.Qg)],
        ["Pd (pu)", num(b.Pd)], ["Qd (pu)", num(b.Qd)], ["Bs (pu)", num(b.Bs)]]));
    const res = r?.res[sel.index];
    if (res) {
      box.append(h("div", "sec", "Solution"), rows([
        ["|V| (pu)", num(res["V (pu)"])], ["Angle (deg)", num(res["Angle (deg)"], 3)],
        ["P inj (MW)", num((res.P_inj as number) * r!.base, 2)],
        ["Q inj (MVAr)", num((res.Q_inj as number) * r!.base, 2)]]));
    }
  } else {
    const l = c.lines[sel.index] ?? {};
    const name = `${l.From}-${l.To}`;
    box.append(h("div", "sec", `Line ${name}`),
      rows([["Id", `branch:${sel.index + 1}`], ["From / To", `${l.From} / ${l.To}`],
        ["R (pu)", num(l.R)], ["X (pu)", num(l.X)], ["B (pu)", num(l.B)], ["Tap", num(l.Tap ?? 1, 3)]]));
    const f = r?.flows[sel.index];
    if (f) {
      const b = r!.base;
      box.append(h("div", "sec", "Flow"), rows([
        ["P from (MW)", num((f.P_ij as number) * b, 2)], ["Q from (MVAr)", num((f.Q_ij as number) * b, 2)],
        ["P to (MW)", num((f.P_ji as number) * b, 2)], ["Q to (MVAr)", num((f.Q_ji as number) * b, 2)],
        ["Loss (MW)", num((f.Loss_P as number) * b, 3)]]));
    }
  }
  if (!r && s.results) box.append(h("div", "empty", "Results are stale: press Run (F5)."));
  el.replaceChildren(box);
}
