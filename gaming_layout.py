import math
from pathlib import Path

import cv2


DETECTOR_VERSION = "gaming-face-v1"
FACE_NOT_FOUND_MESSAGE = "Facecam tidak ditemukan. Gunakan video dengan facecam yang terlihat jelas, lalu coba lagi."


class GamingLayoutError(ValueError):
    pass


def validate_roi(roi):
    if not isinstance(roi, dict):
        return None
    try:
        values = {key: float(roi[key]) for key in ("x", "y", "width", "height")}
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in values.values()):
        return None
    if values["x"] < 0 or values["y"] < 0 or values["width"] <= 0 or values["height"] <= 0:
        return None
    if values["x"] + values["width"] > 1 or values["y"] + values["height"] > 1:
        return None
    return values


def _iou(first, second):
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[0] + first[2], second[0] + second[2])
    bottom = min(first[1] + first[3], second[1] + second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = first[2] * first[3] + second[2] * second[3] - intersection
    return intersection / union if union else 0.0


def cluster_detections(detections, sample_count):
    clusters = []
    for frame_index, box in detections:
        center = (box[0] + box[2] / 2, box[1] + box[3] / 2)
        match = None
        for cluster in clusters:
            mean = cluster["mean"]
            mean_center = (mean[0] + mean[2] / 2, mean[1] + mean[3] / 2)
            distance = math.hypot(center[0] - mean_center[0], center[1] - mean_center[1])
            if _iou(box, mean) >= 0.15 or distance <= 0.12:
                match = cluster
                break
        if match is None:
            match = {"items": [], "frames": set(), "mean": box}
            clusters.append(match)
        match["items"].append(box)
        match["frames"].add(frame_index)
        match["mean"] = tuple(sum(item[index] for item in match["items"]) / len(match["items"]) for index in range(4))
    candidates = []
    for cluster in clusters:
        boxes = cluster["items"]
        mean = cluster["mean"]
        frequency = len(cluster["frames"]) / max(1, sample_count)
        centers = [(box[0] + box[2] / 2, box[1] + box[3] / 2) for box in boxes]
        position_variance = sum((x - sum(item[0] for item in centers) / len(centers)) ** 2 + (y - sum(item[1] for item in centers) / len(centers)) ** 2 for x, y in centers) / len(centers)
        areas = [box[2] * box[3] for box in boxes]
        mean_area = sum(areas) / len(areas)
        size_variance = sum((area - mean_area) ** 2 for area in areas) / len(areas)
        edge_distance = min(mean[0], mean[1], 1 - mean[0] - mean[2], 1 - mean[1] - mean[3])
        edge_score = max(0.0, 1 - edge_distance / 0.3)
        stability = max(0.0, 1 - math.sqrt(position_variance) / 0.08)
        size_stability = max(0.0, 1 - math.sqrt(size_variance) / max(mean_area, 0.001))
        confidence = 0.55 * frequency + 0.2 * stability + 0.15 * size_stability + 0.1 * edge_score
        candidates.append({"box": mean, "confidence": confidence, "frequency": frequency})
    return sorted(candidates, key=lambda item: item["confidence"], reverse=True)


def _normalized_crop(center_x, center_y, target_ratio, width, height):
    crop_height = min(1.0, max(height, width / target_ratio) * 2.4)
    crop_width = crop_height * target_ratio
    if crop_width > 1:
        crop_width = 1.0
        crop_height = crop_width / target_ratio
    x = min(max(0.0, center_x - crop_width / 2), 1 - crop_width)
    y = min(max(0.0, center_y - crop_height / 2), 1 - crop_height)
    return {"x": x, "y": y, "width": crop_width, "height": crop_height}


def facecam_crop(roi, source_width=1, source_height=1):
    valid = validate_roi(roi)
    if not valid:
        raise GamingLayoutError(FACE_NOT_FOUND_MESSAGE)
    normalized_ratio = 27 / 16 * source_height / source_width
    return _normalized_crop(valid["x"] + valid["width"] / 2, valid["y"] + valid["height"] / 2, normalized_ratio, valid["width"], valid["height"])


def gameplay_crop(source_width, source_height, facecam_roi):
    if source_width <= source_height:
        raise GamingLayoutError("Mode gaming hanya mendukung source landscape.")
    crop_height = source_height
    crop_width = min(source_width, int(source_height * 27 / 32))
    crop_width -= crop_width % 2
    x = (source_width - crop_width) // 2
    roi = validate_roi(facecam_roi)
    if roi:
        face_left = roi["x"] * source_width
        face_right = (roi["x"] + roi["width"]) * source_width
        if face_right > x and face_left < x + crop_width:
            x = source_width - crop_width if roi["x"] + roi["width"] / 2 < 0.5 else 0
    return {"x": x - x % 2, "y": 0, "width": crop_width, "height": crop_height - crop_height % 2}


def build_gaming_filtergraph(source_width, source_height, output_width, output_height, roi):
    if source_width <= source_height:
        raise GamingLayoutError("Mode gaming hanya mendukung source landscape.")
    face = validate_roi(roi)
    if not face:
        raise GamingLayoutError(FACE_NOT_FOUND_MESSAGE)
    face_px = {
        "x": int(face["x"] * source_width),
        "y": int(face["y"] * source_height),
        "width": int(face["width"] * source_width),
        "height": int(face["height"] * source_height),
    }
    for key in face_px:
        face_px[key] -= face_px[key] % 2
    game = gameplay_crop(source_width, source_height, roi)
    top_height = round(output_height / 3)
    top_height -= top_height % 2
    bottom_height = output_height - top_height
    filters = [
        "[0:v]setpts=PTS-STARTPTS,split=2[facecam_src][gameplay_src]",
        f"[facecam_src]crop={face_px['width']}:{face_px['height']}:{face_px['x']}:{face_px['y']},scale={output_width}:{top_height}:flags=lanczos[facecam]",
        f"[gameplay_src]crop={game['width']}:{game['height']}:{game['x']}:{game['y']},scale={output_width}:{bottom_height}:flags=lanczos[gameplay]",
        "[facecam][gameplay]vstack=inputs=2,setsar=1[v0]",
    ]
    return filters, {"facecam": face_px, "gameplay": game, "output": {"width": output_width, "height": output_height, "facecam_height": top_height, "gameplay_height": bottom_height}}


def detect_facecam(source_path, sample_count=24, minimum_confidence=0.62):
    capture = cv2.VideoCapture(str(Path(source_path)))
    try:
        if not capture.isOpened():
            raise GamingLayoutError(FACE_NOT_FOUND_MESSAGE)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if width <= height:
            raise GamingLayoutError("Mode gaming hanya mendukung source landscape.")
        if frame_count <= 0:
            raise GamingLayoutError(FACE_NOT_FOUND_MESSAGE)
        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
        if cascade.empty():
            raise GamingLayoutError("Model deteksi facecam tidak tersedia. Install ulang dependency aplikasi.")
        detections = []
        sampled = 0
        for sample_index in range(sample_count):
            frame_index = round(sample_index * max(0, frame_count - 1) / max(1, sample_count - 1))
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                continue
            sampled += 1
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)
            for x, y, face_width, face_height in cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(max(24, width // 40), max(24, height // 40))):
                detections.append((sample_index, (x / width, y / height, face_width / width, face_height / height)))
        candidates = cluster_detections(detections, sampled)
        if not candidates or candidates[0]["confidence"] < minimum_confidence:
            raise GamingLayoutError(FACE_NOT_FOUND_MESSAGE)
        crop = facecam_crop({"x": candidates[0]["box"][0], "y": candidates[0]["box"][1], "width": candidates[0]["box"][2], "height": candidates[0]["box"][3]}, width, height)
        return {**crop, "confidence": round(candidates[0]["confidence"], 4), "source_width": width, "source_height": height, "detector_version": DETECTOR_VERSION}
    finally:
        capture.release()
