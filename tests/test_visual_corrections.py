"""Koreksi visual V3: subtitle, credit, hook, quality-aware defaults."""
from pathlib import Path

import pytest

from config.editor_defaults import (
    EDITOR_DEFAULTS,
    HOOK_MAX_LINES,
    HOOK_MAX_WORDS,
    SUBTITLE_WORD_MAX,
    SUBTITLE_WORD_MIN,
    v3_locked_render_settings,
)
from layout_modes import build_filtergraph, output_geometry
from speaker_tracking import choose_speaker
from subtitle_cues import build_subtitle_cues
from visual_style import find_hook_name_span, hook_name_from_title, hook_tts_text, normalize_hook_text, sanitize_subtitle_text, sanitize_subtitle_token, validate_hook_text
from clipper_core import LocalClipRenderer


def test_hook_sentence_keeps_name_inside_one_readable_sentence():
    raw = "ternyata [raditya dika] hampir bangkrut"
    display = normalize_hook_text(raw)
    flat = display.replace("\n", " ")
    assert flat == "TERNYATA RADITYA DIKA HAMPIR BANGKRUT"
    assert len(flat.split()) <= 8
    assert display.count("\n") <= 1
    assert ":" not in flat
    assert "[" not in flat and "]" not in flat
    assert hook_tts_text(raw) == flat
    span = find_hook_name_span(flat.split(), original_text=raw)
    assert span == (1, 3)


def test_hook_removes_emoji_from_overlay_and_tts():
    raw = "ASILA MAISA DITUDUH JADI SELINGKUHAN 😮"
    assert "😮" not in normalize_hook_text(raw)
    assert "😮" not in hook_tts_text(raw)


def test_user_hook_above_eight_words_is_rejected_not_truncated():
    with pytest.raises(ValueError, match="maksimal 8 kata"):
        validate_hook_text("satu dua tiga empat lima enam tujuh delapan sembilan")


def test_hook_infers_leading_person_name_shared_with_title():
    hook = "ASILA MAISA DITUDUH JADI SELINGKUHAN RIZKY BILLAR"
    title = "Asila Maisa Digosipkan Jadi Selingkuhan Rizky Billar"
    assert hook_name_from_title(hook, title) == "ASILA MAISA"
    words = normalize_hook_text(hook).replace("\n", " ").split()
    assert find_hook_name_span(words, known_names=[hook_name_from_title(hook, title)], original_text=hook) == (0, 2)


@pytest.mark.parametrize("text", [
    "AKU PERNAH HAMPIR BANGKRUT",
    "BANYAK PODCASTER CUMA PURA PURA SUKSES",
])
def test_hook_does_not_infer_generic_shared_prefix_as_name(text):
    assert hook_name_from_title(text, text) == ""


def test_segment_only_subtitles_are_split_to_max_three_words():
    cues = build_subtitle_cues({
        "duration": 6,
        "words": [],
        "segments": [{"text": "one two three four five six", "start": 0.0, "end": 6.0}],
    })
    assert [cue["text"] for cue in cues] == ["ONE TWO THREE", "FOUR FIVE SIX"]
    assert all(len(cue["text"].split()) <= 3 for cue in cues)


def test_legacy_colon_hook_still_becomes_one_sentence():
    display = normalize_hook_text("Raditya Dika: blabla lucu banget")
    assert display.replace("\n", " ") == "RADITYA DIKA BLABLA LUCU BANGET"
    assert ":" not in display


def test_hook_detects_honorific_name_without_internal_marker():
    text = "DETIK-DETIK DR. TIRTA PINGSAN DI JALUR PACITAN"
    words = normalize_hook_text(text).replace("\n", " ").split()
    assert find_hook_name_span(words, original_text=text) == (1, 3)


def test_hook_overlay_keeps_all_eight_long_words(tmp_path, monkeypatch):
    from PIL import ImageDraw

    drawn = []
    real_draw = ImageDraw.Draw

    class RecordingDraw:
        def __init__(self, image):
            self._draw = real_draw(image)

        def textbbox(self, *args, **kwargs):
            return self._draw.textbbox(*args, **kwargs)

        def text(self, position, text, *args, **kwargs):
            drawn.append(text)
            return self._draw.text(position, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw, "Draw", RecordingDraw)
    renderer = object.__new__(LocalClipRenderer)
    renderer.hook_style_settings = {
        "font_size": 0.075, "font_weight": 700, "outline_thickness": 1.5,
        "max_lines": 2, "position_x": 0.5, "position_y": 0.22,
        "text_color": "#FFFFFF", "outline_color": "#000000",
    }
    words = " ".join(chr(65 + index) * 100 for index in range(8))
    renderer._create_hook_overlay(words, 540, 960, tmp_path / "long-hook.png")
    assert drawn == words.split()


def test_hook_overlay_highlights_inline_name_yellow(tmp_path):
    renderer = object.__new__(LocalClipRenderer)
    renderer.hook_style_settings = {
        "font_size": 0.056, "font_weight": 700, "outline_thickness": 1.5,
        "max_lines": 2, "position_x": 0.5, "position_y": 0.22,
        "text_color": "#FFFFFF", "outline_color": "#000000",
    }
    output = tmp_path / "hook.png"
    renderer._create_hook_overlay("ternyata [raditya dika] hampir bangkrut", 540, 960, output)
    from PIL import Image
    pixels = list(Image.open(output).convert("RGBA").getdata())
    assert any(r > 220 and g > 220 and b < 80 and a > 200 for r, g, b, a in pixels)
    assert any(r > 220 and g > 220 and b > 220 and a > 200 for r, g, b, a in pixels)


def test_subtitle_defaults_target_108px_and_bright_yellow():
    sub = EDITOR_DEFAULTS["subtitle"]
    assert sub["color"] == "#FFFF00"
    assert sub["text_transform"] == "uppercase"
    assert sub["font_family"] == "Poppins"
    assert sub["font_weight"] == 700
    assert sub["word_min"] == 3
    assert sub["word_max"] == 3
    assert SUBTITLE_WORD_MIN == 3
    assert SUBTITLE_WORD_MAX == 3
    # size formula: size * 500 / 340 * width ≈ 108 @1080 (54px @540)
    size = float(sub["size"])
    px = int(max(12, size * 500) / 340 * 1080)
    assert 106 <= px <= 110
    assert sub["position_y"] == 0.78


def test_credit_defaults_40px_opacity_045_without_outline():
    credit = EDITOR_DEFAULTS["credit_watermark"]
    assert credit["opacity"] == 0.45
    assert float(credit.get("outline_thickness", 0)) == 0.0
    size = float(credit["size"])
    px = int(round(max(10, size * 320) / 340 * 1080))
    assert 39 <= px <= 41


def test_hook_defaults_max_eight_words_two_lines():
    hook = EDITOR_DEFAULTS["hook_style"]
    assert HOOK_MAX_LINES == 2
    assert HOOK_MAX_WORDS == 8
    assert hook["max_lines"] == 2
    assert hook["max_words"] == 8
    # size formula: font_size * 500 / 340 * width ≈ 108 @1080 (54px @540)
    px = int(max(16, float(hook["font_size"]) * 500) / 340 * 1080)
    assert 106 <= px <= 110


def test_sanitize_subtitle_strips_question_comma_period():
    assert sanitize_subtitle_token("halo?") == "halo"
    assert sanitize_subtitle_token("apa,") == "apa"
    assert sanitize_subtitle_token("stop.") == "stop"
    assert sanitize_subtitle_text("Halo? apa, stop.") == "Halo apa stop"


def test_subtitle_cues_are_max_3_words_uppercase_no_punct():
    words = [
        {"word": "Satu?", "start": 0.0, "end": 0.2},
        {"word": "dua,", "start": 0.2, "end": 0.4},
        {"word": "tiga.", "start": 0.4, "end": 0.6},
        {"word": "empat", "start": 0.6, "end": 0.8},
        {"word": "lima", "start": 0.8, "end": 1.0},
        {"word": "enam", "start": 1.0, "end": 1.2},
        {"word": "tujuh", "start": 1.2, "end": 1.4},
    ]
    cues = build_subtitle_cues({"duration": 2, "words": words, "segments": []})
    assert cues
    for cue in cues:
        n = len(cue["text"].split())
        assert 1 <= n <= 3
        assert cue["text"] == cue["text"].upper()
        assert "?" not in cue["text"]
        assert "," not in cue["text"]
        assert "." not in cue["text"]
    assert len(cues[0]["text"].split()) == 3


def test_subtitle_cue_holds_through_short_speech_gap():
    words = [
        {"word": "orang", "start": 0.0, "end": 0.3},
        {"word": "lagi", "start": 0.3, "end": 0.6},
        {"word": "bicara", "start": 0.6, "end": 0.9},
        {"word": "terus", "start": 1.5, "end": 1.75},
        {"word": "tanpa", "start": 1.75, "end": 1.9},
        {"word": "henti", "start": 1.9, "end": 2.0},
    ]
    cues = build_subtitle_cues({"duration": 2, "words": words, "segments": []})
    assert cues[0]["end"] == pytest.approx(1.5)


def test_overlapping_whisper_words_produce_non_overlapping_cues():
    words = [
        {"word": "salah", "start": 3.42, "end": 4.10},
        {"word": "aja", "start": 3.74, "end": 3.90},
        {"word": "oke", "start": 3.92, "end": 4.92},
        {"word": "gitu", "start": 4.10, "end": 4.34},
        {"word": "sama", "start": 5.72, "end": 5.96},
        {"word": "kan", "start": 5.96, "end": 6.10},
        {"word": "akhir-akhir", "start": 5.96, "end": 7.16},
        {"word": "dia", "start": 6.10, "end": 6.20},
        {"word": "kan", "start": 6.20, "end": 6.36},
    ]
    cues = build_subtitle_cues({"duration": 8, "words": words, "segments": []})
    assert all(cue["end"] <= cues[index + 1]["start"] for index, cue in enumerate(cues[:-1]))
    events = [word for cue in cues for word in cue["words"]]
    assert all(word["active_from"] < word["active_until"] for word in events)
    assert all(word["active_until"] <= events[index + 1]["active_from"] for index, word in enumerate(events[:-1]))


def test_normalize_hook_caps_eight_words_two_lines():
    text = "ini adalah hook panjang yang diucapkan penuh tanpa potong delapan kata saja"
    out = normalize_hook_text(text)
    flat = out.replace("\n", " ")
    assert len(flat.split()) == 8
    assert flat == "INI ADALAH HOOK PANJANG YANG DIUCAPKAN PENUH TANPA"
    assert out == out.upper()
    assert out.count("\n") <= 1  # max 2 lines => max 1 newline


def test_v3_locked_settings_force_new_visual_contract():
    settings = v3_locked_render_settings({"video_layout": {"mode": "split_middle"}})
    assert settings["subtitle"]["color"] == "#FFFF00"
    assert settings["subtitle"]["word_max"] == 3
    assert settings["credit_watermark"]["opacity"] == 0.45
    assert settings["hook_style"]["max_lines"] == 2
    assert settings["hook_style"]["max_words"] == 8
    assert settings["video_layout"]["mode"] == "split_middle"


def test_vertical_full_alone_gets_larger_hook_and_subtitle():
    vertical = v3_locked_render_settings({"video_layout": {"mode": "vertical_full"}})
    split = v3_locked_render_settings({"video_layout": {"mode": "split_middle"}})
    assert vertical["hook_style"]["font_size"] == 0.075
    assert vertical["subtitle"]["size"] == 0.075
    assert split["hook_style"]["font_size"] == 0.068
    assert split["subtitle"]["size"] == 0.068


def test_choose_speaker_holds_previous_when_two_active_scores_close():
    candidates = [
        {"id": 0, "score": 0.80, "crop_x": 10},
        {"id": 1, "score": 0.78, "crop_x": 400},
    ]
    chosen, conf, hold = choose_speaker(candidates, current_id=0, hold_frames_left=0)
    assert chosen == 0


def test_split_middle_uses_person_rois_not_blind_halves():
    top = {"x": 0.05, "y": 0.1, "width": 0.35, "height": 0.8}
    bottom = {"x": 0.55, "y": 0.1, "width": 0.35, "height": 0.8}
    filters, label = build_filtergraph(
        "split_middle",
        1920,
        1080,
        roi={"top": top, "bottom": bottom},
        out_w=540,
        out_h=960,
    )
    joined = ";".join(filters)
    assert "vstack=inputs=2" in joined
    assert "crop=960:1080:0:0" not in joined  # not blind left half of 1920
    assert "crop=672:864:96:108" in joined
    assert "crop=672:864:1056:108" in joined
    assert top != bottom
    assert label == "v0"


def test_split_rois_reject_same_person_scales():
    from speaker_tracking import split_rois_are_distinct

    sameish = {
        "top": {"x": 0.33, "y": 0.45, "width": 0.28, "height": 0.55},
        "bottom": {"x": 0.35, "y": 0.11, "width": 0.32, "height": 0.76},
        "count": 2,
    }
    dual_frame = {
        "top": {"x": 0.35, "y": 0.2, "width": 0.28, "height": 0.55},
        "bottom": {"x": 0.3, "y": 0.05, "width": 0.4, "height": 0.9},
        "count": 1,
    }
    distinct = {
        "top": {"x": 0.05, "y": 0.1, "width": 0.35, "height": 0.8},
        "bottom": {"x": 0.55, "y": 0.1, "width": 0.35, "height": 0.8},
        "count": 2,
    }
    assert not split_rois_are_distinct(sameish)
    assert split_rois_are_distinct(dual_frame)
    assert split_rois_are_distinct(distinct)


def test_prompt_prioritizes_funny_moments():
    from clipper_ai import AiMixin

    prompt = AiMixin.get_default_prompt()
    lower = prompt.lower()
    funny_idx = lower.find("lucu")
    conflict_idx = lower.find("konflik")
    assert funny_idx != -1
    assert funny_idx < conflict_idx or "prioritas utama" in lower
    assert "maksimal 8 kata" in lower or "maks 8 kata" in lower
    assert "2 baris" in lower
    assert "membuat penasaran" in lower
    assert '"[lucu] "' in lower
