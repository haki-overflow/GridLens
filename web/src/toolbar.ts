// Toolbar: Run (F5) + STALE · Reset · Case [preset, Import, Export] ·
// View [Fit (Ctrl+0), Grid, Flows, Angles] · Report.
import { loadPreset, presets, report, reset, run } from "./actions";
import { ICON } from "./icons";
import { navigate } from "./router";
import { h } from "./shell";
import { exportProject, getState, importProject, isStale, setState, subscribe, type View } from "./state";

function btn(icon: string, label: string, title: string, testid?: string): HTMLButtonElement {
  const b = h("button", "tb-btn");
  b.type = "button";
  b.innerHTML = `${icon}<span>${label}</span>`;
  b.title = title;
  if (testid) b.dataset.testid = testid;
  return b;
}

function group(...els: HTMLElement[]): HTMLElement {
  const g = h("div", "tb-group");
  g.append(...els);
  return g;
}

export function fitCanvas(): void {
  window.dispatchEvent(new CustomEvent("gl:fit"));
}

export function mountToolbar(bar: HTMLElement): void {
  const runB = btn(ICON.run, "Run", "Run the load flow and every study (F5)", "run");
  runB.classList.add("primary");
  const stale = h("span", "badge stale", "STALE");
  stale.title = "The case changed since the last run";
  const resetB = btn(ICON.reset, "Reset", "Clear results and reload the preset");

  const sel = h("select", "tb-select");
  sel.title = "Preset case";
  sel.setAttribute("aria-label", "Preset case");
  const importB = btn(ICON.open, "Import", "Open a .gridlens.json project");
  const exportB = btn(ICON.save, "Export", "Save the case as .gridlens.json");
  const file = h("input");
  file.type = "file";
  file.accept = ".json,.gridlens.json,application/json";
  file.hidden = true;

  const fitB = btn(ICON.fit, "Fit", "Fit the diagram to the window (Ctrl+0)");
  const toggles: [keyof View, HTMLButtonElement][] = [
    ["grid", btn(ICON.grid, "Grid", "Show the drawing grid")],
    ["flows", btn(ICON.flows, "Flows", "Show line flows (MW) on the diagram")],
    ["angles", btn(ICON.angles, "Angles", "Show bus voltage angles on the diagram")],
  ];
  const reportB = btn(ICON.report, "Report", "Open the study report");

  bar.append(
    group(runB, stale), group(resetB), group(sel, importB, exportB, file),
    group(fitB, ...toggles.map(([, b]) => b)), group(reportB));

  runB.addEventListener("click", () => void run());
  resetB.addEventListener("click", () => void reset());
  sel.addEventListener("change", () => void loadPreset(sel.value));
  importB.addEventListener("click", () => file.click());
  file.addEventListener("change", async () => {
    const f = file.files?.[0];
    file.value = "";
    if (f) await importProject(f).catch((e) => report(e, `Importing ${f.name}`));
  });
  exportB.addEventListener("click", exportProject);
  fitB.addEventListener("click", fitCanvas);
  for (const [k, b] of toggles) {
    b.addEventListener("click", () => {
      const v = getState().view;
      setState({ view: { ...v, [k]: !v[k] } });
    });
  }
  reportB.addEventListener("click", () => navigate("report"));

  window.addEventListener("keydown", (e) => {
    if (e.key === "F5") {
      e.preventDefault();
      void run();
    } else if ((e.ctrlKey || e.metaKey) && e.key === "0") {
      e.preventDefault();
      navigate("canvas");
      fitCanvas();
    }
  });

  const paint = () => {
    const s = getState();
    stale.hidden = !isStale(s);
    runB.disabled = !s.case;
    exportB.disabled = !s.case;
    for (const [k, b] of toggles) {
      b.classList.toggle("on", s.view[k]);
      b.setAttribute("aria-pressed", String(s.view[k]));
    }
    if (s.case && [...sel.options].some((o) => o.value === s.case!.name)) sel.value = s.case.name;
  };
  subscribe(paint);
  paint();

  presets().then((names) => {
    sel.replaceChildren(...names.map((n) => {
      const o = h("option", "", n);
      o.value = n;
      return o;
    }));
    if (!getState().case && names[0]) void loadPreset(names[0]);
    else if (getState().case && !names.includes(getState().case!.name)) {
      const o = h("option", "", getState().case!.name);
      o.value = getState().case!.name;
      sel.prepend(o);
    }
    paint();
  }).catch((e) => report(e, "Listing presets"));
}
