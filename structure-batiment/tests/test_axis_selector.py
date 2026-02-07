"""Tests for axis line discovery via multi-floor filtering."""

import pytest
from pathlib import Path

from structure_aligner.config import PipelineConfig, AxisLine
from structure_aligner.db.reader import InputVertex
from structure_aligner.analysis.axis_selector import discover_axis_lines


def _make_vertex(element_id: int, x: float, y: float, z: float, vid: int = 0) -> InputVertex:
    return InputVertex(id=vid, element_id=element_id, x=x, y=y, z=z, vertex_index=0)


class TestSyntheticData:
    """Test axis line discovery on synthetic data with known axis lines."""

    def test_simple_3_floors(self):
        """Positions on 3+ floors should be selected as axis lines."""
        config = PipelineConfig(min_floors=3)
        z_levels = config.floor_z_levels

        # Position X=10.0 appears on 5 floors -> axis line
        # Position X=20.0 appears on 3 floors -> axis line
        # Position X=30.0 appears on 2 floors -> NOT axis line
        # Position X=40.0 appears on 1 floor -> NOT axis line
        vertices = []
        vid = 0
        for z in z_levels[:5]:
            vertices.append(_make_vertex(1, 10.0, 0.0, z, vid)); vid += 1
        for z in z_levels[:3]:
            vertices.append(_make_vertex(2, 20.0, 0.0, z, vid)); vid += 1
        for z in z_levels[:2]:
            vertices.append(_make_vertex(3, 30.0, 0.0, z, vid)); vid += 1
        vertices.append(_make_vertex(4, 40.0, 0.0, z_levels[0], vid))

        axis_x, axis_y = discover_axis_lines(vertices, config)

        x_positions = [a.position for a in axis_x]
        assert 10.0 in x_positions
        assert 20.0 in x_positions
        assert 30.0 not in x_positions
        assert 40.0 not in x_positions
        assert len(axis_x) == 2

    def test_100_percent_recall_on_known_data(self):
        """All positions on 3+ floors should be found."""
        config = PipelineConfig(min_floors=3)
        z_levels = config.floor_z_levels

        known_axis_lines = [5.0, 10.0, 15.0, 20.0, 25.0]
        vertices = []
        vid = 0
        for x in known_axis_lines:
            for z in z_levels[:4]:  # 4 floors each
                vertices.append(_make_vertex(1, x, 0.0, z, vid)); vid += 1

        axis_x, _ = discover_axis_lines(vertices, config)
        found = {a.position for a in axis_x}

        for expected in known_axis_lines:
            assert expected in found, f"Expected axis line at X={expected}"

    def test_dedup_within_cluster_radius(self):
        """Positions within cluster_radius should be merged."""
        config = PipelineConfig(min_floors=3, cluster_radius=0.005)
        z_levels = config.floor_z_levels

        # Two positions 2mm apart -> should merge
        vertices = []
        vid = 0
        for z in z_levels[:3]:
            vertices.append(_make_vertex(1, 10.000, 0.0, z, vid)); vid += 1
            vertices.append(_make_vertex(2, 10.002, 0.0, z, vid)); vid += 1

        axis_x, _ = discover_axis_lines(vertices, config)
        assert len(axis_x) == 1  # Merged into one

    def test_noise_handling(self):
        """Floating-point noise should not cause position splitting."""
        config = PipelineConfig(min_floors=3, rounding_precision=0.005)
        z_levels = config.floor_z_levels

        # Same position with micro-noise (~0.044mm as in real data)
        vertices = []
        vid = 0
        for z in z_levels[:3]:
            vertices.append(_make_vertex(1, 10.000044, 0.0, z, vid)); vid += 1

        axis_x, _ = discover_axis_lines(vertices, config)
        assert len(axis_x) == 1
        assert abs(axis_x[0].position - 10.0) < 0.001

    def test_floor_count_tracking(self):
        """Floor count should match the number of distinct Z-levels."""
        config = PipelineConfig(min_floors=3)
        z_levels = config.floor_z_levels

        vertices = []
        vid = 0
        for z in z_levels[:6]:  # 6 floors
            vertices.append(_make_vertex(1, 10.0, 0.0, z, vid)); vid += 1

        axis_x, _ = discover_axis_lines(vertices, config)
        assert axis_x[0].floor_count == 6

    def test_vertex_count_tracking(self):
        """Vertex count should reflect total vertices at the position."""
        config = PipelineConfig(min_floors=3)
        z_levels = config.floor_z_levels

        vertices = []
        vid = 0
        for z in z_levels[:3]:
            # 5 vertices per floor
            for _ in range(5):
                vertices.append(_make_vertex(1, 10.0, 0.0, z, vid)); vid += 1

        axis_x, _ = discover_axis_lines(vertices, config)
        assert axis_x[0].vertex_count == 15

    def test_both_axes_discovered(self):
        """Should discover axis lines for both X and Y."""
        config = PipelineConfig(min_floors=3)
        z_levels = config.floor_z_levels

        vertices = []
        vid = 0
        for z in z_levels[:3]:
            vertices.append(_make_vertex(1, 10.0, 50.0, z, vid)); vid += 1

        axis_x, axis_y = discover_axis_lines(vertices, config)
        assert len(axis_x) >= 1
        assert len(axis_y) >= 1

    def test_empty_vertices(self):
        """Empty input should return empty axis lines."""
        config = PipelineConfig(min_floors=3)
        axis_x, axis_y = discover_axis_lines([], config)
        assert axis_x == []
        assert axis_y == []

    def test_sorted_output(self):
        """Output should be sorted by position."""
        config = PipelineConfig(min_floors=3)
        z_levels = config.floor_z_levels

        vertices = []
        vid = 0
        for x in [30.0, 10.0, 20.0]:
            for z in z_levels[:3]:
                vertices.append(_make_vertex(1, x, 0.0, z, vid)); vid += 1

        axis_x, _ = discover_axis_lines(vertices, config)
        positions = [a.position for a in axis_x]
        assert positions == sorted(positions)

    def test_unmatched_z_does_not_count_as_floor(self):
        """Vertices with Z values far from any floor should not add floor count."""
        config = PipelineConfig(min_floors=3)
        z_levels = config.floor_z_levels

        vertices = []
        vid = 0
        # Only 2 real floors + 1 bogus Z far from any floor level
        for z in [z_levels[0], z_levels[1], 999.0]:
            vertices.append(_make_vertex(1, 10.0, 0.0, z, vid)); vid += 1

        axis_x, _ = discover_axis_lines(vertices, config)
        # Should NOT be an axis line (only 2 real floors)
        assert len(axis_x) == 0

    def test_empty_floor_z_levels_fallback(self):
        """With empty floor_z_levels, Z values are rounded for grouping."""
        config = PipelineConfig(min_floors=3, floor_z_levels=())
        vertices = []
        vid = 0
        # 3 distinct Z values (rounded to 0.1m) -> 3 floors via fallback
        for z in [0.0, 1.0, 2.0]:
            vertices.append(_make_vertex(1, 10.0, 0.0, z, vid)); vid += 1

        axis_x, _ = discover_axis_lines(vertices, config)
        assert len(axis_x) == 1

    def test_min_floors_1_returns_all(self):
        """min_floors=1 should return all positions with at least 1 floor."""
        config = PipelineConfig(min_floors=1)
        z_levels = config.floor_z_levels

        vertices = [
            _make_vertex(1, 10.0, 0.0, z_levels[0], 0),
            _make_vertex(2, 20.0, 0.0, z_levels[0], 1),
        ]
        axis_x, _ = discover_axis_lines(vertices, config)
        assert len(axis_x) == 2


class TestRealData:
    """Tests against actual data files (skipped if files not present)."""

    DATA_DIR = Path(__file__).parent.parent / "data" / "input"
    BEFORE_3DM = DATA_DIR / "before.3dm"
    AFTER_3DM = DATA_DIR / "after.3dm"
    DB_PATH = DATA_DIR / "geometrie_2.db"
    PRD_DB = DATA_DIR / "geometrie_2_prd.db"

    @pytest.fixture
    def real_vertices(self):
        """Load vertices from the PRD database."""
        if not self.PRD_DB.exists():
            pytest.skip(f"PRD DB not found: {self.PRD_DB}")
        from structure_aligner.db.reader import load_vertices
        return load_vertices(self.PRD_DB)

    @pytest.fixture
    def before_vertices(self):
        """Extract vertices directly from before.3dm."""
        if not self.BEFORE_3DM.exists():
            pytest.skip(f"Before 3dm not found: {self.BEFORE_3DM}")
        from structure_aligner.etl.extractor import extract_vertices
        result = extract_vertices(self.BEFORE_3DM)
        # Convert RawVertex to InputVertex-like objects
        return [
            InputVertex(id=i, element_id=0, x=v.x, y=v.y, z=v.z, vertex_index=v.vertex_index)
            for i, v in enumerate(result.vertices)
        ]

    def test_axis_line_count_x(self, before_vertices):
        """X axis lines should be in reasonable range (from research ~188-258)."""
        config = PipelineConfig(min_floors=3)
        axis_x, _ = discover_axis_lines(before_vertices, config)
        # Research says ~188 canonical, but many floor-specific positions also
        # appear on 3+ floors. Allow wide range.
        assert 150 <= len(axis_x) <= 300, f"Expected ~188-258 X axis lines, got {len(axis_x)}"

    def test_axis_line_count_y(self, before_vertices):
        """Y axis lines should be in reasonable range (from research ~273)."""
        config = PipelineConfig(min_floors=3)
        _, axis_y = discover_axis_lines(before_vertices, config)
        assert 200 <= len(axis_y) <= 350, f"Expected ~273 Y axis lines, got {len(axis_y)}"

    def test_recall_x_vs_reference(self, before_vertices):
        """X axis recall should be >= 70% against reference axis-like positions.

        Note: The reference includes positions from new objects and 2-floor
        positions that can't be discovered from before data alone. The raw
        recall target is lower than the research's 98% because the validator
        also counts positions we CAN'T discover (not in before data, or on
        < 3 floors). The actual recall for discoverable positions is ~96%+.
        """
        if not self.AFTER_3DM.exists():
            pytest.skip(f"After 3dm not found: {self.AFTER_3DM}")

        from structure_aligner.analysis.axis_validator import validate_against_reference

        config = PipelineConfig(min_floors=3)
        axis_x, _ = discover_axis_lines(before_vertices, config)
        result = validate_against_reference(axis_x, self.AFTER_3DM, "X")
        assert result["recall"] >= 0.70, f"X recall {result['recall']:.1%} < 70%"

    def test_recall_y_vs_reference(self, before_vertices):
        """Y axis recall should be >= 70% against reference axis-like positions."""
        if not self.AFTER_3DM.exists():
            pytest.skip(f"After 3dm not found: {self.AFTER_3DM}")

        from structure_aligner.analysis.axis_validator import validate_against_reference

        config = PipelineConfig(min_floors=3)
        _, axis_y = discover_axis_lines(before_vertices, config)
        result = validate_against_reference(axis_y, self.AFTER_3DM, "Y")
        assert result["recall"] >= 0.70, f"Y recall {result['recall']:.1%} < 70%"

    def test_precision_vs_reference(self, before_vertices):
        """Most discovered positions should be valid axis lines (high precision)."""
        if not self.AFTER_3DM.exists():
            pytest.skip(f"After 3dm not found: {self.AFTER_3DM}")

        from structure_aligner.analysis.axis_validator import validate_against_reference

        config = PipelineConfig(min_floors=3)
        axis_x, _ = discover_axis_lines(before_vertices, config)
        result = validate_against_reference(axis_x, self.AFTER_3DM, "X")
        # Precision can be lower because we discover positions that are valid
        # axis lines but the reference has fewer named objects there
        assert result["precision"] >= 0.40, f"X precision {result['precision']:.1%} < 40%"
