# v1.6 notes

All planned steps are done and pushed (see README "v1.6: solve any problem" and AGENTS "v1.6: any case").
Decisions: kept the v1.4 workflow list (C4/C5 described the old tree and tab strip); solver additions
approved; no networkx; new features are in the web workspace only (Streamlit still loads, checked).

Checks used before every commit: python -m pytest -q (126), cd web && npx tsc --noEmit && npm run build,
python tools/sync_tokens.py --check, python tools/check_contrast.py, python tools/walkthrough.py,
CHROME=... python tools/shots.py http://localhost:8000 - <out dir>.

Open ideas (not done): analytical Jacobian in the solver (needs a snapshot regeneration), MATPOWER's
B/tap^2 charging convention as an option, New case / import in the Streamlit app.
