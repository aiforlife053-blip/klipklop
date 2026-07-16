import math

import pytest

from gaming_layout import GamingLayoutError, build_gaming_filtergraph, cluster_detections, facecam_crop, gameplay_crop, validate_roi


def test_clustering_prefers_consistent_corner_face_over_occasional_game_face():
    detections = []
    for frame in range(20):
        detections.append((frame, (0.03 + frame % 2 * 0.002, 0.04, 0.12, 0.18)))
    for frame in (2, 9, 17):
        detections.append((frame, (0.55, 0.35, 0.08, 0.12)))
    candidates = cluster_detections(detections, 24)
    assert candidates[0]["box"][0] < 0.1
    assert candidates[0]["frequency"] > candidates[1]["frequency"]
    assert candidates[0]["confidence"] > 0.62


def test_low_frequency_candidate_has_low_confidence():
    candidates = cluster_detections([(0, (0.02, 0.03, 0.1, 0.15)), (8, (0.02, 0.03, 0.1, 0.15))], 24)
    assert candidates[0]["confidence"] < 0.62


@pytest.mark.parametrize("roi", [None, {}, {"x": -0.1, "y": 0, "width": 0.2, "height": 0.2}, {"x": 0.9, "y": 0, "width": 0.2, "height": 0.2}, {"x": float("nan"), "y": 0, "width": 0.2, "height": 0.2}])
def test_validate_roi_rejects_invalid_values(roi):
    assert validate_roi(roi) is None


def test_facecam_crop_stays_inside_frame_and_uses_27_by_16_ratio():
    crop = facecam_crop({"x": 0.91, "y": 0.01, "width": 0.08, "height": 0.12})
    assert crop["x"] >= 0 and crop["y"] >= 0
    assert crop["x"] + crop["width"] <= 1
    assert crop["y"] + crop["height"] <= 1
    assert math.isclose(crop["width"] / crop["height"], 27 / 16)


def test_gameplay_crop_uses_27_by_32_ratio_and_even_dimensions():
    crop = gameplay_crop(1920, 1080, {"x": 0.3, "y": 0.02, "width": 0.2, "height": 0.25})
    assert crop["width"] % 2 == crop["height"] % 2 == crop["x"] % 2 == 0
    assert math.isclose(crop["width"] / crop["height"], 27 / 32, rel_tol=0.002)
    assert crop["x"] == 1920 - crop["width"]


def test_gaming_filtergraph_places_facecam_above_gameplay_at_one_third_ratio():
    roi = {"x": 0.02, "y": 0.02, "width": 0.18, "height": 0.25}
    filters, geometry = build_gaming_filtergraph(1920, 1080, 720, 1280, roi)
    graph = ";".join(filters)
    assert "split=2[facecam_src][gameplay_src]" in graph
    assert "[facecam][gameplay]vstack=inputs=2,setsar=1[v0]" in graph
    assert geometry["facecam"] == {"x": 38, "y": 20, "width": 344, "height": 270}
    assert geometry["output"]["facecam_height"] == 426
    assert geometry["output"]["gameplay_height"] == 854
    assert all(value % 2 == 0 for panel in (geometry["facecam"], geometry["gameplay"]) for value in panel.values())


def test_expanded_detected_crop_is_reused_without_second_expansion():
    detected = facecam_crop({"x": 0.05, "y": 0.05, "width": 0.1, "height": 0.15}, 1920, 1080)
    _, geometry = build_gaming_filtergraph(1920, 1080, 720, 1280, detected)
    assert geometry["facecam"] == {key: int(detected[key] * (1920 if key in {"x", "width"} else 1080)) // 2 * 2 for key in ("x", "y", "width", "height")}


def test_gaming_filtergraph_rejects_portrait_source():
    with pytest.raises(GamingLayoutError, match="landscape"):
        build_gaming_filtergraph(720, 1280, 720, 1280, {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})
