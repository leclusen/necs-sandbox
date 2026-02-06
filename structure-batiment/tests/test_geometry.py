"""Tests for structure_aligner.alignment.geometry."""
import math

import pytest

from structure_aligner.alignment.geometry import euclidean_displacement, find_matching_thread
from structure_aligner.config import Thread


def _make_thread(reference: float, fil_id: str = "X_001", axis: str = "X",
                 delta: float = 0.01, vertex_count: int = 10) -> Thread:
    """Helper to create a Thread for testing."""
    return Thread(
        fil_id=fil_id, axis=axis, reference=reference, delta=delta,
        vertex_count=vertex_count, range_min=reference - 0.05, range_max=reference + 0.05,
    )


class TestEuclideanDisplacement:

    def test_zero_displacement(self):
        assert euclidean_displacement(1.0, 2.0, 3.0, 1.0, 2.0, 3.0) == 0.0

    def test_known_triangle_345(self):
        result = euclidean_displacement(0, 0, 0, 3, 4, 0)
        assert result == pytest.approx(5.0)

    def test_single_axis_x(self):
        result = euclidean_displacement(1.0, 0.0, 0.0, 4.0, 0.0, 0.0)
        assert result == pytest.approx(3.0)

    def test_single_axis_z(self):
        result = euclidean_displacement(0, 0, 0, 0, 0, 7.5)
        assert result == pytest.approx(7.5)

    def test_3d_displacement(self):
        result = euclidean_displacement(1, 2, 3, 4, 6, 3)
        assert result == pytest.approx(5.0)  # sqrt(9 + 16 + 0)


class TestFindMatchingThread:

    def test_coord_within_alpha_returns_thread(self):
        thread = _make_thread(10.0)
        result = find_matching_thread(10.03, [thread], alpha=0.05)
        assert result is thread

    def test_coord_outside_alpha_returns_none(self):
        thread = _make_thread(10.0)
        result = find_matching_thread(10.06, [thread], alpha=0.05)
        assert result is None

    def test_exact_match(self):
        thread = _make_thread(10.0)
        result = find_matching_thread(10.0, [thread], alpha=0.05)
        assert result is thread

    def test_boundary_at_alpha_matches(self):
        """Displacement exactly at alpha should match (using exact floats)."""
        thread = _make_thread(10.0)
        # Use 0.5 and alpha=0.5 to avoid floating-point rounding issues
        result = find_matching_thread(10.5, [thread], alpha=0.5)
        assert result is thread

    def test_just_beyond_alpha_no_match(self):
        thread = _make_thread(10.0)
        result = find_matching_thread(10.06, [thread], alpha=0.05)
        assert result is None

    def test_closest_thread_returned_for_overlapping(self):
        """When multiple threads match, the CLOSEST one is returned."""
        thread_a = _make_thread(10.0, fil_id="X_001")
        thread_b = _make_thread(10.08, fil_id="X_002")
        # coord=10.04 is within alpha=0.05 of both 10.0 (dist=0.04) and 10.08 (dist=0.04)
        # but 10.0 is closer (0.04 < 0.04 is false, they're equal, first wins)
        # Use coord=10.03 instead: dist to A=0.03, dist to B=0.05 -> A wins
        result = find_matching_thread(10.03, [thread_a, thread_b], alpha=0.05)
        assert result is thread_a

    def test_closest_thread_not_first(self):
        """Closest thread should win even if it's not first in the list."""
        thread_a = _make_thread(10.0, fil_id="X_001")
        thread_b = _make_thread(10.08, fil_id="X_002")
        # coord=10.07 -> dist to A=0.07 (out of alpha), dist to B=0.01 -> B wins
        result = find_matching_thread(10.07, [thread_a, thread_b], alpha=0.05)
        assert result is thread_b

    def test_empty_threads_returns_none(self):
        result = find_matching_thread(10.0, [], alpha=0.05)
        assert result is None

    def test_thread_with_small_delta_still_matches_within_alpha(self):
        """Matching uses alpha, not delta. Even if delta is tiny, alpha controls."""
        thread = _make_thread(10.0, delta=0.001)
        result = find_matching_thread(10.04, [thread], alpha=0.05)
        assert result is thread
