# Alignment Plan Review Findings

Date: 2026-02-06
Source plan: `docs/plans/2026-02-05-alignment-algorithm-implementation.md`

## Executive Summary
The plan is detailed and test-driven, but there are several algorithmic and contract issues that likely make the current approach non-viable on real data or misaligned with the PRD. The biggest risks are around clustering semantics, displacement constraints, and schema strategy. These need clarification and redesign before implementation starts.

## Findings

### Blocker
1. **DBSCAN chaining + centroid reference can violate alpha**
   - DBSCAN only guarantees local density, not that all points in a cluster are within `alpha` of the cluster mean. Chaining can yield cluster points farther than `alpha` from the centroid, and the processor then throws on displacement.
   - Affected sections: clustering + thread detection + alignment processor.

2. **3D displacement check likely conflicts with PRD tolerance**
   - The plan enforces `euclidean_displacement <= alpha`. If X and Y both move by `alpha`, the 3D displacement exceeds `alpha` even though each axis is within tolerance.
   - If PRD CF-02 is per-axis, this will falsely fail alignment.
   - Affected sections: alignment processor + validator.

### Major
1. **Thread reference rounding ignores config**
   - `round(cluster_mean, 2)` is hardcoded, conflicting with `AlignmentConfig.rounding_precision`.
   - Affected sections: thread detector, config.

2. **Matching uses thread delta, not alpha**
   - `find_matching_thread` matches within `range_min/range_max` based on `delta = min(std, alpha)`. If `std` is small, valid points within `alpha` are excluded, reducing alignment rate.
   - Affected sections: geometry utilities.

3. **Overlap resolution is non-deterministic**
   - The first thread whose range matches is selected, which is order-dependent and not guaranteed to be the closest thread.
   - Affected sections: geometry utilities.

4. **Dropping `vertices` and replacing with a view can break FKs**
   - `DROP TABLE vertices` with `foreign_keys=ON` fails if other tables reference it, and replacing it with a view breaks writes and FK expectations.
   - Affected sections: DB writer.

5. **Alignment rate thresholds inconsistent**
   - Plan targets >=85% (CQ-01), but validator warns at 80%.
   - Affected sections: validation + success criteria.

6. **Z-axis thread expectations inconsistent**
   - Plan cites 13 floor levels but “Desired End State” expects ~4 Z threads.
   - Affected sections: desired end state + tests.

7. **Unused heavy dependencies**
   - `pandas` and `pyyaml` are included but plan explicitly excludes YAML support and does not use pandas.
   - Affected sections: `pyproject.toml`.

### Minor
1. **Rounding precision calculation is fragile**
   - `int(-math.log10(config.rounding_precision))` assumes power-of-10 precision and will misbehave otherwise.
   - Affected sections: alignment processor.

2. **Std dev definition not clarified**
   - `np.std` uses population std. If PRD expects sample std (`ddof=1`), results will differ.
   - Affected sections: statistics.

3. **Report includes absolute paths**
   - Reports include full input/output paths, which may leak environment details.
   - Affected sections: report generator.

## Viability Concerns
As specified, the algorithm will likely fail on real data because DBSCAN clustering can produce points outside `alpha` of the centroid, but the processor enforces a strict displacement bound. Without revising cluster definition or displacement criteria, the alignment step is brittle and the 85% target is at risk.

## Open Questions
1. Does PRD CF-02 mean per-axis displacement <= `alpha` or 3D Euclidean <= `alpha`?
2. Does PRD F-08 require the enriched schema to be the `vertices` table itself, or is `vertices_aligned` + view acceptable?
3. Is 85% alignment a hard requirement (CQ-01) or only a warning threshold?
4. Are Z-axis threads expected to be 13 (floor levels) or ~4 as stated in the Desired End State?

## Recommendations
1. Clarify and document displacement rule (per-axis vs 3D) before coding.
2. Redesign thread detection so all points assigned to a thread satisfy the displacement constraint.
3. Revisit output schema strategy with FK constraints in mind.
4. Resolve inconsistencies (alignment rate threshold, Z-axis thread count) and remove unused dependencies.
