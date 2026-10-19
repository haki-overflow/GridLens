// "New from textbook data": enter a question's data in real units (MVA, kV,
// ohm, ohm/km, uS, MW, MVAr), check the per-unit conversion, load it as the
// project case. The conversion itself is units.to_pu on the server.
import { get, post, type Rec } from "./api";
import { report } from "./actions";
import { h } from "./shell";
import { DEFAULT_SETTINGS, log, setState } from "./state";
import { fmt, numIn, selectIn, table } from "./ui";

interface Example {
  sbase: number; ref_bus: number; ref_kv: number;
  buses: Rec[]; lines: Rec[]; trafos: Rec[]; z_units: string[]; b_units: string[];
}
interface ToPu { bus: Rec[]; lines: Rec[]; zones: Rec[]; table: Rec[] }

const STEPS = ["System", "Buses", "Lines", "Transformers", "Review"] as const;
const COLS: Record<"buses" | "lines" | "trafos", { key: string; label: string; sel?: "z" | "b" | "type" }[]> = {
  buses: [{ key: "Type", label: "Type", sel: "type" }, { key: "V", label: "V (pu)" }, { key: "Pg", label: "Pg (MW)" },
    { key: "Qg", label: "Qg (MVAr)" }, { key: "Pd", label: "Pd (MW)" }, { key: "Qd", label: "Qd (MVAr)" },
    { key: "Qmin", label: "Qmin (MVAr)" }, { key: "Qmax", label: "Qmax (MVAr)" }, { key: "Shunt", label: "Shunt (MVAr)" }],
  lines: [{ key: "From", label: "From" }, { key: "To", label: "To" }, { key: "R", label: "R" }, { key: "X", label: "X" },
    { key: "Z unit", label: "Z unit", sel: "z" }, { key: "Length", label: "Length (km)" }, { key: "B", label: "B" },
    { key: "B unit", label: "B unit", sel: "b" }],
  trafos: [{ key: "From", label: "From" }, { key: "To", label: "To" }, { key: "kV From", label: "kV From" },
    { key: "kV To", label: "kV To" }, { key: "MVA", label: "MVA" }, { key: "R", label: "R (pu own)" },
    { key: "X", label: "X (pu own)" }, { key: "Tap", label: "Tap" }],
};

function editTable(kind: keyof typeof COLS, rows: Rec[], ex: Example, onChange: () => void): HTMLElement {
  const wrap = h("div", "wz-table");
  const draw = () => {
    const t = h("table", "grid");
    const head = h("tr");
    head.append(h("th", "", "#"), ...COLS[kind].map((c) => h("th", "", c.label)), h("th", "", ""));
    t.append(head);
    rows.forEach((r, i) => {
      const tr = h("tr");
      tr.append(h("td", "s", String(i + 1)));
      for (const c of COLS[kind]) {
        const td = h("td", "s");
        const cur = r[c.key];
        if (c.sel) {
          const opts = c.sel === "z" ? ex.z_units : c.sel === "b" ? ex.b_units : ["Slack", "PV", "PQ"];
          const s = selectIn(opts, String(cur ?? opts[0]));
          s.addEventListener("change", () => { r[c.key] = s.value; onChange(); });
          td.append(s);
        } else {
          const inp = numIn(typeof cur === "number" ? cur : 0, "any", 78);
          inp.addEventListener("change", () => {
            const v = Number(inp.value);
            if (Number.isFinite(v)) { r[c.key] = v; onChange(); } else inp.classList.add("bad");
          });
          td.append(inp);
        }
        tr.append(td);
      }
      const del = h("button", "btn", "×");
      del.title = "Delete this row";
      del.addEventListener("click", () => { rows.splice(i, 1); draw(); onChange(); });
      tr.append(h("td", "").appendChild(del).parentElement!);
      t.append(tr);
    });
    const add = h("button", "btn", "+ Add row");
    add.addEventListener("click", () => {
      const base = rows[rows.length - 1] ?? Object.fromEntries(COLS[kind].map((c) => [c.key, 0]));
      rows.push({ ...base });
      draw();
      onChange();
    });
    wrap.replaceChildren(t, add);
  };
  draw();
  return wrap;
}

export async function openWizard(): Promise<void> {
  let ex: Example;
  try {
    ex = await get<Example>("/api/units/example");
  } catch (e) {
    report(e, "Opening the textbook input");
    return;
  }
  const d = h("dialog", "wizard");
  const sys = { sbase: ex.sbase, ref_bus: ex.ref_bus, ref_kv: ex.ref_kv };
  let step = 0;
  let result: ToPu | null = null;
  let problem = "";

  const head = h("div", "wz-head");
  const body = h("div", "wz-body");
  const foot = h("div", "wz-foot");
  d.append(head, body, foot);
  document.body.append(d);

  const convert = async () => {
    problem = "";
    try {
      result = await post<ToPu>("/api/topu", { ...sys, buses: ex.buses, lines: ex.lines, trafos: ex.trafos });
    } catch (e) {
      result = null;
      problem = e instanceof Error ? e.message : String(e);
    }
  };

  const draw = async () => {
    head.replaceChildren(h("div", "wz-title", "New from textbook data"),
      h("div", "wz-steps", ""));
    const steps = head.querySelector(".wz-steps")!;
    STEPS.forEach((s, i) => steps.append(h("span", i === step ? "on" : i < step ? "done" : "", `${i + 1}  ${s}`)));
    body.replaceChildren();
    if (step === 0) {
      body.append(h("p", "cap", "Enter the data the way the question gives it. Buses are numbered by row; " +
        "transformers start a new voltage zone."));
      const sb = numIn(sys.sbase), rb = numIn(sys.ref_bus, "1", 70), rk = numIn(sys.ref_kv);
      sb.addEventListener("change", () => (sys.sbase = Number(sb.value)));
      rb.addEventListener("change", () => (sys.ref_bus = Number(rb.value)));
      rk.addEventListener("change", () => (sys.ref_kv = Number(rk.value)));
      const row = h("div", "inputs");
      row.append(label("System base (MVA)", sb), label("Reference bus", rb), label("Its base kV", rk));
      body.append(row);
    } else if (step <= 3) {
      const kind = (["buses", "lines", "trafos"] as const)[step - 1]!;
      body.append(h("p", "cap", kind === "buses" ? "Loads and generation in MW / MVAr; V in pu. Qmin / Qmax in MVAr (±9999 = no limit)."
        : kind === "lines" ? "R, X in ohm or ohm/km; B in uS, uS/km or total MVAr charging."
          : "kV From / kV To are the rated voltages; R and X are per unit on the transformer's own MVA."));
      body.append(editTable(kind, ex[kind], ex, () => { result = null; }));
    } else {
      await convert();
      if (!result) {
        body.append(h("div", "gl-bad", problem || "The data could not be converted."));
      } else {
        body.append(h("p", "cap", "Check these against your hand calculation, then load them as the project."));
        const tabs = h("div", "wz-review");
        tabs.append(h("div", "sec", "Base values per zone"), table(result.zones),
          h("div", "sec", "Every converted value"), table(result.table, { maxHeight: 220, digits: { "Per unit": 6 } }));
        body.append(tabs);
      }
    }
    foot.replaceChildren();
    const cancel = h("button", "btn", "Cancel");
    cancel.addEventListener("click", () => d.close());
    const back = h("button", "btn", "Back");
    back.disabled = step === 0;
    back.addEventListener("click", () => { step--; void draw(); });
    const next = h("button", "btn primary", step === 4 ? "Load into project" : "Next");
    next.disabled = step === 4 && !result;
    next.addEventListener("click", async () => {
      if (step < 4) { step++; void draw(); return; }
      if (!result) return;
      setState({
        case: { name: "Textbook case", bus: result.bus, lines: result.lines,
                settings: { ...DEFAULT_SETTINGS, base: sys.sbase } },
        results: null, solvedCase: null, solvedSig: null, selection: null, outage: null,
        conversion: { zones: result.zones, table: result.table },
        fileName: "textbook_case.gridlens.json",
      });
      log("info", `Loaded textbook case: ${result.bus.length} buses, ${result.lines.length} branches (base ${sys.sbase} MVA). Press Run.`);
      d.close();
    });
    foot.append(cancel, h("span", "fill"), back, next);
  };
  d.addEventListener("close", () => d.remove());
  await draw();
  d.showModal();
}

function label(text: string, input: HTMLElement): HTMLLabelElement {
  const l = h("label", "field");
  l.append(h("span", "", text), input);
  return l;
}
export { fmt };
