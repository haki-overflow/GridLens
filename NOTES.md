# Notes for the next session (v2.8: phase 2, jobs done)

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
  Intended changes (user, 2026-10-22, standing): regenerate the snapshots without asking when a
  change moves results on purpose, after a diff shows only the intended values changed; say
  exactly what changed in the commit message and the TL;DR (as in v2.5, the IEEE 14 7-8 row).
- tools/reference_pf.py (PYPOWER, dev tool only, not a dependency) stays: user OK 2026-10-22.
- The user wants short TL;DRs as work progresses.
- If context gets above ~90% (user, 2026-10-22), update this file and tell the user to /clear;
  the next session continues from here.

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

- v2.7: teaching size TEACH_MAX = 30 buses (GS skipped in the method check, Show working refused,
  no dense Zbus in /api/fault above it). 198 tests. Review workflow ran on the diff (fixes follow).
- Fast N-1 baseline: 50 ms per outage on case2383wp (all 2,896 ~145 s), 70% SuperLU factorisation.
  A design workflow prototyped lean-Newton / factorisation-reuse / screen+parallel options in
  the scratchpad (n1/); its benchmark decides v2.9.

- The first run of workflow "design-fast-n1" (wf_f00bdf11-0fb) died with /clear before any
  result: a workflow only resumes in the session that launched it. Never /clear while one runs.
- 2026-10-22 15:30 UTC: the usage limit stopped both workflows (design-fast-n1 and review-v28)
  with no results; after the restart the Workflow tool was off, so the same plan runs as six
  background agents (effort max): prototypes lean/, reuse/ (continuing their own files) and
  screen/ in the n1 scratch below, and three v2.8 reviewers (Python, web, callers/docs/tests;
  scripts in scratchpad/review28/). Their reports reach only the session that started them: after
  a /clear, rerun from the files on disk (n1/*/proto.py, n1/bench.py if any). n1/ref.py is making
  reference_qlim.pkl again (it was killed at a time limit; reference.pkl is done).
- Earlier (2026-10-22, session a5b7a850): "design-fast-n1" rerun wf_314ef0c9-14f, agents at
  effort max (the user asked for ultracode / max). Scratch:
  /tmp/claude-0/-home-user/a5b7a850-f9b9-4e44-bf19-1dc1368ade9e/scratchpad/n1/ (lean/, reuse/,
  screen/ prototypes, lean_old/ and reuse_old/ from the first run, ref.py -> reference.pkl and
  reference_qlim.pkl = the exact N-1 of case2383wp, bench.py, final/proto.py = the merged winner,
  verify1/, verify2/). Results: "result" lines of
  /root/.claude/projects/-home-user/a5b7a850-f9b9-4e44-bf19-1dc1368ade9e/subagents/workflows/wf_314ef0c9-14f/journal.jsonl
  (prototypes, benchmark, three judges, synthesis with a v2.9 integration plan, two verifiers).
  If lost, re-read those files or rerun bench.py on final/proto.py before redesigning.
- v2.8: background jobs (jobs.py; /api/jobs start / poll / cancel; kinds "study" and "layout",
  one at a time per kind, kinds in parallel; web: Run becomes Stop with stage, count and time left,
  layout chip on the canvas). 219 tests. Browser check (scratchpad jobcheck.py): progress, Stop,
  a new case stopping the study and the layout, case300 full study 10 s.
- Found in v2.8: the layout of case2383wp takes ~145 s CPU on one core (300 dense stress
  iterations, 0.43 s each; hops 4.6 s, MDS eigh 3.4 s, pinv 7 s), and while it runs it slows the
  study job (same process). A faster layout is its own version (same algorithm, vectorised:
  precomputed W*D, no (n, n, 2) temporaries, csgraph BFS, eigh-based pinv), after the fast N-1.
- Plan: v2.9 the winning fast N-1, then the fast layout.

## Next: Phase 2, studies and jobs (docs/design-v2.md; one version bump per change, v2.7 on)
Gate: all 2,896 branch outages of case2383wp in under 2 min; IEC TR 60909-4 examples match.
Suggested order:
1. (done in v2.7) Teaching methods only up to 30 buses: Gauss-Seidel and Show working.
2. (done in v2.8) Jobs: long studies (N-1, P-V) as background jobs with progress and cancel
   (polling; web progress instead of a frozen Run). Layout progress too.
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
