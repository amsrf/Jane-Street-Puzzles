# Jane Street October 2026 — 11×11 States & Capitols (CP-SAT, K = 14)

A CP-SAT (OR-Tools) model for the 11×11 *states and capitols* puzzle.  The
K = 14 run finds a valid, fully checked solution of the small-clue model; the
same encoding at K = 15 is infeasible.

## The puzzle

Partition the 11×11 board into orthogonally connected polyomino **states**.

- Every state must be symmetric under at least one non-trivial symmetry of the
  square lattice (rotation/reflection).
- A state has a **capitol** iff every non-trivial symmetry of the state fixes
  **exactly one** cell; that common cell is the capitol.  Capitol-less states
  are allowed.
- Moving between orthogonally adjacent cells `u, v` costs
  `min(size(u), size(v))`.
- A clue at cell `x` is the minimum cost from `x` to any capitol.
- The answer is the sum over rows of `(row sum of state sizes)²`.

## Technique: exact small states + BIG abstraction

The difficulty is that the edge weights depend on the state sizes, which are
themselves part of the partition.  The model decomposes the board as follows.

1. **Small states (size ≤ K).**  Enumerate every placement of every symmetric
   polyomino of size ≤ K on the board, together with its capitol (derived from
   the capitol rule).  A Boolean `x[p]` selects a placement; every cell is
   covered exactly once by a small placement or is marked `BIG`.

2. **BIG cells (size > K).**  A BIG cell represents a cell of a state of size
   ≥ K+1 and is priced at `K+1`.  A BIG–BIG edge therefore costs `K+1`, which
   is larger than every enforced clue `T ≤ K`.  Hence BIG–BIG edges are never
   used on a shortest path for an enforced clue, and the small-clue distance
   equations are **exact** for `T ≤ K` while remaining a relaxation for the
   large clues (which are only bounded).

3. **Distance layer.**  `d[c]` is the distance to the nearest capitol:
   `d = 0` at capitols, `d > 0` elsewhere, and for every edge
   `d[u] ≤ d[v] + min(size(u), size(v))`; every non-capitol cell has a tight
   predecessor.  Clues with `T ≤ K` are fixed: `d[clue] == T`.

4. **BIG-shape constraints.**
   - every BIG connected component has at least `K+1` cells (rooted-flow
     encoding, root = minimum-index cell of the component);
   - at most one BIG capitol (`max_big_caps=1`);
   - Manhattan-ball necessary condition: a clue of value `T` needs a capitol
     within Manhattan distance `(T+1)//2`;
   - no BIG cell is isolated.

5. **Checking.**  `validate_stage1.py` recomputes each small state's symmetry
   and capitol, checks every BIG component is ≥ K+1, checks the enforced clues
   exactly and the large clues' lower/upper bounds.  `render_solution.py`
   prints the grid and independently recomputes all clue distances with
   Dijkstra.

## K = 14 configuration

```python
Stage1Config(
    n=11, clues=PUZZLE_11X11_CLUES, K=14,
    workers=16,
    big_min=15,               # total BIG cells >= K+1
    max_big_caps=1,           # at most one BIG capitol
    big_connected_min=True,   # every BIG component >= K+1
    manhattan_ring=True,
)
```

Result (16 cores, OR-Tools 9.15.6755):

```
status=OPTIMAL wall=334.7s placements=235050
VALID: 16 small states, 34 BIG cells, 1 BIG capitol
enforced failures: 0
```

The same configuration at K = 15 returns `INFEASIBLE` after 930.7 s, so K = 14
is the largest K solved by this decomposition.

## Files

| file | purpose |
|---|---|
| `stage1.py` | CP-SAT stage-1 model (`Stage1Config`, `solve`), clue grid, distance layer, BIG constraints |
| `placements.py` | enumerates all placements of symmetric polyominoes of size ≤ K |
| `shapes.py` | D4 symmetries, capitol rule (`analyse`), shape generation |
| `validate_stage1.py` | independent validator |
| `main.py` | `offending_big_components` and helpers |
| `try_k14.py` | the K = 14 run |
| `render_solution.py` | pretty printer + independent Dijkstra clue check |
| `requirements.txt` | `ortools==9.15.6755` |

## Run

```bash
pip install -r requirements.txt
python try_k14.py
```

## Final answer

Labelling every cell with its state's size gives row sums

```
[58, 86, 202, 215, 211, 221, 180, 234, 212, 208, 206]
```

and the sum of their squares is **408951**.
