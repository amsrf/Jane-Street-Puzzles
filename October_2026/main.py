"""Command line driver for the Stage-1 solver.

  python main.py shapes  [n] [K]        library statistics only
  python main.py gate5                  the 5x5 gate (K=11, then K=4 with a hint)
  python main.py puzzle11 [options]     the 11x11 stage-1 run

Options for puzzle11:
  --K K              state size cap (default 12)
  --time-limit S     solver time limit in seconds (default 120)
  --workers N        CP-SAT workers (default 8)
  --hunch            add the (6,0),(6,1),(6,2) / capitol (6,1) hypothesis
  --maximize         debug: clues become soft, maximise satisfied
  --count            keep looking for more solutions with cuts (max 50)
  --yes              skip the transcription confirmation prompt
  --log              CP-SAT search log
"""

from __future__ import annotations

import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from placements import build_placements
from shapes import Cell, generate_shapes
from stage1 import (EXAMPLE_5X5_CLUES, PUZZLE_11X11_CLUES, Stage1Config,
                    Stage1Result, Stage1Solution, build_library,
                    compute_min_sizes, filter_placements, monomino_analysis,
                    solve)
import validate_stage1


def render_clue_grid(n: int, clues: Dict[Cell, int]) -> str:
    out = []
    for r in range(n):
        row = []
        for c in range(n):
            v = clues.get((r, c))
            row.append(f'{v:3d}' if v is not None else '  .')
        out.append(' '.join(row))
    return '\n'.join(out)


def render_solution(sol: Stage1Solution) -> str:
    n = sol.n
    wide = max(2, len(str(len(sol.states))))
    out = []
    for r in range(n):
        row = []
        for c in range(n):
            sid = sol.state_of[r][c]
            if sid is None:
                row.append('#*' if (r, c) in sol.big_capitols else ' #')
            else:
                row.append(f'{sid:>{wide}}')
        out.append(' '.join(row))
    sizes = ', '.join(
        f'{i}:{len(cells)}{"*" if cap is not None else ""}'
        for i, (cells, cap) in enumerate(sol.states)
    )
    caps = ', '.join(f'{v}->{k}' for v, k in
                     ((len(cells), cap) for (cells, cap) in sol.states if cap is not None))
    big = sorted(sol.big)
    lines = [f'BIG cells: {len(big)}; BIG capitols: {sorted(sol.big_capitols)}']
    if big:
        lines.append('   ' + ' '.join(str(x) for x in big))
    lines.append(f'small states (id:size, * = has capitol): {sizes}')
    if caps:
        lines.append(f'capitols (size->cell): {caps}')
    return '\n'.join(out) + '\n' + '\n'.join(lines)


def report(result: Stage1Result, clues: Dict[Cell, int], K: int,
           verbose: bool = True) -> bool:
    """Validate and print.  Returns True only for a validated solution."""
    print(f'status={result.status} branches={result.nodes} wall={result.wall:.1f}s '
          f'placements_in_model={result.placements_used}')
    if result.solution is None:
        return False
    rep = validate_stage1.validate_stage1(result.solution, clues, K)
    print(render_solution(result.solution))
    if verbose:
        print(rep.text())
    if not rep.ok:
        print('*** validator FAILED - not reporting a solution ***')
        return False
    return True


# ---------------------------------------------------------------------------
def cmd_shapes(n: int, K: int) -> None:
    shapes = generate_shapes(n, K, verbose=True)
    pieces = build_placements(n, shapes, verbose=True)


def cmd_gate5() -> int:
    print('=' * 70)
    print('GATE 1: 5x5, K=11 - every clue enforced')
    print('=' * 70)
    cfg = Stage1Config(n=5, clues=EXAMPLE_5X5_CLUES, K=11, time_limit=60,
                       workers=8, no_big=True)
    res = solve(cfg)
    ok11 = report(res, EXAMPLE_5X5_CLUES, 11)

    print()
    print('the known 5x5 tiling, checked directly by the validator (K=11):')
    known = [
        ({(0, 0), (1, 0), (2, 0), (2, 1), (3, 1), (3, 2), (3, 3)}, (2, 1)),
        ({(0, 1), (0, 2), (1, 1), (1, 2)}, None),
        ({(1, 3), (2, 2), (2, 3)}, (2, 3)),
        ({(0, 3), (0, 4), (1, 4), (2, 4), (3, 0), (3, 4),
          (4, 0), (4, 1), (4, 2), (4, 3), (4, 4)}, (4, 4)),
    ]
    state_of = [[None] * 5 for _ in range(5)]
    for sid, (cells, _cap) in enumerate(known):
        for (r, c) in cells:
            state_of[r][c] = sid
    known_sol = Stage1Solution(5, state_of, [(frozenset(cells), cap) for cells, cap in known],
                               frozenset(), frozenset(), [])
    rep_known = validate_stage1.validate_stage1(known_sol, EXAMPLE_5X5_CLUES, 11)
    print(rep_known.text())
    ok_known = rep_known.ok
    print()

    print('=' * 70)
    print('GATE 2: 5x5, K=4 - only clues with T<=4 are enforced, true tiling fixed')
    print('=' * 70)
    # the true tiling: 7- and 11-cell states become BIG, the 2x2 and the L stay
    true_small = [
        frozenset({(0, 1), (0, 2), (1, 1), (1, 2)}),          # size 4 (2x2)
        frozenset({(1, 3), (2, 2), (2, 3)}),                  # size 3 (L)
    ]
    true_big = (
        {(0, 0), (1, 0), (2, 0), (2, 1), (3, 1), (3, 2), (3, 3)}          # size 7
        | {(0, 3), (0, 4), (1, 4), (2, 4), (3, 0), (3, 4),                # size 11
           (4, 0), (4, 1), (4, 2), (4, 3), (4, 4)}
    )
    cfg4 = Stage1Config(n=5, clues=EXAMPLE_5X5_CLUES, K=4, time_limit=60, workers=8,
                        fix={'placements': true_small, 'big': true_big,
                             'big_capitols': {(2, 1), (4, 4)}})
    res4 = solve(cfg4)
    ok4 = res4.solution is not None
    print(f'status={res4.status} branches={res4.nodes} wall={res4.wall:.1f}s')
    if res4.solution is not None:
        rep = validate_stage1.validate_stage1(res4.solution, EXAMPLE_5X5_CLUES, 4)
        print(rep.text())
        ok4 = rep.ok
    print()
    gate_ok = ok11 and ok4 and ok_known and res4.status in ('FEASIBLE', 'OPTIMAL')
    print('GATE RESULT:', 'PASS' if gate_ok else 'FAIL')
    return 0 if gate_ok else 1


def offending_big_components(sol: Stage1Solution, K: int):
    """BIG components smaller than K+1, with their non-BIG neighbours."""
    n = sol.n
    seen = set()
    out = []
    for start in sol.big:
        if start in seen:
            continue
        comp = []
        stack = [start]
        seen.add(start)
        while stack:
            r, c = stack.pop()
            comp.append((r, c))
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nb = (r + dr, c + dc)
                if nb in sol.big and nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        if len(comp) < K + 1:
            nbrs = set()
            for (r, c) in comp:
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nb = (r + dr, c + dc)
                    if 0 <= nb[0] < n and 0 <= nb[1] < n and nb not in sol.big:
                        nbrs.add(nb)
            out.append((set(comp), nbrs))
    return out


def cmd_puzzle11(args) -> int:
    n = 11
    clues = PUZZLE_11X11_CLUES
    K = args.K
    print('transcribed 11x11 clues (row, col) = value:')
    print(render_clue_grid(n, clues))
    print()
    enforced = sorted(c for c, t in clues.items() if t <= K)
    skipped = sorted(c for c, t in clues.items() if t > K)
    print(f'K={K}: {len(enforced)} clues enforced, {len(skipped)} skipped '
          f'(values {sorted(clues[c] for c in skipped)})')
    print(f'  enforced: {enforced}')
    if not args.yes:
        answer = input('Does the transcription look right? [y/N] ').strip().lower()
        if answer != 'y':
            print('aborted')
            return 2

    mins = compute_min_sizes(n, clues)
    forbidden, forced, cands = monomino_analysis(n, clues, mins)
    print()
    for clue_cell, mono in sorted(forced.items()):
        print(f'derived: the 1 at {clue_cell} forces a monomino at {mono}')
    assert forced.get((4, 10)) == (5, 10), 'monomino rule must reproduce (5,10)'
    print('  (assertion holds: the rule reproduces (5,10) from the 1 at (4,10))')
    for clue_cell, c in sorted(cands.items()):
        if clue_cell not in forced:
            print(f'candidates for the 1 at {clue_cell}: {c}')

    print()
    results = []
    for use_hunch in ([False, True] if args.hunch else [False]):
        label = 'with hunch' if use_hunch else 'plain'
        print('=' * 70)
        print(f'11x11 stage-1, K={K}, {label}, time limit {args.time_limit}s')
        print('=' * 70)
        growth_cuts = []
        res = None
        good = False
        for round_index in range(args.rounds):
            cfg = Stage1Config(n=n, clues=clues, K=K, time_limit=args.time_limit,
                               workers=args.workers, hunch=use_hunch,
                               maximize=args.maximize, log_progress=args.log,
                               big_growth_cuts=list(growth_cuts))
            res = solve(cfg)
            if res.solution is None:
                print(f'round {round_index+1}: status={res.status}')
                break
            bad = offending_big_components(res.solution, K)
            if not bad:
                good = report(res, clues, K)
                break
            print(f'round {round_index+1}: solution has {len(bad)} BIG component(s) '
                  f'smaller than K+1={K+1} (sizes {[len(c) for c, _ in bad]}); cutting')
            growth_cuts.extend(bad)
        results.append((label, res, good))
        print()
        if use_hunch and res.status == 'INFEASIBLE':
            print('the hunch is INFEASIBLE; the plain run below (or above) is the '
                  'meaningful one - this says nothing about the puzzle itself')
            print()

    if args.count and results:
        print('counting solutions with cuts ...')
        count_solutions(clues, K, args)
    return 0


def count_solutions(clues, K, args, limit: int = 50) -> None:
    """Repeat solve, each time cutting the (x, big) assignment just found."""
    n = 11
    from stage1 import solve as run_stage1
    found = []
    for _ in range(limit):
        cfg = Stage1Config(n=n, clues=clues, K=K, time_limit=args.time_limit,
                           workers=args.workers)
        res = run_stage1(dict(cfg.__dict__) and cfg, verbose=False)
        if res.solution is None:
            print(f'  stopped: {res.status}')
            break
        sig = (frozenset(res.solution.big),
               frozenset(res.solution.big_capitols),
               tuple(sorted(tuple(sorted(c)) for c, _ in res.solution.states)))
        if sig in found:
            print('  duplicate signature - stopping')
            break
        found.append(sig)
        print(f'  solution {len(found)}: BIG={len(res.solution.big)} '
              f'states={len(res.solution.states)}')
        if len(found) >= limit:
            break
    print(f'  total distinct signatures found: {len(found)}')


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == 'shapes':
        n = int(argv[2]) if len(argv) > 2 else 5
        K = int(argv[3]) if len(argv) > 3 else 5
        cmd_shapes(n, K)
        return 0
    if cmd == 'gate5':
        return cmd_gate5()
    if cmd == 'puzzle11':
        import argparse
        ap = argparse.ArgumentParser()
        ap.add_argument('--K', type=int, default=12)
        ap.add_argument('--time-limit', type=float, default=120.0)
        ap.add_argument('--workers', type=int, default=8)
        ap.add_argument('--hunch', action='store_true')
        ap.add_argument('--maximize', action='store_true')
        ap.add_argument('--count', action='store_true')
        ap.add_argument('--yes', action='store_true')
        ap.add_argument('--log', action='store_true')
        ap.add_argument('--rounds', type=int, default=6)
        return cmd_puzzle11(ap.parse_args(argv[2:]))
    print(f'unknown command {cmd}')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))
