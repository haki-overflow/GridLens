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
