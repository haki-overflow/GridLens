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
- Use only: numpy, scipy (sparse matrices, v2 engine), pandas, matplotlib, plotly, streamlit, requests, pytest, fastapi, httpx, uvicorn. Ask before adding a dependency.
- Fix bugs in the module that owns them. Do not patch around them in callers.

## Layout (v1.3: few files, each with one job)
```
solver.py      METHODS, build_ybus (dense, for teaching), branch_admittances,
               ybus_sparse (the engine's Ybus), newton_raphson (sparse),
               fast_decoupled, gauss_seidel, solve_loadflow, branch_flows;
               solve_with_qlimits (PV -> PQ switching)
studies.py     contingency (N-1), outage (one line out), pv_curve (load
               scaling to the nose), fault_analysis (3-phase, Zbus)
working.py     ybus_parts, gauss_seidel_trace (alpha), newton_trace (analytical
               J1..J4), fast_decoupled_trace, results_tables, answer_text
topics.py      textbook calculators: symcomp (phase <-> sequence), tline (ABCD),
               seqfaults (sequence networks, 3-phase / SLG / LL / DLG), dispatch
               (economic dispatch), units (real units -> per unit)
gridcore.py    prep_case (validation, islands), loadflow (fallback chain,
               failure_hint), run_study, outage, line_loading; the CASES
               examples; ai_report / lm_models (LM Studio). No Streamlit; used
               by app.py and the API
formats.py     case file readers: MATPOWER .m, IEEE common data format, CSV
               templates -> GridLens case (per unit, bus rows, file numbers in Num)
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
- **Bus DataFrame** columns: `Type` (Slack/PV/PQ), `V`, `Pg`, `Qg`, `Pd`, `Qd`, `Bs` (shunt susceptance). Optional: `Gs` (shunt conductance, in the Ybus), `Va` (deg: the Slack's reference angle and the set-point start), `Qmin`, `Qmax` (pu generator Q limits), `kV` (base kV), `Num`, `Name` (labels; lines still refer to bus rows 1..N), `x`, `y` (diagram position).
- Case setting `units`: "pu" (default) or "actual" (MW, MVAr, kV, ohm, uS); `topics.case_to_pu` converts per bus base kV inside prep_case, so everything after prep_case is per unit.
- **Problem input tables** (real units) are defined in the `topics.py` units section; `units.to_pu` returns the bus/line DataFrames above plus `kv`, `zones`, `table`.
- **Sequence data** (`topics.py`, sequence-fault section): gens `Bus, X1, X2, X0, Xn, Conn`; branches `From, To, Kind, X1, X2, X0, Conn From, Conn To`.
- **Line DataFrame** columns: `From`, `To` (1-based bus rows), `R`, `X`, `B`, `Tap` (off-nominal ratio, 1 = none). Optional: `Shift` (deg, phase shifter at the From side, t = a e^{j shift}), `Rate` (MVA, 0 = none), `InService` (0 = out: stays in the table, no flow, skipped by N-1), `Kind` ("line" / "trafo", drawing only). `solver.branch_y` gives a branch's four admittances; with Shift = 0 it is exactly the old tap model.
- Islands: one Slack per island; prep_case names islands without one. The solver's Jacobian is block-diagonal across islands, so solve_loadflow needs only "at least one Slack".
- `solve_loadflow(bus, lines, method, tol, init="flat", damp=1.0, max_iter=None)` returns `(res, flows, ok, hist)` (init "setpoint" starts from V and Va; damp < 1 shortens Newton steps). The app calls `gridcore.loadflow`, which tries the chosen method first (identical when it converges) and then `ATTEMPTS`:
  - `res`: Bus, V (pu), Angle (deg), P_inj, Q_inj
  - `flows`: From, To, P_ij, Q_ij, P_ji, Q_ji, Loss_P, Loss_Q
  - `ok`: converged flag, `hist`: error per iteration (`len(hist) - 1` = iterations)

## Methods
- Newton-Raphson (v2.1: sparse, analytical Jacobian as MATPOWER's newtonpf, one sparse LU per iteration; `working.newton_trace` shows the same steps with dense J1..J4)
- Fast Decoupled (XB version: B' from series X, B'' from Ybus imaginary part)
- Gauss-Seidel (PV buses: Q recomputed each sweep, |V| held at setpoint)

## Run
```
pip install -r requirements.txt
streamlit run app.py
```
LM Studio is only needed for the AI report: Developer tab, load Gemma, Start Server (port 1234). The app lists loaded models from `http://127.0.0.1:1234/v1/models`; no model id is hardcoded.

## Report generation
- Summary string is built from solver results (bus table, total loss in MW, voltage limits, worst N-1 outages) and sent to `/chat/completions`.
- Prompt must say: use ONLY the given numbers.
- Output should include: voltage violations, losses, worst contingencies, practical suggestions.
- Handle LM Studio errors clearly (wrong model id vs server unreachable are different errors).

## Known issues / planned fixes (do as separate changes, not mixed into refactors)
1. (fixed in v1.6) Gauss-Seidel now honours `tol` in `solve_loadflow`, so the method comparison is fair.
2. (fixed in v1.3) `ai_report` now raises on HTTP errors.
3. (fixed in v1.6) Fault kA uses each bus's own base kV where the case has one (the input is the default for the rest).
4. (fixed in v2.1) Newton-Raphson uses the sparse analytical Jacobian: case2383wp solves in about 50 ms (47 s before). Results moved by at most 1.2e-12, and the golden snapshots were regenerated with the user's OK. The full study on big cases is still slow (N-1 and the P-V curve re-solve once per outage / step, and the 3-method check runs dense Gauss-Seidel); that is phase 2.
7. MATPOWER divides a transformer's charging by tap²; GridLens keeps B/2 unscaled at both ends (only differs for a tapped branch with B > 0).
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
- `venv/bin/python -m pytest` (tests/): per unit, Q limits (identical results with no binding limit), Ybus terms and symmetry, analytical vs numerical Jacobian, sparse Ybus = dense Ybus and the sparse Jacobian vs central differences (`test_engine.py`), every trace ends on the solver's answer, GS/NR/FD agree within 1e-4 pu, SLG = 3Vf/(Z1+Z2+Z0+3Zf) and LL/DLG boundary conditions, dispatch, ABCD reciprocity.
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
- v1.5: Properties panel can add/delete buses and lines (deleting a bus drops its lines and renumbers); dispatch units and sequence data are editable in place (`rowEditor` in `documents.ts`); `tests/test_textbook.py` checks the solver against closed forms.
- v1.5 drawing: `canvas.ts` uses semantic zoom: the d3 zoom transform is stored, not put on a `<g>`; every point is drawn at `t.applyX/applyY` and redrawn once per animation frame, so strokes and text are CSS pixels (bar 5px, branch 1.5px, labels 12/11px) and stay sharp. Drags convert back with `t.invert()`. Do not reintroduce unit-sized fonts or strokes.
- Drawing tools on the canvas: Select (V), Bus (B), Line (L), Transformer (T, adds line column `Kind = "trafo"`, which prep_case passes through and the solver ignores), Generator (G), Load (D), Delete (Del); Esc = Select. The first canvas edit writes `x`, `y` to every bus. When `/api/validate` reports problems the canvas skips `/api/layout`, draws from `x`, `y` with simple connectors and shows a warning chip.
- Shared case actions live in `app.ts` (`addBus`, `addLine`, `delBus`, `delLine`, `editBus`, `editLine`, `newNetwork`); the canvas, Properties and Data tables all use them. Each `setState({case})` pushes one undo step (history of 50; a drag pushes once, on drag end); `undo`/`redo` (Ctrl+Z, Ctrl+Shift+Z / Ctrl+Y, toolbar buttons) swap the case without pushing.
- Network > Data tables (doc `case-tables` in `documents.ts`): bus and line tables built with `rowEditor` (index, select, numeric columns, cell/add/delete/paste callbacks); bad cells are marked from the `/api/validate` messages. `tools/walkthrough.py` also draws a network, solves it, edits Pd in the tables and zooms.

## v1.6: any case
- Golden rule for v1.6+: `tests/test_golden_api.py` snapshots every study endpoint on both examples (`tests/data/api_golden.json`); a change that moves a number must be an approved maths change, then `GOLDEN_WRITE=1 pytest tests/test_golden_api.py`. `tests/test_core.py` compares the old columns only (new columns are allowed).
- `/api/import` (formats.py) returns a case with taps and shunts on; the web File menu (New case..., Open or import a file..., Examples) replaces the toolbar example select; no example loads by itself.
- Web settings gain `init`, `fallback`, `freq`, `units` (Properties > Study settings / Advanced); web defaults have taps and shunts on (the API defaults stay off for the snapshots).
- Data tables: Buses / Branches / Generators / Loads / Shunts (`case-tables` in documents.ts); Generators, Loads and Shunts are views over bus rows (`busView`); headers carry units from `unitLabels`.
- Layout: `figures.layout` uses `_layered` up to `BIG` = 24 buses and `_stress_rows` (stress majorization on hop distances, rows of equal count, packed) with `_straight` branches above; the canvas writes only bus numbers when zoomed out and shrinks symbols (`symUnit` 8-60 px). A new case opens fitted when the fit keeps names readable (k >= `NAMES_K` 14 px per unit); a bigger one opens at `READ_K` (22) around its Slack bus, kept inside the drawing, with a "Showing n of N buses" chip that fits on click (Fit / Ctrl+0 always shows all).
- Chrome colours: selection is `--hdr` fill with an `--axis` border; Run is the only accent (`--sel` fill); blue (`--accent`) remains only for the selected element on the diagram.
- Messages: the log holds the current run only (cleared by Run, a new case, and the Clear button) and is not saved to localStorage.

## v2: engine (plan in docs/design-v2.md)
- Golden snapshots: standing OK from the user (2026-10-22) to regenerate them (`GOLDEN_WRITE=1` for `test_golden_api.py` and `test_core.py`) for phase 1 engine changes, after checking every result against the old snapshot within 1e-9; give the largest difference in the commit message.
- v2.1: `solver.ybus_sparse` builds Ybus as a scipy CSR array from `branch_admittances` (the vectorised `branch_y`, in-service rows only). `build_ybus` (dense, a Python loop) stays for the worked solution, the Ybus page and the Zbus fault study; `test_engine.py` checks that the two agree. `newton_raphson` works on the sparse Ybus: `_jacobian(Y, ang, mag)` fixes the sparse pattern once per solve and refills it on every iteration, and an exactly singular step raises `LinAlgError`, as numpy does. `branch_flows` computes every branch at once. Fast Decoupled is still dense (moving in v2.2); Gauss-Seidel stays dense (teaching only).
