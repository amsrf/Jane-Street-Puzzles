"""Plain K=14 run: no 37-blob, no big_root, at most one BIG capitol,
every BIG component >= 15, small-clue model + Manhattan ring."""

import os

os.environ["K"] = "14"

import time

from stage1 import PUZZLE_11X11_CLUES, Stage1Config, solve
import validate_stage1
from main import offending_big_components
from render_solution import render

N = 11
K = 14
PER = float(os.environ.get("PER_TIME", "1500"))


def main():
    cfg = Stage1Config(
        n=N, clues=PUZZLE_11X11_CLUES, K=K,
        time_limit=PER,
        workers=int(os.environ.get("WORKERS", "16")),
        big_min=K + 1,
        max_big_caps=1,
        big_connected_min=True,
        manhattan_ring=True,
        seed=1,
    )
    res = solve(cfg, verbose=False)
    print(f"status={res.status} wall={res.wall:.1f}s "
          f"placements={res.placements_used}", flush=True)

    if res.solution is None:
        print("no solution")
        return

    sol = res.solution
    bad = offending_big_components(sol, K)
    if bad:
        print(f"reject: BIG comps < K+1: {[len(c) for c, _ in bad]}")
        return
    rep = validate_stage1.validate_stage1(sol, PUZZLE_11X11_CLUES, K)
    print(rep.text(), flush=True)
    if not rep.ok:
        print("validator failed")
        return

    print(f"\nVALID: {len(sol.states)} small states, "
          f"{len(sol.big)} BIG cells, {len(sol.big_capitols)} BIG capitols",
          flush=True)
    render(sol)


if __name__ == "__main__":
    main()
