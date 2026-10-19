// Project state: the case, the last results, staleness, selection, open
// documents and view toggles. One store with a tiny pub/sub; saved to
// localStorage and exportable as a .gridlens.json file.
import type { Rec } from "./api";

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
