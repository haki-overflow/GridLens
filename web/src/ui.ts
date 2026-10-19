// Small DOM helpers for the document views: tables, cards, headlines,
// sub-tabs, inputs. No maths here: every number comes from the API.
import type { Cplx, Rec } from "./api";
import { h } from "./shell";

export function isCplx(v: unknown): v is Cplx {
  return typeof v === "object" && v !== null && "polar" in v && "re" in v;
}

export function fmt(v: unknown, d = 4): string {
  if (v === null || v === undefined) return "-";
  if (isCplx(v)) return v.polar;
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "-";
    return Number.isInteger(v) ? String(v) : v.toFixed(d);
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}

export interface TableOpts {
  cols?: string[];
  digits?: Record<string, number>;
  scale?: Record<string, number>; // multiply a column (e.g. pu -> MW)
  rename?: Record<string, string>;
  bad?: (r: Rec) => boolean;
  maxHeight?: number;
}

export function table(rows: Rec[], o: TableOpts = {}): HTMLElement {
  const cols = o.cols ?? Object.keys(rows[0] ?? {});
  const t = h("table", "grid");
  const head = h("tr");
  for (const c of cols) head.append(h("th", "", o.rename?.[c] ?? c));
  t.append(head);
  for (const r of rows) {
    const tr = h("tr", o.bad?.(r) ? "bad" : "");
    for (const c of cols) {
      let v = r[c];
      if (typeof v === "number" && o.scale?.[c] !== undefined) v = v * o.scale[c]!;
      const td = h("td", typeof v === "string" || typeof v === "boolean" || isCplx(v) ? "s" : "",
        fmt(v, o.digits?.[c] ?? 4));
      tr.append(td);
    }
    t.append(tr);
  }
  if (!o.maxHeight) return t;
  const wrap = h("div");
  wrap.style.maxHeight = `${o.maxHeight}px`;
  wrap.style.overflow = "auto";
  wrap.style.display = "inline-block";
  wrap.append(t);
  return wrap;
}

export function matrix(M: unknown[][], labels: string[]): HTMLElement {
  const t = h("table", "grid");
  const head = h("tr");
  head.append(h("th", "", ""));
  for (const l of labels) head.append(h("th", "", l));
  t.append(head);
  M.forEach((row, i) => {
    const tr = h("tr");
    tr.append(h("th", "", labels[i] ?? ""));
    for (const v of row) tr.append(h("td", "", fmt(v, 4)));
    t.append(tr);
  });
  return t;
}

export function title(el: HTMLElement, text: string, cap: string): void {
  el.append(h("h2", "", text), h("p", "cap", cap));
}

export function section(text: string): HTMLElement {
  return h("div", "sec", text);
}

export function headline(text: string, tone: "" | "ok" | "bad" = ""): HTMLElement {
  return h("div", `headline ${tone}`.trim(), text);
}

export function cards(items: [string, string, string?, boolean?][]): HTMLElement {
  const g = h("div", "cards");
  for (const [l, v, d, bad] of items) {
    const c = h("div", `card${bad ? " bad" : ""}`);
    c.append(h("div", "l", l), h("div", "v", v));
    if (d) c.append(h("div", "d", d));
    g.append(c);
  }
  return g;
}

/** Sub-tabs inside a document; returns the panes in order. */
export function subtabs(el: HTMLElement, names: string[], key: string): HTMLElement[] {
  const bar = h("div", "subtabs");
  bar.setAttribute("role", "tablist");
  const panes = names.map(() => h("div", "subpane"));
  const store = `gridlens.sub.${key}`;
  let on = 0;
  try {
    on = Math.min(Number(sessionStorage.getItem(store) ?? 0) || 0, names.length - 1);
  } catch {
    /* ignore */
  }
  const btns = names.map((n, i) => {
    const b = h("button", "", n);
    b.type = "button";
    b.setAttribute("role", "tab");
    b.addEventListener("click", () => pick(i));
    return b;
  });
  const pick = (i: number) => {
    btns.forEach((b, k) => b.classList.toggle("on", k === i));
    panes.forEach((p, k) => p.classList.toggle("on", k === i));
    try {
      sessionStorage.setItem(store, String(i));
    } catch {
      /* ignore */
    }
  };
  bar.append(...btns);
  el.append(bar, ...panes);
  pick(on);
  return panes;
}

export function field(label: string, input: HTMLInputElement | HTMLSelectElement): HTMLLabelElement {
  const l = h("label");
  l.append(document.createTextNode(label), input);
  return l;
}

export function numIn(value: number, step = "any", width = 90): HTMLInputElement {
  const i = h("input");
  i.type = "number";
  i.step = step;
  i.value = String(value);
  i.style.width = `${width}px`;
  return i;
}

export function selectIn(options: string[], value: string): HTMLSelectElement {
  const s = h("select");
  for (const o of options) {
    const op = h("option", "", o);
    op.value = o;
    s.append(op);
  }
  s.value = value;
  return s;
}

export function notice(el: HTMLElement, html: string): void {
  const n = h("div", "notice");
  n.innerHTML = html;
  el.append(n);
}

export const NEED_RUN = "No results yet: press <b>Run</b> (F5) in the toolbar.";
