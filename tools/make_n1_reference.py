"""Write the exact N-1 tables that tests/test_n1.py holds n1.py to.

    python tools/make_n1_reference.py case300 [--qlim]      (about 30 s / 3 min)
    python tools/make_n1_reference.py case2383wp            (about 3 min)
    python tools/make_n1_reference.py case2383wp --qlim     (about an hour)

studies.contingency (remove one line, solve the rest from a flat start) on a
MATPOWER case of tests/data, base MVA and limits as the web workspace sets
them (taps and shunts on, 0.95-1.10 pu), saved as tests/data/n1_<case>[_qlim].csv.gz.
Dev tool only: the tests read the files, they never run this.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import formats  # noqa: E402
import gridcore  # noqa: E402
from studies import contingency  # noqa: E402

DATA = ROOT / "tests" / "data"


def path(case, qlim):
    return DATA / f"n1_{case}{'_qlim' if qlim else ''}.csv.gz"


def prepared(case, qlim):
    """bus, lines, base of a MATPOWER case as the tests solve it."""
    c = formats.read_case(f"{case}.m", (DATA / f"{case}.m").read_text())
    b, l, probs, _ = gridcore.prep_case(c["bus"], c["lines"], dict(
        method="Newton-Raphson", base=c["base"], vmin=0.95, vmax=1.1, tol=1e-8,
        taps=True, shunts=True, qlim=qlim))
    assert not probs, probs
    return b, l, c["base"]


def write(df, case, qlim):
    df.to_csv(path(case, qlim), index=False, compression="gzip")


if __name__ == "__main__":
    case, qlim = sys.argv[1], "--qlim" in sys.argv
    b, l, base = prepared(case, qlim)
    t = time.perf_counter()
    df = contingency(b, l, 0.95, 1.1, base=base, qlim=qlim)
    write(df, case, qlim)
    print(f"{path(case, qlim).name}: {len(df)} outages in {time.perf_counter() - t:.0f} s,",
          df["Status"].value_counts().to_dict())
