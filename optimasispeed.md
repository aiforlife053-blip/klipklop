# Optimasi Speed

## Mode: Fast CPU untuk hosting 2 CPU

Target: tetap jalan enak di local, tapi aman untuk hosting 2 CPU.

### 1. Download sections, bukan full video
- Pakai range 3 highlight saja.
- Jangan download full video kalau sudah tahu timestamp clip.
- Impact terbesar untuk waktu proses.

### 2. Clip serial, bukan 3 paralel
- Hosting 2 CPU jangan pakai 3 worker.
- Serial lebih aman dan stabil.
- Opsi local: parallel 2 kalau CPU kuat.

### 3. FFmpeg preset cepat
- Hosting: `libx264 -preset veryfast -crf 23`.
- Local: `fast` atau `veryfast`.
- 1080p hindari 

### 4. Satu pass filter
- Gabungkan portrait + subtitle + credit dalam satu render FFmpeg.
- Hindari banyak tahap encode.
- Sekarang banyak pass, itu boros waktu.

### 5. Subtitle priority
- Prioritas 1: pakai YouTube SRT kalau ada.
- Prioritas 2: local Whisper fallback jika gaada yt srt.

### 6. Hook TTS API tetap
- Gemini TTS tidak makan CPU besar.
- Kalau TTS gagal, skip hook total.
- Jangan fallback silent hook.

### 7. Quality cap hosting
- Default hosting: 480p atau 720p.
- 720p jadi batas realistis.

### 8. Cache
- Cache transcript/SRT.
- Cache highlights hasil AI.
- Cache TTS hook audio.
- Source section cache optional karena bisa makan storage besar.
- URL sama jangan proses ulang dari nol.

Struktur cache yang disarankan:

```text
cache/
  <video_id>/
    transcript.srt
    transcript.json
    highlights.<instruction_hash>.json
    sections/
      <start>-<end>.mp4
  tts/
    <hook_text_hash>.wav
```

Auto-cleanup:
- hapus cache lebih dari 7 hari, atau
- batasi total cache 5-10GB.

### 9. Progress incremental
- Clip 1 tampil begitu selesai.
- Clip 2 dan 3 lanjut background.
- Loading tetap tampil sampai semua selesai.

### 10. Config profile
- `LOCAL_MODE`: kualitas lebih tinggi, parallel 2 optional.
- `HOSTING_2CPU_MODE`: section download, serial, veryfast, 720p max.

## Target realistis 2 CPU
- 3 clips 720p: 2-5 menit.
- 3 clips 480p: 1.5-3 menit.

## Prioritas implementasi
1. Download sections.
2. FFmpeg preset veryfast + CRF 23.
3. Subtitle pakai SRT dulu.
4. Cache SRT/highlights/TTS.
5. Gabung filter jadi satu pass.
6. Profile `HOSTING_2CPU_MODE`.
