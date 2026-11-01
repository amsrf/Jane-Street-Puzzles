"""Pretty-print a stage-1 solution and independently check every clue."""

import heapq

from stage1 import PUZZLE_11X11_CLUES

N = 11
K = 14


def render(sol):
    states = [(frozenset(cells), cap) for cells, cap in sol.states]
    big = set(sol.big)
    big_caps = set(sol.big_capitols)

    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    cell_char = {}
    cap_char = {}
    for i, (cells, cap) in enumerate(states):
        L = labels[i] if i < len(labels) else "?"
        for c in cells:
            cell_char[c] = L
        if cap is not None:
            cap_char[cap] = L

    print(f"\nsolution: {len(states)} small states, {len(big)} BIG cells, "
          f"{len(big_caps)} BIG capitols")
    print("     " + " ".join(f"{c:>2}" for c in range(N)))
    for r in range(N):
        line = ""
        for c in range(N):
            p = (r, c)
            if p in cap_char:
                line += "*"
            elif p in cell_char:
                line += cell_char[p]
            elif p in big_caps:
                line += "@"
            elif p in big:
                line += "#"
            else:
                line += "."
        print(f"{r:>2}   " + " ".join(f"{ch:>2}" for ch in line))

    print("\nstate legend (* = small capitol, @ = BIG capitol):")
    for i, (cells, cap) in enumerate(states):
        L = labels[i] if i < len(labels) else "?"
        print(f"  {L}: size {len(cells):>2}  capitol {cap}  cells {sorted(cells)}")
    print(f"\nBIG capitols ({len(big_caps)}): {sorted(big_caps)}")

    size = {}
    for cells, cap in states:
        for c in cells:
            size[c] = len(cells)
    for c in big:
        size[c] = K + 1
    sources = [cap for cells, cap in states if cap is not None] + list(big_caps)
    dist = {s: 0 for s in sources}
    pq = [(0, s) for s in sources]
    heapq.heapify(pq)
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, 10 ** 9):
            continue
        r, c = u
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            v = (r + dr, c + dc)
            if v in size:
                nd = d + min(size[u], size[v])
                if nd < dist.get(v, 10 ** 9):
                    dist[v] = nd
                    heapq.heappush(pq, (nd, v))

    print("\nclue check:")
    bad = 0
    for cell, target in sorted(PUZZLE_11X11_CLUES.items()):
        d = dist.get(cell, 10 ** 9)
        enforced = target <= K
        ok = (d == target) if enforced else (d <= target)
        if enforced and not ok:
            bad += 1
        print(f"  {str(cell):>7} T={target:>2} d={d:>3} "
              f"{'ENFORCED' if enforced else 'large   '} "
              f"{'OK' if ok else 'FAIL'}")
    print(f"enforced failures: {bad}")
