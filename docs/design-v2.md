# GridLens v2 design (summary)

Full version with diagrams: https://claude.ai/artifact/Q58NCpRtLWeRMAd5N5vttV (Claude Docs).

## Verdict (measured 2026-10-22 on v1.6)
Correct on small cases (126 tests, MATPOWER case9/case14 match runpf), not usable on real grids:

| Case | Buses | NR load flow (v1.6) | Layout | Note |
|---|---|---|---|---|
| case118 | 118 | 0.1 s | 0.2 s | full study 26-50 s (N-1, PV) |
| case300 | 300 | - | - | refused: negative X (series capacitor) |
| case1354pegase | 1,354 | 12.5 s | 27.8 s | blank diagram while layout runs; Data tables 7.4 s, 39,651 inputs |
| case2383wp | 2,383 | 47.5 s | 135.7 s | one N-1 sweep about 38 h |

Cause: dense n x n matrices and a numerical Jacobian (about n^3 per Newton step).
A sparse, vectorised Python NR (MATPOWER newtonpf style, numpy + scipy.sparse) solved case2383wp
in 57 ms with the same answer (max |V| diff 5e-11 pu). C++ is not needed.

## Phase 1 result (v2.6, 2026-10-22)
Engine v2 done in v2.1-v2.6: sparse Newton-Raphson (analytical Jacobian) and Fast Decoupled, DC load
flow, negative X, element model with stable ids, Q limits in N-1 and P-V, N-1 that reports lost load.
Gate passed: case2383wp load flow 0.07 s (was 47.5 s); ten MATPOWER cases (case9 to case2383wp) match
MATPOWER's runpf / rundcpf to round-off (|V| 2e-12 pu, angles 1e-10 deg), every generator's P and Q
too (tests/test_reference.py).

## Phase 2 progress (2026-10-22)
v2.7 teaching size limit (30 buses); v2.8 background jobs with progress and cancel (study, layout);
v2.9 fast exact N-1: all 2,896 outages of case2383wp in about 20 s (37 s with Q limits), the same
table as the plain re-solve (gate: under 2 minutes, passed); v2.10 layout of case2383wp in about 12 s
(was 2.5 minutes). Open: generator outages, continuation power flow, IEC 60909.

## Blockers
1. Dense engine (above). 2. Data model: generators, loads, shunts are bus columns; transformers are
lines with a tag. 3. Validation rejects negative X. 4. Install needs Python, Node and a terminal.

## Users
Transmission planner (RAW import, fast N-1 incl. generators, ratings, reports), sub-transmission
engineer (taps, switched shunts), protection engineer (IEC 60909, per-machine sequence data),
operations support (live what-if), consultant (scenarios, diffs, Excel), student/teacher (keep Learn mode).

## Falstad lessons -> GridLens
Always solving (Live mode, re-solve < 200 ms per edit) · state drawn on the diagram (moving flow
arrows, voltage colours, red violations) · sliders on any value · watch strip (pinned values) ·
examples library · no install, share as file/link · one small engine, everything else is UI.
Batch studies (N-1, PV, faults) run as background jobs with progress.

## Architecture
One engine package (model with stable IDs, sparse solvers, studies, teaching traces) called by three
clients: browser editor (through a session service that keeps each open case solved in memory and
runs long studies as jobs over WebSocket), a command line, Python/Jupyter. Readers/writers: PSS/E RAW,
MATPOWER, IEEE CDF, CSV; project files on disk with a schema version and migrations. Diagram: Canvas/
WebGL with level of detail; layout computed once and saved. Virtualised grids. Streamlit frozen.
One pip/pipx install with the built editor inside; Docker for teams.

## Data model (stable IDs; bus number is a label)
Bus (number, name, base kV, Vmin/Vmax, area, zone, x/y; type derived from its generators) · Line (R,
X may be negative, B, ratings A/B/C, in service) · Transformer (R, X on own base, rated kV per side,
tap range/step, shift, vector group, control) · Generator (P, Q, Qmin/Qmax, Vset, regulated bus,
MVA base, X''d, X2, X0, status; several per bus) · Load (P, Q, ZIP, status; several per bus) · Shunt
(G, B, switched steps) · Scenario (base + changes) · Contingency list.

## Studies (method · must match · target on case2383wp)
AC load flow: sparse analytic NR (+FD, GS for teaching) · MATPOWER solutions case9..case2383wp · < 1 s
Controls: Q limits, taps, switched shunts, phase shifters · same cases with controls · < 2x load flow
DC flow, PTDF, LODF · textbook formulas · < 0.2 s
N-1: branches, transformers, generators; LODF screening then AC; islands report lost load · brute-force
AC on IEEE 118 · all 2,896 outages < 2 min
Voltage stability: continuation PF with Q limits, PV/QV · published noses IEEE 14/118 · < 30 s
Short circuit: IEC 60909 (ANSI later) · IEC TR 60909-4 examples · all buses < 1 s
Teaching traces: up to ~30 buses, hidden above.

## Roadmap (each phase ships; gate must pass)
1. Engine v2: element model with IDs, sparse NR/FD/DC, controls, Q limits everywhere, negative X.
   Gate: case2383wp < 1 s; matches MATPOWER case9..case2383wp.
2. Studies and jobs: N-1 (gens, islands, LODF), CPF, IEC 60909, jobs with progress/cancel.
   Gate: 2,896 outages < 2 min; IEC TR 60909-4 examples match.
3. Live editor: canvas renderer, live solve, moving flows, sliders, watch strip, virtual grids, search,
   examples library, Learn mode. Gate: smooth pan at 2,383 buses; edit-to-result < 200 ms on IEEE 118.
4. Analyst workflow: PSS/E RAW in/out, scenarios + diffs, Excel/PDF reports, Python API + CLI.
   Gate: five pilot analysts finish a real study.
5. Release: pip/Docker install, manual, file migrations, CI. Gate: install in 5 min on a clean laptop.

## Fix on the way (small)
Accept negative X (refuse only R = X = 0) · Q limits in N-1 and PV (or label them) · N-1 drops
isolated buses and reports lost load · layout progress instead of a blank canvas · hide Show working
above 30 buses · freeze Streamlit · CI (pytest, tsc, build, walkthrough) on every push.
