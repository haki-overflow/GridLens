// Workspace shell: layout, splitters, tabs, toolbar, title/status.
// Sections follow the order of the files this one replaced; search for '// ----'.
import { exportProject, viewOf, getState, importProject, isStale, loadPreset, navigate, presets, report, reset, run, setState, subscribe, type State, type View } from "./app";
import { openWizard } from "./documents";
import { mountOutput, paintProps } from "./panels";
import { ICON, h } from "./ui";

// ---- shell -------------------------------------------------------------

// Builds the workspace skeleton (CSS grid) and returns its parts.

export interface Shell {
  root: HTMLElement;
  readouts: HTMLElement;
  tools: HTMLElement;
  busy: HTMLElement;
  tree: HTMLElement;
  tabs: HTMLElement;
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
  title.append(h("div", "brand", "GRIDLENS"), readouts);
  const tools = h("nav", "ws-tools");
  tools.setAttribute("aria-label", "Toolbar");
  const busy = h("div", "ws-busy");
  busy.setAttribute("aria-hidden", "true");
  const [treeP, tree] = panel("ws-tree", "Project");
  const splitL = h("div", "ws-split-l");
  const splitR = h("div", "ws-split-r");
  const [propsP, props] = panel("ws-props", "Properties");

  const centre = h("main", "ws-centre");
  const tabs = h("div", "tabs");
  tabs.setAttribute("role", "tablist");
  const docs = h("div", "docs");
  const splitO = h("div", "");
  const output = h("section", "output");
  const outTabs = h("div", "out-tabs");
  const out = h("div", "out-body");
  output.append(outTabs, out);
  centre.append(tabs, docs, splitO, output);

  const status = h("footer", "ws-status");
  root.append(title, tools, busy, treeP, splitL, centre, splitR, propsP, status);
  app.replaceChildren(root);

  initSplitters(root, [
    { el: splitL, cssVar: "--tree-w", axis: "x", def: 220, min: 140,
      max: () => Math.min(460, window.innerWidth * 0.35), sign: 1 },
    { el: splitR, cssVar: "--props-w", axis: "x", def: 280, min: 180,
      max: () => Math.min(520, window.innerWidth * 0.4), sign: -1 },
    { el: splitO, cssVar: "--out-h", axis: "y", def: 240, min: 60,
      max: () => (window.innerHeight - 28 - 32 - 22) * 0.7, sign: -1 },
  ]);
  return { root, readouts, tools, busy, tree, tabs, docs, outTabs, out, props, status };
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

// Toolbar: Run (F5) + STALE · Reset · Case [preset, Import, Export] ·
// View [Fit (Ctrl+0), Grid, Flows, Angles] · Report.

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

export function mountToolbar(bar: HTMLElement): void {
  const runB = btn(ICON.run, "Run", "Run the load flow and every study (F5)", "run");
  runB.classList.add("primary");
  const stale = h("span", "badge stale", "STALE");
  stale.title = "The case changed since the last run";
  const resetB = btn(ICON.reset, "Reset", "Clear results and reload the preset");

  const sel = h("select", "tb-select");
  sel.title = "Preset case";
  sel.setAttribute("aria-label", "Preset case");
  const textB = btn(ICON.report, "Textbook", "New case from textbook data in real units (MVA, kV, ohm)");
  const importB = btn(ICON.open, "Import", "Open a .gridlens.json project");
  const exportB = btn(ICON.save, "Export", "Save the case as .gridlens.json");
  const file = h("input");
  file.type = "file";
  file.accept = ".json,.gridlens.json,application/json";
  file.hidden = true;

  const fitB = btn(ICON.fit, "Fit", "Fit the diagram to the window (Ctrl+0)");
  const toggles: [keyof View, HTMLButtonElement][] = [
    ["grid", btn(ICON.grid, "Grid", "Show the drawing grid")],
    ["flows", btn(ICON.flows, "Flows", "Show line flows (MW) on the diagram")],
    ["angles", btn(ICON.angles, "Angles", "Show bus voltage angles on the diagram")],
  ];
  const reportB = btn(ICON.report, "Report", "Open the study report");

  bar.append(
    group(runB, stale), group(resetB), group(sel, textB, importB, exportB, file),
    group(fitB, ...toggles.map(([, b]) => b)), group(reportB));

  runB.addEventListener("click", () => void run());
  resetB.addEventListener("click", () => void reset());
  sel.addEventListener("change", () => void loadPreset(sel.value));
  textB.addEventListener("click", () => void openWizard());
  importB.addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    const f = file.files?.[0];
    file.value = "";
    if (f) await importProject(f).catch((e) => report(e, `Importing ${f.name}`));
  });
  exportB.addEventListener("click", exportProject);
  fitB.addEventListener("click", fitCanvas);
  for (const [k, b] of toggles) {
    b.addEventListener("click", () => {
      const v = getState().view;
      setState({ view: { ...v, [k]: !v[k] } });
    });
  }
  reportB.addEventListener("click", () => navigate("report"));

  window.addEventListener("keydown", (e) => {
    if (e.key === "F5") {
      e.preventDefault();
      void run();
    } else if ((e.ctrlKey || e.metaKey) && e.key === "0") {
      e.preventDefault();
      navigate("canvas");
      fitCanvas();
    }
  });

  const paint = () => {
    const s = getState();
    stale.hidden = !isStale(s);
    runB.disabled = !s.case;
    exportB.disabled = !s.case;
    for (const [k, b] of toggles) {
      b.classList.toggle("on", s.view[k]);
      b.setAttribute("aria-pressed", String(s.view[k]));
    }
    if (s.case) {
      if (![...sel.options].some((o) => o.value === s.case!.name)) {
        const o = h("option", "", s.case.name);
        o.value = s.case.name;
        sel.prepend(o);
      }
      sel.value = s.case.name;
    }
  };
  subscribe(paint);
  paint();

  presets().then((names) => {
    sel.replaceChildren(...names.map((n) => {
      const o = h("option", "", n);
      o.value = n;
      return o;
    }));
    if (!getState().case && names[0]) void loadPreset(names[0]);
    else if (getState().case && !names.includes(getState().case!.name)) {
      const o = h("option", "", getState().case!.name);
      o.value = getState().case!.name;
      sel.prepend(o);
    }
    paint();
  }).catch((e) => report(e, "Listing presets"));
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
      `<div class="fill"><b>Status</b>${sol === "SOLVED" ? "Converged" : sol === "STALE"
        ? "Stale: press Run (F5)" : r ? "Not converged" : "Ready"}</div>` +
      `<div class="file">${esc(s.fileName)}</div>`;

    paintProps(props, s);
  };
  subscribe(paint);
  paint(getState());
}
