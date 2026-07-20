"""Vertical Full crop: active-speaker face crop with hard cuts.

Policy (camera-first, full-frame only):
- Follow the talking face; center crop on that face.
- After a speaker switch, hold ~1s before another switch (anti-hunt).
- New speaker must lead mouth activity briefly (debounce), then cut.
- If nobody is clearly talking, lock onto any credible face (never empty B-roll).
- Missing face → hold last known face crop (never re-center on pots/walls).
- Never emit contain_blur / letterbox for vertical_full.
- Never block/fail render when crop is imperfect.
"""

from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


def extract_audio_energy(source_path: str, fps: float, frame_count: int, sample_rate: int = 16000) -> list[float]:
    """Decode mono PCM with FFmpeg and return normalized RMS per video frame.

    Audio is global, so it acts as speech-activity confidence while mouth motion
    distinguishes speakers. Missing FFmpeg/audio degrades to zeros.
    """
    if fps <= 0 or frame_count <= 0:
        return []
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return [0.0] * frame_count
    try:
        result = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(source_path), "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "pipe:1"],
            capture_output=True,
            timeout=max(30, int(frame_count / fps) * 2),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return [0.0] * frame_count
    if result.returncode != 0 or not result.stdout:
        return [0.0] * frame_count
    samples = np.frombuffer(result.stdout, dtype="<f4")
    per_frame = sample_rate / fps
    energies = []
    for frame_index in range(frame_count):
        start = int(frame_index * per_frame)
        end = min(samples.size, max(start + 1, int((frame_index + 1) * per_frame)))
        energies.append(audio_energy_score(samples[start:end]) if start < samples.size else 0.0)
    return energies


TRACKER_VERSION = "scene-face-v4-mediapipe-shot-lock"
# Stay on current speaker ~1s after cut, then allow switch to next talker.
HOLD_SECONDS = 1.0
SMOOTH_SECONDS = 0.25
SWITCH_MARGIN = 0.12
MIN_FACE_CONFIDENCE = 0.25
# New talker must lead continuously this long before hard-cut.
SWITCH_DEBOUNCE_SECONDS = 0.45


def tracking_strategy():
    """Vertical Full follows active speaker with full-frame face crops."""
    return track_active_speaker_positions, False


MOUTH_ACTIVE_THRESHOLD = 0.14
MOUTH_LEAD_MARGIN = 0.04
# Current speaker must be quiet this long before we leave them for a new talker.
SPEAKER_RELEASE_SECONDS = 1.0
DEAD_ZONE_PX = 16.0
MAX_PAN_PX_PER_FRAME = 5.0
SCENE_DIFF_THRESHOLD = 0.12
MIN_SHOT_SECONDS = 0.7
FACE_SAMPLE_PER_SHOT = 5
DOMINANT_FACE_RATIO = 1.45


def valid_face_detection(score: float, min_confidence: float = MIN_FACE_CONFIDENCE) -> bool:
    """Only geometrically credible faces may become camera targets."""
    return float(score) >= float(min_confidence)


def center_crop_x(source_width: int, crop_width: int) -> int:
    crop_width = max(1, min(crop_width, source_width))
    return max(0, min((source_width - crop_width) // 2, source_width - crop_width))


def face_score(face, source_width: int, source_height: int, prev_center=None) -> float:
    """Score a face box (x, y, w, h) for speaker likelihood."""
    x, y, w, h = face
    area = (w * h) / max(1.0, source_width * source_height)
    # Prefer larger faces (closer to camera / primary subject)
    size_score = min(1.0, area / 0.08)
    # Prefer faces in upper half (typical talking-head framing)
    cy = (y + h / 2) / max(1.0, source_height)
    # Reject printed/decorative face false positives around torso/table level.
    if cy > 0.72:
        return 0.0
    vertical_score = max(0.0, 1.0 - abs(cy - 0.35) / 0.5)
    # Temporal continuity bonus
    continuity = 0.0
    if prev_center is not None:
        cx = (x + w / 2) / max(1.0, source_width)
        dist = abs(cx - prev_center)
        continuity = max(0.0, 1.0 - dist / 0.25)
    return 0.55 * size_score + 0.25 * vertical_score + 0.20 * continuity


def mouth_motion_score(gray_roi: np.ndarray, prev_gray_roi: np.ndarray | None) -> float:
    """Estimate mouth activity from lower-third face ROI mean absolute diff."""
    if prev_gray_roi is None or gray_roi is None or gray_roi.size == 0:
        return 0.0
    if prev_gray_roi.shape != gray_roi.shape:
        return 0.0
    h = gray_roi.shape[0]
    mouth = gray_roi[int(h * 0.55):, :]
    prev_mouth = prev_gray_roi[int(h * 0.55):, :]
    if mouth.size == 0 or prev_mouth.size == 0:
        return 0.0
    mad = float(np.mean(np.abs(mouth.astype(np.float32) - prev_mouth.astype(np.float32))))
    return max(0.0, min(1.0, mad / 18.0))


def mediapipe_face_box(landmarks: list[tuple[float, float]], frame_width: int, frame_height: int):
    """Convert normalized MediaPipe landmarks to a clamped pixel face box."""
    if not landmarks or frame_width <= 0 or frame_height <= 0:
        return None
    xs = [max(0.0, min(1.0, float(point[0]))) for point in landmarks]
    ys = [max(0.0, min(1.0, float(point[1]))) for point in landmarks]
    left, right = int(min(xs) * frame_width), int(max(xs) * frame_width)
    top, bottom = int(min(ys) * frame_height), int(max(ys) * frame_height)
    return left, top, max(1, right - left), max(1, bottom - top)


def mediapipe_lip_activity(landmarks: dict[int, tuple[float, float]], previous=None) -> float:
    """Score normalized mouth opening and frame-to-frame lip movement."""
    required = (13, 14, 61, 291)
    if not all(index in landmarks for index in required):
        return 0.0
    upper, lower = landmarks[13], landmarks[14]
    left, right = landmarks[61], landmarks[291]
    width = math.hypot(right[0] - left[0], right[1] - left[1])
    if width <= 1e-6:
        return 0.0
    opening = math.hypot(lower[0] - upper[0], lower[1] - upper[1]) / width
    movement = 0.0
    if previous and all(index in previous for index in required):
        prev_upper, prev_lower = previous[13], previous[14]
        prev_left, prev_right = previous[61], previous[291]
        prev_width = math.hypot(prev_right[0] - prev_left[0], prev_right[1] - prev_left[1])
        if prev_width > 1e-6:
            prev_opening = math.hypot(
                prev_lower[0] - prev_upper[0], prev_lower[1] - prev_upper[1]
            ) / prev_width
            movement = abs(opening - prev_opening)
    return max(0.0, min(1.0, opening * 0.4 + movement * 2.4))


def audio_energy_score(samples: np.ndarray | None) -> float:
    """Normalize short-window RMS energy into 0..1."""
    if samples is None or samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))))
    return max(0.0, min(1.0, rms / 0.12))


def combine_scores(face: float, mouth: float, audio: float) -> float:
    return max(0.0, min(1.0, 0.45 * face + 0.35 * mouth + 0.20 * audio))


def hard_cut_positions(
    targets: list[float],
    speaker_ids: list[int | None],
    fps: float,
    debounce_seconds: float = SWITCH_DEBOUNCE_SECONDS,
    hold_seconds: float = HOLD_SECONDS,
    dead_zone_px: float = DEAD_ZONE_PX,
    max_pan_px: float = MAX_PAN_PX_PER_FRAME,
) -> list[int]:
    """Hard-cut on speaker switch; gentle re-center while same speaker.

    - New speaker after debounce+hold → snap crop to that frame's face center.
    - Same speaker → ease toward latest face center (dead-zone + pan cap) so
      talker stays mid-frame without micro-shake.
    - None / ambiguous → hold previous crop.
    """
    if not targets:
        return []
    n = len(targets)
    if n != len(speaker_ids):
        speaker_ids = list(speaker_ids[:n]) + [None] * max(0, n - len(speaker_ids))

    debounce_frames = max(1, int(round(fps * debounce_seconds))) if fps > 0 else 1
    hold_frames = max(1, int(round(fps * hold_seconds))) if fps > 0 else 1

    current_id = next((sid for sid in speaker_ids if sid is not None), None)
    current_crop = float(targets[0])
    for sid, target in zip(speaker_ids, targets):
        if current_id is not None and sid == current_id:
            current_crop = float(target)
            break

    out: list[int] = []
    candidate_id: int | None = None
    candidate_streak = 0
    held = 0

    for sid, target in zip(speaker_ids, targets):
        target = float(target)

        if current_id is None and sid is not None:
            current_id = sid
            current_crop = target
            held = 1
            candidate_id = None
            candidate_streak = 0
            out.append(int(round(current_crop)))
            continue

        if sid is None or sid == current_id:
            # Lock crop while speaker identity is unchanged. Detector drift must
            # not become virtual camera motion.
            held += 1
            candidate_id = None
            candidate_streak = 0
            out.append(int(round(current_crop)))
            continue

        # Different speaker proposed.
        if held < hold_frames:
            held += 1
            candidate_id = None
            candidate_streak = 0
            out.append(int(round(current_crop)))
            continue

        if candidate_id != sid:
            candidate_id = sid
            candidate_streak = 1
        else:
            candidate_streak += 1

        if candidate_streak >= debounce_frames:
            current_id = sid
            current_crop = target  # snap once onto new talker's face center
            held = 1
            candidate_id = None
            candidate_streak = 0
        else:
            held += 1

        out.append(int(round(current_crop)))

    return out


def smooth_positions(
    positions: list[float],
    fps: float,
    smooth_seconds: float = SMOOTH_SECONDS,
    dead_zone_px: float = DEAD_ZONE_PX,
    max_pan_px: float = MAX_PAN_PX_PER_FRAME,
) -> list[int]:
    """Ease crop x; ignore small noise, hard-cap pan speed to kill shake."""
    if not positions:
        return []
    alpha = 1.0 if fps <= 0 else min(1.0, 1.0 / max(1.0, fps * smooth_seconds))
    current = float(positions[0])
    smoothed = [current]
    for value in positions[1:]:
        target = float(value)
        delta = target - current
        if abs(delta) <= dead_zone_px:
            target = current
            delta = 0.0
        eased = current + (target - current) * alpha
        step = eased - current
        if max_pan_px > 0:
            if step > max_pan_px:
                step = max_pan_px
            elif step < -max_pan_px:
                step = -max_pan_px
        current = current + step
        smoothed.append(current)
    return [int(round(value)) for value in smoothed]


def enforce_hold(
    raw_ids: list[int | None],
    fps: float,
    hold_seconds: float = HOLD_SECONDS,
) -> list[int | None]:
    """Post-process speaker ids so switches respect minimum hold duration."""
    if not raw_ids:
        return []
    hold_frames = max(1, int(round(fps * hold_seconds))) if fps > 0 else 1
    result = []
    current = raw_ids[0]
    held = 0
    for speaker_id in raw_ids:
        if speaker_id == current or speaker_id is None:
            result.append(current)
            held += 1
            continue
        if held < hold_frames:
            result.append(current)
            held += 1
            continue
        current = speaker_id
        held = 1
        result.append(current)
    return result


def crop_x_for_face(face, source_width: int, crop_width: int) -> int:
    """Center the crop window on the face (speaker in middle of frame)."""
    x, _y, w, _h = face
    center = x + w / 2
    crop_x = int(round(center - crop_width / 2))
    return max(0, min(crop_x, source_width - crop_width))


def choose_speaker(
    candidates: list[dict],
    current_id: int | None,
    hold_frames_left: int,
    switch_margin: float = SWITCH_MARGIN,
    min_confidence: float = MIN_FACE_CONFIDENCE,
    mouth_active_threshold: float = MOUTH_ACTIVE_THRESHOLD,
    mouth_lead_margin: float = MOUTH_LEAD_MARGIN,
    current_quiet_frames: int = 0,
    release_frames: int = 0,
) -> tuple[int | None, float, int, int]:
    """Pick speaker id with hold + quiet-release + mouth lead.

    Returns (chosen_id, confidence, new_hold_frames_left, new_quiet_frames).
    Switch only after current speaker has been quiet for release_frames (≈1s)
    unless there is no current speaker.
    """
    if not candidates:
        quiet = current_quiet_frames + 1 if current_id is not None else 0
        return current_id, 0.0, max(0, hold_frames_left - 1), quiet

    ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)
    best = ranked[0]
    second = ranked[1]["score"] if len(ranked) > 1 else 0.0
    margin = best["score"] - second

    current = next((item for item in ranked if item["id"] == current_id), None)
    current_mouth = float(current.get("mouth", 0.0) or 0.0) if current else 0.0
    if current is not None and current_mouth >= mouth_active_threshold:
        quiet = 0
    elif current_id is not None:
        quiet = current_quiet_frames + 1
    else:
        quiet = 0

    # Dual active mouths (both laughing / overlapping) → never switch.
    mouths = [float(item.get("mouth", 0.0) or 0.0) for item in candidates]
    active_mouths = sum(1 for mouth in mouths if mouth >= mouth_active_threshold)
    if active_mouths >= 2 and current_id is not None:
        conf = current["score"] if current else second
        return current_id, conf, max(0, hold_frames_left - 1), quiet

    if best["score"] < min_confidence:
        return current_id, best["score"], max(0, hold_frames_left - 1), quiet

    if current_id is None:
        return best["id"], best["score"], 0, 0

    if best["id"] == current_id:
        return current_id, best["score"], max(0, hold_frames_left - 1), quiet

    # New speaker must lead on mouth activity, not just face size.
    best_mouth = float(best.get("mouth", 0.0) or 0.0)
    if best_mouth < mouth_active_threshold or best_mouth < current_mouth + mouth_lead_margin:
        conf = current["score"] if current else second
        return current_id, conf, max(0, hold_frames_left - 1), quiet

    # Hold window after last cut, or current still talking / not yet quiet 1s.
    if hold_frames_left > 0 or margin < switch_margin:
        conf = current["score"] if current else second
        return current_id, conf, max(0, hold_frames_left - 1), quiet

    if release_frames > 0 and quiet < release_frames and current is not None:
        # Neighbor is talking but current only just stopped — wait ~1s.
        conf = current["score"] if current else second
        return current_id, conf, max(0, hold_frames_left - 1), quiet

    return best["id"], best["score"], 0, 0


def ensure_visible_face_crop(crop_x: float, candidates: list[dict], crop_width: int, source_width: int) -> int:
    """Reject a stale crop that contains no complete credible face."""
    left = max(0, min(int(crop_x), max(0, source_width - crop_width)))
    right = left + crop_width
    visible = [item for item in candidates if left <= item["face"][0] and item["face"][0] + item["face"][2] <= right]
    if visible or not candidates:
        return left
    best = max(candidates, key=lambda item: float(item.get("score", 0.0)))
    return max(0, min(int(best["crop_x"]), max(0, source_width - crop_width)))


def resolve_visible_crop(crop_x: float, candidates: list[dict], fallback_crop_x: float | None, crop_width: int, source_width: int, source_cut: bool = False) -> int:
    """Use shot-level face framing when frame-level face detection is missing."""
    if candidates:
        return ensure_visible_face_crop(crop_x, candidates, crop_width, source_width)
    target = fallback_crop_x if source_cut and fallback_crop_x is not None else crop_x
    return max(0, min(int(target), max(0, source_width - crop_width)))


def stabilize_visible_crops(positions, frame_candidates, fallback_positions, source_cuts, crop_width: int, source_width: int) -> list[int]:
    """Hold last face-verified crop through detector misses; avoid micro-snaps.

    Only re-snap when the locked crop contains ZERO complete faces. If a face
    is already fully inside the crop, keep the position (kills geter).
    """
    stabilized = []
    last_verified = None
    for index, (position, candidates) in enumerate(zip(positions, frame_candidates)):
        fallback = fallback_positions[min(index, len(fallback_positions) - 1)] if fallback_positions else position
        source_cut = source_cuts[min(index, len(source_cuts) - 1)] if source_cuts else False
        if source_cut:
            last_verified = None
        requested = last_verified if last_verified is not None and not source_cut else position
        left = max(0, min(int(requested), max(0, source_width - crop_width)))
        right = left + crop_width
        if candidates:
            fully_inside = [
                item for item in candidates
                if left <= item["face"][0] and item["face"][0] + item["face"][2] <= right
            ]
            if fully_inside:
                current = left
            else:
                # Prefer face nearest crop center (talker), not raw max score.
                crop_cx = left + crop_width / 2
                best = min(
                    candidates,
                    key=lambda item: abs((item["face"][0] + item["face"][2] / 2) - crop_cx),
                )
                current = max(0, min(int(best["crop_x"]), max(0, source_width - crop_width)))
            last_verified = current
        elif last_verified is not None:
            current = last_verified
        else:
            current = resolve_visible_crop(position, candidates, fallback, crop_width, source_width, source_cut)
        stabilized.append(current)
    return stabilized


def scene_changed(
    previous_gray: np.ndarray | None,
    current_gray: np.ndarray,
    diff_threshold: float = SCENE_DIFF_THRESHOLD,
) -> bool:
    """Return true on a source camera cut; small subject motion stays same shot."""
    if previous_gray is None or current_gray is None or current_gray.size == 0:
        return False
    if previous_gray.shape != current_gray.shape:
        return True
    diff = float(np.mean(cv2.absdiff(previous_gray, current_gray))) / 255.0
    return diff >= diff_threshold


def choose_scene_crop_x(
    faces: list[tuple[int, int, int, int]],
    source_width: int,
    crop_width: int,
    previous_crop_x: int | None = None,
    dominant_ratio: float = DOMINANT_FACE_RATIO,
) -> int:
    """Pick one fixed crop for a shot from accumulated face observations."""
    crop_x, _layout = choose_scene_layout(
        faces, source_width, crop_width, previous_crop_x, dominant_ratio,
    )
    return crop_x


def face_motion_score(samples: list[float], source_width: int) -> float:
    """0..1 how much a face center wanders inside one shot (body/camera motion)."""
    if len(samples) < 2 or source_width <= 0:
        return 0.0
    arr = np.asarray(samples, dtype=np.float32)
    span = float(np.max(arr) - np.min(arr)) / float(source_width)
    return max(0.0, min(1.0, span / 0.18))


def prefer_still_over_moving_speaker(
    groups: list[dict],
    dominant_ratio: float = DOMINANT_FACE_RATIO,
    motion_threshold: float = 0.45,
) -> dict:
    """If the talker is moving hard and a still face exists, lock the still face."""
    if not groups:
        raise ValueError("groups required")
    primary = groups[0]
    if len(groups) < 2:
        return primary
    secondary = groups[1]
    primary_motion = float(primary.get("motion", 0.0) or 0.0)
    secondary_motion = float(secondary.get("motion", 0.0) or 0.0)
    # Moving primary + calmer secondary → still face wins for camera stability.
    if primary_motion >= motion_threshold and secondary_motion + 0.12 < primary_motion:
        return secondary
    # No clear talker lead on mouth: prefer larger/still face over empty space.
    if float(primary.get("mouth", 0.0) or 0.0) < MOUTH_ACTIVE_THRESHOLD:
        still = min(groups, key=lambda item: (float(item.get("motion", 0.0) or 0.0), -float(item.get("area", 0.0))))
        return still
    ratio = float(primary["area"]) / max(1.0, float(secondary["area"]))
    if ratio < dominant_ratio and secondary_motion + 0.08 < primary_motion:
        return secondary
    return primary


def choose_scene_layout(
    faces: list[tuple[int, int, int, int]],
    source_width: int,
    crop_width: int,
    previous_crop_x: int | None = None,
    dominant_ratio: float = DOMINANT_FACE_RATIO,
    previous_layout: str = "crop",
    detection_coverage: float | None = None,
    last_face_crop_x: int | None = None,
    face_centers: list[float] | None = None,
    face_mouths: list[float] | None = None,
) -> tuple[int, str]:
    """Return fixed full-frame crop x. Face-only; never empty center / blur."""
    layout = "crop"
    # Low coverage is not an excuse to show pots/walls — keep last face crop.
    if not faces:
        if last_face_crop_x is not None:
            return int(last_face_crop_x), layout
        if previous_crop_x is not None:
            return int(previous_crop_x), layout
        # Absolute last resort only when the whole clip never showed a face yet.
        return center_crop_x(source_width, crop_width), layout

    buckets: dict[int, list[tuple[int, int, int, int, float, float]]] = {}
    centers = list(face_centers or [])
    mouths = list(face_mouths or [])
    for index, face in enumerate(faces):
        x, _y, w, _h = face
        cx = x + w / 2
        bucket = min(2, max(0, int(cx / max(1, source_width) * 3)))
        motion_sample = centers[index] if index < len(centers) else cx
        mouth_sample = mouths[index] if index < len(mouths) else 0.0
        buckets.setdefault(bucket, []).append((x, _y, w, _h, motion_sample, mouth_sample))

    groups = []
    for items in buckets.values():
        center_samples = [item[4] for item in items]
        mouth_samples = [item[5] for item in items]
        groups.append({
            "area": float(np.median([w * h for _x, _y, w, h, _m, _mo in items])),
            "center": float(np.median([x + w / 2 for x, _y, w, _h, _m, _mo in items])),
            "width": float(np.median([w for _x, _y, w, _h, _m, _mo in items])),
            "count": len(items),
            "motion": face_motion_score(center_samples, source_width),
            "mouth": float(np.median(mouth_samples)) if mouth_samples else 0.0,
        })
    groups.sort(key=lambda item: (item["mouth"], item["area"], item["count"]), reverse=True)
    primary = prefer_still_over_moving_speaker(groups, dominant_ratio=dominant_ratio)
    # Weak coverage still uses the best face group — never demote to center/blur.
    _ = detection_coverage
    target_center = primary["center"]
    crop_x = int(round(target_center - crop_width / 2))
    return max(0, min(crop_x, source_width - crop_width)), layout


def track_scene_crop_positions(
    source_path: str,
    analysis_stride: int = 3,
    face_stride: int = 9,
    scene_threshold: float = SCENE_DIFF_THRESHOLD,
    min_shot_seconds: float = MIN_SHOT_SECONDS,
) -> dict:
    """Detect source shots and lock one face crop for every shot."""
    capture = cv2.VideoCapture(str(Path(source_path)))
    try:
        if not capture.isOpened():
            raise RuntimeError(f"Failed to open video: {source_path}")
        source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) or 30.0
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if source_width <= 0 or source_height <= 0:
            raise RuntimeError("Invalid video dimensions")

        crop_width = min(source_width, int(source_height * 9 / 16))
        crop_width = max(2, crop_width - crop_width % 2)
        center_x = center_crop_x(source_width, crop_width)
        if source_width <= source_height:
            return {
                "crop_positions": [0] * max(1, total_frames),
                "crop_width": crop_width,
                "source_width": source_width,
                "source_height": source_height,
                "fps": fps,
                "tracker_version": TRACKER_VERSION,
                "mode": "portrait_passthrough",
                "shot_count": 1,
            }

        cascade = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
        min_shot_frames = max(1, int(round(fps * min_shot_seconds)))
        down_w = min(320, source_width)
        down_h = max(1, int(round(source_height * down_w / source_width)))
        scale_x = source_width / down_w
        scale_y = source_height / down_h

        shots: list[tuple[int, int, list[tuple[int, int, int, int]], int, int]] = []
        shot_start = 0
        shot_faces: list[tuple[int, int, int, int]] = []
        shot_face_samples = 0
        shot_face_hits = 0
        previous_gray = None
        frame_index = 0

        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % max(1, analysis_stride) == 0:
                small = cv2.resize(frame, (down_w, down_h), interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (5, 5), 0)
                enough = frame_index - shot_start >= min_shot_frames
                if enough and scene_changed(previous_gray, gray, scene_threshold):
                    shots.append((shot_start, frame_index, shot_faces, shot_face_samples, shot_face_hits))
                    shot_start = frame_index
                    shot_faces = []
                    shot_face_samples = 0
                    shot_face_hits = 0
                previous_gray = gray

                if frame_index % max(1, face_stride) == 0 and not cascade.empty():
                    shot_face_samples += 1
                    detected = cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.1,
                        minNeighbors=5,
                        minSize=(max(18, down_w // 18), max(18, down_h // 18)),
                    )
                    if len(detected):
                        shot_face_hits += 1
                    for x, y, w, h in detected:
                        shot_faces.append((
                            int(round(x * scale_x)), int(round(y * scale_y)),
                            int(round(w * scale_x)), int(round(h * scale_y)),
                        ))
            frame_index += 1

        if frame_index == 0:
            raise RuntimeError("Video contains no frames")
        shots.append((shot_start, frame_index, shot_faces, shot_face_samples, shot_face_hits))

        positions = [center_x] * frame_index
        layouts = ["crop"] * frame_index
        source_cuts = [False] * frame_index
        previous_crop = None
        previous_layout = "crop"
        last_face_crop = None
        for start, end, faces, face_samples, face_hits in shots:
            detection_coverage = face_hits / face_samples if face_samples else 0.0
            face_centers = [x + w / 2 for x, _y, w, _h in faces]
            crop_x, layout = choose_scene_layout(
                faces, source_width, crop_width,
                previous_crop_x=previous_crop, previous_layout=previous_layout,
                detection_coverage=detection_coverage,
                last_face_crop_x=last_face_crop,
                face_centers=face_centers,
            )
            # Always full-frame crop for vertical product contract.
            layout = "crop"
            positions[start:end] = [crop_x] * max(0, end - start)
            layouts[start:end] = [layout] * max(0, end - start)
            if start > 0:
                source_cuts[start] = True
            previous_crop = crop_x
            previous_layout = layout
            if faces:
                last_face_crop = crop_x

        if total_frames > 0:
            if len(positions) < total_frames:
                positions.extend([positions[-1]] * (total_frames - len(positions)))
                layouts.extend([layouts[-1]] * (total_frames - len(layouts)))
            else:
                positions = positions[:total_frames]
                layouts = layouts[:total_frames]

        return {
            "crop_positions": positions,
            "layouts": layouts,
            "source_cuts": source_cuts,
            "crop_width": crop_width,
            "source_width": source_width,
            "source_height": source_height,
            "fps": fps,
            "tracker_version": TRACKER_VERSION,
            "mode": "scene_face_crop",
            "shot_count": len(shots),
            "frames_analyzed": frame_index,
        }
    finally:
        capture.release()


def track_crop_positions(
    source_path: str,
    sample_stride: int = 1,
    hold_seconds: float = HOLD_SECONDS,
    smooth_seconds: float = SMOOTH_SECONDS,
) -> dict:
    """Analyze video and return per-frame crop_x list + metadata.

    Does not re-encode; used by portrait conversion pass 1.
    """
    capture = cv2.VideoCapture(str(Path(source_path)))
    try:
        if not capture.isOpened():
            raise RuntimeError(f"Failed to open video: {source_path}")
        source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) or 30.0
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if source_width <= 0 or source_height <= 0:
            raise RuntimeError("Invalid video dimensions")
        audio_energies = extract_audio_energy(source_path, fps, total_frames)
        scene_fallback = track_scene_crop_positions(source_path)
        fallback_positions = scene_fallback["crop_positions"]
        source_cuts = scene_fallback.get("source_cuts") or [False] * len(fallback_positions)

        crop_width = min(source_width, int(source_height * 9 / 16))
        crop_width -= crop_width % 2
        center_x = center_crop_x(source_width, crop_width)

        if source_width <= source_height:
            # Already portrait-ish: no horizontal tracking needed
            positions = [0] * max(1, total_frames)
            return {
                "crop_positions": positions,
                "crop_width": crop_width,
                "source_width": source_width,
                "source_height": source_height,
                "fps": fps,
                "tracker_version": TRACKER_VERSION,
                "mode": "portrait_passthrough",
            }

        cascade = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
        use_faces = not cascade.empty()
        face_mesh = None
        try:
            import mediapipe as mp
            face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=3,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        except (ImportError, AttributeError, RuntimeError):
            face_mesh = None
        hold_frames = max(1, int(round(fps * hold_seconds)))
        raw_targets: list[float] = []
        raw_ids: list[int | None] = []
        frame_candidates: list[list[dict]] = []
        prev_mouth_rois: dict[int, np.ndarray] = {}
        prev_lip_landmarks: dict[int, dict[int, tuple[float, float]]] = {}
        current_id = None
        hold_left = 0
        last_target = float(center_x)
        last_face_target: float | None = None
        quiet_frames = 0
        last_face_centers: dict[int, float] = {}
        frame_index = 0

        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if sample_stride > 1 and frame_index % sample_stride != 0 and raw_targets:
                raw_targets.append(raw_targets[-1])
                raw_ids.append(raw_ids[-1] if raw_ids else current_id)
                frame_candidates.append(frame_candidates[-1] if frame_candidates else [])
                frame_index += 1
                continue

            source_cut = source_cuts[min(frame_index, len(source_cuts) - 1)] if source_cuts else False
            if source_cut:
                current_id = None
                hold_left = 0
                quiet_frames = 0
                last_face_centers.clear()
                prev_lip_landmarks.clear()
                prev_mouth_rois.clear()
            candidates = []
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face_rows = []
            if face_mesh is not None:
                result = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                for face_landmarks in result.multi_face_landmarks or []:
                    points = [(point.x, point.y) for point in face_landmarks.landmark]
                    box = mediapipe_face_box(points, source_width, source_height)
                    if box is None:
                        continue
                    x, y, w, h = box
                    f_score = face_score(box, source_width, source_height, None)
                    if valid_face_detection(f_score):
                        lips = {index: points[index] for index in (13, 14, 61, 291)}
                        face_rows.append((x, y, w, h, f_score, lips))
            # MediaPipe miss/error path: retain OpenCV detector as fallback.
            if not face_rows and use_faces:
                faces = cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5,
                    minSize=(max(24, source_width // 40), max(24, source_height // 40)),
                )
                for x, y, w, h in faces:
                    box = (int(x), int(y), int(w), int(h))
                    f_score = face_score(box, source_width, source_height, None)
                    if valid_face_detection(f_score):
                        face_rows.append((*box, f_score, None))

            # Stable IDs: match previous x, else use left/right slot.
            face_rows.sort(key=lambda row: row[0] + row[2] / 2)
            assigned: dict[int, dict] = {}
            for x, y, w, h, f_score, lips in face_rows:
                cx = x + w / 2
                face_id = None
                if current_id is not None and last_face_centers:
                    prev_cx = last_face_centers.get(current_id)
                    if prev_cx is not None and abs(cx - prev_cx) <= max(80.0, crop_width * 0.28):
                        face_id = current_id
                if face_id is None and last_face_centers:
                    best_id, best_dist = None, 1e18
                    for pid, pcx in last_face_centers.items():
                        dist = abs(cx - pcx)
                        if dist < best_dist and dist <= max(100.0, crop_width * 0.35):
                            best_id, best_dist = pid, dist
                    face_id = best_id
                if face_id is None:
                    face_id = 0 if cx < source_width * 0.5 else 1
                    if face_id in assigned:
                        face_id = 1 - face_id
                if lips is not None:
                    m_score = mediapipe_lip_activity(lips, prev_lip_landmarks.get(face_id))
                    prev_lip_landmarks[face_id] = lips
                else:
                    face_roi = gray[y:y + h, x:x + w]
                    m_score = mouth_motion_score(face_roi, prev_mouth_rois.get(face_id))
                    prev_mouth_rois[face_id] = face_roi.copy()
                a_score = audio_energies[frame_index] if frame_index < len(audio_energies) else 0.0
                score = combine_scores(f_score, m_score, a_score)
                if current_id is not None and face_id == current_id:
                    score = min(1.0, score + 0.08)
                item = {
                    "id": face_id,
                    "score": score,
                    "mouth": m_score,
                    "face": (x, y, w, h),
                    "crop_x": crop_x_for_face((x, y, w, h), source_width, crop_width),
                    "center_x": cx,
                }
                prev = assigned.get(face_id)
                if prev is None or item["score"] > prev["score"]:
                    assigned[face_id] = item
            candidates = list(assigned.values())
            last_face_centers = {item["id"]: float(item["center_x"]) for item in candidates}

            # Prefer active talker: boost highest mouth score so crop follows speech.
            if candidates:
                talker = max(candidates, key=lambda item: float(item.get("mouth", 0.0) or 0.0))
                if float(talker.get("mouth", 0.0) or 0.0) >= MOUTH_ACTIVE_THRESHOLD:
                    talker["score"] = min(1.0, float(talker["score"]) + 0.12)

            release_frames = max(1, int(round(fps * SPEAKER_RELEASE_SECONDS))) if fps > 0 else 1
            chosen_id, conf, hold_left, quiet_frames = choose_speaker(
                candidates,
                current_id,
                hold_left,
                current_quiet_frames=quiet_frames,
                release_frames=release_frames,
            )
            # No face this frame: keep last face crop id; do not invent empty center target.
            if not candidates and current_id is not None:
                chosen_id = current_id
            if chosen_id is not None and (current_id is None or chosen_id != current_id):
                if current_id is None or hold_left == 0:
                    hold_left = hold_frames
                quiet_frames = 0
            current_id = chosen_id
            if chosen_id is not None:
                match = next((item for item in candidates if item["id"] == chosen_id), None)
                if match:
                    # Always re-center crop on the chosen face each update.
                    last_target = float(match["crop_x"])
                    last_face_target = last_target
            elif candidates:
                # Any face better than empty B-roll.
                best = max(candidates, key=lambda item: float(item.get("score", 0.0)))
                last_target = float(best["crop_x"])
                last_face_target = last_target
                current_id = best["id"]
            elif last_face_target is not None:
                last_target = float(last_face_target)
            # Safety invariant: every crop with credible detections must contain
            # one complete face, even while speaker debounce holds an old id.
            # Prefer last face crop over scene-center fallback (pots/walls).
            face_fallback = last_face_target if last_face_target is not None else (
                fallback_positions[min(frame_index, len(fallback_positions) - 1)] if fallback_positions else last_target
            )
            last_target = float(resolve_visible_crop(last_target, candidates, face_fallback, crop_width, source_width, source_cut))
            # Missing face: hold last face crop; never re-center empty frame if a face was seen.
            raw_targets.append(last_target)
            raw_ids.append(current_id)
            frame_candidates.append(candidates)
            frame_index += 1

        if not raw_targets:
            # Absolute cold start only: no frames produced any face evidence.
            seed = float(last_face_target) if last_face_target is not None else float(center_x)
            raw_targets = [seed]
            raw_ids = [None]

        # One fixed crop per active speaker. Switch only after stable debounce;
        # no interpolation/pan between positions.
        cut_positions = hard_cut_positions(
            raw_targets,
            raw_ids,
            fps,
            debounce_seconds=SWITCH_DEBOUNCE_SECONDS,
            hold_seconds=hold_seconds,
        )
        cut_positions = stabilize_visible_crops(
            cut_positions, frame_candidates, fallback_positions, source_cuts,
            crop_width, source_width,
        )
        # Reference policy: active-speaker evidence chooses framing, then one
        # fixed crop is held for each confirmed source shot.
        cut_positions = lock_crop_per_source_shot(cut_positions, source_cuts)
        # Pad/truncate to total_frames if known
        if total_frames > 0:
            if len(cut_positions) < total_frames:
                cut_positions.extend([cut_positions[-1]] * (total_frames - len(cut_positions)))
            else:
                cut_positions = cut_positions[:total_frames]

        return {
            "crop_positions": cut_positions,
            "source_cuts": source_cuts,
            "crop_width": crop_width,
            "source_width": source_width,
            "source_height": source_height,
            "fps": fps,
            "tracker_version": TRACKER_VERSION,
            "mode": "active_speaker",
            "frames_analyzed": frame_index,
        }
    finally:
        if "face_mesh" in locals() and face_mesh is not None:
            face_mesh.close()
        capture.release()


def track_active_speaker_positions(source_path: str) -> dict:
    """Choose talking face, then hold one full-frame crop per source shot.

    MediaPipe lip landmarks rank speakers; OpenCV is fallback. Source cuts reset
    identity, then final shot lock prevents detector noise from moving camera.

    sample_stride=2 analyzes every other frame on small VPS.
    """
    result = track_crop_positions(source_path, sample_stride=2)
    result["mode"] = "active_speaker"
    result["layouts"] = ["crop"] * len(result.get("crop_positions") or [])
    return result


def lock_crop_per_source_shot(
    active_positions: list[int],
    source_cuts: list[bool],
    bucket_px: int = 24,
) -> list[int]:
    """Choose dominant active-speaker crop once per source camera shot."""
    if not active_positions:
        return []
    cuts = list(source_cuts[:len(active_positions)])
    cuts.extend([False] * (len(active_positions) - len(cuts)))
    boundaries = [0] + [i for i in range(1, len(active_positions)) if cuts[i]] + [len(active_positions)]
    locked = list(active_positions)
    bucket_px = max(1, int(bucket_px))
    for start, end in zip(boundaries, boundaries[1:]):
        shot = active_positions[start:end]
        counts: dict[int, int] = {}
        first_seen: dict[int, int] = {}
        for offset, value in enumerate(shot):
            bucket = int(round(int(value) / bucket_px))
            counts[bucket] = counts.get(bucket, 0) + 1
            first_seen.setdefault(bucket, offset)
        winner = max(counts, key=lambda bucket: (counts[bucket], -first_seen[bucket]))
        members = sorted(int(value) for value in shot if int(round(int(value) / bucket_px)) == winner)
        crop = members[len(members) // 2]
        locked[start:end] = [crop] * (end - start)
    return locked


def track_shot_speaker_positions(source_path: str) -> dict:
    """Legacy: active-speaker evidence locked once per source cut (too sticky)."""
    result = track_crop_positions(source_path)
    positions = result.get("crop_positions") or []
    cuts = result.get("source_cuts") or [False] * len(positions)
    result["crop_positions"] = lock_crop_per_source_shot(positions, cuts)
    result["layouts"] = ["crop"] * len(result["crop_positions"])
    result["mode"] = "shot_active_speaker"
    return result


def split_rois_are_distinct(rois: dict, min_center_gap: float = 0.2) -> bool:
    """Reject two boxes likely representing same person at different scales."""
    if not isinstance(rois, dict):
        return False
    top, bottom = rois.get("top"), rois.get("bottom")
    if not isinstance(top, dict) or not isinstance(bottom, dict):
        return False
    try:
        top_cx = float(top["x"]) + float(top["width"]) / 2
        bottom_cx = float(bottom["x"]) + float(bottom["width"]) / 2
        top_area = float(top["width"]) * float(top["height"])
        bottom_area = float(bottom["width"]) * float(bottom["height"])
    except (KeyError, TypeError, ValueError):
        return False
    if int(rois.get("count", 0)) == 1:
        # Same speaker is valid only as intentionally different tight/wide framing.
        return abs(top_area - bottom_area) >= 0.08
    return abs(top_cx - bottom_cx) >= min_center_gap


def detect_split_person_rois(source_path: str, sample_frames: int = 12) -> dict:
    """Detect up to two distinct person ROIs for Split Middle panels.

    Returns normalized {top, bottom} dict. Falls back to left/right halves when
    fewer than two faces are found. Uses OpenCV Haar cascade only (no new deps).
    """
    path = Path(source_path)
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            return {}
        source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if source_width <= source_height or source_width <= 0:
            return {}
        cascade = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
        if cascade.empty():
            return {}
        step = max(1, total_frames // max(1, sample_frames)) if total_frames else 5
        buckets: list[list[float]] = []  # [cx, cy, w, h, count]
        frame_index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % step != 0:
                frame_index += 1
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(max(24, source_width // 40), max(24, source_height // 40)),
            )
            for x, y, w, h in faces:
                cx = (x + w / 2) / source_width
                cy = (y + h / 2) / source_height
                nw = w / source_width
                nh = h / source_height
                matched = None
                for bucket in buckets:
                    if abs(bucket[0] - cx) < 0.12 and abs(bucket[1] - cy) < 0.18:
                        matched = bucket
                        break
                if matched is None:
                    buckets.append([cx, cy, nw, nh, 1.0])
                else:
                    n = matched[4]
                    matched[0] = (matched[0] * n + cx) / (n + 1)
                    matched[1] = (matched[1] * n + cy) / (n + 1)
                    matched[2] = (matched[2] * n + nw) / (n + 1)
                    matched[3] = (matched[3] * n + nh) / (n + 1)
                    matched[4] = n + 1
            frame_index += 1
            if sample_frames and len(buckets) >= 2 and frame_index > step * sample_frames:
                break
        if not buckets:
            return {}
        # Prefer two spatially distinct people (left/right), not two scales of one face.
        buckets.sort(key=lambda item: item[4], reverse=True)
        primary = buckets[0]
        secondary = None
        for bucket in buckets[1:]:
            if abs(bucket[0] - primary[0]) >= 0.2:
                secondary = bucket
                break
        people = [primary] if secondary is None else sorted([primary, secondary], key=lambda item: item[0])

        def expand(bucket, tight=False):
            cx, cy, nw, nh, _count = bucket
            # Expand face box to upper-body-ish panel crop.
            if tight:
                width = min(0.48, max(0.24, nw * 2.0))
                height = min(0.85, max(0.45, nh * 2.6))
                y = max(0.0, min(1.0 - height, cy - height * 0.42))
            else:
                width = min(0.58, max(0.32, nw * 2.8))
                height = min(0.98, max(0.62, nh * 3.6))
                y = max(0.0, min(1.0 - height, cy - height * 0.28))
            x = max(0.0, min(1.0 - width, cx - width / 2))
            return {"x": round(float(x), 4), "y": round(float(y), 4), "width": round(float(width), 4), "height": round(float(height), 4)}

        if len(people) == 1:
            # Single speaker: dual framing (tight face + wider body), not empty complementary wall.
            result = {"top": expand(people[0], tight=True), "bottom": expand(people[0], tight=False), "count": 1}
        else:
            result = {"top": expand(people[0], tight=False), "bottom": expand(people[1], tight=False), "count": 2}
            if not split_rois_are_distinct(result):
                result = {"top": expand(primary, tight=True), "bottom": expand(primary, tight=False), "count": 1}
        return result
    finally:
        capture.release()
