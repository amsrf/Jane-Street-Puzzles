"""Expand shapes into board placements: 8 orientations x translations.

A placement is a concrete cell set inside the n x n board, together with the
capitol recomputed for that exact cell set (the capitol rotates with the shape).
Placements are deduplicated by cell set, so a shape with extra symmetry does not
produce duplicate placements.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from shapes import (Cell, D4, IDENTITY, analyse, apply, canonical, cell_of,
                    centre, generate_shapes)


@dataclass(frozen=True)
class Placement:
    cells: FrozenSet[Cell]
    capitol: Optional[Cell]
    size: int
    shape_key: Tuple

    @property
    def has_capitol(self) -> bool:
        return self.capitol is not None


def orientations(shape_key: Tuple[Tuple[int, int], ...]) -> List[FrozenSet[Cell]]:
    """The distinct D4 images of a shape, as cells translated to the origin."""
    out: Set[FrozenSet[Cell]] = set()
    for matrix in (IDENTITY, *D4.values()):
        points = [apply(matrix, (0, 0), (x, y)) for (x, y) in shape_key]
        mx = min(p[0] for p in points)
        my = min(p[1] for p in points)
        cells = frozenset(((y - my) // 2, (x - mx) // 2) for (x, y) in points)
        out.add(cells)
    return sorted(out, key=lambda s: (len(s), sorted(s)))


def translations(cells: FrozenSet[Cell], n: int) -> Iterable[FrozenSet[Cell]]:
    rows = [r for (r, c) in cells]
    cols = [c for (r, c) in cells]
    height = max(rows) - min(rows) + 1
    width = max(cols) - min(cols) + 1
    for dr in range(n - height + 1):
        for dc in range(n - width + 1):
            yield frozenset((r + dr, c + dc) for (r, c) in cells)


def build_placements(n: int, shapes: Dict[Tuple, object],
                     verbose: bool = True) -> List[Placement]:
    """Every placement of every shape, deduplicated by cell set."""
    t0 = time.time()
    seen: Dict[FrozenSet[Cell], Placement] = {}
    for shape_key in shapes:
        for orient in orientations(shape_key):
            for cells in translations(orient, n):
                if cells in seen:
                    continue
                info = analyse(cells)
                seen[cells] = Placement(cells, info.capitol, len(cells), shape_key)
    if verbose:
        by_size: Dict[int, int] = {}
        for p in seen.values():
            by_size[p.size] = by_size.get(p.size, 0) + 1
        total = sum(by_size.values())
        print(f'placements (n={n}): {total} in {time.time()-t0:.2f}s')
        for size in sorted(by_size):
            print(f'   size {size:2d}: {by_size[size]:6d} placements')
        caps = sum(1 for p in seen.values() if p.has_capitol)
        print(f'   with capitol: {caps}   without: {total-caps}')
    return list(seen.values())


def placements_by_cell(placements: Sequence[Placement], n: int
                       ) -> List[List[Placement]]:
    """Index placements by the cell they cover (flat list of length n*n)."""
    index: List[List[Placement]] = [[] for _ in range(n * n)]
    for p in placements:
        for (r, c) in p.cells:
            index[r * n + c].append(p)
    return index


if __name__ == '__main__':
    import sys
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    k = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    shapes = generate_shapes(n, k, verbose=True)
    pieces = build_placements(n, shapes, verbose=True)
    print(f'shapes={len(shapes)} placements={len(pieces)} '
          f'ratio={len(pieces)/max(1,len(shapes)):.1f}')
