// Builds the workspace skeleton (CSS grid) and returns its parts.
import { initSplitters } from "./splitters";

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

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K, cls = "", text = "",
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text) el.textContent = text;
  return el;
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
