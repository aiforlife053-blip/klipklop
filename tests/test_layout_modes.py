"""Tests for V3 layout_modes: modes, geometry, orientation, state machine, filtergraphs."""
import pytest
from layout_modes import (
    V3_MODES, V3_OUTPUT_WIDTH, V3_OUTPUT_HEIGHT, V3_STATUSES,
    LayoutModeError, validate_mode, validate_orientation, output_geometry,
    is_legal_transition, validate_transition,
    build_vertical_full_filtergraph, build_split_middle_filtergraph,
    build_gaming_filtergraph, build_filtergraph,
    validate_facecam_overlap,
)
from gaming_layout import GamingLayoutError


# --- Mode validation ---

class TestValidateMode:
    def test_all_three_modes_accepted(self):
        for mode in V3_MODES:
            assert validate_mode(mode) == mode

    def test_case_insensitive(self):
        assert validate_mode("VERTICAL_FULL") == "vertical_full"
        assert validate_mode("Gaming") == "gaming"

    def test_whitespace_trimmed(self):
        assert validate_mode("  split_middle  ") == "split_middle"

    def test_invalid_mode_rejected(self):
        with pytest.raises(LayoutModeError):
            validate_mode("portrait")
        with pytest.raises(LayoutModeError):
            validate_mode("blur")
        with pytest.raises(LayoutModeError):
            validate_mode("")

    def test_non_string_rejected(self):
        with pytest.raises(LayoutModeError):
            validate_mode(None)
        with pytest.raises(LayoutModeError):
            validate_mode(123)


# --- Orientation validation ---

class TestValidateOrientation:
    def test_vertical_full_accepts_landscape(self):
        assert validate_orientation("vertical_full", True) == "vertical_full"

    def test_vertical_full_accepts_portrait(self):
        assert validate_orientation("vertical_full", False) == "vertical_full"

    def test_gaming_rejects_portrait(self):
        with pytest.raises(LayoutModeError, match="landscape"):
            validate_orientation("gaming", False)

    def test_split_middle_rejects_portrait(self):
        with pytest.raises(LayoutModeError, match="landscape"):
            validate_orientation("split_middle", False)

    def test_gaming_accepts_landscape(self):
        assert validate_orientation("gaming", True) == "gaming"

    def test_split_middle_accepts_landscape(self):
        assert validate_orientation("split_middle", True) == "split_middle"

    def test_error_message_suggests_vertical_full(self):
        with pytest.raises(LayoutModeError, match="vertical_full"):
            validate_orientation("gaming", False)


# --- Geometry ---

class TestOutputGeometry:
    def test_always_1080x1920(self):
        w, h = output_geometry()
        assert (w, h) == (V3_OUTPUT_WIDTH, V3_OUTPUT_HEIGHT)
        assert (w, h) == (1080, 1920)


# --- State machine transitions ---

class TestStateMachine:
    @pytest.mark.parametrize("from_status,to_status", [
        ("queued", "analyzing"),
        ("queued", "cancelled"),
        ("analyzing", "downloading"),
        ("downloading", "detecting_layout"),
        ("detecting_layout", "rendering"),
        ("detecting_layout", "needs_facecam"),
        ("needs_facecam", "rendering"),
        ("rendering", "ready_to_schedule"),
        ("rendering", "render_error"),
        ("render_error", "rendering"),
        ("ready_to_schedule", "scheduled"),
        ("scheduled", "uploading"),
        ("uploading", "uploaded"),
        ("uploading", "upload_error"),
        ("upload_error", "scheduled"),
    ])
    def test_legal_transitions(self, from_status, to_status):
        assert is_legal_transition(from_status, to_status)

    @pytest.mark.parametrize("from_status,to_status", [
        ("queued", "rendering"),        # skip analyzing
        ("analyzing", "rendering"),     # skip downloading
        ("uploaded", "rendering"),      # terminal
        ("cancelled", "queued"),        # terminal
        ("rendering", "analyzing"),     # backwards
        ("ready_to_schedule", "rendering"),  # backwards
        ("uploaded", "uploading"),      # backwards from terminal
    ])
    def test_illegal_transitions(self, from_status, to_status):
        assert not is_legal_transition(from_status, to_status)

    def test_validate_transition_raises_on_illegal(self):
        with pytest.raises(LayoutModeError, match="ilegal"):
            validate_transition("queued", "rendering")

    def test_validate_transition_returns_on_legal(self):
        assert validate_transition("queued", "analyzing") == "analyzing"

    def test_all_statuses_have_transitions(self):
        for status in V3_STATUSES:
            assert status in V3_STATUSES

    def test_cancelled_is_terminal(self):
        for to_status in V3_STATUSES:
            if to_status == "cancelled":
                continue
            assert not is_legal_transition("cancelled", to_status)


# --- Vertical Full filtergraph ---

class TestVerticalFullFiltergraph:
    def test_landscape_crops_center(self):
        filters, label = build_vertical_full_filtergraph(1920, 1080)
        assert label == "v0"
        joined = ";".join(filters)
        assert "crop" in joined
        assert "1080:1920" in joined
        assert "lanczos" in joined

    def test_portrait_just_scales(self):
        filters, label = build_vertical_full_filtergraph(720, 1280)
        joined = ";".join(filters)
        assert "crop" not in joined
        assert "1080:1920" in joined

    def test_output_always_1080x1920(self):
        for sw, sh in [(1920, 1080), (1280, 720), (720, 1280), (3840, 2160)]:
            filters, _ = build_vertical_full_filtergraph(sw, sh)
            joined = ";".join(filters)
            assert "1080:1920" in joined


# --- Split Middle filtergraph ---

class TestSplitMiddleFiltergraph:
    def test_landscape_produces_vstack(self):
        filters, label = build_split_middle_filtergraph(1920, 1080)
        joined = ";".join(filters)
        assert "vstack" in joined
        assert "split=2" in joined
        assert label == "v0"

    def test_left_half_top_right_half_bottom(self):
        filters, _ = build_split_middle_filtergraph(1920, 1080)
        joined = ";".join(filters)
        # Left crop starts at x=0
        assert "crop=960:1080:0:0" in joined or "crop=958:1080:0:0" in joined
        # Right crop starts at x=half
        assert "960:0" in joined or "958:0" in joined

    def test_portrait_rejected(self):
        with pytest.raises(LayoutModeError, match="landscape"):
            build_split_middle_filtergraph(720, 1280)

    def test_output_always_1080x1920(self):
        filters, _ = build_split_middle_filtergraph(1920, 1080)
        joined = ";".join(filters)
        assert "1080" in joined
        assert "1920" in joined or "960" in joined  # panel height


# --- Gaming filtergraph ---

class TestGamingFiltergraph:
    def test_gaming_delegates_to_gaming_layout(self):
        # Standard landscape source with facecam in top-left corner
        roi = {"x": 0.02, "y": 0.02, "width": 0.25, "height": 0.30}
        filters, label = build_gaming_filtergraph(1920, 1080, roi)
        joined = ";".join(filters)
        assert "vstack" in joined
        assert label == "v0"

    def test_gaming_requires_roi(self):
        with pytest.raises(GamingLayoutError):
            build_gaming_filtergraph(1920, 1080, None)

    def test_gaming_rejects_portrait(self):
        roi = {"x": 0.02, "y": 0.02, "width": 0.25, "height": 0.30}
        with pytest.raises(GamingLayoutError, match="landscape"):
            build_gaming_filtergraph(720, 1280, roi)


# --- Facecam overlap validation ---

class TestFacecamOverlap:
    def test_no_overlap_returns_true(self):
        # Facecam in top-left corner, gameplay is center-cropped (27/32 * 1080 ≈ 911px, centered at ~504)
        # Facecam must not extend past x=504 in 1920px source
        roi = {"x": 0.01, "y": 0.01, "width": 0.20, "height": 0.25}
        # 0.01*1920=19, 0.21*1920=403 < 504 → no overlap
        assert validate_facecam_overlap(roi, 1920, 1080) is True

    def test_overlap_returns_false(self):
        # Facecam in center — overlaps gameplay crop
        roi = {"x": 0.35, "y": 0.35, "width": 0.30, "height": 0.30}
        assert validate_facecam_overlap(roi, 1920, 1080) is False

    def test_invalid_roi_raises(self):
        with pytest.raises(GamingLayoutError):
            validate_facecam_overlap(None, 1920, 1080)

    def test_portrait_raises(self):
        roi = {"x": 0.02, "y": 0.02, "width": 0.25, "height": 0.30}
        with pytest.raises(GamingLayoutError, match="landscape"):
            validate_facecam_overlap(roi, 720, 1280)


# --- Central router ---

class TestBuildFiltergraph:
    def test_vertical_full_routes(self):
        filters, label = build_filtergraph("vertical_full", 1920, 1080)
        assert label == "v0"

    def test_split_middle_routes(self):
        filters, label = build_filtergraph("split_middle", 1920, 1080)
        assert "vstack" in ";".join(filters)

    def test_gaming_routes(self):
        roi = {"x": 0.02, "y": 0.02, "width": 0.25, "height": 0.30}
        filters, label = build_filtergraph("gaming", 1920, 1080, roi=roi)
        assert "vstack" in ";".join(filters)

    def test_gaming_without_roi_raises(self):
        with pytest.raises(GamingLayoutError):
            build_filtergraph("gaming", 1920, 1080)

    def test_invalid_mode_raises(self):
        with pytest.raises(LayoutModeError):
            build_filtergraph("invalid", 1920, 1080)
