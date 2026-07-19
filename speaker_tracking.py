"""Vertical Full crop: active-speaker face crop with hard cuts.

Policy:
- Detect source camera shot changes (histogram/frame diff).
- Pick crop once per shot from faces in that shot.
- 1 dominant face → medium close-up lock on that face.
- 2 roughly equal faces → center/two-shot crop.
- Missing face → hold previous shot crop (or center if never seen).
- Hard cut only when source shot changes. No pan. No lip/audio speaker guess.
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


TRACKER_VERSION = "active-speaker-v2"
HOLD_SECONDS = 2.0
SMOOTH_SECONDS = 0.0
SWITCH_MARGIN = 0.16
MIN_FACE_CONFIDENCE = 0.35
SWITCH_DEBOUNCE_SECONDS = 1.2


def tracking_strategy():
    """Vertical Full uses speaker selection; no wide/two-shot layouts."""
    return track_crop_positions, False
MOUTH_ACTIVE_THRESHOLD = 0.16
MOUTH_LEAD_MARGIN = 0.06
DEAD_ZONE_PX = 12.0
MAX_PAN_PX_PER_FRAME = 6.0
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
    mouth_active_threshold: float = MOUTH_ACTIVE_THRESHOLD,
    mouth_lead_margin: float = MOUTH_LEAD_MARGIN,
) -> tuple[int | None, float, int]:
    """Pick speaker id with hold + confidence margin + anti-laugh rules.

    candidates: list of {id, score, crop_x, mouth?}
    Returns (chosen_id, confidence, new_hold_frames_left).
    """
    if not candidates:
        return current_id, 0.0, max(0, hold_frames_left - 1)

    ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)
    best = ranked[0]
    second = ranked[1]["score"] if len(ranked) > 1 else 0.0
    margin = best["score"] - second

    # Dual active mouths (both laughing / overlapping) → never switch.
    mouths = [float(item.get("mouth", 0.0) or 0.0) for item in candidates]
    active_mouths = sum(1 for mouth in mouths if mouth >= mouth_active_threshold)
    if active_mouths >= 2 and current_id is not None:
        current = next((item for item in ranked if item["id"] == current_id), None)
        conf = current["score"] if current else second
        return current_id, conf, max(0, hold_frames_left - 1)

    if best["score"] < min_confidence:
        return current_id, best["score"], max(0, hold_frames_left - 1)

    if current_id is None:
        return best["id"], best["score"], 0

    if best["id"] == current_id:
        return current_id, best["score"], max(0, hold_frames_left - 1)

    # New speaker must lead on mouth activity, not just face size.
    current = next((item for item in ranked if item["id"] == current_id), None)
    best_mouth = float(best.get("mouth", 0.0) or 0.0)
    current_mouth = float(current.get("mouth", 0.0) or 0.0) if current else 0.0
    if best_mouth < mouth_active_threshold or best_mouth < current_mouth + mouth_lead_margin:
        conf = current["score"] if current else second
        return current_id, conf, max(0, hold_frames_left - 1)

    # Ambiguous / early switch: keep current speaker
    if hold_frames_left > 0 or margin < switch_margin:
        conf = current["score"] if current else second
        return current_id, conf, max(0, hold_frames_left - 1)

    return best["id"], best["score"], 0


def hard_cut_positions(
    targets: list[float],
    speaker_ids: list[int | None],
    fps: float,
    debounce_seconds: float = SWITCH_DEBOUNCE_SECONDS,
    hold_seconds: float = HOLD_SECONDS,
) -> list[int]:
    """Lock crop per speaker; hard-cut only after stable new speaker.

    - Same speaker: crop stays fixed (median of that speaker's targets).
    - Candidate speaker must lead continuously for debounce_seconds.
    - After a cut, hold_seconds before another cut is allowed.
    - Ambiguous / None: keep previous crop.
    """
    if not targets:
        return []
    n = len(targets)
    if n != len(speaker_ids):
        speaker_ids = list(speaker_ids[:n]) + [None] * max(0, n - len(speaker_ids))

    debounce_frames = max(1, int(round(fps * debounce_seconds))) if fps > 0 else 1
    hold_frames = max(1, int(round(fps * hold_seconds))) if fps > 0 else 1

    current_id = next((sid for sid in speaker_ids if sid is not None), None)
    # Seed crop from first non-null target for current speaker, else first target.
    current_crop = float(targets[0])
    for sid, target in zip(speaker_ids, targets):
        if current_id is not None and sid == current_id:
            current_crop = float(target)
            break

    out: list[int] = []
    candidate_id: int | None = None
    candidate_streak = 0
    held = 0
    speaker_samples: dict[int, list[float]] = {}

    for sid, target in zip(speaker_ids, targets):
        if sid is not None:
            speaker_samples.setdefault(sid, []).append(float(target))
            # Keep only a short recent window to avoid old shot positions.
            if len(speaker_samples[sid]) > 45:
                speaker_samples[sid] = speaker_samples[sid][-45:]

        if current_id is None and sid is not None:
            current_id = sid
            samples = speaker_samples.get(sid) or [float(target)]
            current_crop = float(np.median(samples))
            held = 1
            candidate_id = None
            candidate_streak = 0
            out.append(int(round(current_crop)))
            continue

        if sid is None or sid == current_id:
            # Hard lock: head movement must not move the virtual camera.
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
            samples = speaker_samples.get(sid) or [float(target)]
            current_crop = float(np.median(samples))
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
    x, _y, w, _h = face
    center = x + w / 2
    crop_x = int(round(center - crop_width / 2))
    return max(0, min(crop_x, source_width - crop_width))


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


def choose_scene_layout(
    faces: list[tuple[int, int, int, int]],
    source_width: int,
    crop_width: int,
    previous_crop_x: int | None = None,
    dominant_ratio: float = DOMINANT_FACE_RATIO,
    previous_layout: str = "crop",
) -> tuple[int, str]:
    """Return fixed crop x and layout; wide equal two-shots use blur-contain."""
    center = center_crop_x(source_width, crop_width)
    if not faces:
        return (center if previous_crop_x is None else int(previous_crop_x), previous_layout)

    buckets: dict[int, list[tuple[int, int, int, int]]] = {}
    for face in faces:
        x, _y, w, _h = face
        cx = x + w / 2
        bucket = min(2, max(0, int(cx / max(1, source_width) * 3)))
        buckets.setdefault(bucket, []).append(face)

    groups = []
    for items in buckets.values():
        groups.append({
            "area": float(np.median([w * h for _x, _y, w, h in items])),
            "center": float(np.median([x + w / 2 for x, _y, w, _h in items])),
            "width": float(np.median([w for _x, _y, w, _h in items])),
            "count": len(items),
        })
    groups.sort(key=lambda item: (item["area"], item["count"]), reverse=True)
    primary = groups[0]
    layout = "crop"

    if len(groups) >= 2:
        secondary = groups[1]
        ratio = primary["area"] / max(1.0, secondary["area"])
        if ratio < dominant_ratio:
            target_center = (primary["center"] + secondary["center"]) / 2
            left = min(primary["center"] - primary["width"] / 2, secondary["center"] - secondary["width"] / 2)
            right = max(primary["center"] + primary["width"] / 2, secondary["center"] + secondary["width"] / 2)
            layout = "crop" if right - left <= crop_width else "contain_blur"
        else:
            target_center = primary["center"]
    else:
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

        shots: list[tuple[int, int, list[tuple[int, int, int, int]]]] = []
        shot_start = 0
        shot_faces: list[tuple[int, int, int, int]] = []
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
                    shots.append((shot_start, frame_index, shot_faces))
                    shot_start = frame_index
                    shot_faces = []
                previous_gray = gray

                if frame_index % max(1, face_stride) == 0 and not cascade.empty():
                    detected = cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.1,
                        minNeighbors=5,
                        minSize=(max(18, down_w // 18), max(18, down_h // 18)),
                    )
                    for x, y, w, h in detected:
                        shot_faces.append((
                            int(round(x * scale_x)), int(round(y * scale_y)),
                            int(round(w * scale_x)), int(round(h * scale_y)),
                        ))
            frame_index += 1

        if frame_index == 0:
            raise RuntimeError("Video contains no frames")
        shots.append((shot_start, frame_index, shot_faces))

        positions = [center_x] * frame_index
        layouts = ["crop"] * frame_index
        previous_crop = None
        previous_layout = "crop"
        for start, end, faces in shots:
            crop_x, layout = choose_scene_layout(
                faces, source_width, crop_width,
                previous_crop_x=previous_crop, previous_layout=previous_layout,
            )
            positions[start:end] = [crop_x] * max(0, end - start)
            layouts[start:end] = [layout] * max(0, end - start)
            previous_crop = crop_x
            previous_layout = layout

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
                # Stable-ish IDs by horizontal bucket so left/right speakers keep identity.
                for x, y, w, h in faces:
                    cx_norm = (x + w / 2) / max(1.0, source_width)
                    face_id = 0 if cx_norm < 0.5 else 1
                    # Prefer finer buckets when many faces cluster near center
                    if abs(cx_norm - 0.5) < 0.08:
                        face_id = 0 if current_id == 0 else (1 if current_id == 1 else (0 if cx_norm < 0.5 else 1))
                    prev_center = None
                    if raw_targets:
                        prev_center = (raw_targets[-1] + crop_width / 2) / source_width
                    f_score = face_score((x, y, w, h), source_width, source_height, prev_center)
                    if not valid_face_detection(f_score):
                        continue
                    face_roi = gray[y:y + h, x:x + w]
                    m_score = mouth_motion_score(face_roi, prev_mouth_rois.get(face_id))
                    prev_mouth_rois[face_id] = face_roi.copy()
                    a_score = audio_energies[frame_index] if frame_index < len(audio_energies) else 0.0
                    score = combine_scores(f_score, m_score, a_score)
                    # Prefer continuing current speaker when boxes are close.
                    if current_id is not None and face_id == current_id:
                        score = min(1.0, score + 0.08)
                    candidates.append({
                        "id": face_id,
                        "score": score,
                        "mouth": m_score,
                        "crop_x": crop_x_for_face((x, y, w, h), source_width, crop_width),
                    })
                # If two detections map to same bucket, keep higher score only.
                by_id = {}
                for item in candidates:
                    prev = by_id.get(item["id"])
                    if prev is None or item["score"] > prev["score"]:
                        by_id[item["id"]] = item
                candidates = list(by_id.values())

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

        # One fixed crop per active speaker. Switch only after stable debounce;
        # no interpolation/pan between positions.
        cut_positions = hard_cut_positions(
            raw_targets,
            raw_ids,
            fps,
            debounce_seconds=SWITCH_DEBOUNCE_SECONDS,
            hold_seconds=hold_seconds,
        )
        # Pad/truncate to total_frames if known
        if total_frames > 0:
            if len(cut_positions) < total_frames:
                cut_positions.extend([cut_positions[-1]] * (total_frames - len(cut_positions)))
            else:
                cut_positions = cut_positions[:total_frames]

        return {
            "crop_positions": cut_positions,
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
