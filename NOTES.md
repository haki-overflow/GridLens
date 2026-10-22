# Notes for the next session (v2.6: phase 1 done)

Read first: AGENTS.md, then docs/design-v2.md (plan, gates, data model). Full design doc with
diagrams: https://claude.ai/artifact/Q58NCpRtLWeRMAd5N5vttV

## Rules from the user
- Versions: every change bumps the version by 0.1 and gets its own branch from the previous one:
  v2.0 -> v2.1 -> v2.2 ... Bump web/package.json, api/server.py (FastAPI version) and the brand
  label in web/src/shell.ts. Never push to an older branch.
- Work autonomously, small commits, push after each; tell the user briefly what changed.
- Keep the theme.css palette exactly as is. Ask before any new dependency.
- scipy is in (v2.1: requirements.txt, AGENTS.md dependency list).
- Golden snapshots (2026-10-22, standing OK for phase 1 engine steps): regenerate them
  (GOLDEN_WRITE=1 pytest tests/test_golden_api.py tests/test_core.py) once every result matches the
  old snapshot within 1e-9; put the largest difference in the commit message and tell the user.
  Per-iteration mismatches (hist) can move more when the old method was less exact (v2.1: 2.1e-9,
  the old numerical Jacobian; the new value matched the analytical trace to 6e-15): say so.
  Phase 1 is done, so ask again before regenerating in phase 2. A planned change that moves
  results on purpose (v2.5: the IEEE 14 7-8 N-1 row) was regenerated after a diff showing only
  the intended rows changed, and reported; confirm that practice with the user too.
- If context gets above ~85%, update this file and tell the user to /clear.

## State
- v1.6 is done (any-case input, imports, islands, fallback, Falstad-style plan).
- v2.0: version 2.0, docs/design-v2.md, this file.
- v2.1: sparse Ybus (solver.ybus_sparse) and sparse Newton-Raphson with the analytical Jacobian
  (solver._jacobian fills a fixed pattern; splu). case2383wp 49 ms, case1354pegase 37 ms, case118
  7 ms, 5-bus 4.6 ms (v2.0: 47.5 s, 12.5 s, 0.1 s, 6.3 ms). Results within 1.2e-12 of v2.0.
  139 tests pass (tests/test_engine.py is new).
- v2.2: sparse Fast Decoupled (B', B'' factorised once; case2383wp 33 ms, 17 its; results within
  4e-13 of v2.1) and solver.dc_loadflow (MATPOWER makeBdc model; case2383wp 9 ms). DC matches
  PYPOWER rundcpf to 1e-11 on case9..case2383wp; AC NR matches PYPOWER runpf to round-off on
  case9, 14, 30, 118, 1354pegase. 146 tests pass.
- Found: case300 and case2383wp differ from MATPOWER by up to 6e-5 pu because of known issue 7
  (tapped branches with B != 0, here negative B: MATPOWER Yff = (y + jB/2)/a^2, GridLens
  y/a^2 + jB/2). Fix it in the reference-suite step: branch_y, branch_admittances and
  working.ybus_parts ("charging jB/2/a^2" at the From side when tapped). No preset has such a
  branch, so the golden snapshots do not move.
- Cross-check tool (scratch only, not a dependency): pip install --target <dir> pypower, then
  pypower.api rundcpf / runpf on a ppc built from the same .m text (formats._matrix).
- v2.3: only R = X = 0 (in service) is refused; negative X and X = 0 with R > 0 are accepted.
  FD raises LinAlgError for X = 0 (fallback -> NR; method comparison shows FD not converged),
  DC and the FD trace raise ValueError, a zero sequence reactance is a plain error. case300 now
  loads and solves (NR 5 its, 15 ms; FD 15 its). tests/data/case300.m added. 151 tests pass.
- Seen on case300: Gauss-Seidel does not converge in 5000 sweeps and takes 18 s; run_study's
  3-method check runs it on every study. Phase 2 item (with "hide Show working above 30 buses").
- case300.m stored Vm/Va are not MATPOWER's runpf answer (up to 9.8 deg away): for the reference
  suite use runpf values (PYPOWER runpf gives MATPOWER's algorithm), not the stored ones.

- v2.4: model.py (element model: bus / branch / gen / load / shunt tables, stable ids, MW / MVAr),
  from_tables / to_tables, results keyed by id with MATPOWER's generator sharing (matches PYPOWER
  runpf to 1e-11 on case24_ieee_rts, 33 units); formats.read_matpower_model keeps every
  generator and read_matpower now goes through it (v1 output identical on all 7 cases, and
  case2383wp reads in 0.09 s instead of 0.6 s); gridcore.solve_case(case). tests/test_model.py,
  tests/data/case24_ieee_rts.m. 162 tests pass. API and web still use the v1 tables.
- Later (phase 3/4): API and web on the model; validation messages by id / bus number (prep_case
  still says "bus rows", e.g. outage messages on imported cases name rows, not file numbers);
  readers for CDF / CSV straight to the model.

- v2.5: N-1 and the P-V curve use generator Q limits when qlim is on; an outage that cuts buses
  off from every Slack solves the rest (Status ISLANDED, Lost load (MW), Buses cut off), also in
  /api/outage and the canvas (greyed buses, chip). Golden snapshots: only the IEEE 14 7-8 row
  changed (FAILED -> ISLANDED, 0 MW lost: bus 8 is a synchronous condenser); regenerated as a
  planned change and reported to the user. 165 tests pass.

- v2.6: MATPOWER's transformer model (From-side charging behind the tap) and the reference
  suite: tests/test_reference.py, ten MATPOWER cases (case9 ... case2383wp, .m files in
  tests/data) against tests/data/reference_pf.json (PYPOWER runpf / rundcpf; tools/reference_pf.py,
  dev tool only). All match to round-off; gate passed (case2383wp NR 0.07 s). 196 tests pass.

## Next: Phase 2, studies and jobs (docs/design-v2.md; one version bump per change, v2.7 on)
Gate: all 2,896 branch outages of case2383wp in under 2 min; IEC TR 60909-4 examples match.
Suggested order:
1. Teaching methods only where they make sense: run_study's 3-method check runs dense
   Gauss-Seidel (case300: 5000 sweeps, 18 s, no convergence); skip GS above ~30 buses (say so in
   the table) and hide Show working above 30 buses (design "fix on the way").
2. Jobs: long studies (N-1, P-V) as background jobs with progress and cancel (API job endpoints,
   polling or WebSocket; web progress bar instead of a frozen Run). Layout progress too.
3. Fast N-1: DC screening with PTDF / LODF from solver.dc_model, then AC (studies.outage) only for
   the outages that screen as bad or islanding; generator outages; transformers as their own kind.
4. Continuation power flow with Q limits (PV / QV curves); check the noses of IEEE 14 / 118.
5. IEC 60909 short circuit on the sparse Ybus (sparse LU, not inv): all buses < 1 s on
   case2383wp; IEC TR 60909-4 examples.
Open items seen in phase 1: validation and outage messages name bus rows, not file bus numbers
(imported cases); the API and web still use the v1 tables (move to model.Case in phase 3).

## Useful
- MATPOWER cases: https://raw.githubusercontent.com/MATPOWER/matpower/master/data/<case>.m
  (case9, case14, case30, case118 already in tests/data).
- Browser checks: python tools/walkthrough.py, CHROME=/opt/pw-browsers/chromium-1194/chrome-linux/chrome
  python tools/shots.py http://localhost:8000 - <out dir>. Restart ./run_workspace.sh after Python changes.
