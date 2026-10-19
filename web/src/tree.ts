// Project tree: Project › Case › Buses · Branches · Studies · Worked
// solution · Calculators. Chevrons or Left/Right expand and collapse,
// Up/Down move, Enter (or click) opens a study or selects a bus/branch.
import { ICON } from "./icons";
import { navigate } from "./router";
import { h } from "./shell";
import { getState, setState, subscribe, type State } from "./state";

interface Node {
  key: string;
  label: string;
  icon: string;
  count?: number;
  doc?: string;
  sel?: { kind: "bus" | "branch"; index: number };
  children?: Node[];
}

const GROUPS: [string, string, [string, string][]][] = [
  ["studies", "Studies", [["load-flow", "Load flow"], ["solver-check", "Solver check"],
    ["contingency", "Contingency N-1"], ["pv-analysis", "PV analysis"],
    ["fault-levels", "Fault levels"], ["faults", "Unsymmetrical faults"], ["report", "Report"]]],
  ["worked", "Worked solution", [["ybus", "Ybus matrix"], ["iterations", "Iterations"],
    ["answer", "Worked answer"]]],
  ["calc", "Calculators", [["symmetrical", "Symmetrical components"], ["line", "Line parameters"],
    ["dispatch", "Economic dispatch"]]],
];

function model(s: State): Node {
  const c = s.case;
  const kids: Node[] = [{ key: "doc:canvas", label: "One-line diagram", icon: ICON.doc, doc: "canvas" }];
  if (c) {
    kids.push(
      { key: "buses", label: "Buses", icon: ICON.folder, count: c.bus.length,
        children: c.bus.map((b, i) => ({ key: `bus:${i}`, icon: ICON.bus,
          label: b.Type ? `Bus ${i + 1}  ${String(b.Type)}` : `Bus ${i + 1}`,
          sel: { kind: "bus" as const, index: i } })) },
      { key: "branches", label: "Branches", icon: ICON.folder, count: c.lines.length,
        children: c.lines.map((l, i) => ({ key: `branch:${i}`, label: `Line ${l.From}-${l.To}`,
          icon: ICON.branch, sel: { kind: "branch" as const, index: i } })) });
  }
  for (const [key, label, docs] of GROUPS) {
    kids.push({ key, label, icon: key === "calc" ? ICON.calc : ICON.folder,
      children: docs.map(([doc, l]) => ({ key: `doc:${doc}`, label: l,
        icon: key === "calc" ? ICON.calc : key === "studies" ? ICON.study : ICON.doc, doc })) });
  }
  return { key: "project", label: "Project", icon: ICON.project, children: [
    { key: "case", label: c ? `Case: ${c.name}` : "Case: (none)", icon: ICON.case, children: kids }] };
}

const OPEN_KEY = "gridlens.tree.open";
function loadOpen(): Set<string> {
  try {
    const v = JSON.parse(localStorage.getItem(OPEN_KEY) ?? "null") as string[] | null;
    if (v) return new Set(v);
  } catch {
    /* ignore */
  }
  return new Set(["project", "case", "studies", "worked", "calc"]);
}

interface Row { node: Node; level: number; parent: string | null }

export function mountTree(el: HTMLElement): void {
  const open = loadOpen();
  const box = h("div", "tree");
  box.tabIndex = 0;
  box.setAttribute("role", "tree");
  box.setAttribute("aria-label", "Project");
  el.append(box);
  let rows: Row[] = [];
  let focus = "case";

  const saveOpen = () => {
    try {
      localStorage.setItem(OPEN_KEY, JSON.stringify([...open]));
    } catch {
      /* ignore */
    }
  };

  const activate = (n: Node) => {
    focus = n.key;
    if (n.doc) navigate(n.doc);
    else if (n.sel) setState({ selection: n.sel });
    else if (n.children) toggle(n.key);
    paint(getState());
  };

  const toggle = (key: string, to?: boolean) => {
    const want = to ?? !open.has(key);
    if (want) open.add(key);
    else open.delete(key);
    saveOpen();
    paint(getState());
  };

  const isSelected = (n: Node, s: State) =>
    (n.doc !== undefined && n.doc === s.activeDoc) ||
    (n.sel !== undefined && s.selection?.kind === n.sel.kind && s.selection.index === n.sel.index);

  const paint = (s: State) => {
    rows = [];
    const walk = (n: Node, level: number, parent: string | null) => {
      rows.push({ node: n, level, parent });
      if (n.children && open.has(n.key)) for (const c of n.children) walk(c, level + 1, n.key);
    };
    walk(model(s), 0, null);
    if (!rows.some((r) => r.node.key === focus)) focus = rows[0]?.node.key ?? "";
    const ul = h("ul");
    for (const { node: n, level } of rows) {
      const li = h("li");
      li.setAttribute("role", "treeitem");
      li.id = `tree-${n.key.replace(/[^\w-]/g, "_")}`;
      if (n.children) li.setAttribute("aria-expanded", String(open.has(n.key)));
      const row = h("div", "row");
      row.style.paddingLeft = `${4 + level * 12}px`;
      row.classList.toggle("sel", isSelected(n, s));
      row.classList.toggle("focus", n.key === focus && document.activeElement === box);
      row.dataset.key = n.key;
      const chev = h("span", `chev${n.children && open.has(n.key) ? " open" : ""}`);
      if (n.children) {
        chev.innerHTML = ICON.chev;
        chev.addEventListener("click", (e) => {
          e.stopPropagation();
          focus = n.key;
          toggle(n.key);
        });
      }
      const ico = h("span", "ico");
      ico.innerHTML = n.icon;
      row.append(chev, ico, h("span", "", n.label));
      if (n.count !== undefined) row.append(h("span", "count", String(n.count)));
      row.addEventListener("click", () => activate(n));
      li.append(row);
      ul.append(li);
      if (n.key === focus) box.setAttribute("aria-activedescendant", li.id);
    }
    box.replaceChildren(ul);
    box.querySelector(".row.focus")?.scrollIntoView({ block: "nearest" });
  };

  box.addEventListener("keydown", (e) => {
    const i = rows.findIndex((r) => r.node.key === focus);
    const cur = rows[i];
    if (!cur) return;
    const n = cur.node;
    const move = (j: number) => {
      const r = rows[Math.max(0, Math.min(rows.length - 1, j))];
      if (r) focus = r.node.key;
      paint(getState());
    };
    switch (e.key) {
      case "ArrowDown": move(i + 1); break;
      case "ArrowUp": move(i - 1); break;
      case "Home": move(0); break;
      case "End": move(rows.length - 1); break;
      case "ArrowRight":
        if (n.children && !open.has(n.key)) toggle(n.key, true);
        else if (n.children) move(i + 1);
        break;
      case "ArrowLeft":
        if (n.children && open.has(n.key)) toggle(n.key, false);
        else if (cur.parent) {
          focus = cur.parent;
          paint(getState());
        }
        break;
      case "Enter": case " ": activate(n); break;
      default: return;
    }
    e.preventDefault();
  });
  // focus only toggles the ring: rebuilding the rows here would detach the
  // element under the pointer between mousedown and click
  const ring = () => box.querySelectorAll<HTMLElement>(".row").forEach((r) =>
    r.classList.toggle("focus", r.dataset.key === focus && document.activeElement === box));
  box.addEventListener("focus", ring);
  box.addEventListener("blur", ring);
  subscribe(paint);
  paint(getState());
}
