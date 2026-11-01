# Jane-Street-Puzzles
Detailed solution for Jane Street Puzzles

https://drive.google.com/drive/folders/1eS_19jZLyKXJExIX_RxgBQwePUq5wHhF?usp=drive_link

---

## October 2026 — 11×11 States & Capitols (CP-SAT, K = 14)

The `k14_sat/` folder contains the CP-SAT model that solves the 11×11 puzzle
exactly for every clue `T ≤ 14`.  See `k14_sat/README.md` for the full
write-up.

**Technique in short.**  Enumerate every placement of every symmetric
polyomino of size ≤ 14 (together with its real capitol, derived from the
capitol rule).  Every cell is either covered by one such placement or marked
`BIG`, meaning it belongs to a state of size > 14; BIG cells are priced at
`15`.  Because a BIG–BIG edge costs 15, which is more than any enforced clue
`T ≤ 14`, such edges are never used on a shortest path for an enforced clue,
so the small-clue distance equations are exact.  CP-SAT then chooses the
placements, the BIG components and the distances, subject to:

- every BIG connected component has at least 15 cells (rooted-flow encoding);
- at most one BIG capitol;
- Manhattan-ball necessary condition: a clue of value `T` needs a capitol
  within Manhattan distance `(T + 1) // 2`;
- weighted-distance equations with a tight predecessor for every non-capitol.

The K = 14 run returns a valid, independently checked solution in ~335 s
(235,050 placements).  The same model at K = 15 is infeasible, so K = 14 is
the largest K solved by this decomposition.

**Final answer.**  Labelling each cell with its state's size gives row sums

```
[58, 86, 202, 215, 211, 221, 180, 234, 212, 208, 206]
```

and the sum of their squares is **408951**.
