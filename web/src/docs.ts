// Document registry: id -> title and how to mount it. The ids match the
// hash routes (#/doc/<id>).
import { h } from "./shell";
import type { DocDef } from "./tabs";

export const DOC_TITLES: Record<string, string> = {
  canvas: "One-line diagram",
  "load-flow": "Load flow",
  "solver-check": "Solver check",
  contingency: "Contingency N-1",
  "pv-analysis": "PV analysis",
  "fault-levels": "Fault levels",
  faults: "Unsymmetrical faults",
  ybus: "Ybus matrix",
  iterations: "Iterations",
  answer: "Worked answer",
  symmetrical: "Symmetrical components",
  line: "Line parameters",
  dispatch: "Economic dispatch",
  report: "Study report",
};

type Mount = (el: HTMLElement) => void;
const mounts: Record<string, Mount> = {};

export function registerDoc(id: string, mount: Mount): void {
  mounts[id] = mount;
}

function unknown(id: string): Mount {
  return (el) => {
    el.append(h("h2", "", "Unknown document"),
      h("p", "cap", `There is no document called "${id}".`));
  };
}

function pending(id: string): Mount {
  return (el) => {
    el.append(h("h2", "", DOC_TITLES[id] ?? id),
      h("p", "cap", "Run the study to fill this view."));
  };
}

export function lookupDoc(id: string): DocDef {
  const title = DOC_TITLES[id];
  if (!title) return { id, title: id, mount: unknown(id) };
  return { id, title, flush: id === "canvas", mount: mounts[id] ?? pending(id) };
}
