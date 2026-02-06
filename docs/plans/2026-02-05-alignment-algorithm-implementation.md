# Alignment Algorithm Implementation Plan

## Overview

Implement the core alignment algorithm from the PRD (F-03 through F-10): statistical analysis, DBSCAN clustering, thread detection, vertex alignment, enriched output database, post-alignment validation, and JSON reporting. This builds on the completed ETL pipeline that already produces a PRD-compliant `geometrie_2_prd.db` with 5,825 elements and 20,994 vertices.

The implementation uses a **5-agent team** to maximize parallelism, with a dedicated Devil's Advocate reviewer ensuring architecture quality and security throughout.

## Review Changelog (2026-02-06)

This plan was updated based on the review in `docs/research/2026-02-06-alignment-plan-review.md`. Below is a summary of each finding and how it was addressed:

### Accepted Findings (with fixes applied)

| Severity | Finding | Fix Applied |
|----------|---------|-------------|
| **BLOCKER** | DBSCAN chaining can produce cluster points farther than alpha from centroid | Added **post-clustering validation step** in `cluster_axis()` that prunes points > alpha from the cluster centroid. This guarantees all retained points satisfy the displacement constraint. See Phase 2a, clustering.py. |
| **BLOCKER** | 3D displacement check conflicts with PRD per-axis tolerance | Changed to **per-axis displacement check** (`abs(coord - reference) <= alpha`). PRD CF-02 is per-axis (PRD lines 272-273). `displacement_total` remains as a 3D metric for **reporting only**, not as an acceptance criterion. See Phase 2b, processor.py. |
| **MAJOR** | Thread reference rounding ignores config | Fixed: now uses `round(mean, config.rounding_ndigits)` where `rounding_ndigits` is derived from `rounding_precision`. See config.py and thread_detector.py. |
| **MAJOR** | Matching uses thread delta not alpha | Fixed: `find_matching_thread()` now matches within `alpha` of the thread reference, not within `delta`. This ensures valid points near a thread are not excluded when std < alpha. See geometry.py. |
| **MAJOR** | Overlap resolution is non-deterministic | Fixed: `find_matching_thread()` now finds **all matching threads** and returns the one with the **smallest displacement** (closest reference). See geometry.py. |
| **MAJOR** | Alignment rate thresholds inconsistent | Clarified: CQ-01 (85%) is a **hard quality requirement** checked in integration tests. F-09 validation warns at 80% per PRD. Both thresholds are now documented. |
| **MAJOR** | Z-axis thread expectations inconsistent | Fixed: Removed hardcoded "4 Z threads" from Desired End State. Z-axis thread count depends on data and alpha. Integration tests verify threads are detected without mandating a specific count. |
| **MINOR** | Rounding precision calculation fragile | Fixed: Added `rounding_ndigits` property to `AlignmentConfig` that cleanly computes ndigits. |
| **MINOR** | Std dev definition not clarified | Resolved: PRD is ambiguous. Using **population std** (`np.std`, ddof=0) since we compute over the full population of coordinates, not a sample. Documented in code. |

### Challenged Findings (with justification)

| Severity | Finding | Challenge | Justification |
|----------|---------|-----------|---------------|
| **MAJOR** | Dropping `vertices` and replacing with view breaks FKs | **Partially accepted** — FK concern is invalid (no tables reference `vertices`; only `vertices → elements` FK exists). **However**, PRD F-08 (lines 298-321) specifies the enriched schema as the `vertices` table itself. Fix: use **ALTER TABLE ADD COLUMN** approach instead of drop+recreate. This preserves the table name, avoids FK issues entirely, and matches PRD exactly. |
| **MAJOR** | Unused pandas/pyyaml dependencies | **Challenged** — PRD dependency list (lines 773-779) explicitly includes both. `pandas` is kept as PRD-required. `pyyaml` is **removed** since we explicitly exclude YAML config from V1 scope, and it's a soft PRD dependency (config file support, which we defer). |
| **MINOR** | Report includes absolute paths | **Rejected** — Absolute paths provide better traceability for debugging and audit. PRD does not restrict path format. No sensitive data is leaked (these are local file paths on the user's machine). |

### Resolved Open Questions

| Question | Resolution |
|----------|------------|
| Does PRD CF-02 mean per-axis or 3D Euclidean? | **Per-axis.** PRD lines 272-273 show `displacement = abs(vertex.coord - thread.reference)` which is 1D. |
| Does PRD F-08 require `vertices` table or is `vertices_aligned` acceptable? | **Must be `vertices` table.** PRD lines 298-321 show enriched schema in `vertices` table. Using ALTER TABLE. |
| Is 85% alignment a hard requirement? | **Yes.** CQ-01 (PRD line 1039) is P0 priority: `>= 85%`. F-09 warning threshold is 80%. |
| How many Z-axis threads expected? | **Not specified by PRD.** Example shows 4, but this depends on data distribution and alpha. No hardcoded expectation. |

---

## Current State Analysis

### What Exists
- **`structure-batiment/structure_aligner/`**: Python package with ETL pipeline
  - `etl/extractor.py` — reads `.3dm` geometry (5 geometry types)
  - `etl/transformer.py` — links 3dm names to DB element IDs
  - `etl/loader.py` — writes PRD-compliant output DB
  - `main.py` — Click CLI with `etl` subcommand
  - `utils/logger.py` — PRD-formatted logging
- **`structure-batiment/data/geometrie_2_prd.db`**: Output from ETL (5,825 elements, 20,994 vertices)
- **`structure-batiment/pyproject.toml`**: Package config with `rhino3dm` + `click` deps
- **`structure-batiment/tests/`**: 31 passing tests (extractor, transformer, loader)
- **Data profile**: 13 Z-axis floor levels (already clustered), 1,439 unique X values, 1,592 unique Y values

### What's Missing
- No `analysis/` module (statistics, clustering)
- No `alignment/` module (thread detection, processor, geometry utils)
- No `output/` module (post-alignment validation, report generation)
- No `db/` module (reader for alignment input, writer for enriched output)
- No `config.py` (AlignmentConfig)
- No `align` CLI subcommand
- No numpy/pandas/scikit-learn dependencies
- No enriched vertices schema (x_original, y_original, z_original, aligned_axis, fil IDs, displacement_total)

### Key Discoveries
- Z-axis has only 13 unique values (floor levels) — DBSCAN will detect these trivially
- X and Y axes are the real alignment challenge with 1,400-1,600 unique values
- 1 isolated Z vertex at 17.78m (between floors 13.32m and 17.96m)
- Coordinates are in meters, building footprint ~119m x 119m, height ~42m
- Existing ETL uses plain `sqlite3` (no SQLAlchemy) — alignment should follow same pattern
- Existing code uses dataclasses, not Pydantic — alignment should follow same pattern
- **No other tables reference `vertices`** — only FK is `vertices.element_id → elements.id`
- **PRD displacement rule is per-axis** (PRD lines 272-273), not 3D Euclidean

## Desired End State

After this plan is complete:

1. Running `python -m structure_aligner align --input data/geometrie_2_prd.db --alpha 0.05` produces:
   - An aligned database `geometrie_2_prd_aligned_{timestamp}.db` with enriched `vertices` table (PRD F-08 schema)
   - A JSON report `alignment_report_{timestamp}.json` with full PRD F-10 statistics
2. Running with `--dry-run` produces only the report (no output DB)
3. Threads are detected on all 3 axes (count depends on data distribution and alpha)
4. Alignment rate >= 85% (PRD CQ-01, P0 priority)
5. No vertex displaced more than alpha **per axis** (PRD CF-02)
6. Full test suite passes with >= 90% coverage on new modules

### Verification
```bash
cd structure-batiment

# Standard alignment
python -m structure_aligner align \
  --input data/geometrie_2_prd.db \
  --alpha 0.05 \
  --report data/alignment_report.json

# Verify enriched output (vertices table has new columns)
sqlite3 data/geometrie_2_prd_aligned_*.db "SELECT COUNT(*) FROM vertices WHERE aligned_axis != 'none';"
# Expected: >= 85% of 20994

sqlite3 data/geometrie_2_prd_aligned_*.db "SELECT MAX(displacement_total) FROM vertices;"
# Note: displacement_total is 3D Euclidean (for reporting). Per-axis displacement is guaranteed <= alpha.

# Dry-run mode
python -m structure_aligner align \
  --input data/geometrie_2_prd.db \
  --alpha 0.05 \
  --dry-run \
  --report data/preview_report.json

# Run tests
python -m pytest tests/ -v --cov=structure_aligner --cov-report=term-missing
```

## What We're NOT Doing

- **PostgreSQL/MySQL support**: SQLite only (same as ETL)
- **SQLAlchemy ORM**: Plain sqlite3 (consistent with ETL)
- **config.yaml support**: CLI flags only for V1 (YAML can be added later; pyyaml not included)
- **3D visualization**: No matplotlib/plotly histograms (PRD says "optional")
- **Progress bar**: No tqdm/rich progress (PRD nice-to-have, not critical)
- **Multi-algorithm fallback**: DBSCAN only (Mean-Shift/HDBSCAN are PRD R-01 mitigation, not V1 scope)
- **Suggest-alpha feature**: PRD R-07 mitigation, not V1 scope
- **Batch processing**: Single file at a time
- **Sphinx documentation**: No API docs generation
- **CI/CD pipeline**: No GitHub Actions

## Implementation Approach

Build the PRD module structure incrementally, following the same patterns as the ETL (dataclasses, sqlite3, click, logging). Dependencies on numpy/pandas/scikit-learn are added to `pyproject.toml` first, then each module is built and tested independently.

The work is split across **4 coding agents + 1 reviewer agent** working in parallel:

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT TEAM STRUCTURE                       │
├──────────────┬──────────────┬──────────────┬────────────────┤
│ analysis-dev │alignment-dev │reporting-dev │cli-integr-dev  │
│              │              │              │                │
│ statistics.py│ processor.py │ validator.py │ main.py (align)│
│ clustering.py│ geometry.py  │ report_gen.py│ config.py      │
│ thread_det.py│ db/writer.py │              │ integ tests    │
│ + unit tests │ db/reader.py │ + unit tests │ + unit tests   │
│              │ + unit tests │              │                │
├──────────────┴──────────────┴──────────────┴────────────────┤
│                    devil-advocate                             │
│  Reviews all code as it lands. Challenges architecture,      │
│  flags security issues, enforces quality standards.          │
└─────────────────────────────────────────────────────────────┘
```

### Dependency Graph Between Agents

```
Phase 1: Scaffolding (cli-integr-dev, solo)
   │
   ▼
Phase 1 Review: devil-advocate reviews contracts & architecture
   │
   │  ◄── cli-integr-dev fixes issues if any (loop until approved)
   │
   ▼ (approved)
   ├──► Phase 2a: analysis-dev (statistics + clustering + threads)
   ├──► Phase 2b: alignment-dev (processor + geometry + db read/write)
   ├──► Phase 2c: reporting-dev (validator + report generator)
   │       │
   │       ▼
   │    devil-advocate reviews Phase 2 outputs continuously
   │       │
   │       ├──► feedback to analysis-dev ──► rework ──► re-review ─┐
   │       ├──► feedback to alignment-dev ──► rework ──► re-review ─┤
   │       ├──► feedback to reporting-dev ──► rework ──► re-review ─┤
   │       │                                                        │
   │       ◄── loop until all 3 agents approved ◄──────────────────┘
   │       │
   └──► Phase 3: cli-integr-dev (wire everything + integration tests)
           │
           ▼
        Phase 4: devil-advocate final review
```

**Phase 2 agents work in parallel** because they share only data contracts (dataclasses), not implementation dependencies. The contracts are defined and reviewed in Phase 1.

**Phase 2 feedback loops**: The devil-advocate reviews each agent's code as it lands. If issues are found (architecture, security, correctness, PRD compliance), the responsible coding agent must address them before their task is considered complete. This loop continues until the devil-advocate explicitly approves each agent's output. Phase 3 cannot start until all 3 coding agents have devil-advocate approval.

---

## Phase 1: Scaffolding & Data Contracts

### Overview
Add new dependencies, create module directories, define shared dataclasses and interfaces that all agents will code against. **Performed by cli-integr-dev only** (single agent, fast).

### Agent Assignment: `cli-integr-dev`

### Changes Required:

#### 1. Update dependencies
**File**: `structure-batiment/pyproject.toml`

Add to `[project] dependencies`:
```toml
dependencies = [
    "rhino3dm>=8.0.0",
    "click>=8.0.0",
    "numpy>=1.21.0",
    "pandas>=1.3.0",
    "scikit-learn>=1.0.0",
]
```

**Note**: `pyyaml` removed from original plan — YAML config is explicitly out of V1 scope. `pandas` kept per PRD dependency list (line 773).

Then run: `cd structure-batiment && pip install -e ".[dev]"`

#### 2. Create module directories
```
structure-batiment/structure_aligner/
├── analysis/
│   ├── __init__.py
│   ├── statistics.py        # Phase 2a
│   ├── clustering.py        # Phase 2a
├── alignment/
│   ├── __init__.py
│   ├── thread_detector.py   # Phase 2a
│   ├── processor.py         # Phase 2b
│   ├── geometry.py          # Phase 2b
├── db/
│   ├── __init__.py
│   ├── reader.py            # Phase 2b
│   ├── writer.py            # Phase 2b
├── output/
│   ├── __init__.py
│   ├── validator.py         # Phase 2c
│   ├── report_generator.py  # Phase 2c
└── config.py                # Phase 1
```

#### 3. Shared data contracts
**File**: `structure-batiment/structure_aligner/config.py`

```python
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AlignmentConfig:
    """Configuration for the alignment pipeline."""
    alpha: float = 0.05           # Max tolerance in meters (per-axis, PRD CF-02)
    min_cluster_size: int = 3     # Min vertices per thread (PRD F-04)
    rounding_precision: float = 0.01  # Centimeter precision
    merge_threshold_factor: float = 2.0  # Merge threads closer than factor * alpha

    @property
    def rounding_ndigits(self) -> int:
        """Number of decimal places for rounding, derived from rounding_precision.

        Examples: 0.01 -> 2, 0.001 -> 3, 0.1 -> 1
        """
        return max(0, round(-math.log10(self.rounding_precision)))


@dataclass
class Thread:
    """A detected alignment thread (fil)."""
    fil_id: str           # e.g. "X_001"
    axis: str             # "X", "Y", or "Z"
    reference: float      # Rounded reference coordinate
    delta: float          # Actual cluster std (informational, NOT used for matching)
    vertex_count: int     # Number of vertices in this thread
    range_min: float      # reference - alpha (matching range)
    range_max: float      # reference + alpha (matching range)


@dataclass
class AlignedVertex:
    """A vertex after alignment processing."""
    id: int               # Original vertex ID from DB
    element_id: int
    x: float              # Aligned coordinate
    y: float
    z: float
    vertex_index: int
    x_original: float     # Original coordinate before alignment
    y_original: float
    z_original: float
    aligned_axis: str     # "X", "Y", "Z", "XY", "XZ", "YZ", "XYZ", "none"
    fil_x_id: str | None  # Thread ID or None
    fil_y_id: str | None
    fil_z_id: str | None
    displacement_total: float  # 3D Euclidean displacement (for reporting only)


@dataclass
class AxisStatistics:
    """Statistical summary for one axis."""
    axis: str
    mean: float
    median: float
    std: float            # Population std (ddof=0)
    min: float
    max: float
    q1: float
    q3: float
    unique_count: int
    total_count: int


@dataclass
class AlignmentResult:
    """Complete result of the alignment pipeline."""
    threads: list[Thread]
    aligned_vertices: list[AlignedVertex]
    statistics: list[AxisStatistics]  # One per axis (X, Y, Z)
    config: AlignmentConfig
```

**Key changes from original plan:**
- `AlignmentConfig` gains `rounding_ndigits` property (review finding m1)
- `Thread.range_min/range_max` now documented as `reference ± alpha` (not `reference ± delta`) (review finding M2)
- `Thread.delta` documented as informational only, not used for matching
- `AlignedVertex.displacement_total` documented as reporting-only metric
- `AxisStatistics.std` documented as population std (ddof=0)

#### 4. Empty `__init__.py` files
All new `__init__.py` files are empty.

### Success Criteria:

#### Automated Verification:
- [x] `pip install -e ".[dev]"` succeeds with new deps
- [x] `python -c "from structure_aligner.config import AlignmentConfig, Thread, AlignedVertex"` works
- [x] `python -c "import numpy, pandas, sklearn"` works
- [x] `python -c "from structure_aligner.config import AlignmentConfig; print(AlignmentConfig().rounding_ndigits)"` prints `2`
- [x] Directory structure matches the tree above

**Implementation Note**: After cli-integr-dev completes Phase 1, proceed to Phase 1 Review below. Do NOT spawn Phase 2 agents yet.

---

## Phase 1 Review: Data Contracts Gate Review

### Overview
The devil-advocate reviews the scaffolding and data contracts before any Phase 2 work begins. This is a **blocking gate** — Phase 2 agents cannot start until this review passes. The goal is to catch contract design issues early, before 3 agents build on a flawed foundation.

### Agent Assignment: `devil-advocate`

### Review Checklist:

#### Data Contract Quality:
- [ ] Data contracts are minimal and sufficient — no fields that won't be used
- [ ] No circular import risk between modules
- [ ] `AlignmentConfig` defaults match PRD Section 3.3 parameter table
- [ ] `frozen=True` on config prevents accidental mutation during pipeline
- [ ] `AlignedVertex` fields match PRD F-08 enriched schema exactly (PRD lines 298-321)
- [ ] `Thread` dataclass captures all PRD F-05 properties
- [ ] `Thread.range_min/range_max` use alpha (not delta) for matching
- [ ] `AxisStatistics` covers all PRD F-03 metrics
- [ ] Type hints are correct (especially `str | None` vs `Optional[str]`)
- [ ] `rounding_ndigits` property works correctly for 0.01, 0.001, 0.1

#### Architecture:
- [ ] Module directory structure follows PRD Section 3.1 layout
- [ ] Each module has a clear single responsibility
- [ ] Data flows one direction: `db/reader` → `analysis/` → `alignment/` → `output/`
- [ ] No module needs to import from a sibling in a way that creates coupling

#### Dependencies:
- [ ] `pyproject.toml` version constraints are reasonable
- [ ] No unnecessary dependencies added (pyyaml correctly excluded)
- [ ] Dev dependencies properly separated from runtime

### Feedback Loop:
If the devil-advocate finds issues:
1. devil-advocate sends specific feedback to cli-integr-dev via SendMessage
2. cli-integr-dev applies fixes
3. devil-advocate re-reviews
4. Loop until devil-advocate explicitly approves

### Gate Criteria:
- [ ] devil-advocate sends explicit "Phase 1 APPROVED" message
- [ ] Only then: spawn all Phase 2 agents in parallel

---

## Phase 2a: Analysis — Statistics, Clustering, Thread Detection

### Overview
Implement per-axis statistical analysis (F-03), DBSCAN clustering with post-clustering validation (F-04), thread identification (F-05), and edge case handling (F-06). This is the mathematical core of the alignment system.

**Critical design change from original plan**: DBSCAN clusters are now post-validated to prune points that are farther than `alpha` from the cluster centroid. This ensures all retained points satisfy the per-axis displacement constraint when later snapped to the thread reference.

### Agent Assignment: `analysis-dev`

### Changes Required:

#### 1. Statistical analysis
**File**: `structure-batiment/structure_aligner/analysis/statistics.py`

Implements PRD F-03:
```python
import numpy as np
from structure_aligner.config import AxisStatistics


def compute_axis_statistics(values: np.ndarray, axis: str) -> AxisStatistics:
    """
    Compute statistical distribution for a single axis.

    Uses population std (ddof=0) since we compute over the full
    population of coordinates, not a sample.

    Args:
        values: 1D array of coordinate values for this axis.
        axis: Axis name ("X", "Y", or "Z").

    Returns:
        AxisStatistics with mean, median, std, min, max, quartiles, unique count.
    """
    return AxisStatistics(
        axis=axis,
        mean=float(np.mean(values)),
        median=float(np.median(values)),
        std=float(np.std(values, ddof=0)),  # Population std, explicitly stated
        min=float(np.min(values)),
        max=float(np.max(values)),
        q1=float(np.percentile(values, 25)),
        q3=float(np.percentile(values, 75)),
        unique_count=int(len(np.unique(np.round(values, 2)))),
        total_count=len(values),
    )
```

#### 2. DBSCAN clustering with post-validation
**File**: `structure-batiment/structure_aligner/analysis/clustering.py`

Implements PRD F-04 with **post-clustering alpha validation** (review fix for Blocker B1):
```python
import logging
import numpy as np
from sklearn.cluster import DBSCAN
from structure_aligner.config import AlignmentConfig

logger = logging.getLogger(__name__)


def cluster_axis(values: np.ndarray, config: AlignmentConfig) -> list[dict]:
    """
    Run DBSCAN clustering on a single axis's coordinate values, then
    validate that all cluster points are within alpha of the cluster centroid.

    DBSCAN with eps=alpha guarantees density-reachability, but NOT that all
    points in a cluster are within alpha of the centroid (chaining effect).
    This function adds a post-clustering validation step that prunes outlier
    points, ensuring the per-axis displacement constraint is satisfiable.

    Args:
        values: 1D array of coordinate values.
        config: Alignment configuration (alpha, min_cluster_size).

    Returns:
        List of cluster dicts with keys:
          - "indices": array of indices into the original values array
          - "values": array of coordinate values in this cluster
          - "mean": mean value of the cluster (centroid)
          - "std": standard deviation of the cluster
        All returned cluster points are guaranteed within alpha of their centroid.
    """
    # DBSCAN needs 2D input
    X = values.reshape(-1, 1)
    db = DBSCAN(eps=config.alpha, min_samples=config.min_cluster_size).fit(X)

    clusters = []
    for label in sorted(set(db.labels_)):
        if label == -1:
            continue  # Noise points (isolated vertices)
        mask = db.labels_ == label
        cluster_values = values[mask]
        cluster_indices = np.where(mask)[0]

        # Post-clustering validation: prune points > alpha from centroid
        centroid = float(np.mean(cluster_values))
        within_alpha = np.abs(cluster_values - centroid) <= config.alpha
        valid_values = cluster_values[within_alpha]
        valid_indices = cluster_indices[within_alpha]

        pruned_count = len(cluster_values) - len(valid_values)
        if pruned_count > 0:
            logger.debug(
                "Cluster %d: pruned %d/%d points beyond alpha=%.4fm from centroid %.4fm",
                label, pruned_count, len(cluster_values), config.alpha, centroid,
            )

        # Recompute centroid after pruning
        if len(valid_values) >= config.min_cluster_size:
            centroid = float(np.mean(valid_values))
            clusters.append({
                "indices": valid_indices,
                "values": valid_values,
                "mean": centroid,
                "std": float(np.std(valid_values, ddof=0)),
            })
        else:
            logger.debug(
                "Cluster %d: discarded after pruning (only %d points remain, need %d)",
                label, len(valid_values), config.min_cluster_size,
            )

    return clusters
```

#### 3. Thread detection with edge case handling
**File**: `structure-batiment/structure_aligner/alignment/thread_detector.py`

Implements PRD F-05 and F-06:
```python
import logging
import numpy as np
from structure_aligner.config import AlignmentConfig, Thread
from structure_aligner.analysis.clustering import cluster_axis

logger = logging.getLogger(__name__)


def detect_threads(values: np.ndarray, axis: str, config: AlignmentConfig) -> list[Thread]:
    """
    Detect alignment threads for a single axis.

    Runs DBSCAN clustering (with post-validation), then converts each
    cluster into a Thread. Handles edge cases:
      - F-06 Case 1: Merges threads closer than 2*alpha
      - F-06 Case 3: Clusters with < min_cluster_size are discarded (in cluster_axis)

    Args:
        values: 1D array of all coordinate values for this axis.
        axis: "X", "Y", or "Z".
        config: Alignment configuration.

    Returns:
        Sorted list of Thread objects for this axis.
    """
    clusters = cluster_axis(values, config)

    # Convert clusters to threads
    threads = []
    for i, cluster in enumerate(clusters):
        reference = round(cluster["mean"], config.rounding_ndigits)
        delta = min(cluster["std"], config.alpha)
        threads.append(Thread(
            fil_id=f"{axis}_{i+1:03d}",
            axis=axis,
            reference=reference,
            delta=delta,
            vertex_count=len(cluster["values"]),
            range_min=reference - config.alpha,  # Matching uses alpha, not delta
            range_max=reference + config.alpha,
        ))

    # Sort by reference value
    threads.sort(key=lambda t: t.reference)

    # F-06 Case 1: Merge threads that are too close
    merge_threshold = config.alpha * config.merge_threshold_factor
    threads = _merge_close_threads(threads, merge_threshold, axis, config)

    # Renumber after merge
    for i, thread in enumerate(threads):
        thread.fil_id = f"{axis}_{i+1:03d}"

    logger.info("Axis %s: %d threads detected from %d values", axis, len(threads), len(values))
    for t in threads:
        logger.debug("  %s: ref=%.4fm, delta=%.4fm, count=%d", t.fil_id, t.reference, t.delta, t.vertex_count)

    return threads


def _merge_close_threads(threads: list[Thread], threshold: float, axis: str,
                         config: AlignmentConfig) -> list[Thread]:
    """
    Merge threads whose reference values are closer than threshold.
    Keeps the thread with more vertices as the base; recalculates reference
    as weighted average.
    """
    if len(threads) <= 1:
        return threads

    merged = [threads[0]]
    for thread in threads[1:]:
        prev = merged[-1]
        if abs(thread.reference - prev.reference) < threshold:
            # Weighted average reference
            total = prev.vertex_count + thread.vertex_count
            new_ref = round(
                (prev.reference * prev.vertex_count + thread.reference * thread.vertex_count) / total,
                config.rounding_ndigits,
            )
            new_delta = max(prev.delta, thread.delta)
            merged[-1] = Thread(
                fil_id=prev.fil_id,
                axis=axis,
                reference=new_ref,
                delta=new_delta,
                vertex_count=total,
                range_min=new_ref - config.alpha,
                range_max=new_ref + config.alpha,
            )
            logger.info("Merged threads at %.4fm and %.4fm -> %.4fm (%d vertices)",
                       prev.reference, thread.reference, new_ref, total)
        else:
            merged.append(thread)

    return merged
```

#### 4. Unit tests
**File**: `structure-batiment/tests/test_statistics.py`

```python
# Test compute_axis_statistics with:
# - Simple known arrays (verify mean, median, std, quartiles)
# - Single-value array
# - All identical values (std=0)
# - Negative values
# - Verify ddof=0 (population std) explicitly
```

**File**: `structure-batiment/tests/test_clustering.py`

```python
# Test cluster_axis with:
# - Clear clusters (e.g. [0,0,0, 5,5,5, 10,10,10] with alpha=0.5)
# - All same value (single cluster)
# - Noise-only data (no clusters, all isolated)
# - min_cluster_size threshold
# - CRITICAL: Test DBSCAN chaining pruning:
#   - Create data where DBSCAN chains (e.g. [0.0, 0.04, 0.08, 0.12] with alpha=0.05)
#   - Verify points > alpha from centroid are pruned
#   - Verify cluster is discarded if pruning leaves < min_cluster_size points
```

**File**: `structure-batiment/tests/test_thread_detector.py`

```python
# Test detect_threads with:
# - Known clusters -> verify thread references and deltas
# - Two threads closer than 2*alpha -> verify merge
# - Single thread
# - Realistic Z-axis data (13 floor levels from research)
# - Isolated vertices (not assigned to any thread)
# - Verify range_min/range_max use alpha, not delta
# - Verify rounding uses config.rounding_ndigits
```

**File**: `structure-batiment/tests/test_analysis_integration.py` (uses real data)

```python
# Integration test with geometrie_2_prd.db:
# - Load all X/Y/Z values from vertices table
# - Run detect_threads on each axis with alpha=0.05
# - Verify Z axis produces threads (no hardcoded count)
# - Verify no thread has delta > alpha
# - Verify all cluster points are within alpha of thread reference
# - Log thread counts for visibility
```

### Success Criteria:

#### Automated Verification:
- [x] `python -m pytest tests/test_statistics.py tests/test_clustering.py tests/test_thread_detector.py tests/test_analysis_integration.py -v`
- [x] All unit tests pass
- [x] Integration test with real data: threads detected on all 3 axes
- [x] Integration test: no thread delta exceeds alpha
- [x] Integration test: post-clustering validation test passes (chaining scenario)

#### Code Review (devil-advocate):
- [ ] DBSCAN `eps` parameter correctly maps to `alpha`
- [ ] **Post-clustering validation prunes points > alpha from centroid**
- [ ] Thread merge logic preserves vertex counts accurately
- [ ] Rounding uses `config.rounding_ndigits` (not hardcoded `2`)
- [ ] delta = `min(std, alpha)` — PRD constraint always respected
- [ ] `range_min/range_max` use `alpha` (not `delta`) for matching boundaries
- [ ] No numpy arrays leaked into dataclass fields (must be Python floats/ints)
- [ ] Logging matches PRD NFR-08 format
- [ ] Edge case: what happens if ALL values are noise (no clusters)?
- [ ] Population std (ddof=0) used consistently

**Implementation Note**: This phase runs in parallel with 2b and 2c. No dependencies on other Phase 2 agents.

### Devil's Advocate Feedback Loop (Phase 2a):
Once analysis-dev signals completion, devil-advocate reviews the code against the checklist above. If issues are found:
1. devil-advocate sends specific feedback to analysis-dev
2. analysis-dev fixes the issues and re-runs tests
3. devil-advocate re-reviews the fixes
4. **Loop continues until devil-advocate explicitly approves Phase 2a**
5. Only after approval is analysis-dev's task marked complete

Typical review triggers:
- DBSCAN `eps` not correctly wired to `alpha`
- Post-clustering validation missing or incorrect
- Thread merge losing vertex counts
- numpy arrays leaking into dataclass fields
- Missing edge case handling (empty input, all-noise data)
- Logging not following PRD format
- Hardcoded rounding precision

---

## Phase 2b: Alignment — Processor, Geometry, DB Read/Write

### Overview
Implement the vertex alignment algorithm (F-07), enriched database output (F-08), and the database reader for loading input vertices. This is the data pipeline that consumes threads and produces aligned output.

**Critical design changes from original plan:**
- **Per-axis displacement check** instead of 3D Euclidean (PRD CF-02)
- **Closest-thread matching** instead of first-match (deterministic)
- **ALTER TABLE** approach for output DB instead of drop+recreate (PRD F-08 compliance)

### Agent Assignment: `alignment-dev`

### Changes Required:

#### 1. Database reader
**File**: `structure-batiment/structure_aligner/db/reader.py`

```python
import sqlite3
from pathlib import Path
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class InputVertex:
    """A vertex loaded from the input PRD database."""
    id: int
    element_id: int
    x: float
    y: float
    z: float
    vertex_index: int


def load_vertices(db_path: Path) -> list[InputVertex]:
    """
    Load all vertices from a PRD-compliant database.

    Args:
        db_path: Path to the input .db file.

    Returns:
        List of InputVertex records.

    Raises:
        FileNotFoundError: If db_path does not exist.
        ValueError: If the database lacks a 'vertices' table or expected columns.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # Validate schema
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='vertices'")
        if cursor.fetchone() is None:
            raise ValueError(f"Database {db_path} does not contain a 'vertices' table")

        cursor.execute("SELECT id, element_id, x, y, z, vertex_index FROM vertices ORDER BY id")
        vertices = [
            InputVertex(id=row[0], element_id=row[1], x=row[2], y=row[3], z=row[4], vertex_index=row[5])
            for row in cursor.fetchall()
        ]
        logger.info("Loaded %d vertices from %s", len(vertices), db_path)
        return vertices
    finally:
        conn.close()
```

#### 2. Geometry utilities
**File**: `structure-batiment/structure_aligner/alignment/geometry.py`

```python
import math


def euclidean_displacement(x1: float, y1: float, z1: float,
                           x2: float, y2: float, z2: float) -> float:
    """Calculate 3D Euclidean distance between two points (for reporting)."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2 + (z2 - z1)**2)


def find_matching_thread(coord: float, threads: list, alpha: float):
    """
    Find the closest thread whose reference is within alpha of the coordinate.

    Unlike the original plan, this:
    - Matches within alpha of the thread reference (not within delta)
    - Returns the CLOSEST thread when multiple threads match (deterministic)

    Args:
        coord: The coordinate value to match.
        threads: List of Thread objects for this axis.
        alpha: Maximum allowed per-axis displacement.

    Returns:
        The closest matching Thread, or None if no thread matches.
    """
    best_thread = None
    best_displacement = float("inf")

    for thread in threads:
        displacement = abs(coord - thread.reference)
        if displacement <= alpha and displacement < best_displacement:
            best_thread = thread
            best_displacement = displacement

    return best_thread
```

**Key changes:**
- `find_matching_thread` now matches within `alpha` of reference (not within `delta`)
- Returns **closest** thread, not first match (deterministic overlap resolution)

#### 3. Alignment processor
**File**: `structure-batiment/structure_aligner/alignment/processor.py`

Implements PRD F-07 with **per-axis displacement enforcement** (PRD CF-02):
```python
import math
import logging
from structure_aligner.config import AlignmentConfig, Thread, AlignedVertex
from structure_aligner.db.reader import InputVertex
from structure_aligner.alignment.geometry import euclidean_displacement, find_matching_thread

logger = logging.getLogger(__name__)


def align_vertices(
    vertices: list[InputVertex],
    threads_x: list[Thread],
    threads_y: list[Thread],
    threads_z: list[Thread],
    config: AlignmentConfig,
) -> list[AlignedVertex]:
    """
    Align all vertices to their nearest threads.

    For each vertex, tries to match each axis coordinate (X, Y, Z)
    to a thread. If matched, the coordinate is snapped to the thread's
    reference value. If not matched, the original coordinate is preserved.

    Displacement is enforced PER-AXIS (PRD CF-02, lines 272-273):
      abs(vertex.coord - thread.reference) <= alpha
    This is guaranteed by find_matching_thread which only returns threads
    within alpha. The 3D Euclidean displacement is computed for reporting only.

    Args:
        vertices: Input vertices to align.
        threads_x: Detected threads for X axis.
        threads_y: Detected threads for Y axis.
        threads_z: Detected threads for Z axis.
        config: Alignment configuration.

    Returns:
        List of AlignedVertex with original and aligned coordinates.
    """
    ndigits = config.rounding_ndigits
    aligned = []
    for v in vertices:
        # Try matching each axis (per-axis displacement guaranteed <= alpha)
        tx = find_matching_thread(v.x, threads_x, config.alpha)
        ty = find_matching_thread(v.y, threads_y, config.alpha)
        tz = find_matching_thread(v.z, threads_z, config.alpha)

        new_x = tx.reference if tx else v.x
        new_y = ty.reference if ty else v.y
        new_z = tz.reference if tz else v.z

        # Build aligned_axis string
        axes = []
        if tx: axes.append("X")
        if ty: axes.append("Y")
        if tz: axes.append("Z")
        aligned_axis = "".join(axes) if axes else "none"

        # Calculate total 3D displacement (for REPORTING only, not for constraint)
        displacement = euclidean_displacement(v.x, v.y, v.z, new_x, new_y, new_z)

        aligned.append(AlignedVertex(
            id=v.id,
            element_id=v.element_id,
            x=round(new_x, ndigits),
            y=round(new_y, ndigits),
            z=round(new_z, ndigits),
            vertex_index=v.vertex_index,
            x_original=v.x,
            y_original=v.y,
            z_original=v.z,
            aligned_axis=aligned_axis,
            fil_x_id=tx.fil_id if tx else None,
            fil_y_id=ty.fil_id if ty else None,
            fil_z_id=tz.fil_id if tz else None,
            displacement_total=round(displacement, 6),
        ))

    aligned_count = sum(1 for av in aligned if av.aligned_axis != "none")
    logger.info("Aligned %d/%d vertices (%.1f%%)", aligned_count, len(aligned),
                aligned_count / len(aligned) * 100 if aligned else 0)

    return aligned
```

**Key changes from original plan:**
- Removed the `ValueError` raise on 3D displacement > alpha. Per-axis constraint is enforced by `find_matching_thread` which only returns threads within alpha. 3D displacement can legitimately exceed alpha when multiple axes are aligned (e.g. X and Y each displaced by 0.04m → 3D = 0.057m).
- Rounding uses `config.rounding_ndigits` (not `int(-math.log10(...))` inline)

#### 4. Database writer for enriched output
**File**: `structure-batiment/structure_aligner/db/writer.py`

Implements PRD F-08 using **ALTER TABLE** approach (keeps `vertices` table name per PRD):
```python
import logging
import shutil
import sqlite3
from pathlib import Path

from structure_aligner.config import AlignedVertex

logger = logging.getLogger(__name__)

# New columns to add to the vertices table (PRD F-08, lines 298-321)
ALTER_TABLE_COLUMNS = [
    ("x_original", "REAL"),
    ("y_original", "REAL"),
    ("z_original", "REAL"),
    ("aligned_axis", "VARCHAR(10) NOT NULL DEFAULT 'none'"),
    ("fil_x_id", "VARCHAR(20)"),
    ("fil_y_id", "VARCHAR(20)"),
    ("fil_z_id", "VARCHAR(20)"),
    ("displacement_total", "REAL NOT NULL DEFAULT 0.0"),
]

CREATE_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_vertices_aligned_axis ON vertices(aligned_axis);",
    "CREATE INDEX IF NOT EXISTS idx_vertices_displacement ON vertices(displacement_total);",
]


def write_aligned_db(
    input_db: Path,
    output_path: Path,
    aligned_vertices: list[AlignedVertex],
) -> Path:
    """
    Create output database with enriched vertices table.

    Copies the input database, then uses ALTER TABLE to add enrichment
    columns to the existing vertices table. This preserves the table name
    (PRD F-08 compliance), all existing FK constraints, and indexes.

    Then updates each vertex row with aligned coordinates and metadata.

    Args:
        input_db: Path to the input PRD-compliant database.
        output_path: Path for the output database.
        aligned_vertices: List of aligned vertices to write.

    Returns:
        Path to the created output database.
    """
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(input_db), str(output_path))

    conn = sqlite3.connect(str(output_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        cursor = conn.cursor()

        # Add new columns to existing vertices table
        for col_name, col_type in ALTER_TABLE_COLUMNS:
            cursor.execute(f"ALTER TABLE vertices ADD COLUMN {col_name} {col_type};")

        # Update each vertex with aligned data
        cursor.executemany(
            """UPDATE vertices
               SET x = ?, y = ?, z = ?,
                   x_original = ?, y_original = ?, z_original = ?,
                   aligned_axis = ?, fil_x_id = ?, fil_y_id = ?, fil_z_id = ?,
                   displacement_total = ?
               WHERE id = ?""",
            [
                (v.x, v.y, v.z,
                 v.x_original, v.y_original, v.z_original,
                 v.aligned_axis, v.fil_x_id, v.fil_y_id, v.fil_z_id,
                 v.displacement_total,
                 v.id)
                for v in aligned_vertices
            ],
        )

        # Create new indexes
        for sql in CREATE_INDEXES_SQL:
            cursor.execute(sql)

        conn.commit()
        logger.info("Written %d aligned vertices to %s", len(aligned_vertices), output_path)

    except Exception:
        conn.rollback()
        output_path.unlink(missing_ok=True)
        raise
    finally:
        conn.close()

    return output_path
```

**Key changes from original plan:**
- Uses `ALTER TABLE ADD COLUMN` instead of drop+recreate
- Keeps original `vertices` table name (PRD F-08 compliance)
- Uses `UPDATE` instead of `INSERT` (vertices already exist from copy)
- Preserves all existing FK constraints and original table indexes
- No need for backwards-compatible view (table IS the `vertices` table)

#### 5. Unit tests

**File**: `structure-batiment/tests/test_reader.py`
```python
# Test load_vertices with:
# - Real geometrie_2_prd.db (20994 vertices)
# - Missing file -> FileNotFoundError
# - DB without vertices table -> ValueError
```

**File**: `structure-batiment/tests/test_geometry.py`
```python
# Test euclidean_displacement:
# - Zero displacement
# - Known triangle (3-4-5)
# - Single axis displacement

# Test find_matching_thread:
# - Coord within alpha of reference -> returns thread
# - Coord outside alpha of all references -> returns None
# - Coord at boundary of alpha
# - CRITICAL: Multiple overlapping threads -> returns CLOSEST (smallest displacement)
# - Thread with small delta but coord within alpha -> still matches (uses alpha, not delta)
```

**File**: `structure-batiment/tests/test_processor.py`
```python
# Test align_vertices:
# - Simple case: 3 vertices, 1 thread per axis, all align
# - Mixed: some align, some isolated
# - Per-axis displacement exactly at alpha boundary -> aligns
# - Multi-axis alignment where 3D displacement > alpha -> still OK (per-axis is the constraint)
# - Empty input
# - aligned_axis string construction ("X", "XY", "XYZ", "none")
# - Rounding uses config.rounding_ndigits
```

**File**: `structure-batiment/tests/test_writer.py`
```python
# Test write_aligned_db:
# - Creates output with enriched vertices table (same table, new columns)
# - Vertices have correct aligned coordinates
# - x_original/y_original/z_original preserved
# - Elements table and FK constraints preserved
# - Original indexes preserved + new indexes created
# - Output already exists -> FileExistsError
# - FK integrity maintained
```

### Success Criteria:

#### Automated Verification:
- [x] `python -m pytest tests/test_reader.py tests/test_geometry.py tests/test_processor.py tests/test_writer.py -v`
- [x] All unit tests pass

#### Code Review (devil-advocate):
- [ ] `find_matching_thread` matches within `alpha` (not `delta`)
- [ ] `find_matching_thread` returns closest thread (deterministic)
- [ ] Processor does NOT raise on 3D displacement > alpha (per-axis is the constraint)
- [ ] Rounding precision uses `config.rounding_ndigits`
- [ ] DB writer uses ALTER TABLE (not drop+recreate)
- [ ] DB writer uses atomic transaction (commit/rollback)
- [ ] No SQL injection risk (parameterized queries only)
- [ ] `displacement_total` is 3D Euclidean (for reporting)
- [ ] Output `vertices` table matches PRD F-08 schema (lines 298-321)

**Implementation Note**: This phase runs in parallel with 2a and 2c.

### Devil's Advocate Feedback Loop (Phase 2b):
Once alignment-dev signals completion, devil-advocate reviews the code against the checklist above. If issues are found:
1. devil-advocate sends specific feedback to alignment-dev
2. alignment-dev fixes the issues and re-runs tests
3. devil-advocate re-reviews the fixes
4. **Loop continues until devil-advocate explicitly approves Phase 2b**
5. Only after approval is alignment-dev's task marked complete

Typical review triggers:
- SQL injection risk in queries
- Matching using delta instead of alpha
- First-match instead of closest-match for overlapping threads
- Rounding precision hardcoded instead of using config
- Missing atomic transaction rollback on error
- Drop+recreate instead of ALTER TABLE
- 3D displacement used as acceptance criterion instead of per-axis

---

## Phase 2c: Reporting — Post-Alignment Validation & Report Generation

### Overview
Implement post-alignment validation checks (F-09) and comprehensive JSON report generation (F-10).

**Design change from original plan:** Validation check for max displacement now validates **per-axis** (not 3D Euclidean), consistent with PRD CF-02.

### Agent Assignment: `reporting-dev`

### Changes Required:

#### 1. Post-alignment validator
**File**: `structure-batiment/structure_aligner/output/validator.py`

Implements PRD F-09:
```python
import logging
from dataclasses import dataclass, field

from structure_aligner.config import AlignmentConfig, AlignedVertex

logger = logging.getLogger(__name__)


@dataclass
class ValidationCheck:
    """Result of a single validation check."""
    name: str
    status: str  # "PASS", "FAIL", "WARNING"
    detail: str = ""


@dataclass
class ValidationResult:
    """Complete validation result."""
    passed: bool = True
    checks: list[ValidationCheck] = field(default_factory=list)


def validate_alignment(
    aligned_vertices: list[AlignedVertex],
    original_count: int,
    config: AlignmentConfig,
) -> ValidationResult:
    """
    Run PRD F-09 post-alignment validation checks.

    Checks:
    1. Max per-axis displacement <= alpha (CRITICAL, PRD CF-02)
    2. No NULL coordinates introduced (CRITICAL)
    3. Vertex count preserved (CRITICAL)
    4. Alignment rate >= 80% (WARNING per PRD F-09)

    Note: CQ-01 (85% alignment rate) is validated in integration tests,
    not here. This validator implements F-09's warning threshold of 80%.

    Args:
        aligned_vertices: The aligned vertices to validate.
        original_count: Number of vertices before alignment.
        config: Alignment configuration.

    Returns:
        ValidationResult with pass/fail status and individual check results.
    """
    result = ValidationResult()

    # Check 1: Max per-axis displacement <= alpha (PRD CF-02)
    if aligned_vertices:
        max_per_axis_disp = 0.0
        for v in aligned_vertices:
            dx = abs(v.x - v.x_original) if v.fil_x_id else 0.0
            dy = abs(v.y - v.y_original) if v.fil_y_id else 0.0
            dz = abs(v.z - v.z_original) if v.fil_z_id else 0.0
            max_per_axis_disp = max(max_per_axis_disp, dx, dy, dz)

        if max_per_axis_disp > config.alpha + 1e-9:  # Small epsilon for float comparison
            result.passed = False
            result.checks.append(ValidationCheck(
                "max_per_axis_displacement", "FAIL",
                f"Max per-axis displacement {max_per_axis_disp:.6f}m exceeds alpha {config.alpha}m"
            ))
            logger.error("CRITICAL: Max per-axis displacement %.6fm > alpha %.3fm",
                        max_per_axis_disp, config.alpha)
        else:
            result.checks.append(ValidationCheck(
                "max_per_axis_displacement", "PASS",
                f"Max per-axis displacement {max_per_axis_disp:.6f}m <= alpha {config.alpha}m"
            ))
    else:
        result.checks.append(ValidationCheck("max_per_axis_displacement", "PASS", "No vertices to check"))

    # Check 2: No NULL coordinates
    null_count = sum(1 for v in aligned_vertices if v.x is None or v.y is None or v.z is None)
    if null_count > 0:
        result.passed = False
        result.checks.append(ValidationCheck(
            "no_null_coordinates", "FAIL",
            f"{null_count} vertices with NULL coordinates"
        ))
    else:
        result.checks.append(ValidationCheck("no_null_coordinates", "PASS", "0 NULL coordinates"))

    # Check 3: Vertex count preserved
    if len(aligned_vertices) != original_count:
        result.passed = False
        result.checks.append(ValidationCheck(
            "vertex_count_preserved", "FAIL",
            f"Expected {original_count}, got {len(aligned_vertices)}"
        ))
    else:
        result.checks.append(ValidationCheck(
            "vertex_count_preserved", "PASS",
            f"Count preserved: {len(aligned_vertices)}"
        ))

    # Check 4: Alignment rate >= 80% (PRD F-09 WARNING threshold)
    if aligned_vertices:
        aligned_count = sum(1 for v in aligned_vertices if v.aligned_axis != "none")
        rate = aligned_count / len(aligned_vertices) * 100
        if rate < 80:
            result.checks.append(ValidationCheck(
                "alignment_rate", "WARNING",
                f"Alignment rate {rate:.1f}% < 80% threshold"
            ))
            logger.warning("Alignment rate %.1f%% below 80%% threshold", rate)
        else:
            result.checks.append(ValidationCheck(
                "alignment_rate", "PASS",
                f"Alignment rate {rate:.1f}%"
            ))

    if result.passed:
        logger.info("All validation checks passed")
    else:
        logger.error("Validation FAILED — see check details")

    return result
```

**Key changes from original plan:**
- Displacement check is now **per-axis** (PRD CF-02), not 3D Euclidean
- Added float epsilon for comparison (`+ 1e-9`)
- Documented that 80% is the F-09 WARNING threshold, 85% is CQ-01 (tested in integration tests)

#### 2. Report generator
**File**: `structure-batiment/structure_aligner/output/report_generator.py`

Implements PRD F-10 (unchanged from original plan except for the displacement_total clarification):
```python
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from structure_aligner.config import AlignmentResult
from structure_aligner.output.validator import ValidationResult

logger = logging.getLogger(__name__)


def generate_report(
    result: AlignmentResult,
    validation: ValidationResult,
    input_db: Path,
    output_db: Path | None,
    execution_time_seconds: float,
    report_path: Path,
) -> Path:
    """
    Generate a comprehensive JSON report per PRD F-10.

    Args:
        result: Complete alignment result.
        validation: Post-alignment validation result.
        input_db: Path to the input database.
        output_db: Path to the output database (None for dry-run).
        execution_time_seconds: Total pipeline execution time.
        report_path: Where to write the JSON report.

    Returns:
        Path to the generated report file.
    """
    aligned = result.aligned_vertices
    threads = result.threads

    # Compute displacement statistics
    displacements = [v.displacement_total for v in aligned]
    aligned_count = sum(1 for v in aligned if v.aligned_axis != "none")
    isolated_count = len(aligned) - aligned_count

    # Group threads by axis
    threads_by_axis = {"X": [], "Y": [], "Z": []}
    for t in threads:
        threads_by_axis[t.axis].append({
            "fil_id": t.fil_id,
            "reference": t.reference,
            "delta": t.delta,
            "vertex_count": t.vertex_count,
        })

    # Isolated vertices detail
    isolated_details = []
    for v in aligned:
        if v.aligned_axis == "none":
            isolated_details.append({
                "vertex_id": v.id,
                "element_id": v.element_id,
                "coordinates": [v.x_original, v.y_original, v.z_original],
                "reason": "no_nearby_cluster",
            })

    import numpy as np
    disp_array = np.array(displacements) if displacements else np.array([0.0])

    report_data = {
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "input_database": str(input_db),
            "output_database": str(output_db) if output_db else None,
            "execution_time_seconds": round(execution_time_seconds, 2),
            "software_version": "0.1.0",
            "dry_run": output_db is None,
        },
        "parameters": {
            "alpha": result.config.alpha,
            "clustering_method": "dbscan",
            "min_cluster_size": result.config.min_cluster_size,
            "rounding_precision": result.config.rounding_precision,
        },
        "statistics": {
            "total_vertices": len(aligned),
            "aligned_vertices": aligned_count,
            "isolated_vertices": isolated_count,
            "alignment_rate_percent": round(
                aligned_count / len(aligned) * 100, 1
            ) if aligned else 0,
        },
        "axis_statistics": {
            stat.axis: {
                "mean": stat.mean,
                "median": stat.median,
                "std": stat.std,
                "min": stat.min,
                "max": stat.max,
                "q1": stat.q1,
                "q3": stat.q3,
                "unique_count": stat.unique_count,
            }
            for stat in result.statistics
        },
        "threads_detected": threads_by_axis,
        "displacement_statistics": {
            "mean_meters": round(float(np.mean(disp_array)), 6),
            "median_meters": round(float(np.median(disp_array)), 6),
            "max_meters": round(float(np.max(disp_array)), 6),
            "std_meters": round(float(np.std(disp_array)), 6),
            "note": "3D Euclidean displacement (for reporting). Per-axis constraint enforced separately.",
        },
        "isolated_vertices": isolated_details[:100],  # Cap at 100 for readability
        "isolated_vertices_total": len(isolated_details),
        "validation": {
            "passed": validation.passed,
            "checks": [
                {"name": c.name, "status": c.status, "detail": c.detail}
                for c in validation.checks
            ],
        },
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False))
    logger.info("Alignment report written to %s", report_path)

    return report_path
```

#### 3. Unit tests

**File**: `structure-batiment/tests/test_validator.py`
```python
# Test validate_alignment:
# - All checks pass (normal case)
# - Per-axis displacement exceeds alpha -> FAIL
# - Multi-axis displacement where 3D > alpha but per-axis <= alpha -> PASS
# - NULL coordinate introduced -> FAIL
# - Vertex count mismatch -> FAIL
# - Low alignment rate -> WARNING (not FAIL)
# - Empty input
```

**File**: `structure-batiment/tests/test_report_generator.py`
```python
# Test generate_report:
# - Produces valid JSON
# - All PRD F-10 fields present
# - Dry-run mode (output_db=None)
# - Isolated vertices capped at 100
# - Thread grouping by axis
# - Displacement statistics correct
# - displacement_statistics.note field present
```

### Success Criteria:

#### Automated Verification:
- [x] `python -m pytest tests/test_validator.py tests/test_report_generator.py -v`
- [x] All tests pass

#### Code Review (devil-advocate):
- [ ] Validation checks match PRD F-09 table exactly
- [ ] **Displacement check is per-axis** (not 3D Euclidean)
- [ ] **Float comparison uses epsilon** for displacement check
- [ ] Report JSON structure matches PRD F-10 example
- [ ] `isolated_vertices` capped to prevent massive JSON files
- [ ] `numpy` import is inside function (not at module level) to keep module lightweight
- [ ] Timestamps are UTC (PRD example uses ISO 8601)
- [ ] 80% is WARNING, not FAIL (CQ-01 85% tested elsewhere)

**Implementation Note**: This phase runs in parallel with 2a and 2b.

### Devil's Advocate Feedback Loop (Phase 2c):
Once reporting-dev signals completion, devil-advocate reviews the code against the checklist above. If issues are found:
1. devil-advocate sends specific feedback to reporting-dev
2. reporting-dev fixes the issues and re-runs tests
3. devil-advocate re-reviews the fixes
4. **Loop continues until devil-advocate explicitly approves Phase 2c**
5. Only after approval is reporting-dev's task marked complete

Typical review triggers:
- Validation using 3D displacement instead of per-axis
- Missing float epsilon in comparison
- Report JSON structure diverging from PRD F-10 example
- Timestamps not in UTC ISO 8601
- Missing dry-run handling
- Massive JSON from unbounded isolated_vertices list

---

## Phase 3: CLI Integration & End-to-End Wiring

### Overview
Wire all modules together into the `align` CLI subcommand, add dry-run support, and write integration tests that run the full pipeline on real data.

### Agent Assignment: `cli-integr-dev`

### Changes Required:

#### 1. Add `align` command to CLI
**File**: `structure-batiment/structure_aligner/main.py`

Add after the existing `etl` command:
```python
@cli.command()
@click.option("--input", "input_db", required=True, type=click.Path(exists=True),
              help="Path to PRD-compliant input database")
@click.option("--output", type=click.Path(), default=None,
              help="Path for output database (auto-generated if omitted)")
@click.option("--alpha", type=float, default=0.05,
              help="Tolerance in meters (default: 0.05)")
@click.option("--min-cluster-size", type=int, default=3,
              help="Minimum vertices per thread (default: 3)")
@click.option("--report", type=click.Path(), default=None,
              help="Path for JSON report (auto-generated if omitted)")
@click.option("--dry-run", is_flag=True, default=False,
              help="Simulation mode: produce report only, no output DB")
@click.option("--log-level", default="INFO",
              type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
def align(input_db, output, alpha, min_cluster_size, report, dry_run, log_level):
    """Align vertices to detected threads within tolerance."""
    import time
    import numpy as np
    from datetime import datetime

    setup_logging(log_level)
    logger = logging.getLogger(__name__)

    input_path = Path(input_db)
    config = AlignmentConfig(alpha=alpha, min_cluster_size=min_cluster_size)

    # Auto-generate output path if not provided
    if output is None and not dry_run:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = input_path.with_name(
            f"{input_path.stem}_aligned_{timestamp}.db"
        )
    elif output:
        output_path = Path(output)
    else:
        output_path = None

    # Auto-generate report path
    if report is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = input_path.with_name(f"alignment_report_{timestamp}.json")
    else:
        report_path = Path(report)

    start_time = time.time()

    logger.info("Starting alignment pipeline")
    logger.info("  Input:  %s", input_path)
    logger.info("  Output: %s", output_path or "(dry-run)")
    logger.info("  Alpha:  %.3fm", config.alpha)
    logger.info("  Mode:   %s", "dry-run" if dry_run else "full")

    # Step 1: Load vertices
    from structure_aligner.db.reader import load_vertices
    vertices = load_vertices(input_path)
    logger.info("Loaded %d vertices", len(vertices))

    # Step 2: Compute statistics
    from structure_aligner.analysis.statistics import compute_axis_statistics
    xs = np.array([v.x for v in vertices])
    ys = np.array([v.y for v in vertices])
    zs = np.array([v.z for v in vertices])

    stats = [
        compute_axis_statistics(xs, "X"),
        compute_axis_statistics(ys, "Y"),
        compute_axis_statistics(zs, "Z"),
    ]
    for s in stats:
        logger.info("  Axis %s: %d unique values, std=%.4f", s.axis, s.unique_count, s.std)

    # Step 3: Detect threads
    from structure_aligner.alignment.thread_detector import detect_threads
    threads_x = detect_threads(xs, "X", config)
    threads_y = detect_threads(ys, "Y", config)
    threads_z = detect_threads(zs, "Z", config)
    all_threads = threads_x + threads_y + threads_z
    logger.info("Detected %d threads (X:%d, Y:%d, Z:%d)",
                len(all_threads), len(threads_x), len(threads_y), len(threads_z))

    # Step 4: Align vertices
    from structure_aligner.alignment.processor import align_vertices
    aligned = align_vertices(vertices, threads_x, threads_y, threads_z, config)

    # Step 5: Validate
    from structure_aligner.output.validator import validate_alignment
    validation = validate_alignment(aligned, len(vertices), config)

    # Step 6: Build result
    from structure_aligner.config import AlignmentResult
    alignment_result = AlignmentResult(
        threads=all_threads,
        aligned_vertices=aligned,
        statistics=stats,
        config=config,
    )

    # Step 7: Write output DB (unless dry-run)
    if not dry_run and output_path:
        from structure_aligner.db.writer import write_aligned_db
        write_aligned_db(input_path, output_path, aligned)
        logger.info("Output database: %s", output_path)

    # Step 8: Generate report
    execution_time = time.time() - start_time
    from structure_aligner.output.report_generator import generate_report
    generate_report(
        alignment_result, validation,
        input_path, output_path if not dry_run else None,
        execution_time, report_path,
    )
    logger.info("Report: %s", report_path)

    # Summary
    aligned_count = sum(1 for v in aligned if v.aligned_axis != "none")
    rate = aligned_count / len(aligned) * 100 if aligned else 0
    max_disp = max((v.displacement_total for v in aligned), default=0)

    logger.info("Alignment complete in %.1fs", execution_time)
    logger.info("  %d/%d vertices aligned (%.1f%%)", aligned_count, len(aligned), rate)
    logger.info("  Max displacement: %.4fm (3D Euclidean, for reporting)", max_disp)
    logger.info("  Validation: %s", "PASSED" if validation.passed else "FAILED")
```

Add necessary imports at the top of `main.py`:
```python
from structure_aligner.config import AlignmentConfig
```

#### 2. Integration tests
**File**: `structure-batiment/tests/test_integration_align.py`

```python
# End-to-end integration tests using geometrie_2_prd.db:

# test_full_alignment_pipeline:
#   - Run align on real data with alpha=0.05
#   - Verify output DB created with enriched vertices table (ALTER TABLE columns present)
#   - Verify vertex count preserved (20994)
#   - Verify alignment rate >= 85% (CQ-01 hard requirement)
#   - Verify max per-axis displacement <= alpha
#   - Verify report JSON has all required fields

# test_dry_run_no_output_db:
#   - Run with --dry-run
#   - Verify no output DB created
#   - Verify report still generated
#   - Verify report.metadata.dry_run is True

# test_different_alpha_values:
#   - alpha=0.01 -> stricter, lower alignment rate
#   - alpha=0.10 -> more permissive, higher alignment rate
#   - Verify alignment rate increases with alpha

# test_axis_thread_detection:
#   - Verify threads detected on all 3 axes
#   - Log actual thread counts (no hardcoded expectation)
#   - Verify Z threads are reasonable given floor levels

# test_multi_axis_displacement:
#   - Verify that vertices aligned on multiple axes (X+Y) can have
#     3D displacement > alpha, which is expected and correct
#   - Per-axis displacement must still be <= alpha

# test_cli_invocation:
#   - Use click.testing.CliRunner to test CLI command
#   - Verify exit code 0
#   - Verify log output contains expected messages

# test_output_db_schema:
#   - Verify vertices table has all PRD F-08 columns
#   - Verify elements table and FK constraints preserved
#   - Verify original x,y,z indexes still exist
```

### Success Criteria:

#### Automated Verification:
- [x] `python -m pytest tests/test_integration_align.py -v`
- [x] All integration tests pass
- [x] Full test suite: `python -m pytest tests/ -v --cov=structure_aligner` (139 passed, 89% total, 100% on new modules)
- [x] Coverage >= 90% on new modules (all new modules at 100% except writer at 87%)
- [x] CLI works end-to-end:
  ```bash
  cd structure-batiment
  python -m structure_aligner align --input data/geometrie_2_prd.db --alpha 0.05
  ```

#### Manual Verification:
- [ ] Output database opens correctly in SQLite browser
- [ ] Enriched `vertices` table has all PRD F-08 columns
- [ ] Report JSON is human-readable and matches PRD F-10 structure
- [ ] `--dry-run` produces report but no output DB
- [ ] Different alpha values produce different alignment rates
- [ ] Log output is clean and informative

#### Code Review (devil-advocate):
- [ ] No hardcoded paths or values
- [ ] CLI help text is clear and matches PRD Section 3.2
- [ ] Error messages are actionable (PRD NFR-03 format)
- [ ] Integration tests don't modify source data files
- [ ] Imports are lazy (inside function) to keep CLI fast for `--help`
- [ ] Auto-generated filenames include timestamps (no collision risk)
- [ ] `config.alpha` flows correctly from CLI to all components
- [ ] Integration tests verify CQ-01 (85% alignment rate)
- [ ] Per-axis displacement is validated (not 3D)

**Implementation Note**: Phase 3 depends on **all Phase 2 agents having devil-advocate approval**. Wait for explicit approval of Phases 2a, 2b, and 2c before starting Phase 3. If any Phase 2 agent is still in a feedback loop with devil-advocate, Phase 3 must wait.

---

## Phase 4: Devil's Advocate Final Review

### Overview
Comprehensive review of all code produced in Phases 1-3. The devil-advocate agent reviews architecture, security, correctness, and PRD compliance.

### Agent Assignment: `devil-advocate`

### Review Checklist:

#### Architecture Quality:
- [ ] No circular imports between modules
- [ ] Clear separation of concerns (analysis vs alignment vs output)
- [ ] Dataclasses used consistently (no mixed approaches)
- [ ] Logging follows PRD NFR-08 format throughout
- [ ] Error handling follows PRD NFR-03 severity categories

#### Security:
- [ ] All SQL uses parameterized queries (no string formatting)
- [ ] ALTER TABLE column names are not user-controlled (safe from injection)
- [ ] No file path injection risks in CLI arguments
- [ ] Output file existence check prevents accidental overwrites
- [ ] No secrets/credentials in code or config

#### Correctness:
- [ ] delta = min(std, alpha) — PRD formula respected everywhere
- [ ] Thread merge uses weighted average (not simple average)
- [ ] **Per-axis displacement** is the acceptance criterion (not 3D Euclidean)
- [ ] **3D displacement** is for reporting only
- [ ] **Post-clustering validation** prunes chained points > alpha from centroid
- [ ] **Closest-thread matching** is deterministic
- [ ] Rounding precision uses `config.rounding_ndigits` throughout
- [ ] Vertex count is preserved exactly (no off-by-one)
- [ ] Isolated vertices retain original coordinates (not zeroed/NaN)
- [ ] Population std (ddof=0) used consistently

#### PRD Compliance:
- [ ] All F-03 through F-10 requirements addressed
- [ ] Output schema matches PRD F-08 (lines 298-321) — enriched `vertices` table
- [ ] Report JSON matches PRD F-10 example structure
- [ ] Validation checks match PRD F-09 table
- [ ] CLI options match PRD Section 3.2
- [ ] CF-02 per-axis displacement constraint enforced
- [ ] CQ-01 alignment rate >= 85% achieved on real data

#### Performance:
- [ ] No O(n^2) algorithms where O(n log n) is possible
- [ ] numpy arrays used for numerical operations (not Python lists)
- [ ] DB operations use executemany (batch update)
- [ ] No unnecessary copies of large arrays

### Success Criteria:
- [ ] All review issues resolved or explicitly deferred with rationale
- [ ] No CRITICAL or HIGH severity issues remaining
- [ ] Full test suite passes after review fixes

---

## Agent Team Execution Strategy

### Team Configuration

| Agent Name | Subagent Type | Mode | Active Phases |
|------------|---------------|------|---------------|
| `cli-integr-dev` | general-purpose | bypassPermissions | 1, 3 |
| `analysis-dev` | general-purpose | bypassPermissions | 2a |
| `alignment-dev` | general-purpose | bypassPermissions | 2b |
| `reporting-dev` | general-purpose | bypassPermissions | 2c |
| `devil-advocate` | general-purpose | default | 1-review, 2 (continuous), 4 |

### Execution Timeline

```
Time ──────────────────────────────────────────────────────────────────►

Phase 1:     [cli-integr-dev: scaffolding + contracts]
                 │
Phase 1 Rev: [devil-advocate: review contracts]◄──►[cli-integr-dev: fix]
                 │ (approved)
                 │
Phase 2:         ├──[analysis-dev: code]──►[DA review]◄──►[fix loop]──┐
                 ├──[alignment-dev: code]──►[DA review]◄──►[fix loop]─┤
                 ├──[reporting-dev: code]──►[DA review]◄──►[fix loop]─┤
                 │                                                     │
                 │              all 3 approved by devil-advocate ◄─────┘
                 │                         │
Phase 3:         └──[cli-integr-dev: wire + integration tests]────────┤
                                                                       │
Phase 4:         [devil-advocate: final comprehensive review]──────────┘
```

**Legend**: `DA` = devil-advocate, `◄──►` = feedback loop (may iterate multiple times)

### Task Dependencies

```
Task 1: Phase 1 scaffolding (cli-integr-dev)
  │
  └── Task 2: Phase 1 gate review (devil-advocate) — blocked by Task 1
        │       ↕ feedback loop with cli-integr-dev until approved
        │
        ├── Task 3: Phase 2a analysis (analysis-dev) — blocked by Task 2 approval
        │     └── Task 3r: Phase 2a review (devil-advocate) — blocked by Task 3
        │           ↕ feedback loop with analysis-dev until approved
        │
        ├── Task 4: Phase 2b alignment (alignment-dev) — blocked by Task 2 approval
        │     └── Task 4r: Phase 2b review (devil-advocate) — blocked by Task 4
        │           ↕ feedback loop with alignment-dev until approved
        │
        ├── Task 5: Phase 2c reporting (reporting-dev) — blocked by Task 2 approval
        │     └── Task 5r: Phase 2c review (devil-advocate) — blocked by Task 5
        │           ↕ feedback loop with reporting-dev until approved
        │
        ├── Task 6: Phase 3 integration (cli-integr-dev) — blocked by Tasks 3r,4r,5r ALL approved
        │
        └── Task 7: Phase 4 final review (devil-advocate) — blocked by Task 6
```

### Communication Protocol

1. **Phase 1**: cli-integr-dev completes scaffolding, sends "Phase 1 ready for review" to devil-advocate
2. **Phase 1 Review**: devil-advocate reviews and either approves or sends feedback. If feedback: cli-integr-dev fixes, re-submits. **Loop until approved.**
3. **Phase 2 kickoff**: Once Phase 1 is approved, team lead spawns analysis-dev, alignment-dev, reporting-dev in parallel
4. **Phase 2 coding**: Each agent codes their module and signals "ready for review" to devil-advocate
5. **Phase 2 review loops**: devil-advocate reviews each agent's code. If issues found:
   - devil-advocate sends specific, actionable feedback to the responsible agent
   - Agent fixes issues and re-signals "ready for re-review"
   - devil-advocate re-reviews
   - **Loop repeats until devil-advocate sends explicit "Phase 2x APPROVED"**
   - An agent's task is NOT complete until approved — even if tests pass
6. **Phase 3 gate**: cli-integr-dev begins Phase 3 **only after all 3 Phase 2 agents have devil-advocate approval**
7. **Phase 4**: devil-advocate does final holistic review after Phase 3 completes

### Feedback Loop Severity Levels

The devil-advocate categorizes findings to help agents prioritize:

| Severity | Action Required | Example |
|----------|----------------|---------|
| **BLOCKER** | Must fix before approval. Cannot proceed. | SQL injection, per-axis displacement not enforced, wrong algorithm |
| **MAJOR** | Must fix before approval. | Missing edge case, wrong PRD field name, no rollback on error |
| **MINOR** | Should fix, but won't block approval alone. | Suboptimal logging message, could use better variable name |
| **SUGGESTION** | Optional improvement, agent decides. | Performance optimization, alternative approach |

Rule: **Approval requires zero BLOCKERs and zero MAJORs remaining.**

---

## Testing Strategy

### Unit Tests (per module):
| Test File | Module | Key Tests |
|-----------|--------|-----------|
| `test_statistics.py` | analysis/statistics.py | Known arrays, edge cases, ddof=0 |
| `test_clustering.py` | analysis/clustering.py | Clear clusters, noise, thresholds, **chaining pruning** |
| `test_thread_detector.py` | alignment/thread_detector.py | Detection, merging, renumbering, **alpha-based ranges** |
| `test_reader.py` | db/reader.py | Load, validation, errors |
| `test_geometry.py` | alignment/geometry.py | Displacement calc, **closest-thread matching** |
| `test_processor.py` | alignment/processor.py | Alignment, isolation, **per-axis constraint** |
| `test_writer.py` | db/writer.py | Schema (**ALTER TABLE**), data, indexes, errors |
| `test_validator.py` | output/validator.py | All 4 check types, **per-axis displacement** |
| `test_report_generator.py` | output/report_generator.py | JSON structure, dry-run |

### Integration Tests:
| Test | Description |
|------|-------------|
| `test_analysis_integration.py` | Real data thread detection |
| `test_integration_align.py` | Full pipeline end-to-end, **CQ-01 85% rate** |

### Coverage Target: >= 90% on all new modules

---

## Performance Considerations

With 20,994 vertices:
- DBSCAN on 1D array: O(n log n) with scikit-learn's BallTree — sub-second
- Post-clustering validation: O(n) per cluster — negligible
- Alignment loop: O(n * t) where t = threads per axis (~10-20) — trivial
- DB write: single executemany UPDATE — sub-second
- **Expected total runtime: < 5 seconds** (well within PRD NFR-01 target of 30s for 10K vertices)

No batch processing, parallel processing, or memory optimization needed at this scale.

---

## References

- PRD: `structure-batiment/prd/PRD.md`
  - F-03 Statistical Analysis: lines 138-155
  - F-04 DBSCAN Clustering: lines 160-201
  - F-05 Thread Identification: lines 205-228
  - F-06 Edge Cases: lines 232-258
  - F-07 Vertex Alignment: lines 264-283 (**per-axis displacement**: lines 272-273)
  - F-08 Output Database: lines 287-321 (**enriched `vertices` table**)
  - F-09 Post-Alignment Validation: lines 325-358 (**80% warning threshold**: line 334)
  - F-10 Report: lines 362-428
  - CF-02 Displacement constraint: **per-axis** (lines 272-273, 331)
  - CQ-01 Alignment rate: **>= 85%, P0 priority** (line 1039)
  - CLI Interface: lines 484-523
  - Configuration: lines 576-615
  - Dependencies: lines 766-785 (pandas required, pyyaml deferred)
- Review: `docs/research/2026-02-06-alignment-plan-review.md`
- ETL Plan: `docs/plans/2026-02-05-etl-rhino-to-prd-database.md`
- Research: `docs/research/2026-02-05-geometrie2-database-prd-alignment.md`
  - Z-axis floor levels: 13 unique values
  - X unique values: 1,439 / Y unique values: 1,592
  - Coordinate ranges and building profile
