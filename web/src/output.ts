// Output panel (PSCAD's output window): Messages, Bus report, Branch report,
// Solver check and N-1. Clicking an N-1 row shows that outage on the diagram.
import type { Rec } from "./api";
import { navigate } from "./router";
import { h } from "./shell";
import { getState, isStale, setState, subscribe, type State } from "./state";
import { table } from "./ui";

const TABS = ["Messages", "Bus report", "Branch report", "Solver check", "N-1"] as const;
type Tab = (typeof TABS)[number];
let active: Tab = "Messages";

function messages(s: State): HTMLElement[] {
  if (!s.messages.length) return [h("div", "empty", "No messages yet.")];
  return s.messages.map((m) => {
    const d = h("div", `msg ${m.level}`);
    d.append(h("span", "t", m.t), document.createTextNode(m.text));
    return d;
  });
}

function fresh(s: State) {
  return s.results && !isStale(s) ? s.results : null;
}

const note = (t: string) => [h("div", "empty", t)];

function busReport(s: State): HTMLElement[] {
  const r = fresh(s);
  if (!r || !s.case) return note("Press Run (F5) to fill this table.");
  const rows: Rec[] = r.res.map((x, i) => {
    const b = s.case!.bus[i] ?? {};
    const v = Number(x["V (pu)"]);
    return {
      Bus: x.Bus, Type: b.Type, "V (pu)": v, "Angle (deg)": x["Angle (deg)"],
      "P inj (MW)": Number(x.P_inj) * r.base, "Q inj (MVAr)": Number(x.Q_inj) * r.base,
      "P load (MW)": Number(b.Pd) * r.base, "Q load (MVAr)": Number(b.Qd) * r.base,
      Status: v < r.vmin ? "LOW V" : v > r.vmax ? "HIGH V" : "ok",
    };
  });
  return [table(rows, { digits: { "Angle (deg)": 3, "P inj (MW)": 2, "Q inj (MVAr)": 2,
    "P load (MW)": 1, "Q load (MVAr)": 1 }, bad: (x) => x.Status !== "ok" })];
}

function branchReport(s: State): HTMLElement[] {
  const r = fresh(s);
  if (!r) return note("Press Run (F5) to fill this table.");
  const rows: Rec[] = r.flows.map((f) => ({
    From: f.From, To: f.To, "P from (MW)": Number(f.P_ij) * r.base, "Q from (MVAr)": Number(f.Q_ij) * r.base,
    "P to (MW)": Number(f.P_ji) * r.base, "Q to (MVAr)": Number(f.Q_ji) * r.base,
    "Loss (MW)": Number(f.Loss_P) * r.base, "Loss (MVAr)": Number(f.Loss_Q) * r.base,
  }));
  return [table(rows, { digits: Object.fromEntries(Object.keys(rows[0] ?? {}).map((k) => [k, 2])) })];
}

function solverCheck(s: State): HTMLElement[] {
  const r = fresh(s);
  if (!r) return note("Press Run (F5) to fill this table.");
  return [table(r.cmp)];
}

function n1(s: State): HTMLElement[] {
  const r = fresh(s);
  if (!r || !s.case) return note("Press Run (F5) to fill this table.");
  const t = table(r.n1, { bad: (x) => Number(x.Violations) > 0 || x.Status !== "OK" });
  const lines = s.case.lines.map((l) => `${l.From}-${l.To}`);
  const trs = Array.from(t.querySelectorAll("tr")).slice(1);
  trs.forEach((tr, i) => {
    const k = lines.indexOf(String(r.n1[i]?.Outage));
    if (k < 0) return;
    tr.classList.add("click");
    if (s.outage === k) tr.classList.add("on");
    tr.title = "Show this outage on the diagram";
    tr.addEventListener("click", () => {
      setState({ outage: s.outage === k ? null : k });
      navigate("canvas");
    });
  });
  const cap = h("div", "empty", s.outage !== null
    ? `Showing the outage of line ${lines[s.outage]} on the diagram. Click the row again to clear.`
    : "Click a row to show that outage on the diagram.");
  return [cap, t];
}

const BODY: Record<Tab, (s: State) => HTMLElement[]> = {
  Messages: messages, "Bus report": busReport, "Branch report": branchReport,
  "Solver check": solverCheck, "N-1": n1,
};

export function mountOutput(tabs: HTMLElement, body: HTMLElement): void {
  const els = new Map<Tab, HTMLElement>();
  for (const t of TABS) {
    const el = h("div", "tab", t);
    el.setAttribute("role", "tab");
    el.tabIndex = 0;
    const pick = () => {
      active = t;
      paint(getState(), true);
    };
    el.addEventListener("click", pick);
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") pick();
    });
    els.set(t, el);
    tabs.append(el);
  }
  let shown = "";
  const paint = (s: State, force = false) => {
    for (const [t, el] of els) {
      el.classList.toggle("active", t === active);
      el.setAttribute("aria-selected", String(t === active));
    }
    const key = JSON.stringify([active, s.messages.length, s.solvedSig, isStale(s), s.outage,
      active === "Bus report" || active === "Branch report" ? s.case?.bus.length : 0]);
    if (!force && key === shown) return;
    shown = key;
    const top = body.scrollTop;
    body.replaceChildren(...BODY[active](s));
    body.scrollTop = active === "Messages" ? body.scrollHeight : top;
  };
  subscribe((s) => paint(s));
  paint(getState());
}
