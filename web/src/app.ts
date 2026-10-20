// App core: API, busy bar, router, project state, actions.
// Sections follow the order of the files this one replaced; search for '// ----'.

// ---- api ---------------------------------------------------------------

// Fetch wrapper for the FastAPI server. Every call shows the progress bar;
// a 422 becomes an ApiError carrying the server's problem list.

export type Rec = Record<string, unknown>;
export interface Cplx { re: number | null; im: number | null; polar: string }

export class ApiError extends Error {
  constructor(public status: number, public problems: string[], public notes: string[] = []) {
    super(problems.join(" "));
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(path, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, ["The GridLens server is not reachable. Start it with ./run_workspace.sh."]);
  }
  const data = (await r.json().catch(() => ({}))) as Rec;
  if (!r.ok) {
    const probs = Array.isArray(data.problems) ? (data.problems as string[])
      : [`Request failed (${r.status}).`];
    throw new ApiError(r.status, probs, Array.isArray(data.notes) ? (data.notes as string[]) : []);
  }
  return data as T;
}

export const get = <T>(path: string) => busy(call<T>("GET", path));
export const post = <T>(path: string, body: unknown) => busy(call<T>("POST", path, body));

// ---- busy --------------------------------------------------------------

// Thin progress bar under the toolbar. Requests nest: the bar shows while
// any is running. The screen is never blanked; views keep old results.
let count = 0;
let bar: HTMLElement | null = null;

export function mountBusy(el: HTMLElement): void {
  bar = el;
}

function paint(): void {
  bar?.classList.toggle("on", count > 0);
}

export async function busy<T>(work: Promise<T>): Promise<T> {
  count += 1;
  paint();
  try {
    return await work;
  } finally {
    count -= 1;
    paint();
  }
}

// ---- router ------------------------------------------------------------

// The 14 documents are grouped into 6 views, each with sub-tabs. Routes are
// #/<view>/<sub> (for example #/safety/n1); the older #/doc/<id> still works.
export interface SubView { id: string; label: string; doc: string }
export interface ViewDef {
  id: string; label: string; hint: string;
  needsRun: boolean; // results views stay "locked" until the first Run
  subs: SubView[];
}

export const VIEWS: ViewDef[] = [
  { id: "network", label: "Network", hint: "Draw it, or fill in the tables", needsRun: false,
    subs: [{ id: "diagram", label: "Diagram", doc: "canvas" },
      { id: "tables", label: "Data tables", doc: "case-tables" }] },
  { id: "solve", label: "Solve", hint: "Run the load flow", needsRun: true,
    subs: [{ id: "results", label: "Results", doc: "load-flow" },
      { id: "methods", label: "Do the 3 methods agree?", doc: "solver-check" },
      { id: "report", label: "Report and download", doc: "report" }] },
  { id: "safety", label: "Safety check", hint: "Is the grid within limits?", needsRun: true,
    subs: [{ id: "n1", label: "If a line fails (N-1)", doc: "contingency" },
      { id: "pv", label: "How much more load? (PV curve)", doc: "pv-analysis" }] },
  { id: "faults", label: "Short circuit", hint: "Fault currents", needsRun: true,
    subs: [{ id: "quick", label: "Quick (3-phase)", doc: "fault-levels" },
      { id: "detailed", label: "Detailed (SLG, LL, DLG)", doc: "faults" }] },
  { id: "working", label: "Show working", hint: "The maths, step by step", needsRun: true,
    subs: [{ id: "ybus", label: "Admittance matrix (Ybus)", doc: "ybus" },
      { id: "iterations", label: "Iterations", doc: "iterations" },
      { id: "answer", label: "Worked answer", doc: "answer" }] },
  { id: "tools", label: "Tools", hint: "Calculators, no case needed", needsRun: false,
    subs: [{ id: "symmetrical", label: "Symmetrical components", doc: "symmetrical" },
      { id: "line", label: "Line parameters", doc: "line" },
      { id: "dispatch", label: "Economic dispatch", doc: "dispatch" }] },
];

const lastSub: Record<string, string> = {};

/** The view and sub-view a document belongs to. */
export function viewOf(doc: string): { view: ViewDef; sub: SubView } | null {
  for (const view of VIEWS) {
    const sub = view.subs.find((x) => x.doc === doc);
    if (sub) return { view, sub };
  }
  return null;
}

export function docHref(doc: string): string {
  const v = viewOf(doc);
  return v ? `#/${v.view.id}/${v.sub.id}` : `#/doc/${doc}`;
}

/** The document the URL points at (new #/view/sub, #/view, or legacy #/doc/id). */
export function currentDoc(fallback: string): string {
  const legacy = /^#\/doc\/([\w-]+)/.exec(location.hash);
  if (legacy) return legacy[1]!;
  const m = /^#\/([\w-]+)(?:\/([\w-]+))?/.exec(location.hash);
  const view = VIEWS.find((x) => x.id === m?.[1]);
  if (!view) return fallback;
  const sub = view.subs.find((x) => x.id === m?.[2])
    ?? view.subs.find((x) => x.id === lastSub[view.id]) ?? view.subs[0]!;
  return sub.doc;
}

export function onRoute(fallback: string, open: (id: string) => void): void {
  const go = () => {
    const doc = currentDoc(fallback);
    const v = viewOf(doc);
    if (v) lastSub[v.view.id] = v.sub.id;
    if (location.hash !== docHref(doc) && v) history.replaceState(null, "", docHref(doc));
    open(doc);
  };
  window.addEventListener("hashchange", go);
  go();
}

export function navigate(doc: string): void {
  if (location.hash !== docHref(doc)) location.hash = docHref(doc);
}

/** Open a view (its last-used sub-view, or the first). */
export function navigateView(viewId: string): void {
  const view = VIEWS.find((x) => x.id === viewId);
  if (!view) return;
  const sub = view.subs.find((x) => x.id === lastSub[viewId]) ?? view.subs[0]!;
  navigate(sub.doc);
}

// ---- state -------------------------------------------------------------

// Project state: the case, the last results, staleness, selection, open
// documents and view toggles. One store with a tiny pub/sub; saved to
// localStorage and exportable as a .gridlens.json file.

export interface Settings {
  method: string; tol: number; base: number; vmin: number; vmax: number;
  qlim: boolean; taps: boolean; shunts: boolean;
  init: string; fallback: boolean; freq: number; units: "pu" | "actual";
}
export interface CaseData { name: string; bus: Rec[]; lines: Rec[]; settings: Settings }
export interface Study extends Rec {
  res: Rec[]; flows: Rec[]; cmp: Rec[]; n1: Rec[]; ok: boolean; its: number;
  hist: number[]; method: string; tol: number; base: number; vmin: number; vmax: number;
  loss: number; load: number; slack_k: number; slack_p: number; summary: string;
  pv: { curve: Rec[]; lambda_max: number }; notes: string[]; qlog: Rec[];
  hint: string; solved_with: string; attempts: Rec[]; loading: Rec[];
}
export interface Selection { kind: "bus" | "branch"; index: number }
export interface Msg { t: string; level: "info" | "ok" | "warn" | "error"; text: string }
export interface View { grid: boolean; flows: boolean; angles: boolean }

export interface State {
  case: CaseData | null;
  results: Study | null;
  solvedCase: CaseData | null; // the case the results belong to
  solvedSig: string | null;
  selection: Selection | null;
  started: boolean; // false until the user picks an example, a file or textbook data
  conversion: { zones: Rec[]; table: Rec[] } | null; // textbook per-unit check, for the worked answer
  outage: number | null; // index of the line shown tripped on the diagram
  openDocs: string[];
  activeDoc: string;
  view: View;
  messages: Msg[];
  fileName: string;
}

export const DEFAULT_SETTINGS: Settings = {
  method: "Newton-Raphson", tol: 1e-8, base: 100, vmin: 0.95, vmax: 1.1,
  qlim: false, taps: true, shunts: true,
  init: "flat", fallback: true, freq: 50, units: "pu",
};

const KEY = "gridlens.project";
const fresh = (): State => ({
  case: null, results: null, solvedCase: null, solvedSig: null, selection: null, started: false, outage: null, conversion: null,
  openDocs: ["canvas"], activeDoc: "canvas",
  view: { grid: false, flows: false, angles: false }, messages: [],
  fileName: "untitled.gridlens.json",
});

function restore(): State {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const saved = JSON.parse(raw) as Partial<State>;
      const st = { ...fresh(), ...saved, messages: [] };   // messages belong to one session
      if (st.case) st.case = { ...st.case, settings: { ...DEFAULT_SETTINGS, ...st.case.settings } };
      return st;
    }
  } catch {
    /* corrupt or blocked storage: start fresh */
  }
  return fresh();
}

let state: State = restore();
type Listener = (s: State) => void;
const listeners = new Set<Listener>();
let saveTimer = 0;

export function getState(): State {
  return state;
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Change the state. A new case is pushed onto the undo history unless
 *  history is false (undo / redo themselves, or the very first case). */
export function setState(patch: Partial<State>, history = true): void {
  if (history && "case" in patch && patch.case !== state.case && state.case) {
    undoStack.push(state.case);
    if (undoStack.length > HISTORY) undoStack.shift();
    redoStack.length = 0;
  }
  state = { ...state, ...patch };
  for (const fn of listeners) fn(state);
  clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ ...state, messages: [] }));
    } catch {
      /* quota / blocked: the project just isn't remembered */
    }
  }, 150);
}

// ---- undo history ------------------------------------------------------

// Up to 50 earlier cases. Every case edit pushes one (a drag pushes once, on
// drag end); undo / redo swap the case without pushing.
const HISTORY = 50;
const undoStack: CaseData[] = [];
const redoStack: CaseData[] = [];

export const canUndo = () => undoStack.length > 0;
export const canRedo = () => redoStack.length > 0;

function swapCase(from: CaseData[], to: CaseData[]): void {
  const c = from.pop();
  if (!c) return;
  if (state.case) to.push(state.case);
  const sel = state.selection;
  const keep = sel && (sel.kind === "bus" ? sel.index < c.bus.length : sel.index < c.lines.length);
  setState({ case: c, selection: keep ? sel : null, outage: null }, false);
}

export function undo(): void {
  swapCase(undoStack, redoStack);
}

export function redo(): void {
  swapCase(redoStack, undoStack);
}

export function caseSig(c: CaseData | null): string | null {
  // bar positions (x, y) only place the diagram; they do not change results
  return c ? JSON.stringify([c.bus.map(({ x: _x, y: _y, ...b }) => b), c.lines, c.settings]) : null;
}

export function isStale(s: State = state): boolean {
  return s.results !== null && caseSig(s.case) !== s.solvedSig;
}

export function log(level: Msg["level"], text: string): void {
  const t = new Date().toLocaleTimeString([], { hour12: false });
  setState({ messages: [...state.messages, { t, level, text }].slice(-200) });
}

/** Empty the message log (a new case, a new run, or the Clear button). */
export function clearMessages(): void {
  setState({ messages: [] });
}

// ---- file export / import ---------------------------------------------------
interface ProjectFile { gridlens: 1; case: CaseData; view: View }

export function exportProject(): void {
  if (!state.case) return;
  const file: ProjectFile = { gridlens: 1, case: state.case, view: state.view };
  const blob = new Blob([JSON.stringify(file, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  const name = state.fileName.endsWith(".gridlens.json") ? state.fileName
    : `${state.case.name.replace(/[^\w-]+/g, "_")}.gridlens.json`;
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
  log("info", `Exported ${name}.`);
}

export async function importProject(file: File): Promise<void> {
  const data = JSON.parse(await file.text()) as Partial<ProjectFile>;
  const c = data.case;
  if (!c || !Array.isArray(c.bus) || !Array.isArray(c.lines)) {
    throw new Error("not a GridLens project (expected a case with bus and lines).");
  }
  setState({
    case: { name: c.name ?? file.name, bus: c.bus, lines: c.lines,
            settings: { ...DEFAULT_SETTINGS, ...(c.settings ?? {}) } },
    view: { ...state.view, ...(data.view ?? {}) }, selection: null, fileName: file.name, started: true,
    results: null, solvedCase: null, solvedSig: null, outage: null, conversion: null, messages: [],
  });
  log("info", `Imported ${file.name}: ${c.bus.length} buses, ${c.lines.length} branches. Press Run.`);
}

// ---- actions -----------------------------------------------------------

// What the toolbar does: load presets, run the study, reset.

interface CaseOut { name: string; bus: Rec[]; lines: Rec[]; settings: typeof DEFAULT_SETTINGS }

interface Imported { name: string; bus: Rec[]; lines: Rec[]; settings: Partial<Settings>;
  notes: string[]; problems: string[] }

/** Open any case file: a .gridlens.json project, a MATPOWER .m file, an IEEE
 *  common data format file, or the CSV templates (bus and line CSV together). */
export async function importCaseFiles(files: File[]): Promise<void> {
  const json = files.find((f) => /\.json$/i.test(f.name));
  if (json) return importProject(json);
  const first = files[0];
  if (!first) return;
  const texts = await Promise.all(files.map((f) => f.text()));
  let body: Rec = { filename: first.name, text: texts[0] };
  if (/\.csv$/i.test(first.name)) {
    const isLines = (t: string) => /(^|,)\s*From\s*,/i.test(t.split(/\r?\n/)[0] ?? "");
    const lines = texts.find(isLines), bus = texts.find((t) => !isLines(t));
    if (!bus) throw new Error("choose the bus CSV too (Type, V, Pg, ...), with the line CSV.");
    body = { filename: first.name, text: bus, lines_text: lines ?? null };
  }
  const d = await post<Imported>("/api/import", body);
  setState({
    case: { name: d.name, bus: d.bus, lines: d.lines, settings: { ...DEFAULT_SETTINGS, ...d.settings } },
    selection: null, started: true, results: null, solvedCase: null, solvedSig: null, outage: null,
    conversion: null, messages: [], fileName: `${d.name.replace(/[^\w-]+/g, "_")}.gridlens.json`,
  });
  log("info", `Imported ${first.name}: ${d.bus.length} buses, ${d.lines.length} branches.`);
  for (const n of d.notes) log("warn", n);
  for (const p of d.problems) log("error", p);
  navigate("canvas");   // the diagram fits itself once the layout of a new case arrives
}

export async function presets(): Promise<string[]> {
  return (await get<{ cases: string[] }>("/api/cases")).cases;
}

export async function loadPreset(name: string, chosen = true): Promise<void> {
  try {
    const c = await get<CaseOut>(`/api/case/${encodeURIComponent(name)}`);
    const prev = getState().case;
    setState({
      case: { name: c.name, bus: c.bus, lines: c.lines,
              settings: prev?.settings ?? { ...DEFAULT_SETTINGS } },
      selection: null, fileName: `${c.name.replace(/[^\w-]+/g, "_")}.gridlens.json`,
      results: null, solvedCase: null, solvedSig: null, outage: null, conversion: null, messages: [],
      ...(chosen ? { started: true } : {}),
    });
    log("info", `Loaded preset ${c.name}: ${c.bus.length} buses, ${c.lines.length} branches.`);
  } catch (e) {
    report(e, "Loading the preset");
  }
}

let running = false;

export async function run(): Promise<void> {
  const c = getState().case;
  if (!c || running) return;
  running = true;
  const sig = caseSig(c);
  clearMessages();   // the log shows the current run only
  log("info", `Running study (${c.settings.method}) on ${c.name}...` + (c.lines.length > 60
    ? ` The line-outage (N-1) and PV studies re-solve the case many times: about ${Math.max(5, Math.round(c.lines.length * c.bus.length / 900))} s for ${c.bus.length} buses.`
    : ""));
  try {
    const out = await post<Study>("/api/study", c);
    setState({ results: out, solvedCase: c, solvedSig: sig });
    for (const n of out.notes ?? []) log("warn", n);
    const loss = out.loss.toFixed(3);
    log(out.ok ? "ok" : "error", out.ok
      ? `Solved in ${out.its} iterations (${out.solved_with}). Losses ${loss} MW, slack P ${out.slack_p.toFixed(3)} MW.`
      : `Load flow did not converge (${(out.attempts ?? []).length} attempts: ` +
        `${(out.attempts ?? []).map((a) => `${a.Method}, ${a.Start} start`).join("; ")}).`);
    if (!out.ok && out.hint) log("error", out.hint);
  } catch (e) {
    report(e, "The study");
  } finally {
    running = false;
  }
}

export async function reset(): Promise<void> {
  const c = getState().case;
  setState({ results: null, solvedCase: null, solvedSig: null, selection: null });
  log("info", "Results cleared.");
  try {
    if (c && (await presets()).includes(c.name)) await loadPreset(c.name);
  } catch (e) {
    report(e, "Reset");
  }
}

export function report(e: unknown, what: string): void {
  if (e instanceof ApiError) {
    if (e.status === 422) {
      log("error", `${what} was refused: fix the data first.`);
      for (const p of e.problems) log("error", `  • ${p}`);
      for (const n of e.notes) log("warn", `  • ${n}`);
    } else {
      for (const p of e.problems) log("error", p);
    }
  } else {
    log("error", `${what} failed: ${e instanceof Error ? e.message : String(e)}`);
  }
}

// ---- case actions ------------------------------------------------------

// Shared by the diagram (canvas.ts), the Properties panel and the Data
// tables: each one is a single setState({case}), so one undo step.
type Extra = Partial<State>;

export const NEW_BUS: Rec = { Type: "PQ", V: 1, Pg: 0, Qg: 0, Pd: 0, Qd: 0, Bs: 0 };
export const NEW_LINE: Rec = { R: 0.01, X: 0.1, B: 0, Tap: 1 };
export const NEW_TRAFO: Rec = { R: 0, X: 0.1, B: 0, Tap: 1, Kind: "trafo" };

const finite = (v: unknown) => v !== null && v !== "" && v !== undefined && Number.isFinite(Number(v));

/** A diagram position right of the other buses when they all carry x, y
 *  (so a new row keeps the drawing's positions), otherwise none. */
export function spareXY(bus: Rec[]): Rec {
  if (!bus.length || !bus.every((b) => finite(b.x) && finite(b.y))) return {};
  const snap = (v: number) => Math.round(v * 2) / 2;
  return { x: snap(Math.max(...bus.map((b) => Number(b.x)))) + 4.001,
           y: snap(Math.max(...bus.map((b) => Number(b.y)))) + 0.001 };
}

/** Add a PQ bus (at diagram position `at`, or right of the others when they
 *  all carry x, y) and select it. */
export function addBus(c: CaseData, at?: { x: number; y: number }, extra: Extra = {}): void {
  const nb: Rec = { ...NEW_BUS, ...(at ?? spareXY(c.bus)) };
  setState({ case: { ...c, bus: [...c.bus, nb] }, selection: { kind: "bus", index: c.bus.length }, ...extra });
}

/** Add a line (or, with NEW_TRAFO, a transformer) From -> To and select it. */
export function addLine(c: CaseData, from = 1, to = Math.min(2, c.bus.length), data: Rec = NEW_LINE): void {
  const nl: Rec = { From: from, To: to, ...data };
  setState({ case: { ...c, lines: [...c.lines, nl] }, selection: { kind: "branch", index: c.lines.length } });
}

export function delLine(c: CaseData, i: number): void {
  setState({ case: { ...c, lines: c.lines.filter((_, k) => k !== i) }, selection: null, outage: null });
}

/** Delete a bus: its lines go too and the buses after it are renumbered. */
export function delBus(c: CaseData, i: number): void {
  const fix = (v: unknown) => (Number(v) > i + 1 ? Number(v) - 1 : Number(v));
  const lines = c.lines.filter((l) => Number(l.From) !== i + 1 && Number(l.To) !== i + 1)
    .map((l) => ({ ...l, From: fix(l.From), To: fix(l.To) }));
  setState({ case: { ...c, bus: c.bus.filter((_, k) => k !== i), lines }, selection: null, outage: null });
}

export function editBus(c: CaseData, i: number, patch: Rec, extra: Extra = {}): void {
  setState({ case: { ...c, bus: c.bus.map((b, k) => (k === i ? { ...b, ...patch } : b)) }, ...extra });
}

export function editLine(c: CaseData, i: number, patch: Rec, extra: Extra = {}): void {
  setState({ case: { ...c, lines: c.lines.map((l, k) => (k === i ? { ...l, ...patch } : l)) }, ...extra });
}

export interface NewCase { name: string; base: number; freq: number; units: "pu" | "actual";
  start: "draw" | "tables" }

/** A blank case: one Slack bus (V = 1.0, 0 deg). "draw" opens the diagram with
 *  the Bus tool, "tables" opens Network > Data tables. */
export function newCase(o: NewCase = { name: "New network", base: 100, freq: 50, units: "pu", start: "draw" }): void {
  const slack: Rec = { ...NEW_BUS, Type: "Slack", x: 0.001, y: 0.001,
                       ...(o.units === "actual" ? { kV: 132 } : {}) };
  setState({
    case: { name: o.name || "New network", bus: [slack], lines: [],
            settings: { ...DEFAULT_SETTINGS, base: o.base, freq: o.freq, units: o.units } },
    results: null, solvedCase: null, solvedSig: null, selection: null, outage: null, conversion: null,
    started: true, messages: [], fileName: `${(o.name || "New_network").replace(/[^\w-]+/g, "_")}.gridlens.json`,
  });
  const u = o.units === "actual" ? "MW, MVAr, kV, ohm and uS (each bus needs its base kV)"
    : `per unit on ${o.base} MVA`;
  log("info", `New case "${o.name}": data in ${u}.`);
  if (o.start === "tables") {
    navigate("case-tables");
    return;
  }
  navigate("canvas");
  window.dispatchEvent(new CustomEvent("gl:tool", { detail: "bus" }));
  window.dispatchEvent(new CustomEvent("gl:fit"));
  log("info", "Add buses with the Bus tool (B), then lines (L), generators (G) and loads (D).");
}

/** The quick blank drawing (same as New case with the defaults). */
export function newNetwork(): void {
  newCase();
}
