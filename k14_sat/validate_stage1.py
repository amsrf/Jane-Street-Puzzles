"""Independent validator for Stage-1 solutions.

Nothing here imports the model or the shape library: symmetry, capitols,
distances and clue values are all recomputed from scratch.  A solution that
fails this file is never reported as a solution.

Checks
  1. every cell covered exactly once; every small state connected, symmetric,
     and its capitol recomputed by brute force (must match what was claimed);
  2. weights min(size, K+1) per cell (BIG = K+1), multi-source Dijkstra from all
     small capitols plus the freely chosen BIG capitols;
  3. every enforced clue (target <= K) equals the computed distance;
  4. necessary BIG check: every connected component of BIG cells holds at least
     K+1 cells (a smaller component would really be a small state, so the model
     is only complete if this is reported, not assumed).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence, Set, Tuple

Cell = Tuple[int, int]
INF = 10 ** 9


# --- geometry, written independently of the shape library -------------------
# Doubled coordinates; the seven non-identity isometries of the square.
def _double(cell: Cell) -> Tuple[int, int]:
    r, c = cell
    return (2 * r + 1, 2 * c + 1)


def _undouble(point: Tuple[int, int]) -> Cell:
    a, b = point
    return ((a - 1) // 2, (b - 1) // 2)


_MAPS = {
    'mirror_rows': lambda a, b: (a, -b),
    'mirror_cols': lambda a, b: (-a, b),
    'diagonal':    lambda a, b: (b, a),
    'antidiagonal': lambda a, b: (-b, -a),
    'turn_180':    lambda a, b: (-a, -b),
    'turn_90':     lambda a, b: (b, -a),
    'turn_270':    lambda a, b: (-b, a),
}


def symmetry_elements(cells: FrozenSet[Cell]) -> List[Tuple[str, Tuple[int, int], List[Cell]]]:
    """Every (name, translation, fixed_cells) mapping the cell set onto itself."""
    points = {c: _double(c) for c in cells}
    lo_a = min(p[0] for p in points.values())
    lo_b = min(p[1] for p in points.values())
    target = set(points.values())
    out = []
    for name, fn in _MAPS.items():
        moved = {c: fn(*points[c]) for c in cells}
        ma = min(p[0] for p in moved.values())
        mb = min(p[1] for p in moved.values())
        shift = (lo_a - ma, lo_b - mb)
        image = {c: (moved[c][0] + shift[0], moved[c][1] + shift[1]) for c in cells}
        if set(image.values()) == target:
            fixed = [c for c in cells if image[c] == points[c]]
            out.append((name, shift, fixed))
    return out


def capitol_of(cells: FrozenSet[Cell]) -> Tuple[bool, Optional[Cell]]:
    """(is_symmetric, capitol) by brute force over the seven isometries."""
    elements = symmetry_elements(cells)
    if not elements:
        return False, None
    if not all(len(fixed) == 1 for (_, _, fixed) in elements):
        return False if False else (True, None)     # symmetric but no capitol
    common = {fixed[0] for (_, _, fixed) in elements}
    if len(common) != 1:
        return True, None
    return True, next(iter(common))


def is_connected(cells: FrozenSet[Cell]) -> bool:
    if not cells:
        return False
    first = next(iter(cells))
    seen = {first}
    stack = [first]
    while stack:
        r, c = stack.pop()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = (r + dr, c + dc)
            if nb in cells and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(cells)


@dataclass
class Report:
    ok: bool
    lines: List[str] = field(default_factory=list)
    big_component_sizes: List[int] = field(default_factory=list)

    def add(self, good: bool, text: str) -> bool:
        self.lines.append(('  ok   ' if good else '  FAIL ') + text)
        if not good:
            self.ok = False
        return good

    def text(self) -> str:
        head = 'PASS' if self.ok else 'FAIL'
        return '\n'.join([head] + self.lines)


def validate_stage1(solution, clues: Dict[Cell, int], K: int,
                    require_big_state: bool = False) -> Report:
    n = solution.n
    rep = Report(ok=True)

    # ---- 1. covering, connectivity, symmetry, capitol --------------------
    owner: Dict[Cell, int] = {}
    for sid, (cells, claimed_capitol) in enumerate(solution.states):
        if not rep.add(is_connected(cells), f'state {sid} connected'):
            continue
        symmetric, capitol = capitol_of(cells)
        rep.add(symmetric, f'state {sid} symmetric (size {len(cells)})')
        rep.add(capitol == claimed_capitol,
                f'state {sid} capitol recomputed {capitol} == claimed {claimed_capitol}')
        for cell in cells:
            if cell in owner:
                rep.add(False, f'cell {cell} covered twice')
            owner[cell] = sid

    for cell in solution.big:
        if cell in owner:
            rep.add(False, f'BIG cell {cell} also in a small state')
        owner[cell] = -1

    for r in range(n):
        for c in range(n):
            if (r, c) not in owner:
                rep.add(False, f'cell {(r, c)} not covered')
    rep.add(len(owner) == n * n, f'coverage count {len(owner)} == {n*n}')

    # ---- 2. weights and multi-source Dijkstra ----------------------------
    size = [[0] * n for _ in range(n)]
    for r in range(n):
        for c in range(n):
            sid = solution.state_of[r][c]
            size[r][c] = K + 1 if sid is None else len(solution.states[sid][0])

    sources: List[Cell] = []
    for sid, (cells, capitol) in enumerate(solution.states):
        if capitol is not None:
            sources.append(capitol)
    sources.extend(solution.big_capitols)
    rep.add(bool(sources), f'{len(sources)} capitols used as Dijkstra sources')

    dist = [[INF] * n for _ in range(n)]
    heap = []
    for (r, c) in sources:
        if dist[r][c] > 0:
            dist[r][c] = 0
            heapq.heappush(heap, (0, r, c))
    while heap:
        d, r, c = heapq.heappop(heap)
        if d > dist[r][c]:
            continue
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if not (0 <= rr < n and 0 <= cc < n):
                continue
            step = min(size[r][c], size[rr][cc])
            nd = d + step
            if nd < dist[rr][cc]:
                dist[rr][cc] = nd
                heapq.heappush(heap, (nd, rr, cc))

    # ---- 3a. distances with no BIG-BIG step (upper bound on the real one) --
    big_free = [[INF] * n for _ in range(n)]
    heap = []
    for (r, c) in sources:
        big_free[r][c] = 0
        heapq.heappush(heap, (0, r, c))
    while heap:
        d, r, c = heapq.heappop(heap)
        if d > big_free[r][c]:
            continue
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if not (0 <= rr < n and 0 <= cc < n):
                continue
            # a step between two BIG cells has an unknown cost: exclude it
            if size[r][c] > K and size[rr][cc] > K:
                continue
            step = min(size[r][c], size[rr][cc])
            nd = d + step
            if nd < big_free[rr][cc]:
                big_free[rr][cc] = nd
                heapq.heappush(heap, (nd, rr, cc))

    # ---- 3b. clues ---------------------------------------------------------
    for cell, target in sorted(clues.items()):
        lo = dist[cell[0]][cell[1]]        # lower bound on the true distance
        hi = big_free[cell[0]][cell[1]]    # upper bound on the true distance
        if target <= K:
            rep.add(lo == target, f'clue {cell} = {target} (computed {lo})')
        else:
            # cannot be verified at stage 1, but must not be contradicted
            rep.add(lo <= target,
                    f'clue {cell} = {target}: lower bound {lo} must be <= {target}')
            rep.add(hi >= target,
                    f'clue {cell} = {target}: upper bound {hi} must be >= {target}')

    # ---- 4. BIG components -------------------------------------------------
    seen: Set[Cell] = set()
    for cell in solution.big:
        if cell in seen:
            continue
        comp = []
        stack = [cell]
        seen.add(cell)
        while stack:
            r, c = stack.pop()
            comp.append((r, c))
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (r + dr, c + dc)
                if nb in solution.big and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        rep.big_component_sizes.append(len(comp))
        rep.add(len(comp) >= K + 1,
                f'BIG component of {len(comp)} cells is at least K+1={K+1}')
    # ---- 5. is the BIG region itself a legal state? ------------------------
    # Only when the run assumed ONE big state.  Stage-1 in general allows BIG to
    # be several unspecified states, in which case this check does not apply.
    if require_big_state and solution.big:
        rep.add(is_connected(solution.big),
                f'BIG region connected ({len(solution.big)} cells)')
        symmetric, cap = capitol_of(solution.big)
        rep.add(symmetric, 'BIG region symmetric')
        if symmetric:
            rep.add(cap is not None, f'BIG region has a capitol ({cap})')
            if cap is not None:
                rep.add(set(solution.big_capitols) == {cap},
                        'BIG capitol chosen ' + str(sorted(solution.big_capitols))
                        + ' equals the recomputed ' + str(cap))
    return rep
