# Jane Street October 2026 — 11×11 States & Capitols (CP-SAT, K = 14)

A CP-SAT (OR-Tools) model for the 11×11 *states and capitols* puzzle.  The
K = 14 run does **not** solve the whole puzzle: it returns a **partial
solution** in which all clues are essentially solved except for the biggest
state, of size **37**, which the model leaves as an unresolved BIG region.
That partial solution is good enough to be completed and corrected by human
eye.  The same encoding at K = 15 is infeasible.

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

This is a **partial** solution.  The 16 small states and the single BIG
capitol are determined and all clues `T ≤ 14` are satisfied, but the 37-cell
state itself sits inside the unresolved BIG region, so the model does not fix
it.  The large clues are only bounded.  The remaining 37-cell shape is the
part that was completed by human eye.

The same configuration at K = 15 returns `INFEASIBLE` after 930.7 s, so K = 14
is the largest K solved by this decomposition.

## Files

| file | what it does |
|---|---|
| `stage1.py` | The CP-SAT model itself: `Stage1Config`, `build_library`, `filter_placements`, `solve`, `extract`, the clue grid. |
| `placements.py` | Enumerates every board placement of every symmetric polyomino of size ≤ K, with its capitol. |
| `shapes.py` | D4 symmetry algebra and the capitol rule (`analyse`); generates the symmetric shapes. |
| `validate_stage1.py` | Independent validator: recomputes symmetries, capitols, BIG components and all clue distances. |
| `main.py` | CLI/helper routines, including `offending_big_components` used by the growth cuts. |
| `try_k14.py` | The K = 14 run: builds the config, solves, validates and prints the partial solution. |
| `render_solution.py` | Pretty-printer for a solution plus an independent Dijkstra clue check. |
| `requirements.txt` | `ortools==9.15.6755`. |

### `stage1.py`

- `Stage1Config` — every run parameter: board size `n`, the clue dict, the
  small-state limit `K`, `time_limit`, `workers`, and the BIG-region options
  (`big_min`, `big_max`, `big_root`, `must_big`, `must_small`,
  `big_components`, `big_anchor`, `big_anchor_size`, `big_connected_min`,
  `max_big_caps`), the symmetry helpers (`blob_capitol`, `blob_symmetric`),
  `manhattan_ring`, the growth/no-good cuts, `fix`, and `seed`.
- `build_library` — calls `generate_shapes` and `build_placements` to build the
  placement library for the given `K`.
- `filter_placements` — drops placements that cannot satisfy the clue bounds
  (e.g. a capitol too far from a clued cell).
- `solve` — builds and runs the CP-SAT model:
  - one placement per cell, or `BIG` (`cover` constraints);
  - `size`/`sizecap` per cell (small placement size, or `K+1` for BIG);
  - `cap` and `d` (capitol and distance) variables;
  - edge weights `w = min(size(u), size(v))` via `AddMinEquality`;
  - distance layer: `d[u] ≤ d[v] + w`, triangle inequalities, and a tight
    predecessor for every non-capitol cell;
  - clue equations `d[cell] == T` for `T ≤ K`;
  - rooted-flow BIG components (`flow[(r, c)]`, root = minimum-index cell),
    with each component ≥ `K+1` and optionally an exact component count and an
    anchor component size;
  - the Manhattan-ball rule, the BIG-capitol limit, and the extra cuts;
  - `CpSolver` run, then `extract` into a `Stage1Solution`.
- `extract` — reads the solver's variables back into a solution (small states
  with their capitols, BIG cells, BIG capitols).
- `neighbours`, `compute_min_sizes`, `monomino_analysis` — small helpers used
  to prune and to derive forced monominoes.
- `PUZZLE_11X11_CLUES` / `EXAMPLE_5X5_CLUES` — the clue data.

### `placements.py`

- `Placement` — a placed shape: its cells, size and capitol.
- `orientations` — the D4 orientations of a canonical shape.
- `translations` — all translations of a cell set that fit on the board.
- `build_placements(n, shapes, K)` — every placement of every symmetric shape
  of size ≤ K, deduplicated by canonical cell set, with the capitol computed
  by `shapes.analyse`.
- `placements_by_cell` — the placements grouped by cell (used by the coverage
  constraints).

### `shapes.py`

- `D4` — the seven non-identity D4 elements.
- `centre`, `cell_of`, `apply` — doubled-coordinate helpers for the affine
  symmetries.
- `ShapeInfo`, `analyse(cells)` — computes the symmetry elements and the
  fixed cells; a capitol exists iff every non-trivial symmetry fixes exactly
  one common cell.
- `canonical`, `orbit_and_validity`, `_candidate_shifts` — shape
  canonicalisation and symmetry-orbit helpers.
- `_is_connected` — 4-connectivity check.
- `generate_shapes(n, k)` — all symmetric polyominoes up to size `k`.

### `validate_stage1.py`

- `symmetry_elements`, `capitol_of`, `is_connected` — independent
  re-implementations of the symmetry/capitol/connectivity checks.
- `Report` — validation result with `ok` and `text()`.
- `validate_stage1(solution, clues, K)` — recomputes each small state's
  symmetry and capitol, checks every BIG component is ≥ K+1, recomputes the
  distances by Dijkstra with BIG priced at `K+1`, checks the enforced clues
  exactly (`T ≤ K`) and the large clues' lower/upper bounds.

### `main.py`

- `render_clue_grid`, `render_solution` — text renderers.
- `report` — prints a `Stage1Result`.
- `offending_big_components(sol, K)` — the BIG components smaller than `K+1`
  together with their non-BIG neighbours; used to build the growth cuts.
- `cmd_shapes`, `cmd_gate5`, `cmd_puzzle11`, `count_solutions`, `main` — CLI
  helpers and the 5×5/11×11 drivers.

### `try_k14.py`

The K = 14 run: builds the `Stage1Config` shown above, calls `solve`,
validates the result with `validate_stage1`, checks the BIG components, and
prints the partial solution through `render_solution.render`.

### `render_solution.py`

`render(sol)` prints the 11×11 grid (a letter per small state, `*` for a
small capitol, `@` for a BIG capitol, `#` for a BIG cell), the state legend
(size, capitol, cells), and an independent Dijkstra clue check with the
per-clue status and the number of enforced failures.

### `requirements.txt`

`ortools==9.15.6755`.

## Run

```bash
pip install -r requirements.txt
python try_k14.py
```
