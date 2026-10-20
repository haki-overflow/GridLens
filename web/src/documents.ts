// Documents: registry, study views, textbook wizard.
// Sections follow the order of the files this one replaced; search for '// ----'.
import { DEFAULT_SETTINGS, NEW_BUS, NEW_LINE, addBus, addLine, delBus, delLine, editBus, editLine, get, getState, isStale, log, navigate, post, report, setState, spareXY, subscribe, type CaseData, type Rec, type State, type Study } from "./app";
import { phasorDiagram, stackedPlot } from "./charts";
import { type DocDef } from "./shell";
import { NEED_RUN, cards, csv, download, field, fmt, h, headline, matrix, notice, numIn, section, selectIn, subtabs, table, title, zip } from "./ui";

// ---- docs --------------------------------------------------------------

// Document registry: id -> title and how to mount it. The ids match the
// hash routes (#/doc/<id>).

export const DOC_TITLES: Record<string, string> = {
  canvas: "Network diagram",
  "case-tables": "Data tables",
  "load-flow": "Load flow results",
  "solver-check": "Do the 3 methods agree?",
  contingency: "If a line fails (N-1)",
  "pv-analysis": "How much more load? (PV curve)",
  "fault-levels": "Quick short circuit (3-phase)",
  faults: "Detailed short circuit (SLG, LL, DLG)",
  ybus: "Admittance matrix (Ybus)",
  iterations: "Iterations",
  answer: "Worked answer",
  symmetrical: "Symmetrical components",
  line: "Line parameters",
  dispatch: "Economic dispatch",
  report: "Report and download",
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

// ---- views -------------------------------------------------------------

// Document views. Each one renders from the last study (or its own API
// call on the solved case) and keeps showing the previous content while a
// new request runs, so the screen never blanks.

type Paint = (body: HTMLElement, r: Study, c: CaseData) => void;

/** A document drawn from the study results; redrawn only when they change. */
function resultsDoc(id: string, heading: string, cap: string, paint: Paint): void {
  registerDoc(id, (el) => {
    title(el, heading, cap);
    const stale = h("div", "headline bad");
    stale.textContent = "STALE: the case changed since these results. Press Run (F5).";
    const body = h("div");
    el.append(stale, body);
    let seen: Study | null | undefined;
    const draw = (s: State) => {
      stale.hidden = !isStale(s);
      if (s.results === seen) return;
      seen = s.results;
      body.replaceChildren();
      if (!s.results || !s.solvedCase) notice(body, NEED_RUN);
      else paint(body, s.results, s.solvedCase);
    };
    subscribe(draw);
    draw(getState());
  });
}

/** A document that calls its own endpoint on the solved case. inputs()
 *  builds the input row and returns a function giving the request body. */
function apiDoc(id: string, heading: string, cap: string,
  inputs: (row: HTMLElement, refresh: () => void, c: CaseData) => () => Rec,
  path: string, paint: (body: HTMLElement, data: Rec, c: CaseData, req: Rec) => void,
  wrap = true): void {
  registerDoc(id, (el) => {
    title(el, heading, cap);
    const row = h("div", "inputs");
    const body = h("div");
    el.append(row, body);
    let seen: Study | null | undefined;
    let bodyFn: (() => Rec) | null = null;
    let token = 0;
    const refresh = async () => {
      const s = getState();
      if (!s.solvedCase || !bodyFn) return;
      const my = ++token;
      const req = bodyFn();
      const sent = wrap ? { case: caseBody(s.solvedCase), ...req } : caseBody(s.solvedCase);
      try {
        const data = await post<Rec>(path, sent);
        if (my !== token) return; // a newer request superseded this one
        body.replaceChildren();
        paint(body, data, s.solvedCase, req);
      } catch (e) {
        report(e, heading);
      }
    };
    const draw = (s: State) => {
      if (s.results === seen) return;
      seen = s.results;
      if (!s.solvedCase) {
        row.replaceChildren();
        body.replaceChildren();
        notice(body, NEED_RUN);
        bodyFn = null;
        return;
      }
      row.replaceChildren();
      bodyFn = inputs(row, () => void refresh(), s.solvedCase);
      void refresh();
    };
    subscribe(draw);
    draw(getState());
  });
}

const caseBody = (c: CaseData) => ({ name: c.name, bus: c.bus, lines: c.lines, settings: c.settings });
const n = (x: unknown) => (typeof x === "number" ? x : NaN);

// ---------------------------------------------------------------- load flow
resultsDoc("load-flow", "Load flow results", "Bus voltages, generation, line flows and losses.",
  (el, r) => {
    const V = r.res.map((x) => n(x["V (pu)"]));
    const lo = Math.min(...V), hi = Math.max(...V);
    const busAt = (v: number) => r.res[V.indexOf(v)]?.Bus;
    el.append(cards([
      [`Slack P · bus ${r.slack_k}`, `${r.slack_p.toFixed(1)} MW`],
      ["Losses", `${r.loss.toFixed(2)} MW`, r.load ? `${(r.loss / r.load * 100).toFixed(1)} % of load` : ""],
      [`Min |V| · bus ${busAt(lo)}`, `${lo.toFixed(3)} pu`, `limit ${r.vmin}`, lo < r.vmin],
      [`Max |V| · bus ${busAt(hi)}`, `${hi.toFixed(3)} pu`, `limit ${r.vmax}`, hi > r.vmax],
    ]));
    const viol = r.res.filter((x) => n(x["V (pu)"]) < r.vmin || n(x["V (pu)"]) > r.vmax);
    el.append(section("Violations"), viol.length
      ? table(viol.map((x) => ({ Element: `Bus ${x.Bus}`, "Value (pu)": x["V (pu)"],
          "Limit (pu)": n(x["V (pu)"]) < r.vmin ? r.vmin : r.vmax })))
      : headline("No violations", "ok"));
    const [bus, br, prof] = subtabs(el, ["Bus report", "Branch report", "Profile"], "lf");
    const busNo = r.res.map((x) => n(x.Bus));
    prof!.append(stackedPlot(busNo, [
      { yLabel: "|V| (pu)", digits: 3, series: [{ name: "|V|", y: V }],
        hline: { y: r.vmin, label: `Vmin ${r.vmin}` } },
      { yLabel: "Angle (deg)", digits: 2, series: [{ name: "Angle", y: r.res.map((x) => n(x["Angle (deg)"])) }] },
    ], { xLabel: "Bus number" }));
    bus!.append(table(r.res, { scale: { P_inj: r.base, Q_inj: r.base },
      rename: { P_inj: "P inj (MW)", Q_inj: "Q inj (MVAr)" },
      digits: { "Angle (deg)": 3, P_inj: 2, Q_inj: 2 },
      bad: (x) => n(x["V (pu)"]) < r.vmin || n(x["V (pu)"]) > r.vmax }));
    const s = r.base;
    br!.append(table(r.flows, {
      cols: ["From", "To", "P_ij", "Q_ij", "P_ji", "Q_ji", "Loss_P", "Loss_Q"],
      scale: { P_ij: s, Q_ij: s, P_ji: s, Q_ji: s, Loss_P: s, Loss_Q: s },
      rename: { P_ij: "P from (MW)", Q_ij: "Q from (MVAr)", P_ji: "P to (MW)",
        Q_ji: "Q to (MVAr)", Loss_P: "Loss (MW)", Loss_Q: "Loss (MVAr)" },
      digits: { P_ij: 2, Q_ij: 2, P_ji: 2, Q_ji: 2, Loss_P: 3, Loss_Q: 3 } }));
    if (r.qlog?.length) el.append(section("Generator Q limits: bus type switching"), table(r.qlog));
  });

// -------------------------------------------------------------- solver check
resultsDoc("solver-check", "Do the 3 methods agree?", "The same case through all three load-flow methods.",
  (el, r) => {
    const ok = r.cmp.every((x) => x.Converged);
    el.append(headline(ok ? "All three methods converge to the same answer."
      : "Not every method converged.", ok ? "ok" : "bad"), table(r.cmp));
  });

// --------------------------------------------------------------- contingency
resultsDoc("contingency", "If a line fails (N-1)", "Each line removed in turn, case re-solved, ranked worst first.",
  (el, r) => {
    const bad = r.n1.filter((x) => x.Status !== "OK" || n(x.Violations) > 0);
    const w = r.n1[0];
    if (w) {
      el.append(headline(w.Status !== "OK"
        ? `Worst outage: line ${w.Outage} leaves the case with no solution. ${bad.length} of ${r.n1.length} outages insecure.`
        : `Worst outage: line ${w.Outage} → min |V| ${fmt(w["Min V (pu)"], 3)} pu at bus ${w["At bus"]}. ${bad.length} of ${r.n1.length} outages insecure.`,
      bad.length ? "bad" : "ok"));
    }
    const tbl = table(r.n1, { bad: (x) => x.Status !== "OK" || n(x.Violations) > 0 });
    const lines = (getState().case?.lines ?? []).map((l) => `${l.From}-${l.To}`);
    Array.from(tbl.querySelectorAll("tr")).slice(1).forEach((tr, i) => {
      const k = lines.indexOf(String(r.n1[i]?.Outage));
      if (k < 0) return;
      tr.classList.add("click");
      tr.title = "Show this outage on the diagram";
      tr.addEventListener("click", () => {
        setState({ outage: getState().outage === k ? null : k });
        navigate("canvas");
      });
    });
    el.append(h("p", "cap", "Click a row to show that outage on the diagram (the tripped line is dashed)."), tbl);
  });

// --------------------------------------------------------------- PV analysis
resultsDoc("pv-analysis", "How much more load? (PV curve)", "Loads and generation scaled by λ until the case stops solving.",
  (el, r) => {
    const lam = r.pv.lambda_max;
    const curve = r.pv.curve;
    const last = curve[curve.length - 1] ?? {};
    const buses = Object.keys(last).filter((k) => k !== "lambda");
    const weak = buses.map((b) => ({ Bus: b, "|V| at nose (pu)": n(last[b]) }))
      .sort((a, b) => a["|V| at nose (pu)"] - b["|V| at nose (pu)"]);
    el.append(headline(`Loadability ${lam.toFixed(2)}x base: ${((lam - 1) * r.load).toFixed(0)} MW of extra load. ` +
      `Weakest bus: ${weak[0]?.Bus ?? "-"} (${fmt(weak[0]?.["|V| at nose (pu)"], 3)} pu at the nose).`,
    lam >= 1.5 ? "ok" : "bad"));
    const [c1, c2] = subtabs(el, ["P-V curves", "Weakest buses"], "pv");
    const lamX = curve.map((x) => n(x.lambda));
    const weakNames = new Set(weak.slice(0, 3).map((w) => w.Bus));
    const varying = buses.filter((b) => {
      const ys = curve.map((x) => n(x[b]));
      return Math.max(...ys) - Math.min(...ys) > 1e-6;
    });
    const mk = (f: (ys: number[]) => number[]) => varying.map((b) => ({
      name: b, y: f(curve.map((x) => n(x[b]))), dim: !weakNames.has(b),
    }));
    c1!.append(stackedPlot(lamX, [
      { yLabel: "|V| (pu)", series: mk((y) => y), hline: { y: r.vmin, label: `Vmin ${r.vmin}` } },
      { yLabel: "Drop from λ=0 (pu)", series: mk((y) => y.map((v) => v - y[0]!)) },
    ], { xLabel: "Load scaling λ (all loads and generation)", panelHeight: 150,
      vline: { x: lam, label: `λ max ${lam.toFixed(2)}` } }));
    c2!.append(table(weak, { digits: { "|V| at nose (pu)": 4 } }));
  });

// -------------------------------------------------------------- fault levels
apiDoc("fault-levels", "Quick short circuit (3-phase)", "Three-phase fault current at every bus from the Zbus.",
  (row, refresh) => {
    const xd = numIn(0.2), zf = numIn(0), kv = numIn(33);
    row.append(field("Generator Xd'' (pu)", xd), field("Fault Zf (pu)", zf), field("Base kV", kv));
    for (const i of [xd, zf, kv]) i.addEventListener("change", refresh);
    return () => ({ xd: Number(xd.value), zf: Number(zf.value), kv: Number(kv.value) });
  },
  "/api/fault", (el, d, _c, req) => {
    const t = d.table as Rec[];
    const top = [...t].sort((a, b) => n(b["Fault I (pu)"]) - n(a["Fault I (pu)"]))[0];
    if (top) {
      el.append(headline(`Highest fault level: bus ${top.Bus}, ${fmt(top["Fault I (pu)"], 2)} pu = ` +
        `${fmt(top["Fault I (kA)"], 1)} kA at ${req.kv} kV (${fmt(top["Fault MVA"], 0)} MVA)`));
    }
    el.append(table(t));
  });

// ----------------------------------------------------- unsymmetrical faults
let seqOverride: { gens?: Rec[]; branches?: Rec[] } = {};
let seqRefresh: () => void = () => {};

apiDoc("faults", "Detailed short circuit (SLG, LL, DLG)", "SLG, LL, DLG and three-phase faults from sequence networks.",
  (row, refresh, c) => {
    const kind = selectIn(["3-phase", "SLG", "LL", "DLG"], "SLG");
    const bus = selectIn(c.bus.map((_, i) => String(i + 1)), "1");
    const zr = numIn(0), zx = numIn(0);
    const pre = selectIn(["flat", "loadflow"], "flat");
    row.append(field("Fault type", kind), field("Fault bus", bus), field("Zf R (pu)", zr),
      field("Zf X (pu)", zx), field("Prefault", pre));
    for (const i of [kind, bus, zr, zx, pre]) i.addEventListener("change", refresh);
    seqRefresh = refresh;
    seqOverride = {};
    return () => ({ kind: kind.value, bus: Number(bus.value), zf: { re: Number(zr.value), im: Number(zx.value) },
      prefault: pre.value, ...seqOverride });
  },
  "/api/seqfault", (el, d, _c, req) => {
    const kA = d.kA as number[], I = d.Iabc as Rec[], kv = d.kv as number[];
    const imax = Math.max(...I.map((z) => Math.hypot(n(z.re), n(z.im))));
    el.append(headline(`${req.kind} fault at bus ${req.bus}: ${imax.toFixed(2)} pu = ` +
      `${Math.max(...kA).toFixed(1)} kA at ${kv[n(req.bus) - 1]} kV`));
    const [p1, p2, p3, p4] = subtabs(el, ["Fault currents", "Bus voltages", "Branch currents", "Sequence data"], "sf");
    const I012 = d.I012 as Rec[];
    p1!.append(table([
      { "": "Sequence 0 / 1 / 2 (pu)", "0 / a": I012[0], "1 / b": I012[1], "2 / c": I012[2] },
      { "": "Phase a / b / c (pu)", "0 / a": I[0], "1 / b": I[1], "2 / c": I[2] },
      { "": "Phase a / b / c (kA)", "0 / a": kA[0], "1 / b": kA[1], "2 / c": kA[2] },
    ]), section(`${req.kind} fault level at every bus`), table(d.table as Rec[]));
    const V = d.V012 as Rec[][], Vp = d.Vabc as Rec[][];
    const mag = (z?: Rec) => Math.hypot(n(z?.re), n(z?.im));
    p2!.append(stackedPlot(V.map((_, i) => i + 1), [{ yLabel: "Phase |V| (pu)", digits: 3, series: [
      { name: "Va", y: Vp.map((v) => mag(v[0])) }, { name: "Vb", y: Vp.map((v) => mag(v[1])) },
      { name: "Vc", y: Vp.map((v) => mag(v[2])) }] }], { xLabel: "Bus number", panelHeight: 220 }));
    p2!.append(table(V.map((v, i) => ({ Bus: i + 1, V0: v[0], V1: v[1], V2: v[2],
      Va: Vp[i]?.[0], Vb: Vp[i]?.[1], Vc: Vp[i]?.[2] }))));
    p3!.append(table(d.lines as Rec[]));
    const Z = d.Zth as Rec[];
    const gens = d.gens as Rec[], brs = d.branches as Rec[];
    const apply = () => { seqOverride = { gens, branches: brs }; seqRefresh(); };
    p4!.append(table([{ "Z1 (pu)": Z[1], "Z2 (pu)": Z[2], "Z0 (pu)": Z[0] }]),
      h("p", "cap", "Edit the sequence reactances below; the fault is recalculated."),
      section("Generators"), rowEditor(gens, Object.keys(gens[0] ?? {}), apply),
      section("Lines and transformers"), rowEditor(brs, Object.keys(brs[0] ?? {}), apply));
  });

// ---------------------------------------------------------------------- ybus
apiDoc("ybus", "Admittance matrix (Ybus)", "The bus admittance matrix and the terms that form each element.",
  () => () => ({}), "/api/ybus", (el, d, c) => {
    const labels = c.bus.map((_, i) => String(i + 1));
    const [p1, p2] = subtabs(el, ["Matrix (polar, pu)", "How each element is formed"], "yb");
    p1!.append(matrix(d.Y as unknown[][], labels));
    p2!.append(table(d.parts as Rec[], { cols: ["Element", "Source", "Value"] }));
  }, false);

// ---------------------------------------------------------------- iterations
apiDoc("iterations", "Iterations", "Step-by-step Newton-Raphson, Gauss-Seidel or Fast Decoupled working.",
  (row, refresh, c) => {
    const m = selectIn(["Newton-Raphson", "Gauss-Seidel", "Fast Decoupled"], c.settings.method);
    const alpha = numIn(1, "0.1");
    row.append(field("Method", m), field("Acceleration α (GS)", alpha));
    for (const i of [m, alpha]) i.addEventListener("change", refresh);
    return () => ({ method: m.value, alpha: Number(alpha.value) });
  },
  "/api/iterations", (el, d, c) => {
    const tr = d.trace as Rec;
    const lab = c.bus.map((_, i) => String(i + 1));
    el.append(headline(`${d.method}: ${tr.ok ? "converged" : "did not converge"} (tolerance ${d.tol}).`,
      tr.ok ? "ok" : "bad"));
    if (d.method === "Gauss-Seidel") {
      const Vh = tr.V as Rec[][], dmax = tr.dmax as number[];
      el.append(table(Vh.map((v, k) => {
        const r: Rec = { Iter: k };
        v.forEach((z, i) => (r[`V${lab[i]}`] = z));
        r["max |ΔV|"] = k ? (dmax[k - 1] ?? NaN).toExponential(2) : "-";
        return r;
      }), { maxHeight: 520 }));
      return;
    }
    const its = tr.its as Rec[];
    el.append(table(its.map((it) => ({ Iter: it.done ? "check" : it.k, "max mismatch": n(it.err).toExponential(3) }))));
    if (d.method === "Newton-Raphson") {
      for (const it of its.filter((x) => !x.done)) {
        el.append(section(`Iteration ${it.k}: mismatch and corrections`));
        const dP = it.dP as number[], dQ = it.dQ as number[];
        const dth = it.dth as number[], dV = it.dV as number[];
        el.append(table([{ "": "ΔP / ΔQ", ...Object.fromEntries([...dP, ...dQ].map((v, i) => [`m${i + 1}`, v])) },
          { "": "Δδ (rad) / Δ|V|", ...Object.fromEntries([...dth, ...dV].map((v, i) => [`m${i + 1}`, v])) }],
        { digits: {} }));
      }
    }
  });

// -------------------------------------------------------------- worked answer
apiDoc("answer", "Worked answer", "The solution written out as text, ready to copy.",
  (row, refresh) => {
    const show = numIn(2, "1", 60);
    row.append(field("Iterations written out", show));
    show.addEventListener("change", refresh);
    return () => ({ show: Math.max(1, Math.min(10, Number(show.value) || 2)),
      conversion: getState().conversion ?? undefined });
  },
  "/api/answer", (el, d) => {
    const text = String(d.text);
    const bar = h("div", "inputs");
    const copy = h("button", "btn primary", "Copy");
    const dl = h("button", "btn", "Download .txt");
    copy.addEventListener("click", () => void navigator.clipboard.writeText(text)
      .then(() => (copy.textContent = "Copied")).catch(() => (copy.textContent = "Copy failed")));
    dl.addEventListener("click", () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
      a.download = "gridlens_answer.txt";
      a.click();
      URL.revokeObjectURL(a.href);
    });
    bar.append(copy, dl);
    el.append(bar, h("pre", "answer", text));
  });

// ---------------------------------------------------------------------- report
resultsDoc("report", "Report and download", "The solver's summary, an optional plain-English write-up, and the results as files.",
  (el, r) => {
    const pre = h("pre", "answer", r.summary);
    const exp = h("div", "inputs");
    const zipB = h("button", "btn primary", "Download results (.zip)");
    zipB.title = "Bus report, branch report, solver check, N-1 and the summary as CSV / text";
    zipB.addEventListener("click", () => {
      const c = getState().case;
      const k = r.base;
      const busRows = r.res.map((x, i) => ({ Bus: x.Bus, Type: c?.bus[i]?.Type, "V (pu)": x["V (pu)"],
        "Angle (deg)": x["Angle (deg)"], "P inj (MW)": n(x.P_inj) * k, "Q inj (MVAr)": n(x.Q_inj) * k }));
      const brRows = r.flows.map((f) => ({ From: f.From, To: f.To, "P from (MW)": n(f.P_ij) * k,
        "Q from (MVAr)": n(f.Q_ij) * k, "P to (MW)": n(f.P_ji) * k, "Q to (MVAr)": n(f.Q_ji) * k,
        "Loss (MW)": n(f.Loss_P) * k, "Loss (MVAr)": n(f.Loss_Q) * k }));
      const name = (c?.name ?? "case").replace(/[^\w-]+/g, "_");
      download(zip([
        { name: "bus_report.csv", text: csv(busRows) }, { name: "branch_report.csv", text: csv(brRows) },
        { name: "solver_check.csv", text: csv(r.cmp) }, { name: "n1_contingency.csv", text: csv(r.n1) },
        { name: "summary.txt", text: r.summary }]), `${name}_results.zip`);
    });
    exp.append(zipB);

    const sec = section("Plain-English write-up (local model, LM Studio)");
    const note = h("div", "cap", "The model only rephrases the numbers above; it does no calculation. " +
      "Start LM Studio, load a model and start its server first.");
    const row = h("div", "inputs");
    const model = h("select");
    const typed = h("input");
    typed.placeholder = "model id";
    typed.hidden = true;
    const gen = h("button", "btn", "Generate write-up");
    const out = h("div");
    row.append(field("Model", model), typed, gen);
    const loadModels = async () => {
      try {
        const m = (await get<{ models: string[] }>("/api/lm/models")).models;
        model.replaceChildren(...m.map((x) => new Option(x, x)));
        const g = m.findIndex((x) => x.toLowerCase().includes("gemma"));
        if (g >= 0) model.selectedIndex = g;
        const none = m.length === 0;
        model.hidden = none;
        typed.hidden = !none;
        if (none) note.textContent = "LM Studio was not detected at 127.0.0.1:1234. Start its server, or type a model id.";
      } catch (e) {
        report(e, "Listing LM Studio models");
      }
    };
    gen.addEventListener("click", async () => {
      const id = model.hidden ? typed.value.trim() : model.value;
      if (!id) { out.replaceChildren(h("div", "gl-bad", "Pick or type a model id first.")); return; }
      gen.disabled = true;
      out.replaceChildren(h("div", "cap", "Writing..."));
      try {
        const t = (await post<{ text: string }>("/api/report", { summary: r.summary, model: id })).text;
        const dl = h("button", "btn", "Download .md");
        dl.addEventListener("click", () => download(new Blob([t], { type: "text/markdown" }), "gridlens_report.md"));
        out.replaceChildren(h("pre", "answer wrap", t), dl);
      } catch (e) {
        out.replaceChildren(h("div", "gl-bad", e instanceof Error ? e.message : String(e)));
      } finally {
        gen.disabled = false;
      }
    });
    el.append(exp, section("Study summary"), pre, sec, note, row, out);
    void loadModels();
  });

// -------------------------------------------------- calculators (no case needed)
function calcDoc(id: string, heading: string, cap: string,
  inputs: (row: HTMLElement, refresh: () => void) => () => Rec, path: string,
  paint: (el: HTMLElement, d: Rec, req: Rec) => void): void {
  registerDoc(id, (el) => {
    title(el, heading, cap);
    const row = h("div", "inputs");
    const body = h("div");
    el.append(row, body);
    let token = 0;
    const refresh = async () => {
      const my = ++token;
      const req = get();
      try {
        const d = await post<Rec>(path, req);
        if (my !== token) return;
        body.replaceChildren();
        paint(body, d, req);
      } catch (e) {
        report(e, heading);
      }
    };
    const get = inputs(row, () => void refresh());
    void refresh();
  });
}

calcDoc("symmetrical", "Symmetrical components", "Phase quantities to sequence components and back.",
  (row, refresh) => {
    const ins = [["|Va|", 1], ["∠Va (°)", 0], ["|Vb|", 0.8], ["∠Vb (°)", -110], ["|Vc|", 1.1], ["∠Vc (°)", 125]]
      .map(([l, v]) => [l as string, numIn(v as number)] as const);
    for (const [l, i] of ins) {
      row.append(field(l, i));
      i.addEventListener("change", refresh);
    }
    return () => ({ abc: [0, 2, 4].map((k) => ({ mag: Number(ins[k]![1].value), deg: Number(ins[k + 1]![1].value) })) });
  },
  "/api/symcomp", (el, d, req) => {
    const s = d.s012 as Rec[];
    const m = (z: Rec | undefined) => Math.hypot(n(z?.re), n(z?.im));
    el.append(headline(`Unbalance V2/V1 = ${(m(s[2]) / Math.max(m(s[1]), 1e-12) * 100).toFixed(2)} %`));
    const abc = (req.abc as { mag: number; deg: number }[]).map((z, i) => ({
      name: ["Va", "Vb", "Vc"][i]!, re: z.mag * Math.cos(z.deg * Math.PI / 180),
      im: z.mag * Math.sin(z.deg * Math.PI / 180) }));
    const seq = s.map((z, i) => ({ name: ["V0", "V1", "V2"][i]!, re: n(z?.re), im: n(z?.im) }));
    const row = h("div", "phasor-row");
    row.append(phasorDiagram("Phase voltages", abc), phasorDiagram("Sequence components", seq),
      table([{ Component: "V0 (zero)", Value: s[0] }, { Component: "V1 (positive)", Value: s[1] },
        { Component: "V2 (negative)", Value: s[2] }]));
    el.append(row);
  });

calcDoc("line", "Line parameters", "ABCD constants, regulation and efficiency of a transmission line.",
  (row, refresh) => {
    const model = selectIn(["short", "medium (π)", "long"], "medium (π)");
    const vals: [string, string, number][] = [["R", "R (Ω/km)", 0.1], ["X", "X (Ω/km)", 0.5],
      ["B_uS", "B (µS/km)", 3.2], ["length", "Length (km)", 150], ["VR_kV", "V_R (kV, line)", 220],
      ["PR_MW", "P_R (MW)", 150], ["pf", "pf", 0.85]];
    const ins = vals.map(([k, , v]) => [k, numIn(v)] as const);
    const lag = selectIn(["lagging", "leading"], "lagging");
    row.append(field("Model", model));
    ins.forEach(([, i], k) => row.append(field(vals[k]![1], i)));
    row.append(field("Power factor", lag));
    for (const i of [model, lag, ...ins.map(([, i]) => i)]) i.addEventListener("change", refresh);
    return () => ({ model: model.value, lagging: lag.value === "lagging",
      ...Object.fromEntries(ins.map(([k, i]) => [k, Number(i.value)])) });
  },
  "/api/tline", (el, d) => {
    const p = d.performance as Rec, a = d.abcd as Rec;
    el.append(headline(`Sending end ${fmt(p.VS_LL, 2)} kV · regulation ${fmt(p.reg, 2)} % · ` +
      `efficiency ${fmt(p.eff, 2)} % (loss ${fmt(p.loss, 2)} MW)`));
    el.append(table(["A", "B", "C", "D"].map((k) => ({ Constant: k, Value: a[k] }))),
      section("Both ends"), table([
        { Quantity: "S sending (MVA)", Value: p.SS }, { Quantity: "S receiving (MVA)", Value: p.SR },
        { Quantity: "I sending (kA)", Value: p.IS }, { Quantity: "AD − BC", Value: p.check }]));
  });

calcDoc("dispatch", "Economic dispatch", "Least-cost generation at equal incremental cost, with limits and B-coefficient losses.",
  (row, refresh) => {
    const pd = numIn(150);
    const loss = selectIn(["B-coefficients", "None"], "B-coefficients");
    const lim = selectIn(["On", "Off"], "On");
    row.append(field("Demand PD (MW)", pd), field("Losses", loss), field("Unit limits", lim));
    for (const i of [pd, loss, lim]) i.addEventListener("change", refresh);
    const units: Rec[] = [
      { a: 200, b: 7.0, c: 0.008, Pmin: 10, Pmax: 85 },
      { a: 180, b: 6.3, c: 0.009, Pmin: 10, Pmax: 80 },
      { a: 140, b: 6.8, c: 0.007, Pmin: 10, Pmax: 70 }];
    row.after(h("p", "cap", "Units: cost = a + b·P + c·P² ($/h, P in MW). Edit any value; the B-coefficient matrix assumes 3 units."),
      rowEditor(units, ["a", "b", "c", "Pmin", "Pmax"], () => void refresh()));
    return () => ({ units, PD: Number(pd.value), use_limits: lim.value === "On",
      ...(loss.value === "None" ? {} : {
        B: [[0.0218, 0.0093, 0.0028], [0.0093, 0.0228, 0.0017], [0.0028, 0.0017, 0.0179]],
        B0: [0.0003, 0.0031, 0.0015], B00: 0.00030523, pu_base: 100 }) });
  },
  "/api/dispatch", (el, d, req) => {
    el.append(headline(`λ = ${fmt(d.lam, 4)} $/MWh · cost ${fmt(d.cost, 2)} $/h · losses ${fmt(d.PL, 3)} MW` +
      ` · PD = ${req.PD} MW`, d.ok ? "ok" : "bad"));
    const [p1, p2] = subtabs(el, ["Optimal dispatch", "λ iterations"], "ed");
    p1!.append(table(d.table as Rec[]));
    p2!.append(table(d.its as Rec[], { maxHeight: 480 }));
  });

// ---- small editable table (case tables, dispatch units, sequence data) ---

export interface RowEditorOpts {
  addable?: boolean; // "+ Add row" and a delete button per row
  index?: boolean; // a leading read-only "#" column
  name?: string; // data-t on every cell, so callers can mark bad cells
  select?: Record<string, string[]>; // columns edited with a <select>
  numeric?: string[]; // number columns (default: guessed from the values)
  cell?: (row: number, col: string, value: unknown) => void; // instead of writing rows[row][col]
  onAdd?: () => void; // instead of copying the last row
  onDelete?: (row: number) => void; // instead of splicing the row out
  onPaste?: (row: number, col: number, block: string[][]) => void; // col -1 = the "#" cell
  readonly?: string[]; // columns shown but not editable
  labels?: Record<string, string>; // header text per column (default: the column name)
  addLabel?: string; // text of the add button
}

const show = (v: unknown) => v === null || v === undefined ? ""
  : typeof v === "number" ? String(+v.toPrecision(12)) : String(v);

/** A block copied from Excel (tabs) or a PDF / CSV (commas, or spaces) as rows of cells. */
export function parseBlock(text: string): string[][] {
  const lines = text.replace(/\r/g, "").split("\n").map((l) => l.trim()).filter((l) => l !== "");
  const sep = lines.some((l) => l.includes("\t")) ? /\t/ : lines.some((l) => l.includes(",")) ? /\s*,\s*/ : /\s+/;
  return lines.map((l) => l.split(sep).map((x) => x.trim()));
}

/** Without `cell`, edits `rows` in place: numbers stay numbers, text stays
 *  text. With `numeric`, an empty cell becomes null and a non-number is kept
 *  as typed so the server's validation can name it. */
function rowEditor(rows: Rec[], cols: string[], onChange: () => void, o: RowEditorOpts = {}): HTMLElement {
  const wrap = h("div", "wz-table");
  const isNum = (c: string, v: unknown) => !o.select?.[c] && (o.numeric ? o.numeric.includes(c) : typeof v !== "string");
  const write = (i: number, c: string, v: unknown) => {
    if (o.cell) o.cell(i, c, v);
    else {
      rows[i]![c] = v;
      onChange();
    }
  };
  const tag = (el: HTMLElement, i: number, c: string) => {
    el.dataset.r = String(i);
    el.dataset.c = c;
    if (o.name) el.dataset.t = o.name;
  };
  const paste = (e: ClipboardEvent, i: number, ci: number) => {
    const text = e.clipboardData?.getData("text/plain") ?? "";
    if (!o.onPaste || (!/[\t\n]/.test(text.trim()) && text.split(",").length < 3)) return; // one value: normal paste
    e.preventDefault();
    o.onPaste(i, ci, parseBlock(text));
  };
  const draw = () => {
    const tb = h("table", "grid");
    const head = h("tr");
    head.append(...(o.index ? [h("th", "", "#")] : []), ...cols.map((c) => h("th", "", o.labels?.[c] ?? c)),
      ...(o.addable ? [h("th", "", "")] : []));
    tb.replaceChildren(head);
    rows.forEach((r, i) => {
      const tr = h("tr");
      if (o.index) {
        const idx = h("input", "idx");
        idx.readOnly = true;
        idx.defaultValue = String(i + 1);
        idx.title = "Paste a block here to fill the rows from this one";
        tag(idx, i, "#");
        idx.addEventListener("paste", (e) => paste(e, i, -1));
        const td = h("td", "s");
        td.append(idx);
        tr.append(td);
      }
      cols.forEach((c, ci) => {
        const td = h("td", "s");
        const cur = r[c];
        const opts = o.select?.[c];
        let inp: HTMLInputElement | HTMLSelectElement;
        if (opts) {
          const s = h("select");
          const val = cur === undefined || cur === null || cur === "" ? opts[0]! : String(cur);
          for (const x of opts.includes(val) ? opts : [...opts, val]) s.append(new Option(x, x, false, x === val));
          s.addEventListener("change", () => write(i, c, s.value));
          inp = s;
        } else {
          const t = h("input");
          t.defaultValue = show(cur);
          t.style.width = isNum(c, cur) ? "64px" : "92px";
          if (o.readonly?.includes(c)) t.readOnly = true;
          t.addEventListener("change", () => {
            const raw = t.value.trim();
            t.defaultValue = t.value; // committed: Ctrl+Z now undoes the case
            if (!isNum(c, cur)) return write(i, c, t.value);
            if (raw === "" && o.numeric) return write(i, c, null);
            if (raw !== "" && Number.isFinite(Number(raw))) {
              t.classList.remove("bad");
              return write(i, c, Number(raw));
            }
            if (o.numeric) return write(i, c, raw);
            t.classList.add("bad");
          });
          inp = t;
        }
        tag(inp, i, c);
        inp.addEventListener("paste", (e) => paste(e as ClipboardEvent, i, ci));
        td.append(inp);
        tr.append(td);
      });
      if (o.addable) {
        const del = h("button", "btn rowdel", "×");
        del.type = "button";
        del.title = `Delete row ${i + 1}`;
        del.setAttribute("aria-label", `Delete row ${i + 1}`);
        del.addEventListener("click", () => {
          if (o.onDelete) return o.onDelete(i);
          rows.splice(i, 1);
          draw();
          onChange();
        });
        const td = h("td", "");
        td.append(del);
        tr.append(td);
      }
      tb.append(tr);
    });
    wrap.replaceChildren(tb);
    if (o.addable) {
      const add = h("button", "btn", o.addLabel ?? "+ Add row");
      add.type = "button";
      add.addEventListener("click", () => {
        if (o.onAdd) return o.onAdd();
        rows.push({ ...(rows[rows.length - 1] ?? {}) });
        draw();
        onChange();
      });
      wrap.append(add);
    }
  };
  draw();
  return wrap;
}

// ---- case tables ---------------------------------------------------------

// Network > Data tables: the bus and line tables of the case, like the
// Streamlit Problem input. Every edit goes through the shared case actions
// (one undo step each), so the diagram follows at once and the other way
// round. Bad cells are marked from the prep_case messages of /api/validate.

const BUS_TYPES = ["Slack", "PV", "PQ"];
const LINE_KINDS = ["line", "trafo"];
const IN_SERVICE = ["yes", "no"];
const LINE_COLS = ["From", "To", "R", "X", "B", "Tap", "Shift", "Rate", "InService", "Kind"];
const busCols = (c: CaseData) => ["Num", "Name", "Type", "kV", "V", "Pd", "Qd", "Pg", "Qg",
  ...(c.settings.qlim ? ["Qmin", "Qmax"] : []), "Gs", "Bs"];
const GEN_COLS = ["Bus", "Type", "V", "Pg", "Qg", "Qmin", "Qmax"];
const LOAD_COLS = ["Bus", "Pd", "Qd"];
const SHUNT_COLS = ["Bus", "Gs", "Bs"];

/** Column headers with the units of the case (per unit or actual). */
function unitLabels(c: CaseData): Record<string, string> {
  const act = c.settings.units === "actual";
  const p = act ? "MW" : "pu", q = act ? "MVAr" : "pu";
  return {
    Num: "No.", kV: "Base kV", V: "V set (pu)", Pd: `Pd (${p})`, Qd: `Qd (${q})`, Pg: `Pg (${p})`,
    Qg: `Qg (${q})`, Qmin: `Qmin (${q})`, Qmax: `Qmax (${q})`, Gs: `Gs (${act ? "MW" : "pu"})`,
    Bs: `Bs (${act ? "MVAr" : "pu"})`, R: `R (${act ? "Ω" : "pu"})`, X: `X (${act ? "Ω" : "pu"})`,
    B: `B (${act ? "µS" : "pu"})`, Tap: "Tap", Shift: "Shift (°)", Rate: "Rate (MVA)",
    InService: "In service", Kind: "Kind",
  };
}

const normType = (s: string) => /^(sl|sw|ref|3$)/i.test(s) ? "Slack" : /^(pv|gen|2$)/i.test(s) ? "PV"
  : /^(pq|load|[01]$)/i.test(s) ? "PQ" : s;
const normKind = (s: string) => (/^(t|x)/i.test(s) ? "trafo" : /^l/i.test(s) || s === "" ? "line" : s);

/** A pasted cell as stored: Type / Kind words normalised, numbers as numbers,
 *  anything else kept as typed (validation names it). */
function pasteValue(col: string, raw: string): unknown {
  if (col === "Type") return normType(raw);
  if (col === "Kind") return normKind(raw);
  if (col === "Name") return raw;
  const t = raw.replace(/[−–]/g, "-");
  if (t === "") return null;
  return Number.isFinite(Number(t)) ? Number(t) : raw;
}

const isNumText = (s: string) => s !== "" && Number.isFinite(Number(s.replace(/[−–]/g, "-")));

/** prep_case messages -> bad cells ("bus:<row>:<col>" -> message). */
function cellMarks(problems: string[], c: CaseData): Map<string, string> {
  const m = new Map<string, string>();
  const put = (t: string, r: number, col: string, msg: string) => m.set(`${t}:${r}:${col}`, msg);
  const rows = (s: string) => s.split(",").map((x) => Number(x.trim()) - 1).filter((x) => x >= 0);
  for (const p of problems) {
    let g: RegExpExecArray | null;
    if ((g = /^Bus row (\d+): column (\w+) is not a number/.exec(p))) put("bus", Number(g[1]) - 1, g[2]!, p);
    else if ((g = /^Line row (\d+): column (\w+) is not a number/.exec(p))) put("line", Number(g[1]) - 1, g[2]!, p);
    else if ((g = /^Bus Type must be .*\(row\(s\) ([\d, ]+)\)/.exec(p))) rows(g[1]!).forEach((r) => put("bus", r, "Type", p));
    else if ((g = /^Line (From|To) must be whole .*\(rows ([\d, ]+)\)/.exec(p))) rows(g[2]!).forEach((r) => put("line", r, g![1]!, p));
    else if ((g = /^More than one Slack bus \(buses ([\d, ]+)\)/.exec(p))) rows(g[1]!).forEach((r) => put("bus", r, "Type", p));
    else if ((g = /more than one Slack bus \(([\d, ]+)\)/.exec(p))) rows(g[1]!).forEach((r) => put("bus", r, "Type", p));
    else if ((g = /^Base kV must be greater than 0 \(bus rows ([\d, ]+)\)/.exec(p))) rows(g[1]!).forEach((r) => put("bus", r, "kV", p));
    else if ((g = /missing or not positive at bus rows ([\d, ]+)/.exec(p))) rows(g[1]!).forEach((r) => put("bus", r, "kV", p));
    else if ((g = /^Duplicate bus numbers: ([\d, ]+)/.exec(p))) {
      const dup = new Set(g[1]!.split(",").map((x) => Number(x)));
      c.bus.forEach((b, r) => { if (dup.has(Number(b.Num))) put("bus", r, "Num", p); });
    } else if (p.startsWith("Lines reference buses that do not exist")) {
      for (const x of p.matchAll(/row (\d+): (From|To) =/g)) put("line", Number(x[1]) - 1, x[2]!, p);
    } else if (p.startsWith("Series reactance X must be greater than 0")) {
      c.lines.forEach((l, r) => { if (Number.isFinite(Number(l.X)) && Number(l.X) <= 0) put("line", r, "X", p); });
    } else if ((g = /buses ([\d, ]+) have no path to a Slack/.exec(p))) rows(g[1]!).forEach((r) => put("bus", r, "#", p));
  }
  return m;
}

registerDoc("case-tables", (el) => {
  const head = h("div");
  const probs = h("div", "tbl-probs");
  const [busBox, lineBox, genBox, loadBox, shuntBox] = subtabs(el, ["Buses", "Branches", "Generators",
    "Loads", "Shunts"], "tables") as [HTMLElement, HTMLElement, HTMLElement, HTMLElement, HTMLElement];
  el.prepend(head, probs);
  const foot = h("p", "cap");
  const wiz = h("button", "btn", "Enter textbook data...");
  wiz.type = "button";
  wiz.addEventListener("click", () => void openWizard());
  foot.append("A whole question in MVA, kV and ohms with transformers between voltage levels? ", wiz);
  el.append(foot);

  let shown: CaseData | null = null;
  let writing = false; // a cell edit from this table: keep the DOM (and the focus)
  let marks = new Map<string, string>();
  let checked: CaseData | null = null;
  let timer = 0, token = 0;
  const cur = () => getState().case!;
  const act = (fn: () => void, keep = false) => {
    writing = keep;
    try { fn(); } finally { writing = false; }
  };

  const applyMarks = () => {
    for (const inp of el.querySelectorAll<HTMLElement>("[data-t]")) {
      const why = marks.get(`${inp.dataset.t}:${inp.dataset.r}:${inp.dataset.c}`);
      inp.classList.toggle("bad", !!why);
      if (why) inp.title = why;
      else if (inp.dataset.c !== "#") inp.removeAttribute("title");
    }
  };

  const pasteRows = (t: "bus" | "line", i: number, ci: number, block: string[][]) => {
    const c = cur();
    const cols = t === "bus" ? busCols(c) : LINE_COLS;
    let grid = block;
    if (grid.length && !grid[0]!.some(isNumText)) grid = grid.slice(1); // a header row
    let start = Math.max(ci, 0);
    if (ci < 0 && grid.length) {
      // pasted on "#": drop a leading row-number column (1, 2, 3, ...)
      const first = grid.map((r) => Number(r[0]));
      if (first.every((v, k) => Number.isInteger(v) && v === first[0]! + k) && grid.every((r) => r.length > 1)) {
        grid = grid.map((r) => r.slice(1));
      }
      start = 0;
    }
    const rows = (t === "bus" ? c.bus : c.lines).map((r) => ({ ...r }));
    grid.forEach((cells, j) => {
      const k = i + j;
      if (k >= rows.length) {
        rows.push(t === "bus" ? { ...NEW_BUS, ...spareXY(rows) }
          : { From: 1, To: Math.min(2, Math.max(c.bus.length, 1)), ...NEW_LINE });
      }
      cells.forEach((raw, m) => {
        const col = cols[start + m];
        if (col) rows[k]![col] = pasteValue(col, raw);
      });
    });
    setState({ case: t === "bus" ? { ...c, bus: rows } : { ...c, lines: rows }, outage: null });
    log("info", `Pasted ${grid.length} row(s) into the ${t === "bus" ? "bus" : "branch"} table from row ${i + 1}.`);
  };

  /** A view over some bus rows (generators, loads, shunts): one table row per
   *  bus that has one; edits go to that bus; "add" puts one on a chosen bus. */
  const busView = (box: HTMLElement, c: CaseData, kind: string, cols: string[], has: (b: Rec) => boolean,
    blank: Rec, clear: (b: Rec) => Rec, labels: Record<string, string>) => {
    const at = c.bus.map((b, i) => [b, i] as const).filter(([b]) => has(b)).map(([, i]) => i);
    const rows = at.map((i) => ({ ...c.bus[i]!, Bus: i + 1 }));
    const ed = rowEditor(rows, cols, () => {}, {
      addable: true, name: kind, readonly: ["Bus"], labels, select: kind === "gen" ? { Type: ["Slack", "PV", "PQ"] } : {},
      numeric: cols.filter((x) => x !== "Type"),
      cell: (r, col, v) => act(() => editBus(cur(), at[r]!, { [col]: v }), true),
      onDelete: (r) => act(() => editBus(cur(), at[r]!, clear(cur().bus[at[r]!]!))),
      onAdd: () => pick.focus(),
    });
    for (const inp of ed.querySelectorAll<HTMLElement>("[data-r]")) inp.dataset.r = String(at[Number(inp.dataset.r)]);
    const pick = h("select", "tb-select");
    const free = c.bus.map((b, i) => [b, i] as const).filter(([b]) => !has(b));
    pick.append(new Option(`Add a ${kind === "gen" ? "generator" : kind} at bus...`, ""),
      ...free.map(([b, i]) => new Option(`Bus ${i + 1}${b.Name ? ` (${String(b.Name)})` : ""}`, String(i))));
    pick.addEventListener("change", () => {
      const i = Number(pick.value);
      if (pick.value !== "") act(() => editBus(cur(), i, { ...blank, ...(kind === "gen" && !cur().bus.some((b) => b.Type === "Slack") ? { Type: "Slack" } : {}) }));
    });
    ed.querySelector(":scope > .btn")?.remove();   // "+ Add row": the bus picker below adds one
    const row = h("div", "tbl-add");
    row.append(pick);
    box.replaceChildren(rows.length ? ed : h("p", "cap", `No ${kind === "gen" ? "generators" : kind + "s"} yet.`), row);
  };

  const build = (c: CaseData) => {
    const f = document.activeElement as HTMLElement | null;
    const at = f && el.contains(f) ? [f.dataset.t, f.dataset.r, f.dataset.c] : null;
    const L = unitLabels(c);
    const act_ = c.settings.units === "actual";
    head.replaceChildren(h("h2", "", "Data tables"), h("p", "cap", act_
      ? `Actual units: MW, MVAr, kV, Ω and µS on a ${c.settings.base} MVA system; every bus needs its base kV `
        + "(branch ohms are taken on the From bus base). Change in Properties > Study settings > Data units."
      : `Per unit on ${c.settings.base} MVA. Edit any cell, add or delete rows, or paste a block copied from `
        + "Excel or a textbook PDF into a cell to fill the rows from there. The diagram follows at once."));
    const bcols = busCols(c);
    busBox.replaceChildren(rowEditor(c.bus, bcols, () => {}, {
      index: true, addable: true, name: "bus", select: { Type: BUS_TYPES }, labels: L,
      numeric: bcols.filter((x) => x !== "Type" && x !== "Name"),
      cell: (i, col, v) => act(() => editBus(cur(), i, { [col]: v }), true),
      onAdd: () => act(() => addBus(cur())),
      onDelete: (i) => act(() => delBus(cur(), i)),
      onPaste: (i, ci, b) => act(() => pasteRows("bus", i, ci, b)),
    }));
    const lines = c.lines.map((l) => ({ ...l, InService: l.InService === undefined || l.InService === null
      || Number(l.InService) !== 0 ? "yes" : "no" }));
    lineBox.replaceChildren(rowEditor(lines, LINE_COLS, () => {}, {
      index: true, addable: true, name: "line", labels: L, select: { Kind: LINE_KINDS, InService: IN_SERVICE },
      numeric: LINE_COLS.slice(0, 8),
      cell: (i, col, v) => act(() => editLine(cur(), i, { [col]: col === "InService" ? (v === "no" ? 0 : 1) : v }), true),
      onAdd: () => act(() => addLine(cur())),
      onDelete: (i) => act(() => delLine(cur(), i)),
      onPaste: (i, ci, b) => act(() => pasteRows("line", i, ci, b)),
    }));
    const n = (v: unknown) => Number(v) || 0;
    busView(genBox, c, "gen", GEN_COLS, (b) => b.Type !== "PQ" || n(b.Pg) !== 0 || n(b.Qg) !== 0,
      { Type: "PV", Pg: 0, V: 1 }, (b) => ({ Type: b.Type === "Slack" ? "Slack" : "PQ", Pg: 0, Qg: 0 }), L);
    busView(loadBox, c, "load", LOAD_COLS, (b) => n(b.Pd) !== 0 || n(b.Qd) !== 0,
      { Pd: 0, Qd: 0 }, () => ({ Pd: 0, Qd: 0 }), L);
    busView(shuntBox, c, "shunt", SHUNT_COLS, (b) => n(b.Gs) !== 0 || n(b.Bs) !== 0,
      { Bs: 0, Gs: 0 }, () => ({ Gs: 0, Bs: 0 }), L);
    applyMarks();
    if (at) el.querySelector<HTMLElement>(`[data-t="${at[0]}"][data-r="${at[1]}"][data-c="${at[2]}"]`)?.focus();
  };

  const validate = (c: CaseData) => {
    clearTimeout(timer);
    timer = window.setTimeout(async () => {
      const my = ++token;
      try {
        const r = await post<{ problems: string[]; notes: string[] }>("/api/validate", c);
        if (my !== token) return;
        checked = c;
        marks = cellMarks(r.problems, c);
        applyMarks();
        probs.replaceChildren(...(r.problems.length || r.notes.length
          ? [...r.problems.map((p) => h("div", "msg error", p)), ...r.notes.map((n) => h("div", "msg warn", n))]
          : [h("div", "msg ok", "No problems found. Press Run (F5) to solve.")]));
      } catch (e) {
        report(e, "Checking the tables");
      }
    }, 250);
  };

  const paint = (s: State) => {
    if (s.case !== shown) {
      const prev = shown;
      shown = s.case;
      if (!s.case) {
        for (const b of [busBox, lineBox, genBox, loadBox, shuntBox]) b.replaceChildren();
        notice(probs, "No case loaded.");
        return;
      }
      const sameShape = !!prev && prev.bus.length === s.case.bus.length && prev.lines.length === s.case.lines.length
        && prev.settings.qlim === s.case.settings.qlim && prev.settings.units === s.case.settings.units
        && prev.bus.every((b, i) => ["Type", "Pd", "Qd", "Pg", "Qg", "Gs", "Bs"].every((k) =>
          (Number(b[k]) === 0) === (Number(s.case!.bus[i]?.[k]) === 0) && (k !== "Type" || b[k] === s.case!.bus[i]?.[k])));
      if (!(writing && sameShape)) build(s.case);
    }
    if (s.case && s.activeDoc === "case-tables" && checked !== s.case) validate(s.case);
  };
  subscribe(paint);
  paint(getState());
});

// ---- wizard ------------------------------------------------------------

// "New from textbook data": enter a question's data in real units (MVA, kV,
// ohm, ohm/km, uS, MW, MVAr), check the per-unit conversion, load it as the
// project case. The conversion itself is units.to_pu on the server.

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
        results: null, solvedCase: null, solvedSig: null, selection: null, outage: null, started: true,
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
