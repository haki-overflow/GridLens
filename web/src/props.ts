// Properties panel: a grouped property grid (label left, input right, unit
// suffix). Edits change the case, so results go STALE until the next Run.
import { h } from "./shell";
import { getState, isStale, setState, type CaseData, type Settings, type State } from "./state";

type Rec = Record<string, unknown>;
const num = (v: unknown, d = 4) => (typeof v === "number" ? v.toFixed(d) : v == null ? "-" : String(v));

function group(title: string, open = true): [HTMLDetailsElement, HTMLElement] {
  const d = h("details", "pgroup");
  d.open = open;
  d.append(h("summary", "", title));
  const body = h("div", "prows");
  d.append(body);
  return [d, body];
}

function row(label: string, input: HTMLElement, unit = ""): HTMLElement {
  const r = h("label", "prow");
  r.append(h("span", "pl", label), input, h("span", "pu", unit));
  return r;
}

function numInput(value: unknown, commit: (v: number) => void, digits = 4): HTMLInputElement {
  const i = h("input");
  i.type = "text";
  i.inputMode = "decimal";
  i.value = typeof value === "number" ? String(+value.toFixed(digits)) : "";
  i.addEventListener("change", () => {
    const v = Number(i.value.trim());
    if (i.value.trim() === "" || !Number.isFinite(v)) {
      i.classList.add("bad");
      i.title = "Enter a number.";
      return;
    }
    i.classList.remove("bad");
    commit(v);
  });
  return i;
}

function selectInput(options: string[], value: string, commit: (v: string) => void): HTMLSelectElement {
  const s = h("select");
  for (const o of options) s.append(new Option(o, o, false, o === value));
  s.addEventListener("change", () => commit(s.value));
  return s;
}

function checkInput(value: boolean, commit: (v: boolean) => void): HTMLInputElement {
  const i = h("input");
  i.type = "checkbox";
  i.checked = value;
  i.addEventListener("change", () => commit(i.checked));
  return i;
}

function editBus(c: CaseData, i: number, patch: Rec): void {
  setState({ case: { ...c, bus: c.bus.map((b, k) => (k === i ? { ...b, ...patch } : b)) } });
}
function editLine(c: CaseData, i: number, patch: Rec): void {
  setState({ case: { ...c, lines: c.lines.map((l, k) => (k === i ? { ...l, ...patch } : l)) } });
}
function editSettings(c: CaseData, patch: Partial<Settings>): void {
  setState({ case: { ...c, settings: { ...c.settings, ...patch } } });
}

function readonly(pairs: [string, string, string?][]): HTMLElement {
  const box = h("div", "prows");
  for (const [k, v, u] of pairs) {
    const r = h("div", "prow ro");
    r.append(h("span", "pl", k), h("span", "pv", v), h("span", "pu", u ?? ""));
    box.append(r);
  }
  return box;
}

function projectPanel(c: CaseData): HTMLElement {
  const box = h("div", "props");
  const st = c.settings;
  const [g1, b1] = group("Project");
  b1.append(row("Case", Object.assign(h("input"), { value: c.name, readOnly: true })),
    row("Buses / branches", Object.assign(h("input"), { value: `${c.bus.length} / ${c.lines.length}`, readOnly: true })));
  const [g2, b2] = group("Study settings");
  b2.append(
    row("Method", selectInput(["Newton-Raphson", "Fast Decoupled", "Gauss-Seidel"], st.method,
      (v) => editSettings(c, { method: v }))),
    row("Tolerance", numInput(st.tol, (v) => editSettings(c, { tol: v }), 12), "pu"),
    row("Base", numInput(st.base, (v) => editSettings(c, { base: v }), 2), "MVA"),
    row("V min", numInput(st.vmin, (v) => editSettings(c, { vmin: v }), 3), "pu"),
    row("V max", numInput(st.vmax, (v) => editSettings(c, { vmax: v }), 3), "pu"));
  const [g3, b3] = group("Advanced", false);
  b3.append(
    row("Generator Q limits", checkInput(st.qlim, (v) => editSettings(c, { qlim: v }))),
    row("Transformer taps", checkInput(st.taps, (v) => editSettings(c, { taps: v }))),
    row("Bus shunts", checkInput(st.shunts, (v) => editSettings(c, { shunts: v }))));
  box.append(g1, g2, g3, h("div", "empty", "Click a bus or branch in the diagram or the project tree to edit it."));
  return box;
}

function busPanel(c: CaseData, i: number, s: State): HTMLElement {
  const b = c.bus[i] ?? {};
  const box = h("div", "props");
  const [g, body] = group(`Bus ${i + 1}`);
  const ed = (k: string) => (v: number) => editBus(c, i, { [k]: v });
  body.append(
    row("Type", selectInput(["Slack", "PV", "PQ"], String(b.Type ?? "PQ"), (v) => editBus(c, i, { Type: v }))),
    row("V setpoint", numInput(b.V, ed("V")), "pu"),
    row("Pg", numInput(b.Pg, ed("Pg")), "pu"),
    row("Qg", numInput(b.Qg, ed("Qg")), "pu"),
    row("Pd", numInput(b.Pd, ed("Pd")), "pu"),
    row("Qd", numInput(b.Qd, ed("Qd")), "pu"),
    row("Shunt Bs", numInput(b.Bs ?? 0, ed("Bs")), "pu"));
  box.append(g);
  if (c.settings.qlim) {
    const [gq, bq] = group("Generator limits");
    bq.append(row("Q min", numInput(b.Qmin, ed("Qmin")), "pu"), row("Q max", numInput(b.Qmax, ed("Qmax")), "pu"));
    box.append(gq);
  }
  const r = s.results && !isStale(s) ? s.results : null;
  const res = r?.res[i] as Rec | undefined;
  if (res && r) {
    const [gs, bs] = group("Solution");
    gs.classList.add("psol");
    bs.append(readonly([
      ["|V|", num(res["V (pu)"]), "pu"], ["Angle", num(res["Angle (deg)"], 3), "deg"],
      ["P inj", num((res.P_inj as number) * r.base, 2), "MW"],
      ["Q inj", num((res.Q_inj as number) * r.base, 2), "MVAr"]]));
    box.append(gs);
  }
  return box;
}

function linePanel(c: CaseData, i: number, s: State): HTMLElement {
  const l = c.lines[i] ?? {};
  const box = h("div", "props");
  const [g, body] = group(`Line ${l.From}-${l.To}`);
  const ed = (k: string) => (v: number) => editLine(c, i, { [k]: v });
  body.append(
    row("From bus", numInput(l.From, ed("From"), 0)),
    row("To bus", numInput(l.To, ed("To"), 0)),
    row("R", numInput(l.R, ed("R")), "pu"),
    row("X", numInput(l.X, ed("X")), "pu"),
    row("B charging", numInput(l.B, ed("B")), "pu"),
    row("Tap", numInput(l.Tap ?? 1, ed("Tap"), 3), "ratio"));
  box.append(g);
  const r = s.results && !isStale(s) ? s.results : null;
  const f = r?.flows[i] as Rec | undefined;
  if (f && r) {
    const k = r.base;
    const [gf, bf] = group("Flow");
    gf.classList.add("psol");
    bf.append(readonly([
      ["P from", num((f.P_ij as number) * k, 2), "MW"], ["Q from", num((f.Q_ij as number) * k, 2), "MVAr"],
      ["P to", num((f.P_ji as number) * k, 2), "MW"], ["Q to", num((f.Q_ji as number) * k, 2), "MVAr"],
      ["Loss", num((f.Loss_P as number) * k, 3), "MW"]]));
    box.append(gf);
  }
  return box;
}

let lastKey = "";

/** Repaint the panel. Edits keep the field being typed in: the panel is only
 *  rebuilt when the selection changes or no field inside it has focus. */
export function paintProps(el: HTMLElement, s: State): void {
  const c = s.case;
  if (!c) {
    el.replaceChildren(h("div", "empty", "No case loaded."));
    return;
  }
  const sel = s.selection;
  const key = sel ? `${sel.kind}:${sel.index}:${c.bus.length}:${c.lines.length}:${c.settings.qlim}` : `project:${c.settings.qlim}`;
  const focused = el.contains(document.activeElement) && document.activeElement !== el;
  const stale = !!s.results && isStale(s);
  if (focused && key === lastKey) {
    el.querySelector(".props")?.classList.toggle("stale", stale);
    return;
  }
  lastKey = key;
  const box = !sel ? projectPanel(c)
    : sel.kind === "bus" ? busPanel(c, sel.index, s) : linePanel(c, sel.index, s);
  if (stale) {
    box.classList.add("stale");
    box.append(h("div", "empty", "Results are stale: press Run (F5)."));
  }
  el.replaceChildren(box);
}

export { getState };
