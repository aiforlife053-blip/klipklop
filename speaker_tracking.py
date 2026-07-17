"""Active-speaker crop tracking for Vertical Full.

Policy (Milestone 2):
- Combine face size, mouth motion, and optional audio energy.
- Hold speaker at least 1.5s before switching.
- Require confidence margin before switching.
- Smooth crop transitions over ~300ms.
- Missing face: hold last crop; never-seen: center crop.
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


TRACKER_VERSION = "speaker-track-v1"
HOLD_SECONDS = 1.5
SMOOTH_SECONDS = 0.3
SWITCH_MARGIN = 0.12
MIN_FACE_CONFIDENCE = 0.35


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


def audio_energy_score(samples: np.ndarray | None) -> float:
    """Normalize short-window RMS energy into 0..1."""
    if samples is None or samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float32)))))
    return max(0.0, min(1.0, rms / 0.12))


def combine_scores(face: float, mouth: float, audio: float) -> float:
    return max(0.0, min(1.0, 0.45 * face + 0.35 * mouth + 0.20 * audio))


def choose_speaker(
    candidates: list[dict],
    current_id: int | None,
    hold_frames_left: int,
    switch_margin: float = SWITCH_MARGIN,
    min_confidence: float = MIN_FACE_CONFIDENCE,
) -> tuple[int | None, float, int]:
    """Pick speaker id with hold + confidence margin.

    candidates: list of {id, score, crop_x}
    Returns (chosen_id, confidence, new_hold_frames_left).
    """
    if not candidates:
        return current_id, 0.0, max(0, hold_frames_left - 1)

    ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)
    best = ranked[0]
    second = ranked[1]["score"] if len(ranked) > 1 else 0.0
    margin = best["score"] - second

    if best["score"] < min_confidence:
        return current_id, best["score"], max(0, hold_frames_left - 1)

    if current_id is None:
        return best["id"], best["score"], 0

    if best["id"] == current_id:
        return current_id, best["score"], max(0, hold_frames_left - 1)

    # Ambiguous / early switch: keep current speaker
    if hold_frames_left > 0 or margin < switch_margin:
        current = next((item for item in ranked if item["id"] == current_id), None)
        conf = current["score"] if current else second
        return current_id, conf, max(0, hold_frames_left - 1)

    return best["id"], best["score"], 0


def smooth_positions(positions: list[float], fps: float, smooth_seconds: float = SMOOTH_SECONDS) -> list[int]:
    """Ease crop x over ~smooth_seconds using exponential moving average."""
    if not positions:
        return []
    alpha = 1.0 if fps <= 0 else min(1.0, 1.0 / max(1.0, fps * smooth_seconds))
    smoothed = [float(positions[0])]
    for value in positions[1:]:
        prev = smoothed[-1]
        smoothed.append(prev + (float(value) - prev) * alpha)
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
    x, _y, w, _h = face
    center = x + w / 2
    crop_x = int(round(center - crop_width / 2))
    return max(0, min(crop_x, source_width - crop_width))


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
        hold_frames = max(1, int(round(fps * hold_seconds)))
        raw_targets: list[float] = []
        raw_ids: list[int | None] = []
        prev_mouth_rois: dict[int, np.ndarray] = {}
        current_id = None
        hold_left = 0
        last_target = float(center_x)
        frame_index = 0

        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if sample_stride > 1 and frame_index % sample_stride != 0 and raw_targets:
                raw_targets.append(raw_targets[-1])
                raw_ids.append(raw_ids[-1] if raw_ids else current_id)
                frame_index += 1
                continue

            candidates = []
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if use_faces:
                faces = cascade.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5,
                    minSize=(max(24, source_width // 40), max(24, source_height // 40)),
                )
                for face_id, (x, y, w, h) in enumerate(faces):
                    prev_center = None
                    if current_id is not None and raw_targets:
                        prev_center = (raw_targets[-1] + crop_width / 2) / source_width
                    f_score = face_score((x, y, w, h), source_width, source_height, prev_center)
                    face_roi = gray[y:y + h, x:x + w]
                    m_score = mouth_motion_score(face_roi, prev_mouth_rois.get(face_id))
                    prev_mouth_rois[face_id] = face_roi.copy()
                    a_score = audio_energies[frame_index] if frame_index < len(audio_energies) else 0.0
                    score = combine_scores(f_score, m_score, a_score)
                    candidates.append({
                        "id": face_id,
                        "score": score,
                        "crop_x": crop_x_for_face((x, y, w, h), source_width, crop_width),
                    })

            chosen_id, conf, hold_left = choose_speaker(
                candidates, current_id, hold_left,
            )
            if chosen_id is not None and (current_id is None or chosen_id != current_id):
                if current_id is None or hold_left == 0:
                    hold_left = hold_frames
            current_id = chosen_id
            if chosen_id is not None:
                match = next((item for item in candidates if item["id"] == chosen_id), None)
                if match:
                    last_target = float(match["crop_x"])
            # Missing face: hold last_target (already set); never-seen stays center
            raw_targets.append(last_target)
            raw_ids.append(current_id)
            frame_index += 1

        if not raw_targets:
            raw_targets = [float(center_x)]
            raw_ids = [None]

        held_ids = enforce_hold(raw_ids, fps, hold_seconds)
        # Re-map held ids to crop targets where possible
        id_to_x = {}
        for speaker_id, crop_x in zip(raw_ids, raw_targets):
            if speaker_id is not None:
                id_to_x[speaker_id] = crop_x
        held_targets = []
        last = float(center_x)
        for speaker_id, fallback in zip(held_ids, raw_targets):
            if speaker_id in id_to_x:
                last = id_to_x[speaker_id]
            else:
                last = fallback
            held_targets.append(last)

        smoothed = smooth_positions(held_targets, fps, smooth_seconds)
        # Pad/truncate to total_frames if known
        if total_frames > 0:
            if len(smoothed) < total_frames:
                smoothed.extend([smoothed[-1]] * (total_frames - len(smoothed)))
            else:
                smoothed = smoothed[:total_frames]

        return {
            "crop_positions": smoothed,
            "crop_width": crop_width,
            "source_width": source_width,
            "source_height": source_height,
            "fps": fps,
            "tracker_version": TRACKER_VERSION,
            "mode": "active_speaker",
            "frames_analyzed": frame_index,
        }
    finally:
        capture.release()
