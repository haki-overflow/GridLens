// Document views. Each one renders from the last study (or its own API
// call on the solved case) and keeps showing the previous content while a
// new request runs, so the screen never blanks.
import { post, type Rec } from "./api";
import { report } from "./actions";
import { registerDoc } from "./docs";
import { h } from "./shell";
import { getState, isStale, subscribe, type CaseData, type State, type Study } from "./state";
import {
  cards, field, fmt, headline, matrix, notice, NEED_RUN, numIn, section, selectIn, subtabs, table, title,
} from "./ui";
import { stackedPlot } from "./charts";

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
resultsDoc("load-flow", "Load flow", "Bus voltages, generation, line flows and losses.",
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
    const [bus, br] = subtabs(el, ["Bus report", "Branch report"], "lf");
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
resultsDoc("solver-check", "Solver check", "The same case through all three load-flow methods.",
  (el, r) => {
    const ok = r.cmp.every((x) => x.Converged);
    el.append(headline(ok ? "All three methods converge to the same answer."
      : "Not every method converged.", ok ? "ok" : "bad"), table(r.cmp));
  });

// --------------------------------------------------------------- contingency
resultsDoc("contingency", "Contingency N-1", "Each line removed in turn, case re-solved, ranked worst first.",
  (el, r) => {
    const bad = r.n1.filter((x) => x.Status !== "OK" || n(x.Violations) > 0);
    const w = r.n1[0];
    if (w) {
      el.append(headline(w.Status !== "OK"
        ? `Worst outage: line ${w.Outage} leaves the case with no solution. ${bad.length} of ${r.n1.length} outages insecure.`
        : `Worst outage: line ${w.Outage} → min |V| ${fmt(w["Min V (pu)"], 3)} pu at bus ${w["At bus"]}. ${bad.length} of ${r.n1.length} outages insecure.`,
      bad.length ? "bad" : "ok"));
    }
    el.append(table(r.n1, { bad: (x) => x.Status !== "OK" || n(x.Violations) > 0 }));
  });

// --------------------------------------------------------------- PV analysis
resultsDoc("pv-analysis", "PV analysis", "Loads and generation scaled by λ until the case stops solving.",
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
apiDoc("fault-levels", "Fault levels", "Three-phase fault current at every bus from the Zbus.",
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
apiDoc("faults", "Unsymmetrical faults", "SLG, LL, DLG and three-phase faults from sequence networks.",
  (row, refresh, c) => {
    const kind = selectIn(["3-phase", "SLG", "LL", "DLG"], "SLG");
    const bus = selectIn(c.bus.map((_, i) => String(i + 1)), "1");
    const zr = numIn(0), zx = numIn(0);
    const pre = selectIn(["flat", "loadflow"], "flat");
    row.append(field("Fault type", kind), field("Fault bus", bus), field("Zf R (pu)", zr),
      field("Zf X (pu)", zx), field("Prefault", pre));
    for (const i of [kind, bus, zr, zx, pre]) i.addEventListener("change", refresh);
    return () => ({ kind: kind.value, bus: Number(bus.value), zf: { re: Number(zr.value), im: Number(zx.value) },
      prefault: pre.value });
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
    p2!.append(table(V.map((v, i) => ({ Bus: i + 1, V0: v[0], V1: v[1], V2: v[2],
      Va: Vp[i]?.[0], Vb: Vp[i]?.[1], Vc: Vp[i]?.[2] }))));
    p3!.append(table(d.lines as Rec[]));
    const Z = d.Zth as Rec[];
    p4!.append(table([{ "Z1 (pu)": Z[1], "Z2 (pu)": Z[2], "Z0 (pu)": Z[0] }]),
      section("Generators"), table(d.gens as Rec[]), section("Lines and transformers"),
      table(d.branches as Rec[]));
  });

// ---------------------------------------------------------------------- ybus
apiDoc("ybus", "Ybus matrix", "The bus admittance matrix and the terms that form each element.",
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
    el.append(table(its.map((it) => ({ Iter: it.k, "max mismatch": n(it.err).toExponential(3) }))));
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
    return () => ({ show: Math.max(1, Math.min(10, Number(show.value) || 2)) });
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
resultsDoc("report", "Study report", "The study summary the solver produced (the AI write-up is in the Streamlit app).",
  (el, r) => {
    el.append(h("pre", "answer", r.summary));
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
  "/api/symcomp", (el, d) => {
    const s = d.s012 as Rec[];
    const m = (z: Rec | undefined) => Math.hypot(n(z?.re), n(z?.im));
    el.append(headline(`Unbalance V2/V1 = ${(m(s[2]) / Math.max(m(s[1]), 1e-12) * 100).toFixed(2)} %`),
      table([{ Component: "V0 (zero)", Value: s[0] }, { Component: "V1 (positive)", Value: s[1] },
        { Component: "V2 (negative)", Value: s[2] }]));
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
    const units = [
      { a: 200, b: 7.0, c: 0.008, Pmin: 10, Pmax: 85 },
      { a: 180, b: 6.3, c: 0.009, Pmin: 10, Pmax: 80 },
      { a: 140, b: 6.8, c: 0.007, Pmin: 10, Pmax: 70 }];
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

