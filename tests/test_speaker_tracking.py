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
        chosen, conf, hold = choose_speaker(candidates, None, 0)
        assert chosen == 1
        assert conf == 0.8

    def test_holds_current_during_hold_window(self):
        candidates = [
            {"id": 0, "score": 0.7, "crop_x": 10},
            {"id": 1, "score": 0.9, "crop_x": 50},
        ]
        chosen, conf, hold = choose_speaker(candidates, 0, hold_frames_left=10)
        assert chosen == 0
        assert hold == 9

    def test_requires_margin_to_switch(self):
        candidates = [
            {"id": 0, "score": 0.70, "crop_x": 10},
            {"id": 1, "score": 0.75, "crop_x": 50},  # margin 0.05 < 0.12
        ]
        chosen, _, _ = choose_speaker(candidates, 0, hold_frames_left=0)
        assert chosen == 0

    def test_switches_with_margin_after_hold(self):
        candidates = [
            {"id": 0, "score": 0.50, "crop_x": 10, "mouth": 0.05},
            {"id": 1, "score": 0.90, "crop_x": 50, "mouth": 0.40},
        ]
        chosen, conf, hold = choose_speaker(candidates, 0, hold_frames_left=0)
        assert chosen == 1
        assert conf == 0.90

    def test_empty_keeps_current(self):
        chosen, conf, hold = choose_speaker([], 3, 5)
        assert chosen == 3
        assert conf == 0.0
        assert hold == 4

    def test_low_confidence_keeps_current(self):
        candidates = [{"id": 1, "score": 0.1, "crop_x": 20}]
        chosen, _, _ = choose_speaker(candidates, 0, 0)
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


class TestConstants:
    def test_versions_and_policy(self):
        assert TRACKER_VERSION.startswith("active-speaker-")
        assert HOLD_SECONDS == 2.0
        assert SMOOTH_SECONDS == 0.0


def test_vertical_full_uses_active_speaker_hard_cuts():
    tracker, layouts = tracking_strategy()
    assert tracker is track_crop_positions
    assert layouts is False
