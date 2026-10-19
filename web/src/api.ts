// Fetch wrapper for the FastAPI server. Every call shows the progress bar;
// a 422 becomes an ApiError carrying the server's problem list.
import { busy } from "./busy";

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
