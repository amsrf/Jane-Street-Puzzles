"""Stage-1 CP-SAT model: small states (size <= K) plus BIG cells.

We only need the clues whose target is <= K, because every step of such a
shortest path costs at most K: no step between two BIG cells is ever used, and a
step between a BIG cell and a small one costs the *small* state's size.  So a BIG
state's exact size never matters, and replacing each cell's size by
min(size, K+1) leaves those clues unchanged.

Model
  x[p]      : placement p is used                      (Bool)
  big[c]    : cell c belongs to a BIG state            (Bool)
  cover     : sum(x[p] covering c) + big[c] == 1
  sizecap[c]: sum(size(p) * x[p]) + (K+1) * big[c]     (<= K+1)
  cap[c]    : c is a capitol.  For a small cell this is exactly "some chosen
              placement has its capitol here"; for a BIG cell it is free.
  d[c]      : distance to the nearest capitol, saturated at K+1 ("infinity")
  w[u,v]    : min(sizecap[u], sizecap[v])   (one variable per undirected edge)
  triangle  : d[v] <= d[u] + w[u,v]         (relaxed when d[v] is saturated)
  tightness : cap[v] or d[v] saturated or d[v] == d[u] + w[u,v] for some u
  clues     : d[clue] == T for every clue with T <= K

Saturating at K+1 keeps the distance domains tiny and is sound: a tight chain
for a clue with T <= K only ever visits cells with d < T <= K, so those cells are
never saturated and the chain still bottoms out at a real capitol.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from ortools.sat.python import cp_model

from placements import Placement, build_placements
from shapes import Cell, generate_shapes

NEIGH4 = ((1, 0), (-1, 0), (0, 1), (0, -1))

EXAMPLE_5X5_CLUES: Dict[Cell, int] = {
    (0, 0): 12, (0, 4): 17, (1, 0): 8, (1, 2): 6, (1, 3): 3,
    (3, 1): 7, (3, 2): 6, (3, 4): 10, (4, 0): 25, (4, 4): 0,
}

PUZZLE_11X11_CLUES: Dict[Cell, int] = {
    (0, 1): 8, (0, 2): 4, (0, 5): 11, (0, 9): 5,
    (1, 7): 11,
    (2, 2): 7, (2, 5): 1, (2, 10): 14,
    (3, 0): 28, (3, 3): 51, (3, 6): 1, (3, 8): 6,
    (4, 1): 22, (4, 8): 4, (4, 10): 1,
    (5, 3): 15, (5, 5): 10, (5, 7): 0,
    (6, 0): 11, (6, 2): 11, (6, 9): 9,
    (7, 2): 17, (7, 4): 14, (7, 7): 10, (7, 10): 13,
    (8, 0): 30, (8, 5): 6, (8, 8): 45,
    (9, 3): 10,
    (10, 1): 26, (10, 5): 0, (10, 8): 77, (10, 9): 61,
}


# ---------------------------------------------------------------------------
# deductions
# ---------------------------------------------------------------------------
def neighbours(cell: Cell, n: int) -> List[Cell]:
    r, c = cell
    return [(r + dr, c + dc) for dr, dc in NEIGH4
            if 0 <= r + dr < n and 0 <= c + dc < n]


def compute_min_sizes(n: int, clues: Dict[Cell, int]) -> Dict[Cell, int]:
    """Lower bounds on state sizes from the distance triangle inequality.

    Adjacent cells u,v:  T(u) <= min(s_u, s_v) + T(v)  =>  both >= |T(u)-T(v)|.
    Two steps u - x - v: each step costs at most s_x  =>  s_x >= ceil(|dT|/2).
    """
    mins: Dict[Cell, int] = {}
    for cell in clues:
        best = 0
        for nb in neighbours(cell, n):
            if nb in clues:
                best = max(best, abs(clues[cell] - clues[nb]))
        if best:
            mins[cell] = best
    for r in range(n):
        for c in range(n):
            cell = (r, c)
            near = [nb for nb in neighbours(cell, n) if nb in clues]
            best = mins.get(cell, 0)
            for i in range(len(near)):
                for j in range(i + 1, len(near)):
                    d = abs(clues[near[i]] - clues[near[j]])
                    best = max(best, (d + 1) // 2)
            if best:
                mins[cell] = best
    return mins


def monomino_analysis(n: int, clues: Dict[Cell, int], mins: Dict[Cell, int]):
    """Where monominoes may and may not go, and forced monominoes.

    Rules: a monomino is always a capitol, so its cell has distance 0 and cannot
    be a clue with T != 0.  If a monomino sits at m, every neighbour v has
    d[v] <= 1, so no neighbour may be a clue with T > 1.
    """
    forbidden: Set[Cell] = set()
    for cell, target in clues.items():
        if target != 0:
            forbidden.add(cell)              # a capitol there would give d = 0
    for cell, target in clues.items():
        if target > 1:
            for nb in neighbours(cell, n):
                forbidden.add(nb)            # d[nb] <= 1 would contradict T > 1
    for cell, need in mins.items():
        if need > 1:
            forbidden.add(cell)              # state size >= 2, so not a monomino

    forced: Dict[Cell, Cell] = {}
    candidates: Dict[Cell, List[Cell]] = {}
    for cell, target in clues.items():
        if target != 1:
            continue
        cands = [nb for nb in neighbours(cell, n) if nb not in forbidden]
        candidates[cell] = cands
        if len(cands) == 1:
            forced[cell] = cands[0]
    return forbidden, forced, candidates


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------
@dataclass
class Stage1Config:
    n: int
    clues: Dict[Cell, int]
    K: int = 12
    time_limit: float = 120.0
    workers: int = 8
    hunch: bool = False
    maximize: bool = False
    log_progress: bool = False
    seed: int = 0
    # fixed assignment for gate tests: {'placements': [cells...], 'big': set,
    # 'big_capitols': set}
    fix: Optional[dict] = None
    # forbid BIG cells entirely (only sound when K covers every state size):
    # then every weight is exact and clues above K may be enforced too
    no_big: bool = False
    # forbid BIG cells from being capitols except at the forced 0-clues
    no_big_caps: bool = False
    # at most this many BIG capitols (None = unlimited)
    max_big_caps: Optional[int] = None
    # enforce every BIG connected component has >= K+1 cells
    big_connected_min: bool = False
    # largest target to enforce; None means K (sound in the BIG approximation)
    enforce_limit: Optional[int] = None
    # BIG region: size window, a root cell that makes it connected, cells it must
    # contain, and the Manhattan-ring condition on every clue
    big_min: Optional[int] = None
    big_max: Optional[int] = None
    big_root: Optional[Cell] = None
    must_big: FrozenSet[Cell] = frozenset()
    must_small: FrozenSet[Cell] = frozenset()
    # exact number of BIG components, and the size of the component containing
    # big_anchor (requires big_connected_min=True)
    big_components: Optional[int] = None
    big_anchor: Optional[Cell] = None
    big_anchor_size: Optional[int] = None
    manhattan_ring: bool = False
    # the BIG region must be a legal state whose capitol is this cell.  Since
    # every non-identity symmetry of a state fixes its capitol, only the (at most
    # seven) elements fixing that cell are candidates - a tiny disjunction.
    blob_capitol: Optional[Cell] = None
    # the BIG region must be invariant under at least one D4 map (capitol optional)
    blob_symmetric: bool = False
    # previously found (x, big) assignments to exclude: list of
    # (chosen placement cell sets, BIG cell set)
    cuts: Optional[List[Tuple[Set[Cell], Set[Cell]]]] = None
    # BIG growth cuts: (component, its small neighbours).  Clause: some cell of
    # the component is not BIG, or some neighbour is BIG.  Valid for every real
    # solution, because a BIG component smaller than K+1 can never be maximal.
    big_growth_cuts: Optional[List[Tuple[Set[Cell], Set[Cell]]]] = None


@dataclass
class Stage1Result:
    status: str
    solution: Optional['Stage1Solution'] = None
    nodes: int = 0
    wall: float = 0.0
    enforced: List[Cell] = field(default_factory=list)
    skipped: List[Cell] = field(default_factory=list)
    placements_used: int = 0
    dropped_clues: List[Cell] = field(default_factory=list)


@dataclass
class Stage1Solution:
    n: int
    # cell -> state id (small) or None for BIG
    state_of: List[List[Optional[int]]]
    states: List[Tuple[FrozenSet[Cell], Optional[Cell]]]   # cells, capitol
    big: FrozenSet[Cell]
    big_capitols: FrozenSet[Cell]
    distances: List[List[int]]


_LIB_CACHE: Dict[Tuple[int, int], Tuple[dict, list]] = {}


def build_library(cfg: Stage1Config):
    key = (cfg.n, cfg.K)
    if key not in _LIB_CACHE:
        shapes = generate_shapes(cfg.n, cfg.K, verbose=False)
        pieces = build_placements(cfg.n, shapes, verbose=False)
        _LIB_CACHE[key] = (shapes, pieces)
    return _LIB_CACHE[key]


def filter_placements(cfg: Stage1Config, pieces: Sequence[Placement],
                      mins: Dict[Cell, int], forbidden_mono: Set[Cell]
                      ) -> List[Placement]:
    """Necessary-condition pre-filter.  Every dropped placement is impossible."""
    n, K, clues = cfg.n, cfg.K, cfg.clues
    kept: List[Placement] = []
    for p in pieces:
        if p.size == 1:
            if p.capitol in forbidden_mono:
                continue
        if any(p.size < mins.get(c, 0) for c in p.cells):
            continue
        bad = False
        for c in p.cells:
            if clues.get(c) == 0 and p.capitol != c:
                bad = True
                break
        if bad:
            continue
        for a in p.cells:
            if a not in clues:
                continue
            for b in neighbours(a, n):
                if b in clues and abs(clues[a] - clues[b]) > K and b in p.cells:
                    bad = True
                    break
            if bad:
                break
        if bad:
            continue

        # R6-style bound: if this placement has a capitol, then for every
        # clued cell x it contains, the internal path to that capitol is a
        # candidate, so clue(x) <= size(p) * dist_p(x, capitol).
        if p.capitol is not None:
            dist = {p.capitol: 0}
            stack = [p.capitol]
            while stack:
                u = stack.pop()
                du = dist[u]
                for v in neighbours(u, n):
                    if v in p.cells and v not in dist:
                        dist[v] = du + 1
                        stack.append(v)
            for c in p.cells:
                if c in clues:
                    d = dist.get(c)
                    if d is None or clues[c] > p.size * d:
                        bad = True
                        break
            if bad:
                continue
        kept.append(p)
    return kept


def solve(cfg: Stage1Config, verbose: bool = True) -> Stage1Result:
    t0 = time.time()
    n, K, clues = cfg.n, cfg.K, cfg.clues
    limit = cfg.enforce_limit if cfg.enforce_limit is not None else K
    if cfg.no_big:
        limit = max(limit, max(clues.values()) if clues else 0)
    enforced = sorted(c for c, t in clues.items() if t <= limit)
    skipped = sorted(c for c, t in clues.items() if t > limit)
    if verbose:
        print(f'K={K}: enforcing {len(enforced)} clues, skipping {len(skipped)} '
              f'(targets {sorted(clues[c] for c in skipped)})')

    mins = compute_min_sizes(n, clues)
    forbidden_mono, forced_mono, mono_candidates = monomino_analysis(n, clues, mins)
    if verbose and forced_mono:
        for clue_cell, mono in forced_mono.items():
            print(f'  derived: clue {clue_cell}={clues[clue_cell]} forces a '
                  f'monomino at {mono}')
        for clue_cell, cands in mono_candidates.items():
            if clue_cell not in forced_mono:
                print(f'  candidates for the 1 at {clue_cell}: {cands}')

    shapes, pieces = build_library(cfg)
    kept = filter_placements(cfg, pieces, mins, forbidden_mono)
    if verbose:
        print(f'  shapes={len(shapes)} placements={len(pieces)} '
              f'kept={len(kept)} (filtered {len(pieces)-len(kept)})')

    cover = [[] for _ in range(n * n)]
    for idx, p in enumerate(kept):
        for (r, c) in p.cells:
            cover[r * n + c].append(idx)
    capitol_placements: Dict[Cell, List[int]] = {}
    for idx, p in enumerate(kept):
        if p.capitol is not None:
            capitol_placements.setdefault(p.capitol, []).append(idx)

    model = cp_model.CpModel()
    x = [model.NewBoolVar(f'x{i}') for i in range(len(kept))]
    big = [model.NewBoolVar(f'b{r}_{c}') for r in range(n) for c in range(n)]
    cap = [model.NewBoolVar(f'k{r}_{c}') for r in range(n) for c in range(n)]
    sizecap = [model.NewIntVar(0, K + 1, f's{r}_{c}') for r in range(n) for c in range(n)]
    # distance saturation: K+1 is "beyond every enforced target" and is safe
    # because a tight chain for a clue with T never visits a saturated cell.
    # With no_big the weights are exact, so the saturation only has to cover the
    # largest enforced target.
    # Saturation must sit ABOVE every clue we bound: a saturated cell only says
    # "distance >= M", so an M below the largest target would let the model
    # satisfy `d <= T` with a value that hides a much larger true distance.
    M = max(max(clues.values(), default=0) + 1, K + 1)
    d = [model.NewIntVar(0, M, f'd{r}_{c}') for r in range(n) for c in range(n)]
    inf = [model.NewBoolVar(f'i{r}_{c}') for r in range(n) for c in range(n)]

    for cell_index in range(n * n):
        model.Add(sum(x[i] for i in cover[cell_index]) + big[cell_index] == 1)

    # ---- BIG region: size window, forced cells, connectivity --------------
    if cfg.big_min is not None:
        model.Add(sum(big) >= cfg.big_min)
    if cfg.big_max is not None:
        model.Add(sum(big) <= cfg.big_max)
    for (r, c) in cfg.must_big:
        model.Add(big[r * n + c] == 1)
    for (r, c) in cfg.must_small:
        model.Add(big[r * n + c] == 0)
    # ---- the BIG region must be a symmetric state with capitol blob_capitol --
    if cfg.blob_capitol is not None:
        from shapes import D4 as _D4, apply as _apply, cell_of as _cell_of, centre as _centre
        cap_cell = cfg.blob_capitol
        p0 = _centre(cap_cell)
        elements = []
        for _name, _matrix in _D4.items():
            mp = _apply(_matrix, (0, 0), p0)
            t = (p0[0] - mp[0], p0[1] - mp[1])      # the element fixing cap_cell
            elements.append((_name, _matrix, t))
        sels = [model.NewBoolVar(f'sym{i}') for i in range(len(elements))]
        model.Add(sum(sels) >= 1)
        for idx, (_name, _matrix, t) in enumerate(elements):
            fixed_cells = []
            for r in range(n):
                for c2 in range(n):
                    img = _apply(_matrix, t, _centre((r, c2)))
                    rr, cc = _cell_of(img)
                    if (rr, cc) == (r, c2):
                        fixed_cells.append(r * n + c2)
                    if 0 <= rr < n and 0 <= cc < n:
                        model.Add(big[r * n + c2] == big[rr * n + cc]).OnlyEnforceIf(sels[idx])
                    else:
                        model.Add(big[r * n + c2] == 0).OnlyEnforceIf(sels[idx])
            # capitol rule: exactly one cell of the state is fixed by this element
            model.Add(sum(big[i] for i in fixed_cells) == 1).OnlyEnforceIf(sels[idx])

    # ---- the BIG region is symmetric under at least one D4 map --------------
    # (capitol not required: a capitol-less state is allowed)
    if cfg.blob_symmetric:
        from shapes import D4 as _D4, apply as _apply, cell_of as _cell_of, centre as _centre
        _ORDER = {"rot90": 4, "rot270": 4, "rot180": 2,
                  "refl_vert": 2, "refl_horiz": 2, "refl_diag": 2, "refl_anti": 2}

        def _affine_ok(matrix, shift, order):
            pts = [(0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2), (2, 2)]

            def g(p):
                return _apply(matrix, shift, p)

            for p in pts:
                if g(p) == p:
                    continue
                q = p
                for _ in range(order):
                    q = g(q)
                if q != p:
                    return False
                if order == 4 and g(g(p)) == p:
                    return False
                return True
            return False

        anchor = _centre((10, 8))
        _cands = []
        for _name, _matrix in _D4.items():
            _order = _ORDER[_name]
            mp0 = _apply(_matrix, (0, 0), anchor)
            _seen_t = set()
            for rr in range(n):
                for cc in range(n):
                    q = _centre((rr, cc))
                    t = (q[0] - mp0[0], q[1] - mp0[1])
                    if t in _seen_t:
                        continue
                    _seen_t.add(t)
                    if _affine_ok(_matrix, t, _order):
                        _cands.append((_name, _matrix, t))
        _sels = [model.NewBoolVar(f"bsym{i}") for i in range(len(_cands))]
        model.AddBoolOr(_sels)
        for idx, (_name, _matrix, t) in enumerate(_cands):
            for r in range(n):
                for c2 in range(n):
                    img = _apply(_matrix, t, _centre((r, c2)))
                    rr, cc = _cell_of(img)
                    if 0 <= rr < n and 0 <= cc < n:
                        model.Add(big[r * n + c2] == big[rr * n + cc]).OnlyEnforceIf(_sels[idx])
                    else:
                        model.Add(big[r * n + c2] == 0).OnlyEnforceIf(_sels[idx])

    # ---- Manhattan ring: a capitol within (C+1)//2 of every clue ----------
    if cfg.manhattan_ring:
        for clue, target in clues.items():
            rad = (target + 1) // 2
            ball = [cap[r * n + c] for r in range(n) for c in range(n)
                    if abs(r - clue[0]) + abs(c - clue[1]) <= rad]
            if ball:
                model.AddBoolOr(ball)

    # a BIG state holds more than K >= 1 cells, so no BIG cell is isolated
        for r in range(n):
            for c2 in range(n):
                nbr = [big[rr * n + cc] for (rr, cc) in neighbours((r, c2), n)]
                if nbr:
                    model.AddBoolOr(nbr).OnlyEnforceIf(big[r * n + c2])

    for c in range(n * n):
        # BIG cells carry the capped weight K+1 - never M, which is only the
        # distance saturation bound
        expr = sum(kept[i].size * x[i] for i in cover[c]) + (K + 1) * big[c]
        model.Add(sizecap[c] == expr)
        model.Add(cap[c] <= sum(x[i] for i in capitol_placements.get((c // n, c % n), [])) + big[c])
        for i in capitol_placements.get((c // n, c % n), []):
            model.Add(cap[c] >= x[i])
        model.Add(d[c] == 0).OnlyEnforceIf(cap[c])
        model.Add(d[c] > 0).OnlyEnforceIf(cap[c].Not())
        model.Add(d[c] == M).OnlyEnforceIf(inf[c])
        model.Add(d[c] < M).OnlyEnforceIf(inf[c].Not())

    if cfg.no_big_caps:
        # only the forced 0-clue cells may be BIG capitols
        for r in range(n):
            for c in range(n):
                if clues.get((r, c), -1) != 0:
                    model.Add(cap[r * n + c] + big[r * n + c] <= 1)

    if cfg.max_big_caps is not None:
        # number of BIG capitols = sum(cap) - (chosen placements with a capitol)
        _cap_placements = sorted({i for lst in capitol_placements.values()
                                  for i in lst})
        model.Add(sum(cap) - sum(x[i] for i in _cap_placements)
                  <= cfg.max_big_caps)

    if cfg.big_connected_min:
        # Every BIG connected component has at least K+1 cells.  The root r is
        # the minimum-index cell of its component; flow[(r,c)] says c belongs
        # to the component rooted at r.
        flow = {}
        for r in range(n * n):
            for c in range(r, n * n):
                flow[(r, c)] = model.NewBoolVar(f"g{r}_{c}")
        for r in range(n * n):
            model.Add(flow[(r, r)] <= big[r])
            model.Add(sum(flow[(r, c)] for c in range(r, n * n))
                      >= (K + 1) * flow[(r, r)])
        for c in range(n * n):
            model.Add(sum(flow[(r, c)] for r in range(c + 1)) == big[c])
        for r in range(n * n):
            for c in range(r + 1, n * n):
                rr, cc = divmod(c, n)
                parents = []
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    r2, c2 = rr + dr, cc + dc
                    if 0 <= r2 < n and 0 <= c2 < n:
                        idx = r2 * n + c2
                        if r <= idx < c:
                            parents.append(flow[(r, idx)])
                model.Add(flow[(r, c)] <= sum(parents))

        if cfg.big_components is not None:
            model.Add(sum(flow[(r, r)] for r in range(n * n))
                      == cfg.big_components)
        if cfg.big_anchor is not None and cfg.big_anchor_size is not None:
            _ar, _ac = cfg.big_anchor
            _a = _ar * n + _ac
            for r in range(_a + 1):
                model.Add(sum(flow[(r, c)] for c in range(r, n * n))
                          == cfg.big_anchor_size).OnlyEnforceIf(flow[(r, _a)])

    # one weight variable per undirected edge, shared by both directions
    edges = []
    for r in range(n):
        for c in range(n):
            u = r * n + c
            for (dr, dc) in ((1, 0), (0, 1)):
                rr, cc = r + dr, c + dc
                if rr >= n or cc >= n:
                    continue
                v = rr * n + cc
                w = model.NewIntVar(0, M, f'w{u}_{v}')
                model.AddMinEquality(w, [sizecap[u], sizecap[v]])
                edges.append((u, v, w))

    if cfg.big_root is not None:
        # single-commodity flow: every BIG cell is reachable from the root
        root = cfg.big_root[0] * n + cfg.big_root[1]
        model.Add(big[root] == 1)
        inflow = [[] for _ in range(n * n)]
        outflow = [[] for _ in range(n * n)]
        for (u, v, _w) in edges:
            # flow in BOTH directions - a single direction would leave the root
            # unable to reach cells "behind" it
            for (a, b) in ((u, v), (v, u)):
                f = model.NewIntVar(0, n * n, f'f{a}_{b}')
                model.Add(f <= n * n * big[a])
                model.Add(f <= n * n * big[b])
                outflow[a].append(f)
                inflow[b].append(f)
        for cell in range(n * n):
            if cell == root:
                continue
            model.Add(sum(inflow[cell]) - sum(outflow[cell]) == big[cell])
        model.Add(sum(outflow[root]) - sum(inflow[root]) == sum(big) - 1)

    tight_vars: List[List[cp_model.IntVar]] = [[] for _ in range(n * n)]
    for (u, v, w) in edges:
        for (a, b) in ((u, v), (v, u)):
            model.Add(d[b] <= d[a] + w).OnlyEnforceIf(inf[b].Not())
            # A cell may only be "saturated" (distance >= M) if every neighbour
            # is also far away.  Without this, `inf` would be a free escape
            # hatch: a cell could claim d = M and dodge the triangle
            # inequality, making the clue constraints unsound.  With it, a
            # saturated cell forces saturation along the whole chain back to a
            # capitol, which is impossible (a capitol has d = 0 and an edge
            # costs at most K < M), so only genuinely distant cells saturate.
            model.Add(d[a] + w >= M).OnlyEnforceIf(inf[b])
            t = model.NewBoolVar(f't{a}_{b}')
            model.Add(d[b] == d[a] + w).OnlyEnforceIf(t)
            tight_vars[b].append(t)
    for b in range(n * n):
        model.AddBoolOr(tight_vars[b] + [cap[b], inf[b]])

    # --- second distance field: shortest path with NO BIG-BIG step ----------
    # Such a path uses only known weights, so its length is an UPPER bound on the
    # real distance.  The real distance must equal T, hence this bound must be
    # >= T for every clue - including the ones above K, which is the only
    # sound way to stop the model from contradicting them.
    M2 = (max(clues.values()) if clues else 0) + K + 1
    d2 = [model.NewIntVar(0, M2, f'e{r}_{c}') for r in range(n) for c in range(n)]
    inf2 = [model.NewBoolVar(f'j{r}_{c}') for r in range(n) for c in range(n)]
    for c in range(n * n):
        model.Add(d2[c] == 0).OnlyEnforceIf(cap[c])
        model.Add(d2[c] > 0).OnlyEnforceIf(cap[c].Not())
        model.Add(d2[c] == M2).OnlyEnforceIf(inf2[c])
        model.Add(d2[c] < M2).OnlyEnforceIf(inf2[c].Not())

    tight2: List[List[cp_model.IntVar]] = [[] for _ in range(n * n)]
    for (u, v, _w) in edges:
        minv = model.NewIntVar(0, K + 1, f'u{u}_{v}')
        model.AddMinEquality(minv, [sizecap[u], sizecap[v]])
        band = model.NewBoolVar(f'g{u}_{v}')
        model.Add(band <= big[u])
        model.Add(band <= big[v])
        model.Add(band >= big[u] + big[v] - 1)
        wk = model.NewIntVar(0, M2, f'q{u}_{v}')
        model.Add(wk == M2).OnlyEnforceIf(band)
        model.Add(wk == minv).OnlyEnforceIf(band.Not())
        for (a, b) in ((u, v), (v, u)):
            model.Add(d2[b] <= d2[a] + wk).OnlyEnforceIf(inf2[b].Not())
            model.Add(d2[a] + wk >= M2).OnlyEnforceIf(inf2[b])
            t2 = model.NewBoolVar(f'z{a}_{b}')
            model.Add(d2[b] == d2[a] + wk).OnlyEnforceIf(t2)
            tight2[b].append(t2)
    for b in range(n * n):
        model.AddBoolOr(tight2[b] + [cap[b], inf2[b]])

    for cell, target in clues.items():
        if target > K:
            model.Add(d2[cell[0] * n + cell[1]] >= target)

    # clues
    if cfg.no_big:
        for cell_index in range(n * n):
            model.Add(big[cell_index] == 0)
    for cell in enforced:
        model.Add(d[cell[0] * n + cell[1]] == clues[cell])
    # Clues above K cannot be *enforced* (a BIG cell's real size is unknown),
    # but they can still be contradicted: the model distance uses
    # min(size, K+1) <= real size, so it is a LOWER bound on the true distance.
    # True distance must equal T, hence d <= T is necessary for every clue.
    for cell, target in clues.items():
        if target > K:
            model.Add(d[cell[0] * n + cell[1]] <= target)

    for cell, target in clues.items():
        idx = cell[0] * n + cell[1]
        if target == 0:
            model.Add(cap[idx] == 1)
        else:
            # a capitol here would give distance 0 != target
            model.Add(cap[idx] == 0)

    # Manhattan-ball rule: the nearest capitol to clue v is within
    # Manhattan distance (v+1)//2.  (Non-capitol states have size >= 2,
    # so edges between them cost >= 2; only the last edge to a singleton
    # capitol can cost 1.)
    for cell, target in clues.items():
        r0, c0 = cell
        rad = (target + 1) // 2
        ball = [cap[r * n + c] for r in range(n) for c in range(n)
                if abs(r - r0) + abs(c - c0) <= rad]
        model.AddBoolOr(ball)
    for cell, target in clues.items():
        if target != 1:
            continue
        monos = []
        for nb in neighbours(cell, n):
            for i in cover[nb[0] * n + nb[1]]:
                if kept[i].size == 1:
                    monos.append(x[i])
        if monos:
            model.AddBoolOr(monos)
    for cell, need in mins.items():
        # sizecap is capped at K+1 for BIG cells, so a bound above K means the
        # state cannot be small at all - that is "must be BIG", not "size >= need"
        idx = cell[0] * n + cell[1]
        if need > K:
            model.Add(big[idx] == 1)
        else:
            model.Add(sizecap[idx] >= need)
    for clue_cell, mono in forced_mono.items():
        for i in cover[mono[0] * n + mono[1]]:
            if kept[i].size == 1:
                model.Add(x[i] == 1)

    for (comp, nbrs) in (cfg.big_growth_cuts or []):
        lits = [big[r * n + c].Not() for (r, c) in comp]
        lits += [big[r * n + c] for (r, c) in nbrs]
        model.AddBoolOr(lits)

    for (chosen_cells, cut_big) in (cfg.cuts or []):
        literals = [x[i].Not() for i, p in enumerate(kept) if p.cells in chosen_cells]
        for c in range(n * n):
            cell = (c // n, c % n)
            literals.append(big[c].Not() if cell in cut_big else big[c])
        model.AddBoolOr(literals)

    if cfg.fix:
        fixed = {frozenset(s) for s in cfg.fix.get('placements', [])}
        used = set()
        for idx, p in enumerate(kept):
            if p.cells in fixed:
                model.Add(x[idx] == 1)
                used.add(p.cells)
        for cells in fixed - used:
            print(f'  FIX ERROR: placement {sorted(cells)} is not in the filtered library')
        for (r, c) in cfg.fix.get('big', set()):
            model.Add(big[r * n + c] == 1)
        for (r, c) in cfg.fix.get('big_capitols', set()):
            model.Add(cap[r * n + c] == 1)

    # optional hunch: (6,0),(6,1),(6,2) in one size-11 state with capitol (6,1)
    if cfg.hunch:
        triple = {(6, 0), (6, 1), (6, 2)}
        cands = [i for i, p in enumerate(kept)
                 if p.size == 11 and p.capitol == (6, 1) and triple <= p.cells]
        if verbose:
            print(f'  hunch: {len(cands)} placements of size 11 with capitol '
                  f'(6,1) covering {(6,0),(6,1),(6,2)}')
        if cands:
            model.AddBoolOr([x[i] for i in cands])
        else:
            if verbose:
                print('  hunch placement does not exist in the library - ignored')

    objective_terms = []
    if cfg.maximize:
        soft = []
        for cell in enforced:
            b = model.NewBoolVar(f'ok_{cell[0]}_{cell[1]}')
            model.Add(d[cell[0] * n + cell[1]] == clues[cell]).OnlyEnforceIf(b)
            soft.append(b)
        model.Maximize(sum(soft))
        objective_terms = soft

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = cfg.time_limit
    solver.parameters.num_search_workers = cfg.workers
    solver.parameters.log_search_progress = cfg.log_progress
    solver.parameters.random_seed = cfg.seed
    status = solver.Solve(model)
    wall = time.time() - t0
    name = solver.StatusName(status)
    res = Stage1Result(status=name, nodes=int(solver.NumBranches()),
                       wall=wall, enforced=enforced, skipped=skipped,
                       placements_used=len(kept))

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        solution = extract(solver, cfg, kept, x, big, cap, d, n)
        res.solution = solution
        if cfg.maximize:
            dropped = [c for c in enforced
                       if solver.Value(d[c[0] * n + c[1]]) != clues[c]]
            res.dropped_clues = dropped
            if verbose:
                print(f'  maximize: {len(enforced)-len(dropped)}/{len(enforced)} '
                      f'clues satisfied; dropped {dropped}')
    return res


def extract(solver, cfg: Stage1Config, kept: Sequence[Placement],
            x: Sequence, big: Sequence, cap: Sequence, d: Sequence,
            n: int) -> Stage1Solution:
    """Read a solution out of the CP-SAT values."""
    state_of: List[List[Optional[int]]] = [[None] * n for _ in range(n)]
    states: List[Tuple[FrozenSet[Cell], Optional[Cell]]] = []
    big_cells: Set[Cell] = set()
    big_capitols: Set[Cell] = set()

    for idx, p in enumerate(kept):
        if not solver.Value(x[idx]):
            continue
        sid = len(states)
        states.append((p.cells, p.capitol))
        for (r, c) in p.cells:
            state_of[r][c] = sid

    for r in range(n):
        for c in range(n):
            i = r * n + c
            if solver.Value(big[i]):
                big_cells.add((r, c))
                if solver.Value(cap[i]):
                    big_capitols.add((r, c))

    distances = [[solver.Value(d[r * n + c]) for c in range(n)] for r in range(n)]
    return Stage1Solution(n, state_of, states, frozenset(big_cells),
                          frozenset(big_capitols), distances)
