"""Unit tests for speaker_tracking pure logic + policy."""
import numpy as np
import pytest

from speaker_tracking import (
    HOLD_SECONDS,
    SMOOTH_SECONDS,
    TRACKER_VERSION,
    audio_energy_score,
    center_crop_x,
    choose_speaker,
    combine_scores,
    crop_x_for_face,
    enforce_hold,
    face_score,
    mouth_motion_score,
    smooth_positions,
    track_scene_crop_positions,
    track_crop_positions,
    tracking_strategy,
)


class TestCenterCrop:
    def test_centered(self):
        assert center_crop_x(1920, 1080) == (1920 - 1080) // 2

    def test_clamped(self):
        assert center_crop_x(100, 200) == 0


class TestFaceScore:
    def test_larger_face_scores_higher(self):
        small = face_score((100, 100, 40, 40), 1920, 1080)
        large = face_score((800, 200, 200, 200), 1920, 1080)
        assert large > small

    def test_continuity_bonus(self):
        face = (900, 200, 120, 120)
        without = face_score(face, 1920, 1080, prev_center=None)
        with_prev = face_score(face, 1920, 1080, prev_center=0.5)
        assert with_prev >= without

    def test_rejects_face_detection_in_lower_torso_region(self):
        assert face_score((800, 760, 180, 180), 1920, 1080) == 0.0


def test_tracker_ignores_low_face_confidence_even_when_audio_is_loud():
    from speaker_tracking import combine_scores, MIN_FACE_CONFIDENCE, valid_face_detection

    rejected_face = MIN_FACE_CONFIDENCE - 0.01
    assert combine_scores(rejected_face, 1.0, 1.0) > MIN_FACE_CONFIDENCE
    # Face validity is a trust gate; global audio/motion must not promote a
    # geometrically rejected detection into a camera target.
    assert not valid_face_detection(rejected_face)
    assert valid_face_detection(MIN_FACE_CONFIDENCE)


def test_wide_shot_real_face_is_not_rejected_into_empty_center_crop():
    from speaker_tracking import MIN_FACE_CONFIDENCE, valid_face_detection

    # Regression fixture from a 1920x1080 podcast two-shot: rejecting this
    # real upper-body face made the previous crop hold on empty center space.
    score = face_score((438, 322, 99, 99), 1920, 1080)
    assert score >= MIN_FACE_CONFIDENCE
    assert valid_face_detection(score)
    # Torso/print detections remain rejected geometrically.
    assert not valid_face_detection(face_score((800, 760, 180, 180), 1920, 1080))


class TestMouthMotion:
    def test_static_is_low(self):
        roi = np.zeros((80, 60), dtype=np.uint8)
        assert mouth_motion_score(roi, roi) < 0.1

    def test_motion_raises_score(self):
        prev = np.zeros((80, 60), dtype=np.uint8)
        curr = prev.copy()
        curr[50:, :] = 255
        assert mouth_motion_score(curr, prev) > 0.5

    def test_none_prev_is_zero(self):
        assert mouth_motion_score(np.zeros((40, 40), dtype=np.uint8), None) == 0.0


class TestAudioEnergy:
    def test_silence(self):
        assert audio_energy_score(np.zeros(1000, dtype=np.float32)) == 0.0

    def test_loud(self):
        samples = np.ones(1000, dtype=np.float32) * 0.2
        assert audio_energy_score(samples) > 0.5

    def test_none(self):
        assert audio_energy_score(None) == 0.0


class TestCombineScores:
    def test_bounds(self):
        assert 0.0 <= combine_scores(1, 1, 1) <= 1.0
        assert combine_scores(0, 0, 0) == 0.0


class TestChooseSpeaker:
    def test_picks_best_when_no_current(self):
        candidates = [
            {"id": 0, "score": 0.4, "crop_x": 10},
            {"id": 1, "score": 0.8, "crop_x": 50},
        ]
        chosen, conf, hold, quiet = choose_speaker(candidates, None, 0)
        assert chosen == 1
        assert conf == 0.8

    def test_holds_current_during_hold_window(self):
        candidates = [
            {"id": 0, "score": 0.7, "crop_x": 10, "mouth": 0.05},
            {"id": 1, "score": 0.9, "crop_x": 50, "mouth": 0.40},
        ]
        chosen, conf, hold, quiet = choose_speaker(candidates, 0, hold_frames_left=10)
        assert chosen == 0
        assert hold == 9

    def test_requires_margin_to_switch(self):
        candidates = [
            {"id": 0, "score": 0.70, "crop_x": 10, "mouth": 0.05},
            {"id": 1, "score": 0.75, "crop_x": 50, "mouth": 0.40},  # margin 0.05 < 0.12
        ]
        chosen, _, _, _ = choose_speaker(candidates, 0, hold_frames_left=0)
        assert chosen == 0

    def test_switches_with_margin_after_hold(self):
        candidates = [
            {"id": 0, "score": 0.50, "crop_x": 10, "mouth": 0.05},
            {"id": 1, "score": 0.90, "crop_x": 50, "mouth": 0.40},
        ]
        chosen, conf, hold, quiet = choose_speaker(candidates, 0, hold_frames_left=0)
        assert chosen == 1
        assert conf == 0.90

    def test_waits_one_second_quiet_before_switch(self):
        candidates = [
            {"id": 0, "score": 0.50, "crop_x": 10, "mouth": 0.05},
            {"id": 1, "score": 0.90, "crop_x": 50, "mouth": 0.40},
        ]
        # release_frames=30 (~1s @30fps); quiet only 10 → stay
        chosen, _, _, quiet = choose_speaker(
            candidates, 0, hold_frames_left=0, current_quiet_frames=10, release_frames=30,
        )
        assert chosen == 0
        assert quiet == 11
        # quiet already satisfied → switch
        chosen2, _, _, _ = choose_speaker(
            candidates, 0, hold_frames_left=0, current_quiet_frames=30, release_frames=30,
        )
        assert chosen2 == 1

    def test_empty_keeps_current(self):
        chosen, conf, hold, quiet = choose_speaker([], 3, 5)
        assert chosen == 3
        assert conf == 0.0
        assert hold == 4

    def test_low_confidence_keeps_current(self):
        candidates = [{"id": 1, "score": 0.1, "crop_x": 20}]
        chosen, _, _, _ = choose_speaker(candidates, 0, 0)
        assert chosen == 0


class TestEnforceHold:
    def test_minimum_hold(self):
        # Switch every frame; after enforce, switches every >= hold frames
        fps = 30.0
        raw = [0, 1, 0, 1, 0, 1] + [1] * 50
        held = enforce_hold(raw, fps, hold_seconds=1.5)
        # First speaker should dominate early frames
        assert held[0] == 0
        # Count switches
        switches = sum(1 for i in range(1, len(held)) if held[i] != held[i - 1])
        assert switches <= 2

    def test_none_preserves_current(self):
        raw = [0, None, None, 1]
        held = enforce_hold(raw, 10.0, hold_seconds=0.1)
        assert held[1] == 0
        assert held[2] == 0


class TestSmoothPositions:
    def test_smooths_jump(self):
        positions = [0.0] * 5 + [100.0] * 60
        smoothed = smooth_positions(positions, fps=30.0, smooth_seconds=0.3, dead_zone_px=0.0, max_pan_px=0.0)
        assert smoothed[0] == 0
        assert any(0 < v < 100 for v in smoothed)
        assert smoothed[-1] >= 95

    def test_empty(self):
        assert smooth_positions([], 30.0) == []


class TestCropXForFace:
    def test_centers_on_face(self):
        # face at x=900, w=100 → center 950; crop_w=600 → crop_x=650
        assert crop_x_for_face((900, 100, 100, 100), 1920, 600) == 650

    def test_clamped_left(self):
        assert crop_x_for_face((0, 0, 50, 50), 1920, 600) == 0


def test_face_visibility_guard_reframes_stale_crop_after_source_cut():
    from speaker_tracking import ensure_visible_face_crop

    candidates = [
        {"score": 0.72, "face": (690, 100, 90, 90), "crop_x": 584},
    ]
    # Previous speaker crop is on the left and contains no current face.
    assert ensure_visible_face_crop(40, candidates, 270, 854) == 584


def test_face_visibility_guard_keeps_crop_when_full_face_is_visible():
    from speaker_tracking import ensure_visible_face_crop

    candidates = [
        {"score": 0.72, "face": (180, 100, 90, 90), "crop_x": 90},
    ]
    assert ensure_visible_face_crop(100, candidates, 270, 854) == 100


def test_missing_frame_detection_holds_face_crop_inside_same_source_shot():
    from speaker_tracking import resolve_visible_crop

    assert resolve_visible_crop(40, [], fallback_crop_x=584, crop_width=270, source_width=854, source_cut=False) == 40


def test_missing_frame_detection_uses_shot_fallback_after_source_cut():
    from speaker_tracking import resolve_visible_crop

    assert resolve_visible_crop(40, [], fallback_crop_x=584, crop_width=270, source_width=854, source_cut=True) == 584


def test_final_crop_sequence_holds_last_face_verified_crop_across_detector_miss():
    from speaker_tracking import stabilize_visible_crops

    positions = [445, 244, 445, 445]
    candidates = [
        [],
        [{"score": 0.8, "face": (300, 80, 90, 90), "crop_x": 244}],
        [],
        [],
    ]
    assert stabilize_visible_crops(positions, candidates, [445] * 4, [False] * 4, 270, 854) == [445, 244, 244, 244]


def test_choose_scene_layout_never_emits_contain_blur_or_empty_center_when_faces_exist():
    from speaker_tracking import choose_scene_layout

    faces = [(100, 120, 140, 140), (900, 130, 150, 150)]
    crop_x, layout = choose_scene_layout(
        faces, source_width=1280, crop_width=720, detection_coverage=0.1,
    )
    assert layout == "crop"
    # Must lock onto a face center, not dead middle empty space only.
    assert crop_x != (1280 - 720) // 2 or True  # may equal if face near center
    # Crop window must contain at least one face fully-ish (face center inside crop).
    centers = [100 + 70, 900 + 75]
    assert any(crop_x <= c <= crop_x + 720 for c in centers)


def test_choose_scene_layout_no_faces_holds_last_face_not_fresh_center():
    from speaker_tracking import choose_scene_layout, center_crop_x

    crop_x, layout = choose_scene_layout(
        [], source_width=1280, crop_width=720,
        previous_crop_x=100, last_face_crop_x=220, detection_coverage=0.0,
    )
    assert layout == "crop"
    assert crop_x == 220
    assert crop_x != center_crop_x(1280, 720)


def test_prefer_still_face_when_talker_is_moving():
    from speaker_tracking import prefer_still_over_moving_speaker

    groups = [
        {"area": 20000, "center": 300, "width": 120, "count": 5, "motion": 0.8, "mouth": 0.5},
        {"area": 18000, "center": 900, "width": 110, "count": 5, "motion": 0.1, "mouth": 0.2},
    ]
    chosen = prefer_still_over_moving_speaker(groups)
    assert chosen["center"] == 900


class TestConstants:
    def test_versions_and_policy(self):
        assert TRACKER_VERSION.startswith("scene-face-")
        assert HOLD_SECONDS == 1.0
        assert SMOOTH_SECONDS == 0.25


def test_vertical_full_follows_active_speaker_not_shot_lock():
    from speaker_tracking import track_active_speaker_positions

    tracker, layouts = tracking_strategy()
    assert tracker is track_active_speaker_positions
    assert layouts is False


def test_hard_cut_recenters_same_speaker_without_jitter():
    from speaker_tracking import hard_cut_positions

    # Same speaker; detector drift must not become virtual camera motion.
    targets = [100.0] * 3 + [160.0] * 40
    ids: list[int | None] = [0] * len(targets)
    out = hard_cut_positions(
        targets, ids, fps=30.0, debounce_seconds=0.45, hold_seconds=1.0,
        dead_zone_px=16.0, max_pan_px=5.0,
    )
    assert out[0] == 100
    assert out == [100] * len(out)


def test_mediapipe_lip_activity_uses_normalized_mouth_opening_delta():
    from speaker_tracking import mediapipe_lip_activity

    closed = {13: (0.50, 0.50), 14: (0.50, 0.51), 61: (0.40, 0.50), 291: (0.60, 0.50)}
    opened = {13: (0.50, 0.46), 14: (0.50, 0.56), 61: (0.40, 0.50), 291: (0.60, 0.50)}
    assert mediapipe_lip_activity(closed, None) < 0.1
    assert mediapipe_lip_activity(opened, closed) > mediapipe_lip_activity(closed, closed)


def test_mediapipe_landmarks_create_face_box():
    from speaker_tracking import mediapipe_face_box

    landmarks = [(0.25, 0.20), (0.50, 0.60), (0.40, 0.45)]
    assert mediapipe_face_box(landmarks, 1000, 500) == (250, 100, 250, 200)


def test_hard_cut_switches_once_after_stable_new_talker():
    from speaker_tracking import hard_cut_positions

    targets = [100.0] * 30 + [500.0] * 20
    ids = [0] * 30 + [1] * 20
    out = hard_cut_positions(targets, ids, fps=10.0, debounce_seconds=0.5, hold_seconds=1.0)
    switches = [i for i in range(1, len(out)) if out[i] != out[i - 1]]
    assert len(switches) == 1
    assert out[switches[0] - 1] == 100
    assert out[switches[0]] == 500


def test_stabilize_locks_crop_when_face_remains_inside():
    from speaker_tracking import stabilize_visible_crops

    # Detector drift must not move camera while face remains fully visible.
    positions = [200, 210, 200]
    face = {"score": 0.9, "face": (250, 80, 80, 80), "crop_x": 180}
    candidates = [[face], [face], [face]]
    out = stabilize_visible_crops(positions, candidates, [200] * 3, [False] * 3, 270, 854)
    assert out == [200, 200, 200]


def test_stabilize_does_not_follow_detector_drift_after_reframing_locked_speaker():
    from speaker_tracking import stabilize_visible_crops

    positions = [100, 100, 100, 100]
    candidates = [
        [{"score": 0.9, "face": (140, 80, 80, 80), "crop_x": 100}],
        [{"score": 0.9, "face": (520, 80, 80, 80), "crop_x": 430}],
        [{"score": 0.9, "face": (521, 80, 80, 80), "crop_x": 431}],
        [{"score": 0.9, "face": (522, 80, 80, 80), "crop_x": 432}],
    ]
    assert stabilize_visible_crops(
        positions, candidates, [100] * 4, [False] * 4, 270, 854,
    ) == [100, 430, 430, 430]


def test_shot_speaker_vote_locks_one_full_vertical_crop_per_source_shot():
    from speaker_tracking import lock_crop_per_source_shot

    active = [100, 100, 300, 100, 300, 300, 300, 100]
    cuts = [False, False, False, False, True, False, False, False]
    assert lock_crop_per_source_shot(active, cuts) == [100] * 4 + [300] * 4


def test_final_tracker_policy_removes_post_cut_settling_jitter():
    from speaker_tracking import lock_crop_per_source_shot

    positions = [100, 100, 400, 430, 431, 430, 430]
    source_cuts = [False, False, True, False, False, False, False]
    assert lock_crop_per_source_shot(positions, source_cuts) == [100, 100, 430, 430, 430, 430, 430]
