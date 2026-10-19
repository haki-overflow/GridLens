"""web/src/tokens.css must be the :root block of theme.css (same palette in
the Streamlit app and the web workspace)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_tokens_in_sync():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "sync_tokens.py"),
                        "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
