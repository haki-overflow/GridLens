// Helpers: DOM, tables, icons, zip/csv download.
// Sections follow the order of the files this one replaced; search for '// ----'.
import type { Cplx, Rec } from "./app";

// ---- h -----------------------------------------------------------------

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K, cls = "", text = "",
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text) el.textContent = text;
  return el;
}

// ---- ui ----------------------------------------------------------------

// Small DOM helpers for the document views: tables, cards, headlines,
// sub-tabs, inputs. No maths here: every number comes from the API.

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

/** Plain-words meanings for the jargon, shown as "?" tooltips. One table. */
export const GLOSSARY: Record<string, string> = {
  "per unit": "pu: a value divided by its base (here the base MVA and base kV), so 1.00 pu is nominal.",
  "pu": "Per unit: a value divided by its base, so 1.00 is nominal.",
  "load flow": "Solves the voltage at every bus so generation, load and losses balance.",
  "N-1": "Security check: remove one line at a time and see if the grid still stays within limits.",
  "PV curve": "Increase all load step by step until the case stops solving; shows how much headroom there is.",
  "Ybus": "Admittance matrix: describes how every bus connects to the others.",
  "SLG": "Single line-to-ground fault.",
  "LL": "Line-to-line fault.",
  "DLG": "Double line-to-ground fault.",
  "3-phase": "Balanced fault on all three phases: the usual worst-case fault current.",
  "slack": "The reference bus: fixes the voltage angle and absorbs the power mismatch.",
  "Newton-Raphson": "The standard load-flow method: fast and reliable.",
};

export function term(text: string): HTMLElement {
  const s = h("span", "gloss", "?");
  s.title = GLOSSARY[text] ?? "";
  return s;
}

export function title(el: HTMLElement, text: string, cap: string): void {
  const hd = h("h2", "", text);
  for (const k of Object.keys(GLOSSARY)) {
    if (new RegExp(`(^|[^A-Za-z])${k.replace(/[-+]/g, "\\$&")}([^A-Za-z]|$)`).test(`${text} ${cap}`)) {
      hd.append(term(k));
      break;
    }
  }
  el.append(hd, h("p", "cap", cap));
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

// ---- icons -------------------------------------------------------------

// Small inline SVG icons (16x16 viewBox, currentColor).
const svg = (body: string) =>
  `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" ` +
  `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

export const ICON = {
  run: svg('<path d="M4 3l9 5-9 5z" fill="currentColor" stroke="none"/>'),
  reset: svg('<path d="M3 8a5 5 0 1 0 1.5-3.5"/><path d="M3 2.5v3h3"/>'),
  open: svg('<path d="M2 4h4l1.5 1.5H14v7.5H2z"/>'),
  save: svg('<path d="M8 2v8M5 7l3 3 3-3"/><path d="M3 12v2h10v-2"/>'),
  fit: svg('<path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"/>'),
  grid: svg('<path d="M2 5.5h12M2 10.5h12M5.5 2v12M10.5 2v12"/>'),
  flows: svg('<path d="M2 8h10M9 5l3 3-3 3"/>'),
  angles: svg('<path d="M2 13h11M2 13l8-8"/><path d="M7 13a5 5 0 0 0-1.5-3.5"/>'),
  report: svg('<path d="M4 2h6l3 3v9H4z"/><path d="M6 8h5M6 10.5h5M6 5.5h2"/>'),
  project: svg('<path d="M2 4h4l1.5 1.5H14v7.5H2z"/>'),
  case: svg('<rect x="2.5" y="2.5" width="11" height="11"/><path d="M5 6h6M5 10h6"/>'),
  folder: svg('<path d="M2 4h4l1.5 1.5H14v7.5H2z"/>'),
  bus: svg('<path d="M2 8h12" stroke-width="2.4"/>'),
  branch: svg('<path d="M3 13L13 3"/><circle cx="3" cy="13" r="1.4"/><circle cx="13" cy="3" r="1.4"/>'),
  study: svg('<path d="M2 13l3.5-5 3 3L14 3"/>'),
  doc: svg('<path d="M4 2h6l3 3v9H4z"/>'),
  calc: svg('<rect x="3" y="2" width="10" height="12"/><path d="M5.5 5h5M5.5 8h1M9.5 8h1M5.5 11h1M9.5 11h1"/>'),
  chev: svg('<path d="M6 4l4 4-4 4"/>'),
};

// ---- zip ---------------------------------------------------------------

// Minimal ZIP writer (store, no compression) so results can be exported as
// one download without a library.
const TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();

function crc32(b: Uint8Array): number {
  let c = 0xffffffff;
  for (const x of b) c = TABLE[(c ^ x) & 0xff]! ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

export function zip(files: { name: string; text: string }[]): Blob {
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const f of files) {
    const name = enc.encode(f.name), data = enc.encode(f.text), crc = crc32(data);
    const head = new DataView(new ArrayBuffer(30));
    head.setUint32(0, 0x04034b50, true); head.setUint16(4, 20, true); head.setUint16(6, 0x0800, true);
    head.setUint32(14, crc, true); head.setUint32(18, data.length, true); head.setUint32(22, data.length, true);
    head.setUint16(26, name.length, true);
    parts.push(new Uint8Array(head.buffer), name, data);
    const c = new DataView(new ArrayBuffer(46));
    c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true); c.setUint16(8, 0x0800, true);
    c.setUint32(16, crc, true); c.setUint32(20, data.length, true); c.setUint32(24, data.length, true);
    c.setUint16(28, name.length, true); c.setUint32(42, offset, true);
    central.push(new Uint8Array(c.buffer), name);
    offset += 30 + name.length + data.length;
  }
  const size = central.reduce((a, b) => a + b.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(8, files.length, true); end.setUint16(10, files.length, true);
  end.setUint32(12, size, true); end.setUint32(16, offset, true);
  return new Blob([...parts, ...central, new Uint8Array(end.buffer)] as BlobPart[], { type: "application/zip" });
}

export function csv(rows: Record<string, unknown>[]): string {
  if (!rows.length) return "";
  const cols = Object.keys(rows[0]!);
  const q = (v: unknown) => {
    const s = v === null || v === undefined ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => q(r[c])).join(","))].join("\n");
}

export function download(blob: Blob, name: string): void {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
