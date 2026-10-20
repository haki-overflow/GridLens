# v1.6 progress notes

Decisions (user): keep the v1.4 workflow list; solver additions approved (defaults bit-identical);
no networkx; web workspace only (Streamlit must still load).

Done (backend, all pushed)
- 0 version 1.6; tests/test_golden_api.py snapshots every study endpoint on both presets.
- 1 prep_case: bus Num/Name/Gs/kV, branch Shift/Rate/InService; duplicate numbers, base/kV <= 0.
- 3 solver: branch_y (phase shift), in_service(), Gs, init flat/setpoint, damp, GS honours tol
  (only the GS row of the solver check changed; snapshots updated), slack angle from Va.
- 2 islands: one Slack per island, islands without one named; outage that cuts supply explained.
- 4 gridcore.loadflow: fallback chain + failure_hint; line_loading (Rate); N-1 Overloads columns.
- 5 settings.units = "actual": topics.case_to_pu (MW, MVAr, kV, ohm, uS per bus base kV).
- 6 formats.py: MATPOWER .m, IEEE CDF, CSV; /api/import. case9/case14 match runpf; case118 solves
  (full study ~28 s: N-1 15 s, PV 5 s, GS 3 s; numerical Jacobian, AGENTS issue 4).
- 7 COORDS removed (IEEE 14 x/y are bus columns); fault kA per bus kV.

Next: web UI
- 8 File > New case dialog (name, base MVA, frequency, units); File > Examples submenu; start cards.
- 9 Data tables: Buses / Branches / Generators / Loads / Shunts sub-views over bus + line rows, new columns.
- 10 File > Import (MATPOWER / CDF / CSV) -> /api/import.
- 11 neutral selection (gray fill + 1px light border), blue only on Run.
- 12 messages: current run only, clear on case change, Clear button, not persisted; flat centre;
  brighter header labels; show failure hint + fallback note.
- 13 two-column result pages + small plots.
- 14 tests (2-bus, island, tap, Q-limit, textbook 3-bus ohm/MVA + faults) + Playwright screenshots.
- 15 README / AGENTS, push, final report.
