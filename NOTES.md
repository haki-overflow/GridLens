# Notes for the next session (v2.0)

Read first: AGENTS.md, then docs/design-v2.md (plan, gates, data model). Full design doc with
diagrams: https://claude.ai/artifact/Q58NCpRtLWeRMAd5N5vttV

## Rules from the user
- Versions: every change bumps the version by 0.1 and gets its own branch from the previous one:
  v2.0 -> v2.1 -> v2.2 ... Bump web/package.json, api/server.py (FastAPI version) and the brand
  label in web/src/shell.ts. Never push to an older branch.
- Work autonomously, small commits, push after each; tell the user briefly what changed.
- Keep the theme.css palette exactly as is. Ask before any new dependency.
- scipy for the v2 engine: asked 2026-10-22; the user answered "Yes call it v2.0", taken as yes
  (they can still say no). Add it to requirements.txt and the AGENTS.md dependency list in the
  first engine commit.
- If context gets above ~85%, update this file and tell the user to /clear.

## State
- v1.6 is done (any-case input, imports, islands, fallback, Falstad-style plan). 126 tests pass.
- v2.0 branch: version 2.0, docs/design-v2.md, this file. No engine work yet.

## Next: Phase 1, engine v2 (do in this order, one version bump per change)
1. Sparse solver: new module (e.g. `sparse.py` or inside solver.py) with build_ybus as scipy.sparse
   (Cf/Ct incidence; branch_y model: yff = y/a^2 + jB/2, ytt = y + jB/2, yft = -y/conj(t),
   ytf = -y/t; shunts Gs + jBs on the diagonal) and NR with the analytic sparse Jacobian
   (MATPOWER newtonpf: dS_dVm = diag(V) conj(Y diag(V/|V|)) + conj(diag(I)) diag(V/|V|),
   dS_dVa = j diag(V) conj(diag(I) - Y diag(V)); J = [[Re dVa[pvpq,pvpq], Re dVm[pvpq,pq]],
   [Im dVa[pq,pvpq], Im dVm[pq,pq]]]; spsolve). Prototype measured: case2383wp 57 ms, same answer
   as the dense solver to 5e-11 pu. Keep the dense solver only for the teaching traces.
   Golden snapshots: NR results will move in the last bits -> regenerate with the user's OK
   (GOLDEN_WRITE=1), compare old vs new to 1e-9 first.
2. Fast Decoupled and DC load flow on the same sparse matrices; GS stays dense (teaching only).
3. Accept negative X; refuse only R = X = 0.
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
