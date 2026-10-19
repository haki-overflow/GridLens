"""Editable tables whose edits survive leaving the page.

st.data_editor forgets its edits when its page is not rendered. Here the
table lives in st.session_state[f"tbl_{name}"]; every edit is folded into
it by an on_change callback and the editor restarts from the new table
under a fresh key.
"""
import pandas as pd
import streamlit as st


def apply_delta(df, delta):
    """Apply a data_editor delta (edited / added / deleted rows) to df."""
    df = df.copy()
    for r, cols in delta.get("edited_rows", {}).items():
        for c, v in cols.items():
            df.loc[df.index[int(r)], c] = v
    if delta.get("deleted_rows"):
        df = df.drop(df.index[delta["deleted_rows"]])
    if delta.get("added_rows"):
        df = pd.concat([df, pd.DataFrame(delta["added_rows"])],
                       ignore_index=True)
    return df.reset_index(drop=True)


def _commit(name, key):
    ss = st.session_state
    ss[f"tbl_{name}"] = apply_delta(ss[f"tbl_{name}"], ss[key])
    ss[f"tbl_v_{name}"] = ss.get(f"tbl_v_{name}", 0) + 1


def table(name, default, seed=None):
    """Current table `name`; (re)seeded from default() when the seed value
    changes (e.g. a different case)."""
    ss = st.session_state
    if f"tbl_{name}" not in ss or ss.get(f"tbl_seed_{name}") != seed:
        ss[f"tbl_{name}"] = default().reset_index(drop=True)
        ss[f"tbl_seed_{name}"] = seed
        ss[f"tbl_v_{name}"] = ss.get(f"tbl_v_{name}", 0) + 1
    return ss[f"tbl_{name}"]


def editor(where, name, default, seed=None, **kw):
    """Persistent data_editor; returns the current table."""
    df = table(name, default, seed)
    key = f"tbl_ed_{name}_{st.session_state.get(f'tbl_v_{name}', 0)}"
    kw.setdefault("hide_index", True)
    where.data_editor(df, key=key, on_change=_commit, args=(name, key), **kw)
    return st.session_state[f"tbl_{name}"]
