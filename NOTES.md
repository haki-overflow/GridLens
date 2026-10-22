# Notes for the next session (v2.1)

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
- If context gets above ~85%, update this file and tell the user to /clear.

## State
- v1.6 is done (any-case input, imports, islands, fallback, Falstad-style plan).
- v2.0: version 2.0, docs/design-v2.md, this file.
- v2.1: sparse Ybus (solver.ybus_sparse) and sparse Newton-Raphson with the analytical Jacobian
  (solver._jacobian fills a fixed pattern; splu). case2383wp 49 ms, case1354pegase 37 ms, case118
  7 ms, 5-bus 4.6 ms (v2.0: 47.5 s, 12.5 s, 0.1 s, 6.3 ms). Results within 1.2e-12 of v2.0.
  139 tests pass (tests/test_engine.py is new).

## Next: Phase 1, engine v2 (do in this order, one version bump per change)
2. v2.2: Fast Decoupled and DC load flow on the same sparse matrices (factorise B' and B'' once
   with splu); GS stays dense (teaching only). working.fd_matrices / fast_decoupled_trace stay
   dense; test_working checks the trace ends on the solver's answer (atol 1e-12).
3. Accept negative X; refuse only R = X = 0 (gridcore.prep_case; case300 has a series capacitor).
4. Element model with stable IDs (Bus, Line, Transformer, Generator, Load, Shunt) + converters from
   the v1 bus/line tables and from formats.py readers; results keyed by element ID.
5. Q limits in N-1 and PV curve; N-1 drops isolated buses and reports lost load.
6. Reference suite: MATPOWER case9, 14, 30, 39, 57, 118, 300, 1354pegase, 2383wp vs published
   solutions (stored Vm/Va where valid, runpf values for case9/case14) in tests/.
Gate: case2383wp under 1 s; all reference cases match.

## Useful
- MATPOWER cases: https://raw.githubusercontent.com/MATPOWER/matpower/master/data/<case>.m
  (case9, case14, case30, case118 already in tests/data).
- Browser checks: python tools/walkthrough.py, CHROME=/opt/pw-browsers/chromium-1194/chrome-linux/chrome
  python tools/shots.py http://localhost:8000 - <out dir>. Restart ./run_workspace.sh after Python changes.
