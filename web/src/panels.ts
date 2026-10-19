// Panels: project tree, properties, output.
// Sections follow the order of the files this one replaced; search for '// ----'.
import { getState, isStale, navigate, setState, subscribe, type CaseData, type Rec, type Settings, type State } from "./app";
import { ICON, h, table } from "./ui";

// ---- tree --------------------------------------------------------------

// Project tree: Project › Case › Buses · Branches · Studies · Worked
// solution · Calculators. Chevrons or Left/Right expand and collapse,
// Up/Down move, Enter (or click) opens a study or selects a bus/branch.

interface Node {
  key: string;
  label: string;
  icon: string;
  count?: number;
  doc?: string;
  sel?: { kind: "bus" | "branch"; index: number };
  children?: Node[];
}

const GROUPS: [string, string, [string, string][]][] = [
  ["studies", "Studies", [["load-flow", "Load flow"], ["solver-check", "Solver check"],
    ["contingency", "Contingency N-1"], ["pv-analysis", "PV analysis"],
    ["fault-levels", "Fault levels"], ["faults", "Unsymmetrical faults"], ["report", "Report"]]],
  ["worked", "Worked solution", [["ybus", "Ybus matrix"], ["iterations", "Iterations"],
    ["answer", "Worked answer"]]],
  ["calc", "Calculators", [["symmetrical", "Symmetrical components"], ["line", "Line parameters"],
    ["dispatch", "Economic dispatch"]]],
];

function model(s: State): Node {
  const c = s.case;
  const kids: Node[] = [{ key: "doc:canvas", label: "One-line diagram", icon: ICON.doc, doc: "canvas" }];
  if (c) {
    kids.push(
      { key: "buses", label: "Buses", icon: ICON.folder, count: c.bus.length,
        children: c.bus.map((b, i) => ({ key: `bus:${i}`, icon: ICON.bus,
          label: b.Type ? `Bus ${i + 1}  ${String(b.Type)}` : `Bus ${i + 1}`,
          sel: { kind: "bus" as const, index: i } })) },
      { key: "branches", label: "Branches", icon: ICON.folder, count: c.lines.length,
        children: c.lines.map((l, i) => ({ key: `branch:${i}`, label: `Line ${l.From}-${l.To}`,
          icon: ICON.branch, sel: { kind: "branch" as const, index: i } })) });
  }
  for (const [key, label, docs] of GROUPS) {
    kids.push({ key, label, icon: key === "calc" ? ICON.calc : ICON.folder,
      children: docs.map(([doc, l]) => ({ key: `doc:${doc}`, label: l,
        icon: key === "calc" ? ICON.calc : key === "studies" ? ICON.study : ICON.doc, doc })) });
  }
  return { key: "project", label: "Project", icon: ICON.project, children: [
    { key: "case", label: c ? `Case: ${c.name}` : "Case: (none)", icon: ICON.case, children: kids }] };
}

const OPEN_KEY = "gridlens.tree.open";
function loadOpen(): Set<string> {
  try {
    const v = JSON.parse(localStorage.getItem(OPEN_KEY) ?? "null") as string[] | null;
    if (v) return new Set(v);
  } catch {
    /* ignore */
  }
  return new Set(["project", "case", "studies", "worked", "calc"]);
}

interface Row { node: Node; level: number; parent: string | null }

export function mountTree(el: HTMLElement): void {
  const open = loadOpen();
  const box = h("div", "tree");
  box.tabIndex = 0;
  box.setAttribute("role", "tree");
  box.setAttribute("aria-label", "Project");
  el.append(box);
  let rows: Row[] = [];
  let focus = "case";

  const saveOpen = () => {
    try {
      localStorage.setItem(OPEN_KEY, JSON.stringify([...open]));
    } catch {
      /* ignore */
    }
  };

  const activate = (n: Node) => {
    focus = n.key;
    if (n.doc) navigate(n.doc);
    else if (n.sel) setState({ selection: n.sel });
    else if (n.children) toggle(n.key);
    paint(getState());
  };

  const toggle = (key: string, to?: boolean) => {
    const want = to ?? !open.has(key);
    if (want) open.add(key);
    else open.delete(key);
    saveOpen();
    paint(getState());
  };

  const isSelected = (n: Node, s: State) =>
    (n.doc !== undefined && n.doc === s.activeDoc) ||
    (n.sel !== undefined && s.selection?.kind === n.sel.kind && s.selection.index === n.sel.index);

  const paint = (s: State) => {
    rows = [];
    const walk = (n: Node, level: number, parent: string | null) => {
      rows.push({ node: n, level, parent });
      if (n.children && open.has(n.key)) for (const c of n.children) walk(c, level + 1, n.key);
    };
    walk(model(s), 0, null);
    if (!rows.some((r) => r.node.key === focus)) focus = rows[0]?.node.key ?? "";
    const ul = h("ul");
    for (const { node: n, level } of rows) {
      const li = h("li");
      li.setAttribute("role", "treeitem");
      li.id = `tree-${n.key.replace(/[^\w-]/g, "_")}`;
      if (n.children) li.setAttribute("aria-expanded", String(open.has(n.key)));
      const row = h("div", "row");
      row.style.paddingLeft = `${4 + level * 12}px`;
      row.classList.toggle("sel", isSelected(n, s));
      row.classList.toggle("focus", n.key === focus && document.activeElement === box);
      row.dataset.key = n.key;
      const chev = h("span", `chev${n.children && open.has(n.key) ? " open" : ""}`);
      if (n.children) {
        chev.innerHTML = ICON.chev;
        chev.addEventListener("click", (e) => {
          e.stopPropagation();
          focus = n.key;
          toggle(n.key);
        });
      }
      const ico = h("span", "ico");
      ico.innerHTML = n.icon;
      row.append(chev, ico, h("span", "", n.label));
      if (n.count !== undefined) row.append(h("span", "count", String(n.count)));
      row.addEventListener("click", () => activate(n));
      li.append(row);
      ul.append(li);
      if (n.key === focus) box.setAttribute("aria-activedescendant", li.id);
    }
    box.replaceChildren(ul);
    box.querySelector(".row.focus")?.scrollIntoView({ block: "nearest" });
  };

  box.addEventListener("keydown", (e) => {
    const i = rows.findIndex((r) => r.node.key === focus);
    const cur = rows[i];
    if (!cur) return;
    const n = cur.node;
    const move = (j: number) => {
      const r = rows[Math.max(0, Math.min(rows.length - 1, j))];
      if (r) focus = r.node.key;
      paint(getState());
    };
    switch (e.key) {
      case "ArrowDown": move(i + 1); break;
      case "ArrowUp": move(i - 1); break;
      case "Home": move(0); break;
      case "End": move(rows.length - 1); break;
      case "ArrowRight":
        if (n.children && !open.has(n.key)) toggle(n.key, true);
        else if (n.children) move(i + 1);
        break;
      case "ArrowLeft":
        if (n.children && open.has(n.key)) toggle(n.key, false);
        else if (cur.parent) {
          focus = cur.parent;
          paint(getState());
        }
        break;
      case "Enter": case " ": activate(n); break;
      default: return;
    }
    e.preventDefault();
  });
  // focus only toggles the ring: rebuilding the rows here would detach the
  // element under the pointer between mousedown and click
  const ring = () => box.querySelectorAll<HTMLElement>(".row").forEach((r) =>
    r.classList.toggle("focus", r.dataset.key === focus && document.activeElement === box));
  box.addEventListener("focus", ring);
  box.addEventListener("blur", ring);
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

// ---- output ------------------------------------------------------------

// Output panel (PSCAD's output window): Messages, Bus report, Branch report,
// Solver check and N-1. Clicking an N-1 row shows that outage on the diagram.

const TABS = ["Messages", "Bus report", "Branch report", "Solver check", "N-1"] as const;
type Tab = (typeof TABS)[number];
let active: Tab = "Messages";

function messages(s: State): HTMLElement[] {
  if (!s.messages.length) return [h("div", "empty", "No messages yet.")];
  return s.messages.map((m) => {
    const d = h("div", `msg ${m.level}`);
    d.append(h("span", "t", m.t), document.createTextNode(m.text));
    return d;
  });
}

function fresh(s: State) {
  return s.results && !isStale(s) ? s.results : null;
}

const note = (t: string) => [h("div", "empty", t)];

function busReport(s: State): HTMLElement[] {
  const r = fresh(s);
  if (!r || !s.case) return note("Press Run (F5) to fill this table.");
  const rows: Rec[] = r.res.map((x, i) => {
    const b = s.case!.bus[i] ?? {};
    const v = Number(x["V (pu)"]);
    return {
      Bus: x.Bus, Type: b.Type, "V (pu)": v, "Angle (deg)": x["Angle (deg)"],
      "P inj (MW)": Number(x.P_inj) * r.base, "Q inj (MVAr)": Number(x.Q_inj) * r.base,
      "P load (MW)": Number(b.Pd) * r.base, "Q load (MVAr)": Number(b.Qd) * r.base,
      Status: v < r.vmin ? "LOW V" : v > r.vmax ? "HIGH V" : "ok",
    };
  });
  return [table(rows, { digits: { "Angle (deg)": 3, "P inj (MW)": 2, "Q inj (MVAr)": 2,
    "P load (MW)": 1, "Q load (MVAr)": 1 }, bad: (x) => x.Status !== "ok" })];
}

function branchReport(s: State): HTMLElement[] {
  const r = fresh(s);
  if (!r) return note("Press Run (F5) to fill this table.");
  const rows: Rec[] = r.flows.map((f) => ({
    From: f.From, To: f.To, "P from (MW)": Number(f.P_ij) * r.base, "Q from (MVAr)": Number(f.Q_ij) * r.base,
    "P to (MW)": Number(f.P_ji) * r.base, "Q to (MVAr)": Number(f.Q_ji) * r.base,
    "Loss (MW)": Number(f.Loss_P) * r.base, "Loss (MVAr)": Number(f.Loss_Q) * r.base,
  }));
  return [table(rows, { digits: Object.fromEntries(Object.keys(rows[0] ?? {}).map((k) => [k, 2])) })];
}

function solverCheck(s: State): HTMLElement[] {
  const r = fresh(s);
  if (!r) return note("Press Run (F5) to fill this table.");
  return [table(r.cmp)];
}

function n1(s: State): HTMLElement[] {
  const r = fresh(s);
  if (!r || !s.case) return note("Press Run (F5) to fill this table.");
  const t = table(r.n1, { bad: (x) => Number(x.Violations) > 0 || x.Status !== "OK" });
  const lines = s.case.lines.map((l) => `${l.From}-${l.To}`);
  const trs = Array.from(t.querySelectorAll("tr")).slice(1);
  trs.forEach((tr, i) => {
    const k = lines.indexOf(String(r.n1[i]?.Outage));
    if (k < 0) return;
    tr.classList.add("click");
    if (s.outage === k) tr.classList.add("on");
    tr.title = "Show this outage on the diagram";
    tr.addEventListener("click", () => {
      setState({ outage: s.outage === k ? null : k });
      navigate("canvas");
    });
  });
  const cap = h("div", "empty", s.outage !== null
    ? `Showing the outage of line ${lines[s.outage]} on the diagram. Click the row again to clear.`
    : "Click a row to show that outage on the diagram.");
  return [cap, t];
}

const BODY: Record<Tab, (s: State) => HTMLElement[]> = {
  Messages: messages, "Bus report": busReport, "Branch report": branchReport,
  "Solver check": solverCheck, "N-1": n1,
};

export function mountOutput(tabs: HTMLElement, body: HTMLElement): void {
  const els = new Map<Tab, HTMLElement>();
  for (const t of TABS) {
    const el = h("div", "tab", t);
    el.setAttribute("role", "tab");
    el.tabIndex = 0;
    const pick = () => {
      active = t;
      paint(getState(), true);
    };
    el.addEventListener("click", pick);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") pick();
    });
    els.set(t, el);
    tabs.append(el);
  }
  let shown = "";
  const paint = (s: State, force = false) => {
    for (const [t, el] of els) {
      el.classList.toggle("active", t === active);
      el.setAttribute("aria-selected", String(t === active));
    }
    const key = JSON.stringify([active, s.messages.length, s.solvedSig, isStale(s), s.outage,
      active === "Bus report" || active === "Branch report" ? s.case?.bus.length : 0]);
    if (!force && key === shown) return;
    shown = key;
    const top = body.scrollTop;
    body.replaceChildren(...BODY[active](s));
    body.scrollTop = active === "Messages" ? body.scrollHeight : top;
  };
  subscribe((s) => paint(s));
  paint(getState());
}
