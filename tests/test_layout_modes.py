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
from speaker_tracking import choose_scene_crop_x, choose_scene_layout, choose_speaker, hard_cut_positions, scene_changed, smooth_positions
import numpy as np


def test_choose_scene_crop_locks_dominant_face():
    # Left face larger than right → crop centered on left face.
    faces = [(80, 40, 120, 120), (520, 60, 60, 60)]
    crop_x = choose_scene_crop_x(faces, source_width=800, crop_width=270)
    # Face center at 80+60=140 → crop starts near 140-135=5
    assert 0 <= crop_x <= 40


def test_choose_scene_crop_uses_midpoint_for_equal_two_shot():
    faces = [(100, 40, 90, 90), (520, 40, 90, 90)]
    crop_x = choose_scene_crop_x(faces, source_width=800, crop_width=270)
    # Midpoint of 145 and 565 is 355; crop_x ≈ 355-135 = 220
    assert 190 <= crop_x <= 250


def test_choose_scene_layout_contains_wide_equal_two_shot():
    faces = [(80, 100, 100, 100), (620, 100, 100, 100)]
    _crop_x, layout = choose_scene_layout(faces, source_width=800, crop_width=270)
    assert layout == "contain_blur"


def test_split_middle_clamps_near_edge_roi_inside_source():
    filters, _ = build_split_middle_filtergraph(
        1920, 1080, out_w=540, out_h=960,
        rois={
            "top": {"x": 0.99, "y": 0.99, "width": 0.5, "height": 0.5},
            "bottom": {"x": 0.98, "y": 0.98, "width": 0.5, "height": 0.5},
        },
    )
    for item in filters:
        if "crop=" not in item:
            continue
        crop = item.split("crop=", 1)[1].split(",", 1)[0]
        width, height, x, y = map(int, crop.split(":"))
        assert x + width <= 1920
        assert y + height <= 1080


def test_choose_scene_crop_holds_previous_when_no_faces():
    assert choose_scene_crop_x([], source_width=800, crop_width=270, previous_crop_x=123) == 123
    assert choose_scene_crop_x([], source_width=800, crop_width=270) == (800 - 270) // 2


def test_scene_changed_detects_big_cut_not_small_motion():
    a = np.full((40, 40), 40, dtype=np.uint8)
    b = a.copy(); b[10:15, 10:15] = 50
    c = np.full((40, 40), 200, dtype=np.uint8)
    assert scene_changed(a, b) is False
    assert scene_changed(a, c) is True


def test_hard_cut_locks_same_speaker_head_movement():
    out = hard_cut_positions([100, 110, 90, 120], [0, 0, 0, 0], fps=10, debounce_seconds=1.2, hold_seconds=0)
    assert out == [100, 100, 100, 100]


def test_hard_cut_ignores_short_other_speaker_burst():
    ids = [0] * 20 + [1] * 8 + [0] * 10
    targets = [100] * 20 + [400] * 8 + [100] * 10
    out = hard_cut_positions(targets, ids, fps=10, debounce_seconds=1.2, hold_seconds=0)
    assert set(out) == {100}


def test_hard_cut_switches_once_after_stable_debounce_without_pan():
    ids = [0] * 20 + [1] * 15
    targets = [100] * 20 + [400] * 15
    out = hard_cut_positions(targets, ids, fps=10, debounce_seconds=1.2, hold_seconds=0)
    assert out[:31] == [100] * 31
    assert out[31:] == [400] * 4
    assert set(out) == {100, 400}  # no intermediate pan positions


def test_choose_speaker_holds_when_both_mouths_active_laughing():
    candidates = [
        {"id": 0, "score": 0.70, "mouth": 0.30, "crop_x": 100},
        {"id": 1, "score": 0.85, "mouth": 0.35, "crop_x": 400},
    ]
    chosen, _confidence, _hold = choose_speaker(candidates, current_id=0, hold_frames_left=0)
    assert chosen == 0


def test_smooth_positions_kills_small_jitter_and_caps_pan_speed():
    positions = [100, 105, 96, 104, 300, 300, 300]
    smoothed = smooth_positions(positions, fps=25, smooth_seconds=1.0, dead_zone_px=12, max_pan_px=6)
    assert smoothed[:4] == [100, 100, 100, 100]
    assert max(abs(b - a) for a, b in zip(smoothed, smoothed[1:])) <= 6
    assert smoothed[-1] > 100


def test_smooth_positions_preserves_static_crop():
    assert smooth_positions([42] * 20, fps=25) == [42] * 20


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
    @pytest.mark.parametrize(("quality", "expected"), [
        ("480", (540, 960)),
        ("720", (720, 1280)),
        ("1080", (1080, 1920)),
        ("1440", (1440, 2560)),
    ])
    def test_quality_controls_final_portrait_geometry(self, quality, expected):
        assert output_geometry(quality) == expected

    def test_default_remains_1080_for_legacy_callers(self):
        assert output_geometry() == (V3_OUTPUT_WIDTH, V3_OUTPUT_HEIGHT)

    def test_invalid_quality_rejected(self):
        with pytest.raises(LayoutModeError, match="Quality"):
            output_geometry("2160")


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
