# v1.6 progress notes

Plan: /root/.claude/plans (summary below). Decisions: keep the v1.4 workflow list; solver additions approved
(defaults bit-identical); no networkx; web workspace only (Streamlit must still load).

Done
- Step 0: version 1.6; tests/test_golden_api.py snapshots every study endpoint on both presets
  (tests/data/api_golden.json). Regenerate only after an approved maths change: GOLDEN_WRITE=1.
- Step 1: gridcore.prep_case accepts bus Num/Name/Gs/kV, branch Shift/Rate/InService; checks duplicate bus
  numbers, base MVA <= 0, kV <= 0; API Settings gain freq and units. Tests: tests/test_anycase.py.

Next (in order)
- Step 3 (do before islands): solver.py branch_y() helper with complex tap for Shift (exact old arithmetic
  when Shift = 0), skip InService = 0 in build_ybus / fast_decoupled / working.ybus_parts / fd_matrices,
  zero flow rows for out-of-service lines, Gs on the Ybus diagonal, solve_loadflow(init="flat"|"setpoint",
  damp=1.0), pass tol to gauss_seidel (GS golden entries change: regenerate and say so).
- Step 2 islands, 4 fallback + loading %, 5 actual units, 6 importers (MATPOWER, CDF, CSV), 7 layout,
  8-13 web UI (New case, Examples menu, tables, Import, neutral selection, messages, two-column results),
  14 tests + screenshots, 15 docs.
