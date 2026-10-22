"""Fast exact N-1 (v2.9): studies.contingency's table, the same rows in the
same order, with the work that does not change from one outage to the next
done once for the case. studies.contingency stays as the plain definition
(remove a line, solve the rest from a flat start); tests/test_n1.py holds this
module to it. All 2,896 outages of case2383wp take about 20 s (36 s with
generator Q limits; studies.contingency: 166 s and 58 min).

Once per case: the Ybus (a stored slot for every diagonal), the branch
admittances and where they sit in the Ybus, the Jacobian pattern in a
fill-reducing order (SuperLU MMD on J + J^T, found once and kept), the
bridges (the only branches whose outage can cut buses off) with the buses
each one cuts off, and the base case solved, its Jacobian factorised.

Per outage: subtract the branch's four admittances from a copy of the Ybus
values and run Newton-Raphson (tol 1e-8 pu, as solver.newton_raphson) from
the base-case solution:
- the first step needs no new factorisation: at the base point the outage
  changes the Jacobian only in the rows and columns of the branch ends and
  of the buses cut off, so the base factors and a small dense correction
  (Woodbury) give the exact Newton step;
- later steps factorise the Jacobian in the kept order (diagonal pivots
  preferred); once the mismatch is small and falling fast a step reuses the
  last factors (CHORD), as the last Newton steps barely move J;
- with Q limits the outage starts from the base case's PV -> PQ switches
  and goes on from there by solver.solve_with_qlimits' rules.
An outage the warm start does not solve (in WARM_ITER iterations a solve)
is solved again as studies.outage does: flat start, 30 iterations; with Q
limits every round from flat, starting from all PV. So FAILED means that
fails too. Results differ from the flat-start ones only in the last bits of
the converged voltages (about 1e-9 pu, inside the solver tolerance), which
the table's rounding hides; two buses at the same voltage to that precision
may swap as "At bus".

Slots: every non-Slack bus has a theta slot, every bus that can be PQ a |V|
slot. A slot a solve holds fixed (both slots of a bus cut off from every
Slack, |V| of a PV bus) gets an identity row and column and a zero
mismatch, so one pattern and one ordering serve every outage, island and
PV -> PQ switch, and the free block is the Jacobian studies.outage uses.
"""
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.sparse.linalg import splu

from solver import _on, _va, branch_admittances, ybus_sparse
from studies import branch_names

TOL, MAX_ITER, MAX_ROUNDS = 1e-8, 30, 20      # as solver.newton_raphson / solve_with_qlimits
WARM_ITER = 10      # a warm start that has not converged by then is solved again from flat
LOW_RANK = 16       # the first step uses the base factors when at most this many slots change
CHORD = 1e-3        # warm solves reuse the last factors below this mismatch (Grid.newton)
COLUMNS = ["Outage", "Status", "Violations", "Min V (pu)", "At bus", "Loss (pu)",
           "Buses violating", "Overloads", "Lines overloaded", "Lost load (MW)",
           "Buses cut off"]
FAILED = ["FAILED", None, None, None, None, "no solution (diverged)", None, "-", None, "-"]


def contingency(bus, lines, vmin, vmax, base=100.0, qlim=False, progress=None):
    """studies.contingency, faster: the same rows in the same order.
    progress(done, total) is called before the first outage and after each
    one; whatever it raises stops the run (it is never taken for a FAILED
    outage)."""
    names, ks = branch_names(lines), np.flatnonzero(_on(lines))
    tick = progress or (lambda done, total: None)
    tick(0, len(ks))                            # before the set-up, as before the first outage
    grid = Grid(bus, lines, qlim)
    rows = []
    for k in ks:
        try:
            rows.append([names[k], *grid.row(k, vmin, vmax, base, names)])
        except Exception:                       # no solution, as studies.contingency
            rows.append([names[k], *FAILED])
        tick(len(rows), len(ks))
    df = pd.DataFrame(rows, columns=COLUMNS)
    solved = df["Status"] != "FAILED"
    return df.assign(_s=solved).sort_values(
        ["_s", "Lost load (MW)", "Violations", "Overloads", "Min V (pu)"],
        ascending=[True, False, False, False, True]).drop(columns="_s").reset_index(drop=True)


class Grid:
    """The case, set up once for many outages."""

    def __init__(self, bus, lines, qlim=False):
        n = self.n = len(bus)
        typ = bus["Type"].to_numpy()
        self.slack, self.pv, self.pq = typ == "Slack", typ == "PV", typ == "PQ"
        self.qlim = qlim
        self.ang = np.flatnonzero(~self.slack)                  # θ slots
        self.mag = self.ang if qlim else np.flatnonzero(self.pq)  # |V| slots
        num = {c: bus[c].astype(float).to_numpy() for c in ("V", "Pg", "Qg", "Pd", "Qd")}
        self.S0 = num["Pg"] - num["Pd"] + 1j * (num["Qg"] - num["Qd"])
        self.Pd, self.Qd, self.vset = num["Pd"], num["Qd"], num["V"]
        self.qmin, self.qmax = (bus[c].astype(float).fillna(x).to_numpy() if c in bus
                                else np.full(n, x) for c, x in (("Qmin", -np.inf),
                                                                ("Qmax", np.inf)))
        self.V0 = np.where(self.pq, 1.0, self.vset)             # flat start
        self.th0 = np.where(self.slack, _va(bus), 0.0)
        # branches in service, numbered e; self.k[e] is the line row
        self.k, self.f, self.t, *y4 = branch_admittances(lines)
        self.y4 = np.array(y4)                                  # yff, ytt, yft, ytf
        self.e = np.full(len(lines), -1)
        self.e[self.k] = np.arange(len(self.k))
        Y = ybus_sparse(n, lines, bus).tocoo()                  # + every diagonal stored
        i = np.arange(n)
        Y = sp.csr_array((np.r_[Y.data, np.zeros(n)], (np.r_[Y.row, i], np.r_[Y.col, i])),
                         shape=(n, n))
        self.Yp, self.Yd0 = (Y.indices, Y.indptr), Y.data
        key = np.repeat(i, np.diff(Y.indptr)) * n + Y.indices   # sorted (CSR)
        f, t = self.f, self.t
        self.ypos = np.searchsorted(key, [f * n + f, t * n + t, f * n + t, t * n + f])
        self.jac = Jacobian(Y, self.ang, self.mag)
        self.cuts = cut_sets(n, f, t, self.slack)               # e -> buses its outage cuts off
        self.none_cut = self.cuts.get(-1, np.array([], int))    # cut off with every branch in
        self.rate = pd.to_numeric(lines["Rate"], errors="coerce").fillna(0).to_numpy(float) \
            if "Rate" in lines else None
        self.ft = np.c_[lines["From"].to_numpy(int), lines["To"].to_numpy(int)]
        seen, twin = set(), []                                  # a same From-To row further down
        for ft in map(tuple, self.ft[::-1]):
            twin.append(ft in seen)
            seen.add(ft)
        self.twin_after = twin[::-1]
        self.Vb = self.lu0 = None                               # no warm start (yet)
        self.base()

    # ------------------------------------------------------------ set-up
    def ybus(self, data):
        return sp.csr_array((data, *self.Yp), shape=(self.n, self.n))

    def base(self):
        """The case with every branch in (solved as studies.outage would),
        the warm start of every outage, and its Jacobian factorised for the
        first steps. Without a solution every outage starts flat."""
        Y, live = self.ybus(self.Yd0), self.live(self.none_cut)
        V, th, at = self.V0.copy(), self.th0.copy(), np.zeros(self.n, int)
        V[~live], th[~live] = 0.0, 0.0
        try:
            if self.qlim:
                V, th, ok, at = self.qlimits(Y, self.Yd0, V, th, live, at, warm=False)
            else:
                V, th, ok = self.newton(Y, self.Yd0, V, th, self.S0, self.free(live))
            if not ok or not np.isfinite(V).all():
                return
            Vc = V * np.exp(1j * th)
            self.J0 = self.jac.values(self.Yd0, Vc, np.exp(1j * th), Y @ Vc, self.free(live, at))
            self.Vb, self.thb, self.atb = V, th, at
            self.lu0 = self.jac.factor(self.J0)
        except np.linalg.LinAlgError:
            return

    def live(self, cut):
        live = np.ones(self.n, bool)
        live[cut] = False
        return live

    def free(self, live, at=0):
        """The slots a solve moves: θ of the live buses, |V| of the live PQ
        buses (and of the PV buses switched to PQ, at != 0)."""
        return np.r_[live[self.ang], (live & (self.pq | (at != 0)))[self.mag]]

    # ----------------------------------------------------------- outages
    def outage(self, k):
        """(V, θ, cut) with line row k out; the buses cut off from every
        Slack (cut, ascending) have V = 0, θ = 0. Raises when there is no
        solution."""
        e = self.e[k]
        Yd = self.Yd0.copy()
        np.subtract.at(Yd, self.ypos[:, e], self.y4[:, e])
        Y, cut = self.ybus(Yd), self.cuts.get(e, self.none_cut)
        live = self.live(cut)
        starts = [(self.Vb, self.thb, True)] if self.Vb is not None else []
        for V, th, warm in starts + [(self.V0, self.th0, False)]:
            V, th = V.copy(), th.copy()
            V[cut], th[cut] = 0.0, 0.0
            try:
                if self.qlim:   # warm: from the base case's switches; else as solve_with_qlimits
                    at = np.where(live, self.atb, 0) if warm else np.zeros(self.n, int)
                    V, th, ok, _ = self.qlimits(Y, Yd, V, th, live, at, warm)
                else:
                    V, th, ok = self.newton(Y, Yd, V, th, self.S0, self.free(live), warm, warm)
            except np.linalg.LinAlgError:
                if not warm:
                    raise                               # as studies.outage: no solution
                ok = False
            if ok and np.isfinite(V[live]).all():
                return V, th, cut
        raise ValueError("no convergence")

    def qlimits(self, Y, Yd, V, th, live, at, warm=True):
        """solver.solve_with_qlimits on the live buses from the switches at
        (+1 held at Qmax, -1 at Qmin, 0 PV): a PV bus whose Qg leaves
        [Qmin, Qmax] becomes PQ at that limit, a switched bus goes back to
        PV when |V| passes its setpoint; solved again until nothing changes.
        warm: each round starts from the last one's solution (the first from
        V, θ, its first step from the base factors); else every round starts
        flat, as solve_with_qlimits does. A round that does not converge ends
        it (ok False): solve_with_qlimits would go on switching on the numbers
        of the failed solve, but no outage of the cases in tests/data ends
        converged after such a round. Returns (V, θ, ok, at)."""
        S0 = self.S0.copy()
        for rnd in range(MAX_ROUNDS):
            q = np.where(at > 0, self.qmax, self.qmin) - self.Qd
            S0[at != 0] = S0.real[at != 0] + 1j * q[at != 0]
            if not warm:
                V = np.where(self.pq | (at != 0), 1.0, self.vset)
                th = self.th0.copy()
                V[~live], th[~live] = 0.0, 0.0
            V, th, ok = self.newton(Y, Yd, V, th, S0, self.free(live, at), warm,
                                    warm and rnd == 0)
            if not ok:
                return V, th, False, at
            Vc = V * np.exp(1j * th)
            qg = (Vc * np.conj(Y @ Vc)).imag + self.Qd
            pv = self.pv & live & (at == 0)
            up = pv & (qg > self.qmax + 1e-9)
            dn = pv & ~up & (qg < self.qmin - 1e-9)
            back = live & (((at == 1) & (V > self.vset + 1e-9)) |
                           ((at == -1) & (V < self.vset - 1e-9)))
            if not (up | dn | back).any():
                return V, th, True, at
            at = at.copy()
            at[up], at[dn], at[back] = 1, -1, 0
            V = np.where(back, self.vset, V)
        return V, th, False, at

    def newton(self, Y, Yd, V, th, S0, free, warm=False, first=False):
        """solver.newton_raphson on the free slots. warm: once the mismatch
        is below CHORD and falling at least tenfold a step, the last factors
        are used again instead of new ones (a chord step; a step that does
        not keep up brings fresh factors back); first: the first step uses
        the base factors (see first_step)."""
        ang, mag, jac = self.ang, self.mag, self.jac
        V, th = V.copy(), th.copy()
        keep = jac.fix(free)
        lu, last = None, np.inf
        for it in range(WARM_ITER if warm else MAX_ITER):
            E = np.exp(1j * th)
            Vc = V * E
            I = Y @ Vc
            mis = Vc * np.conj(I) - S0
            f = np.where(free, np.r_[mis.real[ang], mis.imag[mag]], 0.0)
            err = np.abs(f).max(initial=0)
            if err < TOL:
                return V, th, True
            if not np.isfinite(err):
                break
            if warm and CHORD and lu is not None and err < min(CHORD, 0.1 * last):
                dx = jac.solve(lu, f)
            else:
                J = jac.values(Yd, Vc, E, I, free, keep)
                dx = self.first_step(J, f) if first and it == 0 else None
                if dx is None:
                    lu = jac.factor(J)
                    dx = jac.solve(lu, f)
            last = err
            th[ang] -= dx[:len(ang)]
            V[mag] -= dx[len(ang):]
        return V, th, False

    def first_step(self, J, f):
        """J^-1 f from the base factors when J differs from the base Jacobian
        J0 in few slots M only: J = J0 + P D P^T (P the columns M of I, D
        the change on M x M), so by Woodbury J^-1 f = y - Z (I + D Z_M)^-1 D
        y_M with y = J0^-1 f and Z = J0^-1 P. None when too many slots
        changed (or the small system is singular)."""
        if self.lu0 is None:
            return None
        jac = self.jac
        d = J - self.J0                     # zero outside the rows and columns that changed
        nz = np.flatnonzero(d)
        M, ij = np.unique(np.r_[jac.kr[nz], jac.kc[nz]], return_inverse=True)
        m = len(M)
        if m > LOW_RANK:
            return None
        D = np.zeros((m, m))
        D[ij[:len(nz)], ij[len(nz):]] = d[nz]
        R = np.zeros((jac.N, m + 1))
        R[M, np.arange(m)] = 1.0
        R[jac.pos, m] = f
        X = self.lu0.solve(R)
        Z, y = X[:, :m], X[:, m]
        try:
            c = np.linalg.solve(np.eye(m) + D @ Z[M], D @ y[M])
        except np.linalg.LinAlgError:
            return None
        return (y - Z @ c)[jac.pos]

    # ------------------------------------------------------------ report
    def row(self, k, vmin, vmax, base, names):
        """The contingency row after Outage, as studies.contingency builds
        it; raises when the outage has no solution."""
        V, th, cut = self.outage(k)
        live = self.live(cut)
        v = V[live]
        bad = np.flatnonzero(live & ((V < vmin) | (V > vmax))) + 1
        Vc = V * np.exp(1j * th)
        f, t, (yff, ytt, yft, ytf) = self.f, self.t, self.y4
        Sij = Vc[f] * np.conj(yff * Vc[f] + yft * Vc[t])
        Sji = Vc[t] * np.conj(ytt * Vc[t] + ytf * Vc[f])
        over = self.overloads(k, np.maximum(np.abs(Sij), np.abs(Sji)) * base, names)
        return ["ISLANDED" if len(cut) else "OK", len(bad), round(v.min(), 4),
                int(np.flatnonzero(live)[np.argmin(v)] + 1),
                round((Sij + Sji).real[self.k != k].sum(), 4), ", ".join(map(str, bad)) or "-",
                len(over), ", ".join(over) or "-", round(self.Pd[cut].sum() * base, 4),
                ", ".join(str(i + 1) for i in cut) or "-"]

    def overloads(self, k, s, names):
        """studies.overloads on the line table without row k (s: MVA of the
        branches in service)."""
        if self.rate is None:
            return []
        load = np.zeros(len(self.rate))
        load[self.k] = s
        load[k] = 0.0
        rows = np.flatnonzero((self.rate > 0) & (load > self.rate + 1e-9))
        if not self.twin_after[k]:
            return [names[j] for j in rows]
        ft = np.delete(self.ft, k, axis=0)                      # a later twin moves up a number
        nm = branch_names({"From": ft[:, 0], "To": ft[:, 1]})
        return [nm[j - (j > k)] for j in rows]


class Jacobian:
    """solver._jacobian with θ slots at ang and |V| slots at mag, kept in one
    sparse CSC matrix in a fill-reducing order found once (MMD on J + J^T)
    and factorised with diagonal pivots preferred (SuperLU SymmetricMode;
    panel_size 2 halves the factorisation time of these very sparse
    matrices against the default). Y must store every diagonal entry. Slot u
    sits at row and column pos[u]."""
    LU = dict(permc_spec="NATURAL", diag_pivot_thresh=0.1, panel_size=2,
              options=dict(SymmetricMode=True))

    def __init__(self, Y, ang, mag):
        n, Yc = Y.shape[0], Y.tocoo()
        self.row, self.col, m = Yc.row, Yc.col, Yc.nnz
        self.diag = np.flatnonzero(Yc.row == Yc.col)           # (i, i) for i = 0..n-1
        pa, pm = np.full(n, -1), np.full(n, -1)
        pa[ang], pm[mag] = np.arange(len(ang)), len(ang) + np.arange(len(mag))
        r, c, src = [], [], []
        for b, (rr, cc) in enumerate(((pa, pa), (pa, pm), (pm, pa), (pm, pm))):
            s = np.flatnonzero((rr[Yc.row] >= 0) & (cc[Yc.col] >= 0))
            r.append(rr[Yc.row[s]])
            c.append(cc[Yc.col[s]])
            src.append(b * m + s)                               # Re dθ, Re dV, Im dθ, Im dV
        r, c, src = (np.concatenate(x) for x in (r, c, src))
        N = self.N = len(ang) + len(mag)
        # the order: MMD on the pattern (any values do; these never pivot off the diagonal)
        A = sp.csc_array((np.where(r == c, 2.0 * N, 1.0), (r, c)), shape=(N, N))
        self.pos = splu(A, permc_spec="MMD_AT_PLUS_A", diag_pivot_thresh=0.0,
                        options=dict(SymmetricMode=True)).perm_c
        key = self.pos[c] * N + self.pos[r]                     # CSC order of the stored J
        o = np.argsort(key)
        self.take, key = src[o], key[o]
        self.kr, self.kc = key % N, key // N
        self.indptr = np.searchsorted(self.kc, np.arange(N + 1))
        self.eye = (self.kr == self.kc).astype(float)

    def fix(self, free):
        """keep: the stored entries whose row and column slots are both free."""
        a = np.empty(self.N, bool)
        a[self.pos] = free
        return a[self.kr] & a[self.kc]

    def values(self, Yd, Vc, E, I, free, keep=None):
        """The stored values of J at (Vc, E, I): dS_i/dθ_k = -j Vc_i conj(Y_ik
        Vc_k) + (i = k) j Vc_i conj(I_i), dS_i/d|V|_k = Vc_i conj(Y_ik E_k)
        + (i = k) conj(I_i) E_i; identity rows and columns at the fixed slots."""
        keep = self.fix(free) if keep is None else keep
        row, col, d = self.row, self.col, self.diag
        dth = -1j * Vc[row] * np.conj(Yd * Vc[col])
        dV = Vc[row] * np.conj(Yd * E[col])
        dth[d] += 1j * Vc * np.conj(I)
        dV[d] += np.conj(I) * E
        vals = np.concatenate([dth.real, dV.real, dth.imag, dV.imag])[self.take]
        return np.where(keep, vals, self.eye)

    def factor(self, data):
        try:
            return splu(sp.csc_array((data, self.kr, self.indptr), shape=(self.N, self.N)),
                        **self.LU)
        except RuntimeError as e:   # SuperLU: "Factor is exactly singular"
            raise np.linalg.LinAlgError(str(e)) from None

    def solve(self, lu, f):
        """The step dx (slot order) from J dx = f (f in slot order)."""
        rhs = np.empty(self.N)
        rhs[self.pos] = f
        return lu.solve(rhs)[self.pos]


def cut_sets(n, f, t, slack):
    """{e: buses (0-based, ascending) cut off from every Slack with branch e
    out} for the branches whose outage cuts buses off; key -1 holds the
    buses no Slack reaches with every branch in. Tarjan's bridges on depth
    first searches from the Slacks: a bridge's far side is the subtree below
    it."""
    adj = [[] for _ in range(n)]
    for e, (a, b) in enumerate(zip(f.tolist(), t.tolist())):
        adj[a].append((b, e))
        adj[b].append((a, e))
    tin, low, tout, order, bridges = [-1] * n, [0] * n, [0] * n, [], []
    for root in np.flatnonzero(slack).tolist():
        if tin[root] >= 0:
            continue
        tin[root] = low[root] = len(order)
        order.append(root)
        stack = [(root, -1, iter(adj[root]))]
        while stack:
            u, pe, it = stack[-1]
            for v, e in it:
                if e == pe:
                    continue
                if tin[v] < 0:
                    tin[v] = low[v] = len(order)
                    order.append(v)
                    stack.append((v, e, iter(adj[v])))
                    break
                low[u] = min(low[u], tin[v])
            else:
                stack.pop()
                tout[u] = len(order)
                if stack:
                    p = stack[-1][0]
                    low[p] = min(low[p], low[u])
                    if low[u] > tin[p]:
                        bridges.append((pe, u))
    order, unreached = np.array(order, int), np.flatnonzero(np.array(tin) < 0)
    cuts = {-1: unreached} if len(unreached) else {}
    for e, u in bridges:
        side = order[tin[u]:tout[u]]
        if not slack[side].any():
            cuts[e] = np.union1d(side, unreached)
    return cuts
