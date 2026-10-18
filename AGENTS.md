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
- Use only: numpy, pandas, matplotlib, streamlit, requests, pytest. Ask before adding a dependency.
- Fix bugs in the module that owns them. Do not patch around them in callers.

## Layout (target)
```
cases.py       _bus, _lines, CASES (5-bus demo, IEEE 14-bus)
solver.py      METHODS, build_ybus, injections, newton_raphson, fast_decoupled,
               gauss_seidel, solve_loadflow
studies.py     contingency (N-1), fault_analysis (3-phase, Zbus)
plotting.py    draw_network and other matplotlib figures
ui_theme.py    control-room palette, CSS injection (banner, badges, metric
               cards), mpl_dark matplotlib style
ai_report.py   LMSTUDIO_URL, lm_models, ai_report
app.py         Streamlit GUI (main): modes, dynamic inputs, validation, exports
```
If the code is still in the single file `power_flow_methods.py`, it contains all of the above in this order: solver, local AI, study extras, cases, GUI.

## Data model
- **Bus DataFrame** columns: `Type` (Slack/PV/PQ), `V`, `Pg`, `Qg`, `Pd`, `Qd`, `Bs` (shunt susceptance).
- **Line DataFrame** columns: `From`, `To` (1-based bus numbers), `R`, `X`, `B`, `Tap` (off-nominal ratio, 1 = none).
- `solve_loadflow(bus, lines, method, tol)` returns `(res, flows, ok, hist)`:
  - `res`: Bus, V (pu), Angle (deg), P_inj, Q_inj
  - `flows`: From, To, P_ij, Q_ij, P_ji, Q_ji, Loss_P, Loss_Q
  - `ok`: converged flag, `hist`: error per iteration (`len(hist) - 1` = iterations)

## Methods
- Newton-Raphson (numerical central-difference Jacobian)
- Fast Decoupled (XB version: B' from series X, B'' from Ybus imaginary part)
- Gauss-Seidel (PV buses: Q recomputed each sweep, |V| held at setpoint)

## Run
```
pip install streamlit numpy pandas matplotlib requests pytest
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
2. `ai_report` lacks `r.raise_for_status()`; errors surface as a misleading "not reachable".
3. Short circuit uses a single base kV for all buses; wrong kA on multi-voltage cases like IEEE 14.
4. Numerical Jacobian is slow on large cases; analytical Jacobian only if big cases are needed.
5. No PV Q limits / PV-to-PQ switching (document as a limitation).

## UI (app.py + ui_theme.py)
- Sidebar **Mode**: Quick (case source + study checkboxes only), Standard (adds method, base MVA, voltage limits), Advanced (adds tap/shunt column toggles, solver tolerance). Untouched fields use defaults.
- `Tap` and `Bs` columns appear only when their Advanced toggles are on; `_prep` in `app.py` fills `Tap = 1`, `Bs = 0` and missing `B` before calling the solver, and warns when hidden non-default data exists.
- Study checkboxes (N-1, method comparison, short circuit, AI report) gate both computation and tabs: only ticked studies run; short-circuit fields and the LM Studio picker live inside their own tabs.
- Validation happens in `_prep` (app.py owns it): friendly messages for slack count, lines to missing buses, `X = 0`, disconnected networks, non-numeric cells. Fix validation bugs there, not in `solver.py`.
- Everything lives in `st.session_state` under stable keys; table editor keys carry a version counter so preset/upload/column-toggle switches rebuild cleanly.
- Theme code (CSS injection, banner SVG, badge helper, `mpl_dark`) lives in `ui_theme.py`; `.streamlit/config.toml` carries the base dark theme. Keep app.py free of styling.

## Testing
- `pytest`: all three methods converge on both cases and agree on bus voltages within 1e-4 pu; total loss > 0; N-1 returns one row per line.
- After any refactor, run a comparison script that asserts old and new outputs match exactly.

## Models and tooling
- Coding agent: open-weight model via opencode (user's choice, e.g. DeepSeek).
- In-app report: local Gemma through LM Studio (OpenAI-compatible API).
- `opencode.json` is optional and only configures opencode itself. The app does not read it.