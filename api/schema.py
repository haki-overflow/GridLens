"""JSON conversion helpers for the API.

Out: DataFrames -> lists of records, numpy numbers -> plain int / float /
bool, complex -> {"re", "im", "polar"} (polar text from working.pfmt),
NaN / inf -> null. Floats are passed through unrounded, so the JSON round
trip keeps them exact (json writes the shortest repr that reads back to
the same double).
In: records -> DataFrames, {"re", "im"} / {"mag", "deg"} / numbers ->
complex.
"""
import math

import numpy as np
import pandas as pd

from working import pfmt


def _float(x):
    x = float(x)
    return x if math.isfinite(x) else None


def cplx(z):
    z = complex(z)
    return {"re": _float(z.real), "im": _float(z.imag), "polar": pfmt(z)}


def to_json(x):
    """Recursively turn study results into JSON-ready Python objects."""
    if isinstance(x, pd.DataFrame):
        return [{str(k): to_json(v) for k, v in row.items()}
                for row in x.to_dict(orient="records")]
    if isinstance(x, pd.Series):
        return {str(k): to_json(v) for k, v in x.items()}
    if isinstance(x, np.ndarray):
        return [to_json(v) for v in x.tolist()] if x.ndim else to_json(x.item())
    if isinstance(x, dict):
        return {str(k): to_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [to_json(v) for v in x]
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (complex, np.complexfloating)):
        return cplx(x)
    if isinstance(x, (float, np.floating)):
        return _float(x)
    if x is None or isinstance(x, str):
        return x
    if x is pd.NA or x is pd.NaT:
        return None
    return str(x)


def frame(records):
    """List of records -> DataFrame (None -> NaN in numeric columns)."""
    return pd.DataFrame.from_records(records or [])


def complex_in(v):
    """{"re", "im"}, {"mag", "deg"}, [re, im] or a number -> complex."""
    if v is None:
        return 0j
    if isinstance(v, dict):
        if "mag" in v:
            return complex(v["mag"] * np.exp(1j * np.radians(v.get("deg", 0.0))))
        return complex(v.get("re", 0.0), v.get("im", 0.0))
    if isinstance(v, (list, tuple)):
        return complex(v[0], v[1])
    return complex(v)
