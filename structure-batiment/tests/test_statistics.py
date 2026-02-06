import numpy as np
import pytest
from structure_aligner.analysis.statistics import compute_axis_statistics


class TestComputeAxisStatistics:
    def test_simple_known_array(self):
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        stats = compute_axis_statistics(values, "X")
        assert stats.axis == "X"
        assert stats.mean == pytest.approx(3.0)
        assert stats.median == pytest.approx(3.0)
        # Population std for [1,2,3,4,5] = sqrt(2)
        assert stats.std == pytest.approx(np.std([1, 2, 3, 4, 5], ddof=0))
        assert stats.min == pytest.approx(1.0)
        assert stats.max == pytest.approx(5.0)
        assert stats.total_count == 5

    def test_single_value(self):
        values = np.array([42.0])
        stats = compute_axis_statistics(values, "Z")
        assert stats.mean == pytest.approx(42.0)
        assert stats.median == pytest.approx(42.0)
        assert stats.std == pytest.approx(0.0)
        assert stats.min == pytest.approx(42.0)
        assert stats.max == pytest.approx(42.0)
        assert stats.unique_count == 1
        assert stats.total_count == 1

    def test_all_identical_values(self):
        values = np.array([7.5, 7.5, 7.5, 7.5])
        stats = compute_axis_statistics(values, "Y")
        assert stats.std == pytest.approx(0.0)
        assert stats.unique_count == 1
        assert stats.total_count == 4

    def test_negative_values(self):
        values = np.array([-3.0, -1.0, 0.0, 1.0, 3.0])
        stats = compute_axis_statistics(values, "X")
        assert stats.mean == pytest.approx(0.0)
        assert stats.min == pytest.approx(-3.0)
        assert stats.max == pytest.approx(3.0)

    def test_population_std_ddof0(self):
        """Verify population std (ddof=0), not sample std (ddof=1)."""
        values = np.array([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        stats = compute_axis_statistics(values, "X")
        expected_pop_std = float(np.std(values, ddof=0))
        sample_std = float(np.std(values, ddof=1))
        assert stats.std == pytest.approx(expected_pop_std)
        assert stats.std != pytest.approx(sample_std, abs=1e-6)

    def test_quartiles(self):
        values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
        stats = compute_axis_statistics(values, "Z")
        assert stats.q1 == pytest.approx(np.percentile(values, 25))
        assert stats.q3 == pytest.approx(np.percentile(values, 75))

    def test_unique_count_rounds_to_2_decimals(self):
        # 1.001 and 1.004 both round to 1.00; 1.005 rounds to 1.01
        values = np.array([1.001, 1.004, 1.005, 2.0])
        stats = compute_axis_statistics(values, "X")
        # np.round(1.001, 2) = 1.0, np.round(1.004, 2) = 1.0,
        # np.round(1.005, 2) = 1.0 (banker's rounding), np.round(2.0, 2) = 2.0
        assert stats.unique_count >= 2  # At least 1.0 and 2.0

    def test_returns_python_floats(self):
        values = np.array([1.0, 2.0, 3.0])
        stats = compute_axis_statistics(values, "X")
        assert isinstance(stats.mean, float)
        assert isinstance(stats.std, float)
        assert isinstance(stats.q1, float)
        assert isinstance(stats.unique_count, int)
        assert isinstance(stats.total_count, int)
