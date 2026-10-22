// Panels: project tree, properties, output.
// Sections follow the order of the files this one replaced; search for '// ----'.
import { TEACH_MAX, VIEWS, addBus, clearMessages, addLine, delBus, delLine, editBus, editLine, getState, isStale, navigateView, setState, subscribe, viewOf, type CaseData, type Rec, type Settings, type State } from "./app";
import { h } from "./ui";

// ---- nav ---------------------------------------------------------------

// Workflow list: six steps in plain words, each with a one-line hint and a
// status mark (locked until the first Run, ready, or out of date). It
// replaces the project tree; buses and branches are chosen on the diagram or
// in the "Edit:" selector of the Properties panel.
export function mountNav(el: HTMLElement): void {
  const box = h("div", "flow");
  const caseCard = h("div", "flow-case");
  const list = h("nav", "flow-list");
  list.setAttribute("aria-label", "Workflow");
  box.append(caseCard, list);
  el.append(box);

  const mark = (s: State, v: (typeof VIEWS)[number]): [string, string] => {
    if (!v.needsRun) return ["", ""];
    if (v.id === "working" && (s.case?.bus.length ?? 0) > TEACH_MAX) return [`Up to ${TEACH_MAX} buses`, "locked"];
    if (!s.results) return ["Run first", "locked"];
    return isStale(s) ? ["Out of date", "stale"] : ["Ready", "ok"];
  };

  const paint = (s: State) => {
    const c = s.case;
    const [sol, cls] = !s.results ? ["Not solved yet", "locked"]
      : isStale(s) ? ["Results out of date", "stale"] : ["Solved", "ok"];
    caseCard.replaceChildren(h("div", "cname", c ? c.name : "No case"),
      h("div", "cmeta", c ? `${c.bus.length} buses, ${c.lines.length} branches` : ""),
      h("div", `cstat ${cls}`, sol));
    const active = viewOf(s.activeDoc)?.view.id;
    list.replaceChildren(...VIEWS.map((v, i) => {
      const [txt, mcls] = mark(s, v);
      const b = h("button", `flow-item${v.id === active ? " on" : ""}${mcls === "locked" ? " locked" : ""}`);
      b.type = "button";
      if (v.id === active) b.setAttribute("aria-current", "page");
      b.append(h("span", "num", String(i + 1)),
        (() => {
          const t = h("span", "txt");
          t.append(h("span", "lbl", v.label), h("span", "hint", v.hint));
          return t;
        })(),
        h("span", `mark ${mcls}`, txt));
      b.addEventListener("click", () => navigateView(v.id));
      return b;
    }));
  };
  subscribe(paint);
  paint(getState());
}

// ---- props -------------------------------------------------------------

// Properties panel: a grouped property grid (label left, input right, unit
// suffix). Edits change the case, so results go STALE until the next Run.

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
  i.defaultValue = typeof value === "number" ? String(+value.toFixed(digits)) : "";
  i.addEventListener("change", () => {
    const v = Number(i.value.trim());
    if (i.value.trim() === "" || !Number.isFinite(v)) {
      i.classList.add("bad");
      i.title = "Enter a number.";
      return;
    }
    i.classList.remove("bad");
    i.defaultValue = i.value;
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

function labelledSelect(options: [string, string][], value: string, commit: (v: string) => void): HTMLSelectElement {
  const s = h("select");
  for (const [v, t] of options) s.append(new Option(t, v, false, v === value));
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

function editSettings(c: CaseData, patch: Partial<Settings>): void {
  setState({ case: { ...c, settings: { ...c.settings, ...patch } } });
}
/** The case as it is now: panel inputs may outlive the case they were built
 *  from (the panel is not rebuilt while a field has focus). */
const cur = (c: CaseData): CaseData => getState().case ?? c;

function actionBtn(label: string, fn: () => void, danger = false): HTMLElement {
  const b = h("button", `pbtn${danger ? " danger" : ""}`, label);
  b.type = "button";
  b.addEventListener("click", fn);
  return b;
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
      (v) => editSettings(cur(c), { method: v }))),
    row("Tolerance", numInput(st.tol, (v) => editSettings(cur(c), { tol: v }), 12), "pu"),
    row("Base", numInput(st.base, (v) => editSettings(cur(c), { base: v }), 2), "MVA"),
    row("V min", numInput(st.vmin, (v) => editSettings(cur(c), { vmin: v }), 3), "pu"),
    row("V max", numInput(st.vmax, (v) => editSettings(cur(c), { vmax: v }), 3), "pu"),
    row("Data units", labelledSelect([["pu", "Per unit"], ["actual", "MW, kV, Ω"]], st.units ?? "pu",
      (v) => editSettings(cur(c), { units: v as Settings["units"] }))),
    row("Frequency", numInput(st.freq ?? 50, (v) => editSettings(cur(c), { freq: v }), 0), "Hz"));
  const [g3, b3] = group("Advanced", false);
  b3.append(
    row("Generator Q limits", checkInput(st.qlim, (v) => editSettings(cur(c), { qlim: v }))),
    row("Transformer taps", checkInput(st.taps, (v) => editSettings(cur(c), { taps: v }))),
    row("Bus shunts", checkInput(st.shunts, (v) => editSettings(cur(c), { shunts: v }))),
    row("Initial guess", labelledSelect([["flat", "Flat (1∠0°)"], ["setpoint", "Set-points"]],
      st.init ?? "flat", (v) => editSettings(cur(c), { init: v }))),
    row("Auto fallback", checkInput(st.fallback ?? true, (v) => editSettings(cur(c), { fallback: v }))));
  const acts = h("div", "pacts");
  acts.append(actionBtn("+ Add bus", () => addBus(cur(c))), actionBtn("+ Add line", () => addLine(cur(c))));
  box.append(g1, g2, g3, acts, h("div", "empty", "Pick a bus or line above, or click it on the diagram, to edit it."));
  return box;
}

function busPanel(c: CaseData, i: number, s: State): HTMLElement {
  const b = c.bus[i] ?? {};
  const box = h("div", "props");
  const [g, body] = group(`Bus ${i + 1}`);
  const ed = (k: string) => (v: number) => editBus(cur(c), i, { [k]: v });
  body.append(
    row("Type", selectInput(["Slack", "PV", "PQ"], String(b.Type ?? "PQ"), (v) => editBus(cur(c), i, { Type: v }))),
    row("V setpoint", numInput(b.V, ed("V")), "pu"),
    row("Pg", numInput(b.Pg, ed("Pg")), "pu"),
    row("Qg", numInput(b.Qg, ed("Qg")), "pu"),
    row("Pd", numInput(b.Pd, ed("Pd")), "pu"),
    row("Qd", numInput(b.Qd, ed("Qd")), "pu"),
    row("Shunt Bs", numInput(b.Bs ?? 0, ed("Bs")), "pu"));
  box.append(g);
  const acts = h("div", "pacts");
  acts.append(actionBtn(`Delete bus ${i + 1}`, () => delBus(cur(c), i), true));
  box.append(acts);
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
  const [g, body] = group(`${l.Kind === "trafo" ? "Transformer" : "Line"} ${l.From}-${l.To}`);
  const ed = (k: string) => (v: number) => editLine(cur(c), i, { [k]: v });
  body.append(
    row("From bus", numInput(l.From, ed("From"), 0)),
    row("To bus", numInput(l.To, ed("To"), 0)),
    row("R", numInput(l.R, ed("R")), "pu"),
    row("X", numInput(l.X, ed("X")), "pu"),
    row("B charging", numInput(l.B, ed("B")), "pu"),
    row("Tap", numInput(l.Tap ?? 1, ed("Tap"), 3), "ratio"),
    row("Kind", selectInput(["line", "trafo"], l.Kind === "trafo" ? "trafo" : "line",
      (v) => editLine(cur(c), i, { Kind: v }))));
  box.append(g);
  const acts = h("div", "pacts");
  acts.append(actionBtn(`Delete line ${l.From}-${l.To}`, () => delLine(cur(c), i), true));
  box.append(acts);
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

/** "Edit:" selector: Project, any bus or any line, for use without the mouse. */
function editPicker(c: CaseData, sel: State["selection"]): HTMLElement {
  const r = h("label", "pedit");
  const opts: [string, string][] = [["project", "Project settings"]];
  c.bus.forEach((b, i) => opts.push([`bus:${i}`, `Bus ${i + 1}${b.Type ? `  (${String(b.Type)})` : ""}`]));
  c.lines.forEach((l, i) => opts.push([`branch:${i}`, `Line ${l.From}-${l.To}`]));
  const s = h("select");
  for (const [v, t] of opts) s.append(new Option(t, v, false, v === (sel ? `${sel.kind}:${sel.index}` : "project")));
  s.addEventListener("change", () => {
    if (s.value === "project") setState({ selection: null });
    else {
      const [kind, i] = s.value.split(":");
      setState({ selection: { kind: kind as "bus" | "branch", index: Number(i) } });
    }
  });
  r.append(h("span", "pl", "Edit"), s);
  return r;
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
  box.prepend(editPicker(c, sel));
  if (stale) {
    box.classList.add("stale");
    box.append(h("div", "empty", "Results are stale: press Run (F5)."));
  }
  el.replaceChildren(box);
}

export { getState };

// ---- output ------------------------------------------------------------

// Output panel: the message log. Collapsed to one line by default (the latest
// message stays visible); it opens when you click it or when something goes
// wrong. Reports and the N-1 table live in their own views.
const OUT_KEY = "gridlens.out.open";

function messages(s: State): HTMLElement[] {
  if (!s.messages.length) return [h("div", "empty", "No messages yet.")];
  return s.messages.map((m) => {
    const d = h("div", `msg ${m.level}`);
    d.append(h("span", "t", m.t), document.createTextNode(m.text));
    return d;
  });
}

export function mountOutput(tabs: HTMLElement, body: HTMLElement): void {
  const root = tabs.closest(".ws") as HTMLElement | null;
  let open = false;
  try {
    open = localStorage.getItem(OUT_KEY) === "1";
  } catch {
    /* ignore */
  }
  const title = h("div", "tab active", "Messages");
  title.setAttribute("role", "tab");
  const last = h("div", "out-last");
  const toggle = h("button", "out-toggle", "");
  toggle.type = "button";
  const clear = h("button", "out-toggle", "Clear");
  clear.type = "button";
  clear.title = "Empty the message log";
  clear.addEventListener("click", (e) => { e.stopPropagation(); clearMessages(); });
  tabs.append(title, last, clear, toggle);
  const apply = () => {
    root?.classList.toggle("out-collapsed", !open);
    toggle.textContent = open ? "Hide ▾" : "Show ▴";
    toggle.title = open ? "Collapse the message log" : "Open the message log";
    try {
      localStorage.setItem(OUT_KEY, open ? "1" : "0");
    } catch {
      /* ignore */
    }
  };
  const set = (v: boolean) => { open = v; apply(); };
  toggle.addEventListener("click", () => set(!open));
  tabs.addEventListener("click", (e) => { if (e.target === tabs || e.target === last) set(!open); });
  apply();

  let shown = -1;
  const paint = (s: State) => {
    const m = s.messages[s.messages.length - 1];
    last.textContent = m ? `${m.t}  ${m.text}` : "";
    last.className = `out-last ${m?.level ?? ""}`;
    if (s.messages.length === shown) return;
    const first = shown < 0;
    shown = s.messages.length;
    body.replaceChildren(...messages(s));
    body.scrollTop = body.scrollHeight;
    if (!first && m?.level === "error" && !open) set(true);
  };
  subscribe(paint);
  paint(getState());
}

