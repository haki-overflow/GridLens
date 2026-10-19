// What the toolbar does: load presets, run the study, reset.
import { ApiError, get, post, type Rec } from "./api";
import { caseSig, DEFAULT_SETTINGS, getState, log, setState, type Study } from "./state";

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
