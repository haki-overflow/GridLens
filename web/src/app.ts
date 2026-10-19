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

// Hash routing: #/doc/<id> opens (or focuses) that document tab.
export function docHref(id: string): string {
  return `#/doc/${id}`;
}

export function currentDoc(fallback: string): string {
  const m = /^#\/doc\/([\w-]+)/.exec(location.hash);
  return m?.[1] ?? fallback;
}

export function onRoute(fallback: string, open: (id: string) => void): void {
  const go = () => open(currentDoc(fallback));
  window.addEventListener("hashchange", go);
  go();
}

export function navigate(id: string): void {
  if (location.hash !== docHref(id)) location.hash = docHref(id);
}

// ---- state -------------------------------------------------------------

// Project state: the case, the last results, staleness, selection, open
// documents and view toggles. One store with a tiny pub/sub; saved to
// localStorage and exportable as a .gridlens.json file.

export interface Settings {
  method: string; tol: number; base: number; vmin: number; vmax: number;
  qlim: boolean; taps: boolean; shunts: boolean;
}
export interface CaseData { name: string; bus: Rec[]; lines: Rec[]; settings: Settings }
export interface Study extends Rec {
  res: Rec[]; flows: Rec[]; cmp: Rec[]; n1: Rec[]; ok: boolean; its: number;
  hist: number[]; method: string; tol: number; base: number; vmin: number; vmax: number;
  loss: number; load: number; slack_k: number; slack_p: number; summary: string;
  pv: { curve: Rec[]; lambda_max: number }; notes: string[]; qlog: Rec[];
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
  qlim: false, taps: false, shunts: false,
};

const KEY = "gridlens.project";
const fresh = (): State => ({
  case: null, results: null, solvedCase: null, solvedSig: null, selection: null, outage: null, conversion: null,
  openDocs: ["canvas"], activeDoc: "canvas",
  view: { grid: true, flows: false, angles: false }, messages: [],
  fileName: "untitled.gridlens.json",
});

function restore(): State {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...fresh(), ...(JSON.parse(raw) as Partial<State>) };
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

export function setState(patch: Partial<State>): void {
  state = { ...state, ...patch };
  for (const fn of listeners) fn(state);
  clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify({ ...state, messages: state.messages.slice(-200) }));
    } catch {
      /* quota / blocked: the project just isn't remembered */
    }
  }, 150);
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
    view: { ...state.view, ...(data.view ?? {}) }, selection: null, fileName: file.name,
  });
  log("info", `Imported ${file.name}: ${c.bus.length} buses, ${c.lines.length} branches. Press Run.`);
}

// ---- actions -----------------------------------------------------------

// What the toolbar does: load presets, run the study, reset.

interface CaseOut { name: string; bus: Rec[]; lines: Rec[]; settings: typeof DEFAULT_SETTINGS }

export async function presets(): Promise<string[]> {
  return (await get<{ cases: string[] }>("/api/cases")).cases;
}

export async function loadPreset(name: string): Promise<void> {
  try {
    const c = await get<CaseOut>(`/api/case/${encodeURIComponent(name)}`);
    const prev = getState().case;
    setState({
      case: { name: c.name, bus: c.bus, lines: c.lines,
              settings: prev?.settings ?? { ...DEFAULT_SETTINGS } },
      selection: null, fileName: `${c.name.replace(/[^\w-]+/g, "_")}.gridlens.json`,
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
  log("info", `Running study (${c.settings.method}) on ${c.name}...`);
  try {
    const out = await post<Study>("/api/study", c);
    setState({ results: out, solvedCase: c, solvedSig: sig });
    for (const n of out.notes ?? []) log("warn", n);
    const loss = out.loss.toFixed(3);
    log(out.ok ? "ok" : "error", out.ok
      ? `Solved in ${out.its} iterations. Losses ${loss} MW, slack P ${out.slack_p.toFixed(3)} MW.`
      : `Load flow did not converge after ${out.its} iterations.`);
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
