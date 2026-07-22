"""Koreksi visual V3: subtitle, credit, hook, quality-aware defaults."""
from pathlib import Path
import inspect


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
from visual_style import find_hook_name_span, hook_name_from_title, hook_tts_text, normalize_generated_hook_text, normalize_hook_text, sanitize_subtitle_text, sanitize_subtitle_token, validate_hook_text
from clipper_core import LocalClipRenderer
from clipper_core import AutoClipperCore
from clipper_export import ExportMixin, HOOK_TTS_TEMPO
from clipper_ai import ensure_five_hashtags


def test_description_gets_exactly_five_relevant_hashtags():
    description = ensure_five_hashtags(
        "Raditya membahas biaya fisioterapi.",
        "Raditya Dika bicara fisioterapi",
        "RADITYA DIKA WAJIB FISIOTERAPI!",
    )
    assert description.count("#") == 5
    assert "#Raditya" in description
    assert "#Fisioterapi" in description


def test_hook_tts_uses_ardi_with_indonesian_shorts_tuning():
    source = inspect.getsource(ExportMixin._generate_hook_tts)
    source_lower = source.lower()
    assert 'voice = "id-ID-ArdiNeural"' in source
    assert 'rate="+0%"' in source
    assert 'pitch="+2Hz"' in source
    assert 'volume="+6%"' in source
    assert "acompressor=" in source
    assert "loudnorm=" in source
    assert "edge-ardi-v10-oy-to-oi" in source
    assert '.rstrip(".!?") + "?"' not in source


def test_hook_tts_joins_leading_marked_name_without_changing_overlay():
    assert ExportMixin._tts_pronunciation_text("[ALOY] DIBOHONGI DOKTER") == "ALoi DIBOHONGI DOKTER"
    assert ExportMixin._tts_pronunciation_text("DOKTER BOHONGI [ALOY]") == "DOKTER BOHONGI ALoi"


def test_highlight_client_uses_first_backup_when_primary_is_empty(tmp_path):
    core = AutoClipperCore(
        client=None,
        output_dir=str(tmp_path),
        ai_providers={
            "highlight_finder": {
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "model": "gemini-2.5-flash",
                "api_key": "",
                "backup_api_keys": ["backup-key"],
            }
        },
    )
    assert core.highlight_client.api_key == "backup-key"
    assert len(core.highlight_clients) == 1



def test_hook_sentence_keeps_name_inside_one_readable_sentence():
    raw = "ternyata [raditya dika] hampir bangkrut"
    display = normalize_hook_text(raw)
    flat = display.replace("\n", " ")
    assert flat == "TERNYATA RADITYA DIKA HAMPIR BANGKRUT!"
    assert len(flat.split()) <= 6
    assert display.count("\n") <= 3
    assert ":" not in flat
    assert "[" not in flat and "]" not in flat
    assert hook_tts_text(raw) == flat
    span = find_hook_name_span(flat.split(), original_text=raw)
    assert span == (1, 3)


def test_generated_hook_keeps_required_inline_name_marker_for_renderer():
    raw = "TERNYATA [ALDI TAHER] BUKAN JIGONG!"
    stored = normalize_generated_hook_text(raw)
    assert stored == raw
    words = normalize_hook_text(stored).replace("\n", " ").split()
    assert find_hook_name_span(words, original_text=stored) == (1, 3)


def test_generated_hook_rewrites_unnatural_sebut_isi_phrase_generically():
    assert normalize_generated_hook_text("[ALDI TAHER] SEBUT ISI DARAH SETAN") == "[ALDI TAHER] BILANG DARAH BERISI SETAN"
    assert normalize_generated_hook_text("[ALDI TAHER] SEBUT DARAH BERISI SETAN") == "[ALDI TAHER] BILANG DARAH BERISI SETAN"
    assert normalize_generated_hook_text("[BUDI] SEBUT ISI TAS BOM") == "[BUDI] BILANG TAS BERISI BOM"


def test_generated_hook_accepts_seven_words_but_rejects_eight():
    import pytest

    assert normalize_generated_hook_text("[ALDI TAHER] BILANG DARAH MANUSIA BERISI SETAN")
    with pytest.raises(ValueError, match="maksimal 7 kata"):
        normalize_generated_hook_text("[ALDI TAHER] BILANG DARAH MANUSIA TERNYATA BERISI SETAN")


def test_generated_declarative_hook_does_not_require_terminal_punctuation():
    raw = "ALASAN [ALDI TAHER] SERING TERLAMBAT"
    assert normalize_generated_hook_text(raw) == raw


def test_generated_hook_rejects_literal_name_placeholder():
    with pytest.raises(ValueError, match="nama orang nyata"):
        normalize_generated_hook_text("PENYESALAN TERBESAR [NAMA] SELAMA PANDEMI COVID")


def test_prompt_requires_name_but_does_not_force_it_to_the_front():
    from clipper_ai import AiMixin

    prompt = AiMixin.get_default_prompt().lower()
    assert "nama orang wajib ada" in prompt
    assert "nama boleh berada di posisi mana pun" in prompt
    assert "wajib diawali [nama" not in prompt
    assert "satu kalimat utuh, natural" in prompt


def test_prompt_requires_contextual_hook_not_empty_question():
    from clipper_ai import AiMixin

    prompt = AiMixin.get_default_prompt().lower()
    assert "hook kontekstual yang memicu rasa penasaran" in prompt
    assert "pertanyaan boleh jika jawabannya benar-benar ada" in prompt
    assert "kata penentu konteks bersifat opsional" in prompt
    assert "dilarang menambah" in prompt
    assert "alasan [aldi taher] sering terlambat" in prompt
    assert "kenapa [aldi taher] telat terus" in prompt
    assert "wajib akhiri dengan ?" not in prompt


def test_prompt_requires_spoken_shorts_hook_instead_of_stiff_news_language():
    from clipper_ai import AiMixin

    prompt = AiMixin.get_default_prompt().lower()
    assert "bahasa lisan shorts" in prompt
    assert "ucapan teman saat menceritakan momen" in prompt
    assert "[komeng] jailnya kebangetan" in prompt
    assert "kejailan [komeng] yang sangat parah" in prompt
    assert "yang sangat parah" in prompt
    assert "hindari bahasa berita" in prompt


def test_prompt_requires_curiosity_without_inventing_context():
    from clipper_ai import AiMixin

    prompt = AiMixin.get_default_prompt().lower()
    assert "lah kok bisa" in prompt
    assert "kontras, pengakuan, akibat, salah paham, atau punchline" in prompt
    assert "ringkasan datar" in prompt
    assert "pertanyaan boleh" in prompt
    assert "jawabannya benar-benar ada dalam klip" in prompt
    assert "curiosity gap kosong" in prompt


def test_hook_removes_emoji_from_overlay_and_tts():
    raw = "ASILA MAISA DITUDUH JADI SELINGKUHAN 😮"
    assert "😮" not in normalize_hook_text(raw)
    assert "😮" not in hook_tts_text(raw)


def test_hook_keeps_natural_question_or_exclamation():
    assert normalize_hook_text("ASILA MAISA DITUDUH SELINGKUHAN?").endswith("?")
    assert hook_tts_text("TERNYATA DIA BOHONG!").endswith("!")
    assert normalize_hook_text("ASILA MAISA BONGKAR RAHASIA").endswith("!")


def test_tts_removes_comma_after_full_name():
    assert LocalClipRenderer._tts_text("ASILA MAISA, BONGKAR RAHASIA!") == "ASILA MAISA BONGKAR RAHASIA!"


def test_user_hook_above_seven_words_is_rejected_not_truncated():
    with pytest.raises(ValueError, match="maksimal 7 kata"):
        validate_hook_text("satu dua tiga empat lima enam tujuh delapan sembilan")


def test_user_hook_keeps_inline_name_marker_for_renderer():
    stored = validate_hook_text("[ALDI TAHER] TENANG HADAPI KANKER")
    assert "[ALDI TAHER]" in stored
    words = normalize_hook_text(stored).replace("\n", " ").split()
    assert find_hook_name_span(words, original_text=stored) == (0, 2)


def test_subtitle_hyphenated_repetition_becomes_separate_words_with_two_word_cap():
    transcript = {
        "duration": 3.0,
        "words": [
            {"word": "muter-muter", "start": 0.0, "end": 1.2},
            {"word": "tuh", "start": 1.2, "end": 1.5},
            {"word": "sebenernya", "start": 1.5, "end": 2.0},
        ],
        "segments": [],
    }
    cues = build_subtitle_cues(transcript)
    assert [cue["text"] for cue in cues] == ["muter muter", "tuh sebenernya"]
    assert all(len(cue["words"]) <= 2 for cue in cues)


def test_subtitle_drops_same_word_alternative_but_keeps_later_repetition():
    transcript = {
        "duration": 2.0,
        "words": [
            {"word": "single", "start": 0.0, "end": 0.24},
            {"word": "Single", "start": 0.0, "end": 0.64},
            {"word": "gak", "start": 0.24, "end": 0.42},
            {"word": "gak", "start": 0.64, "end": 0.8},
        ],
        "segments": [],
    }
    text = " ".join(cue["text"] for cue in build_subtitle_cues(transcript))
    assert text == "single gak gak"


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


def test_segment_only_subtitles_are_split_to_max_two_words():
    cues = build_subtitle_cues({
        "duration": 6,
        "words": [],
        "segments": [{"text": "one two three four five six", "start": 0.0, "end": 6.0}],
    })
    assert [cue["text"] for cue in cues] == ["one two", "three four", "five six"]
    assert all(len(cue["text"].split()) <= 2 for cue in cues)


def test_legacy_colon_hook_still_becomes_one_sentence():
    display = normalize_hook_text("Raditya Dika: blabla lucu banget")
    assert display.replace("\n", " ") == "RADITYA DIKA BLABLA LUCU BANGET!"
    assert ":" not in display


def test_hook_detects_honorific_name_without_internal_marker():
    text = "DETIK-DETIK DR. TIRTA PINGSAN DI JALUR PACITAN"
    words = normalize_hook_text(text).replace("\n", " ").split()
    assert find_hook_name_span(words, original_text=text) == (1, 3)


def test_hook_overlay_keeps_all_six_long_words(tmp_path, monkeypatch):
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
    words = " ".join(chr(65 + index) * 100 for index in range(6))
    renderer._create_hook_overlay(words, 540, 960, tmp_path / "long-hook.png")
    assert "".join(drawn) == words.replace(" ", "") + "!"


def test_hook_mixed_font_words_share_baseline(tmp_path, monkeypatch):
    from PIL import ImageDraw

    baselines = []
    real_draw = ImageDraw.Draw

    class RecordingDraw:
        def __init__(self, image):
            self.inner = real_draw(image)

        def textbbox(self, *args, **kwargs):
            return self.inner.textbbox(*args, **kwargs)

        def text(self, xy, text, *args, **kwargs):
            baselines.append((text, xy[1], kwargs.get("anchor")))
            return self.inner.text(xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw, "Draw", RecordingDraw)
    renderer = object.__new__(LocalClipRenderer)
    renderer.hook_style_settings = {"font_size": 0.075, "max_lines": 2}
    renderer._create_hook_overlay(
        "[ASILA MAISA] DITUDUH JADI SELINGKUHAN RIZKY BILLAR",
        1080,
        1920,
        tmp_path / "baseline.png",
    )
    first_line = baselines[:4]
    assert {y for _, y, _ in first_line} == {first_line[0][1]}
    assert {anchor for _, _, anchor in first_line} == {"ls"}


def test_hook_bold_font_does_not_add_synthetic_outline(tmp_path, monkeypatch):
    from PIL import ImageDraw

    strokes = []
    real_draw = ImageDraw.Draw

    class RecordingDraw:
        def __init__(self, image):
            self.inner = real_draw(image)

        def textbbox(self, *args, **kwargs):
            return self.inner.textbbox(*args, **kwargs)

        def text(self, *args, **kwargs):
            strokes.append(kwargs.get("stroke_width"))
            return self.inner.text(*args, **kwargs)

    monkeypatch.setattr(ImageDraw, "Draw", RecordingDraw)
    renderer = object.__new__(LocalClipRenderer)
    renderer.hook_style_settings = {"font_weight": 700, "outline_thickness": 1.0}
    renderer._create_hook_overlay("HOOK LEBIH TIPIS", 1080, 1920, tmp_path / "thin.png")
    assert strokes and set(strokes) == {3}


def test_hook_overlay_preserves_inline_sentence_word_order(tmp_path, monkeypatch):
    from PIL import ImageDraw

    drawn = []
    real_draw = ImageDraw.Draw

    class RecordingDraw:
        def __init__(self, image):
            self.inner = real_draw(image)
        def textbbox(self, *args, **kwargs):
            return self.inner.textbbox(*args, **kwargs)
        def text(self, xy, text, *args, **kwargs):
            drawn.append(text)
            return self.inner.text(xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw, "Draw", RecordingDraw)
    renderer = object.__new__(LocalClipRenderer)
    renderer.hook_style_settings = {"font_size": 0.075, "max_lines": 4}
    renderer._create_hook_overlay("KENAPA [ALDI TAHER] TELAT TERUS?!", 1080, 1920, tmp_path / "order.png")
    assert "".join(drawn) == "KENAPAALDITAHERTELATTERUS?!"


def test_hook_name_is_cyan_when_inline(tmp_path):
    from PIL import Image

    renderer = object.__new__(LocalClipRenderer)
    renderer.hook_style_settings = {"font_size": 0.075, "max_lines": 4}
    output = tmp_path / "inline-name-cyan.png"
    renderer._create_hook_overlay("TERNYATA [ZED QIX] BOHONG!", 540, 960, output)
    pixels = Image.open(output).convert("RGBA").getdata()
    assert any(r < 100 and g > 170 and b > 190 and a > 200 for r, g, b, a in pixels)


def test_hook_name_is_only_slightly_larger_than_body(tmp_path, monkeypatch):
    from PIL import ImageDraw

    sizes = {}
    real_draw = ImageDraw.Draw

    class RecordingDraw:
        def __init__(self, image):
            self.inner = real_draw(image)
        def textbbox(self, *args, **kwargs):
            return self.inner.textbbox(*args, **kwargs)
        def text(self, xy, text, *args, **kwargs):
            sizes.setdefault(text, kwargs["font"].size)
            return self.inner.text(xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw, "Draw", RecordingDraw)
    renderer = object.__new__(LocalClipRenderer)
    renderer.hook_style_settings = {"font_size": 0.075, "max_lines": 4}
    renderer._create_hook_overlay("TERNYATA [ZED QIX] BOHONG!", 1080, 1920, tmp_path / "name-size.png")
    assert 1.1 <= sizes["Z"] / sizes["B"] <= 1.25


def test_hook_overlay_highlights_inline_name_blue(tmp_path):
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
    assert any(r < 100 and g > 170 and b > 190 and a > 200 for r, g, b, a in pixels)
    assert any(r > 220 and g > 220 and b > 220 and a > 200 for r, g, b, a in pixels)


def test_subtitle_defaults_target_108px_and_reference_blue():
    sub = EDITOR_DEFAULTS["subtitle"]
    assert sub["color"] == "#2CCDE7"
    assert sub["text_transform"] == "none"
    assert sub["letter_spacing"] == pytest.approx(1.5 / 1080)
    assert sub["font_family"] == "Poppins"
    assert sub["font_weight"] == 700
    assert sub["word_min"] == 2
    assert sub["word_max"] == 2
    assert SUBTITLE_WORD_MIN == 2
    assert SUBTITLE_WORD_MAX == 2
    # size formula: size * 500 / 340 * width ≈ 108 @1080
    size = float(sub["size"])
    px = int(max(12, size * 500) / 340 * 1080)
    assert 106 <= px <= 110
    outline_px = int(round(float(sub["outline_thickness"]) / 340 * 1080))
    assert 5 <= outline_px <= 7
    assert sub["position_y"] == 0.78


def test_credit_defaults_40px_opacity_045_without_outline():
    credit = EDITOR_DEFAULTS["credit_watermark"]
    assert credit["opacity"] == 0.45
    assert float(credit.get("outline_thickness", 0)) == 0.0
    assert credit["letter_spacing"] == pytest.approx(0.5 / 1080)
    size = float(credit["size"])
    px = int(round(max(10, size * 320) / 340 * 1080))
    assert 39 <= px <= 41


def test_hook_defaults_max_seven_words_four_lines():
    hook = EDITOR_DEFAULTS["hook_style"]
    assert HOOK_MAX_LINES == 4
    assert HOOK_MAX_WORDS == 7
    assert hook["max_lines"] == 4
    assert hook["max_words"] == 7
    # compact hook: ≈111px @1080 (56px @540)
    px = int(max(16, float(hook["font_size"]) * 500) / 340 * 1080)
    assert 110 <= px <= 112
    assert hook["outline_thickness"] == pytest.approx(8 * 340 / 1080)


def test_tts_pronunciation_keeps_jigong_overlay_but_guides_final_ng():
    assert LocalClipRenderer._tts_text("[ALDI TAHER] BAHAS JIGONG!") == "ALDI TAHER BAHAS JIGONG!"
    assert "ji-gong" in LocalClipRenderer._tts_pronunciation_text("ALDI TAHER BAHAS JIGONG!").lower()


def test_sanitize_subtitle_strips_question_comma_period():
    assert sanitize_subtitle_token("halo?") == "halo"
    assert sanitize_subtitle_token("apa,") == "apa"
    assert sanitize_subtitle_token("stop.") == "stop"
    assert sanitize_subtitle_text("Halo? apa, stop.") == "Halo apa stop"


def test_subtitle_cues_are_max_2_words_no_punct():
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
        assert 1 <= n <= 2
        assert "?" not in cue["text"]
        assert "," not in cue["text"]
        assert "." not in cue["text"]
    assert len(cues[0]["text"].split()) == 2
    assert cues[0]["text"] == "Satu dua"


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
    assert all(len(cue["text"].split()) <= 2 for cue in cues)
    assert cues[0]["end"] == pytest.approx(cues[1]["start"])


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


def test_normalize_hook_caps_seven_words_four_lines():
    text = "ini adalah hook panjang yang diucapkan penuh tanpa potong delapan kata saja"
    out = normalize_hook_text(text)
    flat = out.replace("\n", " ")
    assert len(flat.split()) == 7
    assert flat == "INI ADALAH HOOK PANJANG YANG DIUCAPKAN PENUH!"
    assert out == out.upper()
    assert out.count("\n") <= 3


def test_v3_locked_settings_force_new_visual_contract():
    settings = v3_locked_render_settings({"video_layout": {"mode": "split_middle"}})
    assert settings["subtitle"]["color"] == "#2CCDE7"
    assert settings["subtitle"]["word_max"] == 2
    assert settings["credit_watermark"]["opacity"] == 0.45
    assert settings["hook_style"]["max_lines"] == 4
    assert settings["hook_style"]["max_words"] == 7
    assert settings["video_layout"]["mode"] == "split_middle"


def test_vertical_full_uses_dense_chest_hook_and_108px_subtitle():
    vertical = v3_locked_render_settings({"video_layout": {"mode": "vertical_full"}})
    split = v3_locked_render_settings({"video_layout": {"mode": "split_middle"}})
    assert vertical["hook_style"]["font_size"] == 0.070
    assert vertical["hook_style"]["letter_spacing"] == pytest.approx(-1.5 / 1080)
    assert vertical["hook_style"]["position_y"] == 0.62
    assert vertical["subtitle"]["size"] == 0.068
    assert vertical["subtitle"]["text_transform"] == "none"
    assert vertical["subtitle"]["outline_thickness"] == 2.0
    assert vertical["subtitle"]["letter_spacing"] == pytest.approx(1.5 / 1080)
    assert split["hook_style"]["font_size"] == 0.070
    assert split["subtitle"]["size"] == 0.068
    assert split["subtitle"]["text_transform"] == "none"


def test_choose_speaker_holds_previous_when_two_active_scores_close():
    candidates = [
        {"id": 0, "score": 0.80, "crop_x": 10, "mouth": 0.30},
        {"id": 1, "score": 0.78, "crop_x": 400, "mouth": 0.28},
    ]
    chosen, conf, hold, quiet = choose_speaker(candidates, current_id=0, hold_frames_left=0)
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


def test_incomplete_highlight_tail_is_rejected_before_render():
    from clipper_ai import highlight_ends_on_complete_thought

    transcript = "\n".join([
        "[00:00:00,000 - 00:00:04,000] Gue menerima bahwa gue",
        "[00:00:04,000 - 00:00:08,000] semakin tua harus",
        "[00:00:08,000 - 00:00:12,000] lebih menjaga kesehatan.",
    ])
    assert not highlight_ends_on_complete_thought(transcript, 8.0)
    assert highlight_ends_on_complete_thought(transcript, 12.0)


def test_highlight_tail_without_sentence_ending_is_rejected_even_after_noun():
    from clipper_ai import highlight_ends_on_complete_thought

    transcript = "\n".join([
        "[00:00:00,000 - 00:00:04,000] setiap manusia punya hal-hal",
        "[00:00:04,000 - 00:00:08,000] yang bisa dikagumi.",
    ])
    assert not highlight_ends_on_complete_thought(transcript, 4.0)
    assert highlight_ends_on_complete_thought(transcript, 8.0)


def test_prefilter_is_only_for_ai_prompt_not_endpoint_validation():
    from clipper_ai import AiMixin

    core = object.__new__(AiMixin)
    core._prefilter_transcript_for_ai = lambda _transcript, max_chars=35000: "FILTERED"
    captured = {}
    core._find_highlights_single = lambda transcript, _info, _count, allow_chunking=True, validation_transcript=None: captured.update(
        prompt=transcript, validation=validation_transcript
    ) or []
    core.log = lambda *_args: None
    full = "[00:00:00,000 - 00:00:04,000] setup\n[00:00:04,000 - 00:00:08,000] payoff."
    core.find_highlights(full, {}, 1)
    assert captured == {"prompt": "FILTERED", "validation": full}


def test_highlight_tail_extends_to_next_complete_segment_within_hard_max():
    from clipper_ai import align_highlight_end

    transcript = "\n".join([
        "[00:00:00,000 - 00:00:04,000] Gue menerima bahwa gue",
        "[00:00:04,000 - 00:00:08,000] semakin tua harus",
        "[00:00:08,000 - 00:00:10,000] menjaga kesehatan.",
    ])
    assert align_highlight_end(transcript, 0.0, 8.0, 10.0) == 10.0
    assert align_highlight_end(transcript, 0.0, 8.0, 9.0) is None


def test_highlight_endpoint_rejects_overlapping_dialog_still_crossing_cut():
    from clipper_ai import align_highlight_end, highlight_ends_on_complete_thought

    transcript = "\n".join([
        "[00:00:00,000 - 00:00:04,000] biar darahnya",
        "[00:00:04,000 - 00:00:08,000] bersih ya.",
        "[00:00:06,000 - 00:00:10,000] keren nih kan bilang",
        "[00:00:10,000 - 00:00:12,000] masyaallah.",
    ])
    assert not highlight_ends_on_complete_thought(transcript, 8.0)
    assert align_highlight_end(transcript, 0.0, 4.0, 12.0) == 12.0


def test_highlight_extension_considers_segment_that_started_before_cut():
    from clipper_ai import align_highlight_end

    transcript = "\n".join([
        "[00:00:00,000 - 00:00:08,000] Setup belum selesai",
        "[00:00:07,000 - 00:00:10,000] Jawaban selesai.",
    ])
    assert align_highlight_end(transcript, 0.0, 8.0, 12.0) == 10.0


def test_prompt_prioritizes_funny_moments():
    from clipper_ai import AiMixin

    prompt = AiMixin.get_default_prompt()
    lower = prompt.lower()
    funny_idx = lower.find("lucu")
    informative_idx = lower.find("informatif")
    emotional_idx = lower.find("emosional")
    assert -1 < funny_idx < informative_idx < emotional_idx
    assert "utamakan emosi & konflik dibanding edukasi" not in lower
    assert "maksimal 7 kata" in lower or "maks 7 kata" in lower
    assert "nama sedikit lebih besar dan cyan" in lower
    assert "memberi konteks inti klip" in lower
    assert '"[lucu] "' in lower
    assert '"[informatif] "' in lower
    assert '"[emosional] "' in lower


def test_highlight_priority_is_funny_then_informative_then_emotional():
    from clipper_ai import rank_highlights_by_priority

    highlights = [
        {"title": "curhat", "description": "[EMOSIONAL] cerita berat", "virality_score": 10},
        {"title": "tips", "description": "[INFORMATIF] cara berguna", "virality_score": 5},
        {"title": "punchline", "description": "[LUCU] setup dan payoff", "virality_score": 4},
    ]

    ranked = rank_highlights_by_priority(highlights)

    assert [item["title"] for item in ranked] == ["punchline", "tips", "curhat"]
    assert [item["description"] for item in ranked] == ["setup dan payoff", "cara berguna", "cerita berat"]
    assert [item["content_category"] for item in ranked] == ["LUCU", "INFORMATIF", "EMOSIONAL"]


def test_only_funny_hook_gets_rendered_laughing_emoji():
    assert ExportMixin._hook_overlay_text("[ALOY] DIBOHONGI DOKTER", "LUCU").endswith(" 🤣")
    assert ExportMixin._hook_overlay_text("[ALOY] DIBOHONGI DOKTER", "INFORMATIF") == "[ALOY] DIBOHONGI DOKTER"
    assert ExportMixin._hook_overlay_text("[ALOY] DIBOHONGI DOKTER", "EMOSIONAL") == "[ALOY] DIBOHONGI DOKTER"


def test_unmarked_highlight_is_last_fallback_even_with_high_score():
    from clipper_ai import rank_highlights_by_priority

    ranked = rank_highlights_by_priority([
        {"title": "unknown", "description": "tanpa kategori", "virality_score": 10},
        {"title": "info", "description": "[INFORMATIF] insight", "virality_score": 1},
    ])

    assert [item["title"] for item in ranked] == ["info", "unknown"]


def test_missing_funny_category_requires_specialized_humor_retry():
    from clipper_ai import needs_humor_retry

    assert needs_humor_retry([{"description": "[INFORMATIF] insight"}])
    assert not needs_humor_retry([{"description": "[LUCU] setup dan payoff"}])


def test_humor_retry_asks_for_funny_candidates_only():
    import json
    from types import SimpleNamespace
    from clipper_ai import AiMixin

    captured = {}

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps([
                {"title": "punchline", "description": "[LUCU] setup dan payoff"}
            ])))])

    ai = object.__new__(AiMixin)
    ai.highlight_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    ai.model = "test-model"
    ai.temperature = 0

    result = ai._retry_humor_candidates("TRANSCRIPT UTUH", 2)

    assert result[0]["description"].startswith("[LUCU]")
    retry_prompt = captured["messages"][0]["content"].lower()
    assert "khusus momen lucu" in retry_prompt
    assert "setup" in retry_prompt and "payoff" in retry_prompt
