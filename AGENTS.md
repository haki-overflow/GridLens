# Power System Analysis (load flow, N-1, short circuit, AI report)

## What this project does
Python tool that solves an N-bus power system and produces:
1. **Data**: bus voltages/angles, line flows, losses, N-1 contingency table, fault table (all exportable as CSV).
2. **Matplotlib figures**: network diagram colored by bus voltage, voltage profile, post-fault voltages, convergence history, method comparison.
3. **A written report**: the solver computes everything, a local open-weight LLM (Gemma via LM Studio) only explains the results in plain English.

Built for Hacktoberfest, so everything must use open-weight models and open-source libraries only.

## Golden rules
- **The solver does all the math. The LLM never computes or invents numbers.** The report prompt may only use numbers passed in the summary.
- All quantities are **per unit**. Base MVA is a setting. Line `B` = total line charging susceptance (split B/2 at each end).
- Do NOT change solver logic unless explicitly asked. Refactors are move-only; verify with a comparison script that old and new outputs match exactly.
- Keep code short and readable. Small functions, one job per module, easy to debug.
- Use only: numpy, pandas, matplotlib, plotly, streamlit, requests, pytest, fastapi, httpx, uvicorn. Ask before adding a dependency.
- Fix bugs in the module that owns them. Do not patch around them in callers.

## Layout (v1.3: few files, each with one job)
```
solver.py      METHODS, build_ybus, injections, newton_raphson, fast_decoupled,
               gauss_seidel, solve_loadflow; solve_with_qlimits (PV -> PQ switching)
studies.py     contingency (N-1), outage (one line out), pv_curve (load
               scaling to the nose), fault_analysis (3-phase, Zbus)
working.py     ybus_parts, gauss_seidel_trace (alpha), newton_trace (analytical
               J1..J4), fast_decoupled_trace, results_tables, answer_text
topics.py      textbook calculators: symcomp (phase <-> sequence), tline (ABCD),
               seqfaults (sequence networks, 3-phase / SLG / LL / DLG), dispatch
               (economic dispatch), units (real units -> per unit)
gridcore.py    prep_case (validation), run_study, outage; the CASES presets and
               COORDS; ai_report / lm_models (LM Studio). No Streamlit; used by
               app.py and the API
figures.py     palette from theme.css, matplotlib / Plotly styles, matplotlib
               charts, the interactive one-line diagram (layout, routing, hover).
               No Streamlit (the API imports it)
ui.py          Streamlit helpers and pages: HTML helpers, editable tables,
               Problem input, textbook topic pages, worked-solution pages
app.py         Streamlit GUI (main): pages, modes, inputs, cached studies
theme.css      all colours/sizes as CSS variables (single KiCad-style dark theme)
api/           FastAPI server (server.py endpoints, schema.py JSON helpers);
               run_api.sh, docs at http://localhost:8000/docs
web/           PSCAD-style workspace (Vite + TypeScript + D3), 8 files in
               src/ (see "Workspace UI"); run_workspace.sh serves it on :8000
tools/         names.py (proves a merge lost nothing), check_contrast.py,
               sync_tokens.py, shots.py
legacy/        power_flow_methods.py + check_refactor.py: the pre-refactor
               baseline, kept for reference only (not part of the app)
tests/         pytest suite (run: venv/bin/python -m pytest)
```
Where to find things: one job per file, banner comments (`# ====`, `// ----`)
mark the sections inside it in the order of the small files they replaced.
New study maths goes in its own module next to the existing ones (never inside
`solver.py`), with a page module for the UI and tests that tie it back to the
solver where they overlap.
The original single-file version lives in `legacy/power_flow_methods.py`.

## Data model
- **Bus DataFrame** columns: `Type` (Slack/PV/PQ), `V`, `Pg`, `Qg`, `Pd`, `Qd`, `Bs` (shunt susceptance). Optional: `Qmin`, `Qmax` (pu generator Q limits), `kV` (base kV), `x`, `y` (diagram position). The solver ignores the optional columns.
- **Problem input tables** (real units) are defined in the `topics.py` units section; `units.to_pu` returns the bus/line DataFrames above plus `kv`, `zones`, `table`.
- **Sequence data** (`topics.py`, sequence-fault section): gens `Bus, X1, X2, X0, Xn, Conn`; branches `From, To, Kind, X1, X2, X0, Conn From, Conn To`.
- **Line DataFrame** columns: `From`, `To` (1-based bus numbers), `R`, `X`, `B`, `Tap` (off-nominal ratio, 1 = none).
- `solve_loadflow(bus, lines, method, tol)` returns `(res, flows, ok, hist)`:
  - `res`: Bus, V (pu), Angle (deg), P_inj, Q_inj
  - `flows`: From, To, P_ij, Q_ij, P_ji, Q_ji, Loss_P, Loss_Q
  - `ok`: converged flag, `hist`: error per iteration (`len(hist) - 1` = iterations)

## Methods
- Newton-Raphson (numerical central-difference Jacobian; `working.newton_trace` uses the analytical one for display)
- Fast Decoupled (XB version: B' from series X, B'' from Ybus imaginary part)
- Gauss-Seidel (PV buses: Q recomputed each sweep, |V| held at setpoint)

## Run
```
pip install streamlit numpy pandas matplotlib plotly requests pytest
streamlit run app.py
```
LM Studio is only needed for the AI report: Developer tab, load Gemma, Start Server (port 1234). The app lists loaded models from `http://127.0.0.1:1234/v1/models`; no model id is hardcoded.

## Report generation
- Summary string is built from solver results (bus table, total loss in MW, voltage limits, worst N-1 outages) and sent to `/chat/completions`.
- Prompt must say: use ONLY the given numbers.
- Output should include: voltage violations, losses, worst contingencies, practical suggestions.
- Handle LM Studio errors clearly (wrong model id vs server unreachable are different errors).

## Known issues / planned fixes (do as separate changes, not mixed into refactors)
1. Gauss-Seidel ignores `tol` in `solve_loadflow`; pass it through so the method comparison is fair.
2. (fixed in v1.3) `ai_report` now raises on HTTP errors.
3. The Fault levels page (`studies.fault_analysis`) still uses a single base kV; the Unsymmetrical faults page (`topics.py`, sequence-fault section) uses each bus's own kV.
4. Numerical Jacobian is slow on large cases; an analytical one exists in `working.jacobian` if the solver ever needs it.
5. PV Q limits are optional (`solver.solve_with_qlimits`, default off) and apply to the main load flow only, not to N-1 / P-V / the solver check.
6. Sequence networks are reactance-only; Δ-Y 30° phase shifts are not modelled.

## UI (app.py + ui.py + figures.py)
- Sidebar **Mode**: Quick (case source only), Standard (adds a collapsible **Study settings** group: method, base MVA, voltage limits), Advanced (adds tap / shunt / generator-Q-limit toggles and solver tolerance to it). Untouched fields use defaults. Base MVA is stored in `_base` (the widget is rebuilt from it), so Problem input can set it.
- `Tap` and `Bs` columns appear only when their Advanced toggles are on; `_prep` in `app.py` fills `Tap = 1`, `Bs = 0` and missing `B` before calling the solver, and warns when hidden non-default data exists.
- All studies (N-1, solver check, PV analysis, fault levels, study report) run on **Run study** (Dashboard, below the case tables) or **Re-run study** (header of every results page). The banner is drawn after the page runs and shows amber STALE when `_inputs_sig(cfg)` differs from the last run. Pages (st.navigation, grouped): Load flow (Dashboard, Problem input, Network diagram, Solver check), Worked solution (Ybus matrix, Iterations, Worked answer), Studies (Contingency N-1, PV analysis, Fault levels, Unsymmetrical faults, Economic dispatch), Calculators (Symmetrical components, Line parameters), Report (Study report, with the single "Download study report" button). Pages in `STANDALONE` need no solved case.
- `_study()` is `st.cache_data`-cached on case + settings; the last solved inputs and report sit in a `st.cache_resource` store so a page opened in a new browser tab shows results without a re-run.
- Optional bus CSV columns `x`, `y` (diagram units, y down; whole numbers = grid column/row) override the one-line layout; presets can carry `gridcore.COORDS`.
- Validation happens in `gridcore.prep_case` (`_prep` in app.py is a thin wrapper): friendly messages for slack count, lines to missing buses, `X = 0`, disconnected networks, non-numeric cells. Fix validation bugs in gridcore.py, not in `solver.py`.
- Everything lives in `st.session_state` under stable keys; table editor keys carry a version counter so preset/upload/column-toggle switches rebuild cleanly.
- Theme: dark only. Colours live in `theme.css` `:root`; `ui.py` injects it and `figures.py` sets matplotlib/Plotly styles from it; `.streamlit/config.toml` is `base = "dark"` with the same colours. One accent, `--accent` #3B82F6 (active page, primary buttons, selected options, focus); `--hazard` #F2B705 rules the header; red/amber only for violations and STALE. Run `tools/check_contrast.py` after colour changes (AA 4.5:1). Keep app.py free of styling.

## Testing
- `venv/bin/python -m pytest` (tests/): per unit, Q limits (identical results with no binding limit), Ybus terms and symmetry, analytical vs numerical Jacobian, every trace ends on the solver's answer, GS/NR/FD agree within 1e-4 pu, SLG = 3Vf/(Z1+Z2+Z0+3Zf) and LL/DLG boundary conditions, dispatch, ABCD reciprocity.
- Textbook worked examples go in `tests/test_textbook.py` with the book's data and its printed precision.
- After any refactor, run a comparison script that asserts old and new outputs match exactly.

## Models and tooling
- Coding agent: open-weight model via opencode (user's choice, e.g. DeepSeek).
- In-app report: local Gemma through LM Studio (OpenAI-compatible API).
- `opencode.json` is optional and only configures opencode itself. The app does not read it.

## Workspace UI (v1.4)
- `api/server.py` + `api/schema.py`: JSON endpoints over the existing modules (no maths in the API). `gridcore.py` holds the pure `prep_case`, `run_study`, `outage` that both the Streamlit app and the API call.
- `web/src/` (Vite + TypeScript + D3, no framework), 8 files in import order: `ui.ts` (DOM helpers, tables, icons, zip) -> `app.ts` (API, busy bar, router, project state in localStorage, actions) -> `charts.ts` (stackedPlot, phasorDiagram) -> `documents.ts` (document registry, study views, textbook wizard) -> `canvas.ts` (D3 diagram, layout from `/api/layout`) -> `panels.ts` (workflow list, property grid with Edit picker, collapsed message log) -> `shell.ts` (layout, splitters, tabs, toolbar, title/status bar) -> `main.ts` (entry). Lower files never import higher ones (no cycles).
- Colours come only from `web/src/tokens.css`, a copy of the `:root` block in `theme.css`; edit `theme.css` and run `python tools/sync_tokens.py` (a test fails if they differ).
- Bar positions are stored as bus columns `x`, `y` in raw diagram units that are never all whole numbers (`figures._xy_columns` reads whole numbers as grid cells). They are not part of the staleness check.
- No calculation code lives in `web/`: every number comes from the API.
- v1.4 navigation: six views (Network, Solve, Safety check, Short circuit, Show working, Tools) defined in `VIEWS` in `app.ts`, each with sub-tabs; routes are `#/view/sub` (old `#/doc/<id>` still works). A Start screen shows until an example/file/textbook case is chosen. Diagram options (Fit/Grid/Flows/Angles) sit on the diagram; File menu holds open/save/export. Jargon tooltips come from `GLOSSARY` in `ui.ts`.
- `python tools/walkthrough.py` (workspace running) walks every view like a new user and fails on console errors or page scroll.
- v1.5: Properties panel can add/delete buses and lines (`addBus`, `delBus`, `addLine`, `delLine` in `panels.ts`; deleting a bus drops its lines and renumbers); dispatch units and sequence data are editable in place (`rowEditor` in `documents.ts`); `tests/test_textbook.py` checks the solver against closed forms.
