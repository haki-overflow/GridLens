// Workspace shell: layout, splitters, tabs, toolbar, title/status.
// Sections follow the order of the files this one replaced; search for '// ----'.
import { VIEWS, canRedo, canUndo, currentJob, exportProject, importCaseFiles, jobText, newCase, navigateView, viewOf, getState, isStale, loadPreset, navigate, onJob, presets, redo, report, reset, run, stop, subscribe, undo, type NewCase, type State } from "./app";
import { openWizard } from "./documents";
import { mountOutput, paintProps } from "./panels";
import { ICON, editingText, h } from "./ui";

// ---- shell -------------------------------------------------------------

// Builds the workspace skeleton (CSS grid) and returns its parts.

export interface Shell {
  root: HTMLElement;
  readouts: HTMLElement;
  tools: HTMLElement;
  busy: HTMLElement;
  tree: HTMLElement;
  tabs: HTMLElement;
  hint: HTMLElement;
  docs: HTMLElement;
  outTabs: HTMLElement;
  out: HTMLElement;
  props: HTMLElement;
  status: HTMLElement;
}


function panel(cls: string, title: string): [HTMLElement, HTMLElement] {
  const p = h("section", `panel ${cls}`);
  const head = h("div", "panel-head", title);
  const body = h("div", "panel-body");
  p.append(head, body);
  return [p, body];
}

export function buildShell(app: HTMLElement): Shell {
  const root = h("div", "ws");
  const title = h("header", "ws-title");
  const readouts = h("div", "read");
  const brand = h("div", "brand", "GRIDLENS");
  brand.append(h("span", "ver", " v2.8"));
  title.append(brand, readouts);
  const tools = h("nav", "ws-tools");
  tools.setAttribute("aria-label", "Toolbar");
  const busy = h("div", "ws-busy");
  busy.setAttribute("aria-hidden", "true");
  const [treeP, tree] = panel("ws-tree", "Workflow");
  const splitL = h("div", "ws-split-l");
  const splitR = h("div", "ws-split-r");
  const [propsP, props] = panel("ws-props", "Properties");

  const centre = h("main", "ws-centre");
  const tabs = h("div", "tabs");
  tabs.setAttribute("role", "tablist");
  const hint = h("div", "nexthint");
  hint.hidden = true;
  const docs = h("div", "docs");
  const splitO = h("div", "ws-split-o");
  const output = h("section", "output");
  const outTabs = h("div", "out-tabs");
  const out = h("div", "out-body");
  output.append(outTabs, out);
  centre.append(tabs, hint, docs, splitO, output);

  const status = h("footer", "ws-status");
  root.append(title, tools, busy, treeP, splitL, centre, splitR, propsP, status);
  app.replaceChildren(root);

  initSplitters(root, [
    { el: splitL, cssVar: "--tree-w", axis: "x", def: 250, min: 200,
      max: () => Math.min(460, window.innerWidth * 0.35), sign: 1 },
    { el: splitR, cssVar: "--props-w", axis: "x", def: 280, min: 180,
      max: () => Math.min(520, window.innerWidth * 0.4), sign: -1 },
    { el: splitO, cssVar: "--out-h", axis: "y", def: 240, min: 60,
      max: () => (window.innerHeight - 28 - 32 - 22) * 0.7, sign: -1 },
  ]);
  return { root, readouts, tools, busy, tree, tabs, hint, docs, outTabs, out, props, status };
}

// ---- splitters ---------------------------------------------------------

// Pointer-drag splitters. Each one drives a CSS variable on the workspace
// root (px), clamped to [min, max]; sizes persist in localStorage and a
// double-click restores the default.
export interface SplitSpec {
  el: HTMLElement;
  cssVar: string; // e.g. "--tree-w"
  axis: "x" | "y";
  def: number;
  min: number;
  max: () => number;
  sign: 1 | -1; // +1: dragging right/down grows the panel
}

const KEY = "gridlens.splits";

function load(): Record<string, number> {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Record<string, number>;
  } catch {
    return {};
  }
}

function save(all: Record<string, number>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(all));
  } catch {
    /* storage blocked: sizes just won't persist */
  }
}

export function initSplitters(root: HTMLElement, specs: SplitSpec[]): void {
  const sizes = load();
  const clamp = (s: SplitSpec, v: number) => Math.round(Math.min(Math.max(v, s.min), Math.max(s.min, s.max())));
  const apply = (s: SplitSpec, v: number) => {
    const c = clamp(s, v);
    root.style.setProperty(s.cssVar, `${c}px`);
    return c;
  };
  for (const s of specs) {
    apply(s, sizes[s.cssVar] ?? s.def);
    s.el.classList.add("split", s.axis === "x" ? "v" : "h");
    s.el.setAttribute("role", "separator");
    s.el.setAttribute("aria-orientation", s.axis === "x" ? "vertical" : "horizontal");
    s.el.title = "Drag to resize, double-click to reset";
    s.el.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      s.el.setPointerCapture(e.pointerId);
      const start = s.axis === "x" ? e.clientX : e.clientY;
      const from = parseFloat(getComputedStyle(root).getPropertyValue(s.cssVar)) || s.def;
      s.el.classList.add("drag");
      document.body.classList.add("dragging", s.axis === "x" ? "v" : "h");
      const move = (ev: PointerEvent) => {
        const pos = s.axis === "x" ? ev.clientX : ev.clientY;
        sizes[s.cssVar] = apply(s, from + s.sign * (pos - start));
      };
      const up = () => {
        s.el.removeEventListener("pointermove", move);
        s.el.classList.remove("drag");
        document.body.classList.remove("dragging", "v", "h");
        save(sizes);
      };
      s.el.addEventListener("pointermove", move);
      s.el.addEventListener("pointerup", up, { once: true });
      s.el.addEventListener("pointercancel", up, { once: true });
    });
    s.el.addEventListener("dblclick", () => {
      delete sizes[s.cssVar];
      apply(s, s.def);
      save(sizes);
    });
  }
  window.addEventListener("resize", () => {
    for (const s of specs) {
      const cur = parseFloat(root.style.getPropertyValue(s.cssVar)) || s.def;
      apply(s, cur);
    }
  });
}

// ---- tabs --------------------------------------------------------------

// Multi-document tab strip. Every open document stays mounted (hidden when
// inactive) so switching tabs never blanks or re-fetches a view; the switch
// is an opacity fade only.

export interface DocDef {
  id: string;
  title: string;
  flush?: boolean; // no padding / no scroll (canvas)
  mount: (el: HTMLElement) => void;
}

export class DocTabs {
  private panes = new Map<string, HTMLElement>();
  active = "";

  constructor(
    private strip: HTMLElement,
    private host: HTMLElement,
    private lookup: (id: string) => DocDef,
    private onChange: (open: string[], active: string) => void = () => {},
  ) {}

  show(id: string): void {
    if (!this.panes.has(id)) {
      const def = this.lookup(id);
      const pane = h("div", `doc${def.flush ? " flush" : ""}`);
      pane.setAttribute("role", "tabpanel");
      pane.dataset.doc = id;
      this.host.append(pane);
      this.panes.set(id, pane);
      def.mount(pane);
    }
    this.active = id;
    for (const [k, p] of this.panes) p.classList.toggle("active", k === id);
    this.paint();
  }

  ids(): string[] {
    return [...this.panes.keys()];
  }

  /** Sub-tabs of the view the active document belongs to (hidden when the
   *  view has only one). */
  private paint(): void {
    const v = viewOf(this.active);
    const subs = v?.view.subs ?? [];
    this.strip.hidden = subs.length < 2;
    this.strip.replaceChildren(...subs.map((s) => {
      const t = h("div", `tab${s.doc === this.active ? " active" : ""}`, s.label);
      t.setAttribute("role", "tab");
      t.setAttribute("aria-selected", String(s.doc === this.active));
      t.tabIndex = 0;
      t.dataset.doc = s.doc;
      t.addEventListener("click", () => navigate(s.doc));
      t.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") navigate(s.doc);
      });
      return t;
    }));
    this.onChange(this.ids(), this.active);
  }
}

// ---- toolbar -----------------------------------------------------------

// Toolbar: Run (F5; Stop and the progress while a study runs) + STALE ·
// Reset · Case [preset, Import, Export] · View [Fit (Ctrl+0), Grid, Flows,
// Angles] · Report.

function btn(icon: string, label: string, title: string, testid?: string): HTMLButtonElement {
  const b = h("button", "tb-btn");
  b.type = "button";
  b.innerHTML = `${icon}<span>${label}</span>`;
  b.title = title;
  if (testid) b.dataset.testid = testid;
  return b;
}

function group(...els: HTMLElement[]): HTMLElement {
  const g = h("div", "tb-group");
  g.append(...els);
  return g;
}

export function fitCanvas(): void {
  window.dispatchEvent(new CustomEvent("gl:fit"));
}

/** A small dropdown menu button: items = [label, action, disabled?]; an item
 *  with no action is a section heading. Closes on outside click, Escape or
 *  after choosing. */
type MenuItem = [string, (() => void) | null, boolean?];
function menu(label: string, title: string, items: () => MenuItem[]): HTMLElement {
  const wrap = h("div", "tb-menu");
  const b = btn(ICON.open, label, title);
  b.append(h("span", "caret", "▾"));
  const pop = h("div", "tb-pop");
  pop.hidden = true;
  pop.setAttribute("role", "menu");
  const close = () => { pop.hidden = true; b.setAttribute("aria-expanded", "false"); };
  b.setAttribute("aria-haspopup", "menu");
  b.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!pop.hidden) { close(); return; }
    pop.replaceChildren(...items().map(([text, act, off]) => {
      if (!act) return h("div", "tb-sec", text);
      const it = h("button", "tb-item", text);
      it.type = "button";
      it.disabled = !!off;
      it.setAttribute("role", "menuitem");
      it.addEventListener("click", () => { close(); act(); });
      return it;
    }));
    pop.hidden = false;
    b.setAttribute("aria-expanded", "true");
  });
  document.addEventListener("click", close);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  wrap.append(b, pop);
  return wrap;
}

/** Hidden file picker for every case format; opens importCaseFiles. */
export function casePicker(): HTMLInputElement {
  const file = h("input");
  file.type = "file";
  file.multiple = true;
  file.accept = ".json,.m,.cdf,.txt,.csv";
  file.hidden = true;
  file.addEventListener("change", async () => {
    const files = [...(file.files ?? [])];
    file.value = "";
    if (files.length) await importCaseFiles(files).catch((e) => report(e, `Opening ${files[0]!.name}`));
  });
  return file;
}

export function mountToolbar(bar: HTMLElement): void {
  const runB = btn(ICON.run, "Run", "Run the load flow and every study (F5)", "run");
  runB.classList.add("primary");
  const jobL = h("span", "tb-job");
  jobL.setAttribute("aria-live", "polite");
  const stale = h("span", "badge stale", "STALE");
  stale.title = "The case changed since the last run";
  const resetB = btn(ICON.reset, "Reset", "Clear the results (an example is reloaded)");

  const file = casePicker();
  let examples: string[] = [];
  presets().then((n) => { examples = n; }).catch((e) => report(e, "Listing examples"));
  const fileMenu = menu("File", "New case, open, import, examples, save", () => [
    ["New case...", () => openNewCase()],
    ["Open or import a file...", () => file.click()],
    ["Enter textbook data (MVA, kV, ohm)...", () => void openWizard()],
    ["Save project (.gridlens.json)", exportProject, !getState().case],
    ["Download results (.zip)", () => navigate("report"), !getState().results],
    ["Examples", null],
    ...examples.map((n): MenuItem => [n, () => void loadPreset(n)]),
  ]);
  const caseName = h("span", "tb-case");

  const undoB = btn(ICON.undo, "Undo", "Undo the last change to the case (Ctrl+Z)", "undo");
  const redoB = btn(ICON.redo, "Redo", "Redo (Ctrl+Shift+Z or Ctrl+Y)", "redo");
  undoB.addEventListener("click", undo);
  redoB.addEventListener("click", redo);

  bar.append(group(runB, jobL, stale, resetB), group(undoB, redoB), group(fileMenu, file, caseName));

  runB.addEventListener("click", () => void (currentJob() ? stop() : run()));
  onJob((j) => {
    runB.innerHTML = j ? `${ICON.stop}<span>Stop</span>` : `${ICON.run}<span>Run</span>`;
    runB.title = j ? "Stop the running study (the last results stay)" : "Run the load flow and every study (F5)";
    jobL.textContent = j ? jobText(j) : "";
    jobL.hidden = !j;
  });
  jobL.hidden = true;
  resetB.addEventListener("click", () => void reset());

  window.addEventListener("keydown", (e) => {
    if (e.key === "F5") {
      e.preventDefault();
      void run();
    } else if ((e.ctrlKey || e.metaKey) && e.key === "0") {
      e.preventDefault();
      navigate("canvas");
      fitCanvas();
    } else if ((e.ctrlKey || e.metaKey) && !e.altKey && !editingText(e) && /^[zy]$/i.test(e.key)) {
      // a field with freshly typed text keeps its own undo
      e.preventDefault();
      if (e.key.toLowerCase() === "y" || e.shiftKey) redo();
      else undo();
    }
  });

  const paint = () => {
    const s = getState();
    stale.hidden = !isStale(s);
    runB.disabled = !s.case;
    undoB.disabled = !canUndo();
    redoB.disabled = !canRedo();
    caseName.textContent = s.case ? s.case.name : "";
  };
  subscribe(paint);
  paint();
}

// ---- new case dialog ---------------------------------------------------

/** File > New case: name, base MVA, frequency, input units, and whether to
 *  start on the diagram or in the tables. */
export function openNewCase(): void {
  const dlg = h("dialog", "wizard newcase");
  const field = (label: string, input: HTMLElement, hint = "") => {
    const r = h("label", "nc-row");
    r.append(h("span", "nc-l", label), input, h("span", "nc-h", hint));
    return r;
  };
  const num = (v: number) => Object.assign(h("input"), { type: "number", value: String(v), step: "any" });
  const name = Object.assign(h("input"), { value: "New network" });
  const base = num(100), freq = h("select"), units = h("select"), start = h("select");
  freq.append(new Option("50 Hz", "50"), new Option("60 Hz", "60"));
  units.append(new Option("Per unit on the system base", "pu"),
    new Option("Actual: MW, MVAr, kV, ohm, uS", "actual"));
  start.append(new Option("Draw it on the diagram", "draw"), new Option("Fill in the tables", "tables"));
  const ok = h("button", "btn primary", "Create");
  const cancel = h("button", "btn", "Cancel");
  const row = h("div", "wz-btns");
  row.append(cancel, ok);
  dlg.append(h("div", "wz-title", "New case"),
    field("Name", name),
    field("System base", base, "MVA"),
    field("Frequency", freq),
    field("Data units", units, "Actual units are converted with each bus's base kV."),
    field("Start by", start), row);
  document.body.append(dlg);
  const close = () => { dlg.close(); dlg.remove(); };
  cancel.addEventListener("click", close);
  dlg.addEventListener("cancel", close);
  ok.addEventListener("click", () => {
    const b = Number(base.value);
    if (!(b > 0)) {
      base.classList.add("bad");
      base.focus();
      return;
    }
    close();
    newCase({ name: name.value.trim() || "New network", base: b, freq: Number(freq.value),
              units: units.value as NewCase["units"], start: start.value as NewCase["start"] });
  });
  dlg.showModal();
  name.select();
}

// ---- chrome ------------------------------------------------------------

// Title readouts, status bar, Messages panel and Properties panel, all
// drawn from the project state.

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
      `<div class="fill"><b>Status</b>${currentJob() ? "Study running" : sol === "SOLVED" ? "Converged"
        : sol === "STALE" ? "Stale: press Run (F5)" : r ? "Not converged" : "Ready"}</div>` +
      `<div class="file">${esc(s.fileName)}</div>`;

    paintProps(props, s);
  };
  subscribe(paint);
  onJobChange(() => paint(getState()));
  paint(getState());
}

// ---- start and hints ---------------------------------------------------

/** First-run welcome: ways to begin. Hidden once a case was chosen. */
export function mountStart(host: HTMLElement): void {
  const box = h("div", "start");
  const file = casePicker();
  const examples = h("div", "start-btns");
  const card = (title: string, text: string, ...btns: HTMLElement[]) => {
    const c = h("div", "start-card");
    c.append(h("h3", "", title), h("p", "", text));
    const row = h("div", "start-btns");
    row.append(...btns);
    c.append(row);
    return c;
  };
  const btn = (label: string, primary = false) => h("button", `btn${primary ? " primary" : ""}`, label);
  const blank = btn("New case", true);
  blank.addEventListener("click", () => openNewCase());
  const wiz = btn("Open the form", true);
  wiz.addEventListener("click", () => void openWizard());
  const pick = btn("Choose a file", true);
  pick.addEventListener("click", () => file.click());
  presets().then((names) => {
    examples.replaceChildren(...names.map((n) => {
      const b = btn(n);
      b.addEventListener("click", () => void loadPreset(n));
      return b;
    }));
  }).catch((e) => report(e, "Listing examples"));
  box.append(
    h("h2", "", "Welcome to GridLens"),
    h("p", "start-lead", "Solve any power system: load flow, safety checks, fault currents, and the working step by step."),
    (() => {
      const row = h("div", "start-cards");
      row.append(
        card("New case", "A blank network. Set the base MVA and units, then draw it or fill in the tables.", blank),
        card("Textbook question", "Type the data as the book gives it: MVA, kV, ohms, MW.", wiz),
        card("Open a file", "A saved project, a MATPOWER case (.m), an IEEE common format file or the CSV templates.", pick, file),
        card("Examples", "Ready-made networks to explore.", examples));
      return row;
    })(),
    h("p", "start-foot", "Then press Run (F5) and follow the steps on the left."));
  host.append(box);
  const paint = (s: State) => { box.hidden = s.started; };
  subscribe(paint);
  paint(getState());
}

const NEXT: Record<string, [string, string]> = {
  network: ["Solved. Next: look at the results.", "solve"],
  solve: ["Next: check what happens if a line fails.", "safety"],
  safety: ["Next: short-circuit currents.", "faults"],
  faults: ["Next: see the maths step by step.", "working"],
  working: ["Finished? Download the results from Solve > Report and download.", "solve"],
};

/** One line under the sub-tabs that says what to do next. */
export function mountHint(el: HTMLElement): void {
  const paint = (s: State) => {
    const view = viewOf(s.activeDoc)?.view.id ?? "";
    let text = "", label = "", act: () => void = () => {};
    if (!s.started || !s.case) {
      el.hidden = true;
      return;
    }
    if (currentJob() && (!s.results || isStale(s))) {
      [text, label, act] = ["The study is running: its progress is in the toolbar, the results appear when it "
        + "finishes.", "Stop", () => void stop()];
    } else if (!s.results && !s.case.lines.length) {
      [text, label, act] = ["Draw the network with the tools on the diagram, or fill in the tables.",
        "Data tables", () => navigate("case-tables")];
    } else if (!s.results) {
      [text, label, act] = [canUndo() ? "Press Run (F5) to solve." : "Press Run (F5) to solve the case.",
        "Run", () => void run()];
    } else if (isStale(s)) {
      [text, label, act] = ["The case changed. Press Run (F5) to solve.", "Run", () => void run()];
    } else if (NEXT[view]) {
      const [t, v] = NEXT[view]!;
      [text, label, act] = [t, `Go to ${VIEWS.find((x) => x.id === v)?.label}`, () => navigateView(v)];
    } else {
      el.hidden = true;
      return;
    }
    const b = h("button", "btn", label);
    b.addEventListener("click", act);
    el.replaceChildren(h("span", "", text), b);
    el.hidden = false;
  };
  subscribe(paint);
  onJobChange(() => paint(getState()));
  paint(getState());
}

/** Call fn when a study starts or ends (not on every progress poll). */
function onJobChange(fn: () => void): void {
  let had = false;
  onJob((j) => {
    if (!!j === had) return;
    had = !!j;
    fn();
  });
}
