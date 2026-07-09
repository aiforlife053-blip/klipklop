# edge-tts Hook TTS Plan

**Goal:** jadikan `edge-tts` TTS utama untuk hook, hapus Gemini TTS, fallback gagal = skip hook.

## Scope

- Project pribadi.
- Hanya hook voice.
- Caption/transcript/highlight pipeline tidak diganti.
- Tidak tambah provider/config besar.

## Files

- Modify: `clipper_export.py`
  - Hapus `_generate_gemini_tts()`.
  - Tambah `_generate_edge_tts(hook_text: str) -> str`.
  - Ubah `add_hook_with_progress()` agar pakai edge-tts.
- Modify: `clipper_core.py`
  - Hapus default Gemini TTS model.
  - Set default `tts_voice` ke voice edge-tts Indonesia.
- Modify: `config/config_manager.py`
  - Hapus default Gemini hook model bila hanya dipakai untuk TTS.
  - Set default hook voice edge-tts.
- Possibly modify: `job_manager.py`
  - Bersihkan `hook_model` jika sudah tidak dipakai.
  - Simpan `hook_voice` sebagai voice edge-tts.
- Possibly modify: Python dependency file, jika ada.
  - Tambah `edge-tts`.

## Default Voice

Use one:

```text
id-ID-ArdiNeural
id-ID-GadisNeural
```

Recommended default:

```text
id-ID-ArdiNeural
```

## Task 1: Dependency

- [ ] Cari dependency Python file:

```powershell
Get-ChildItem -Recurse -File -Include requirements*.txt,pyproject.toml,setup.py,setup.cfg
```

- [ ] Tambah dependency minimal:

```text
edge-tts
```

- [ ] Jangan tambah wrapper package lain.

## Task 2: Replace Gemini Generator

- [ ] Di `clipper_export.py`, hapus:

```python
def _generate_gemini_tts(self, hook_text: str) -> str:
```

- [ ] Tambah generator edge-tts:

```python
    async def _generate_edge_tts_async(self, hook_text: str, output_path: str) -> None:
        import edge_tts
        voice = getattr(self, "tts_voice", "id-ID-ArdiNeural") or "id-ID-ArdiNeural"
        communicate = edge_tts.Communicate(hook_text, voice)
        await communicate.save(output_path)

    def _generate_edge_tts(self, hook_text: str) -> str:
        cache_root = Path(os.environ.get("KLIPKLOP_CACHE_DIR") or self.output_dir.parent / "cache") / "tts"
        cache_root.mkdir(parents=True, exist_ok=True)
        voice = getattr(self, "tts_voice", "id-ID-ArdiNeural") or "id-ID-ArdiNeural"
        cache_file = cache_root / f"{hashlib.sha1((voice + hook_text).encode('utf-8')).hexdigest()}.mp3"
        if cache_file.exists():
            self.log("  ✓ Using cached hook TTS")
            return str(cache_file)
        import asyncio
        asyncio.run(self._generate_edge_tts_async(hook_text, str(cache_file)))
        return str(cache_file)
```

## Task 3: Hook Flow

- [ ] Di `add_hook_with_progress()`, ganti Gemini branch:

```python
        if getattr(self, "tts_api_key", ""):
            try:
                tts_file = self._generate_gemini_tts(hook_text)
            except Exception as e:
                self.log(f"  ⊘ Hook skipped; Gemini TTS failed: {e}")
                return 0
```

- [ ] Menjadi:

```python
        try:
            tts_file = self._generate_edge_tts(hook_text)
        except Exception as e:
            self.log(f"  ⊘ Hook skipped; edge-tts failed: {e}")
            return 0
```

- [ ] Hapus branch `elif self.tts_client:` kalau sudah tidak dipakai.
- [ ] Hapus final branch `else: Hook skipped; Gemini TTS API key empty`.
- [ ] Biarkan probing duration FFmpeg tetap sama.

## Task 4: Core Defaults

- [ ] Di `clipper_core.py`, ubah default hook voice:

```python
self.tts_voice = tts_config.get("voice", "id-ID-ArdiNeural")
```

- [ ] Hapus ketergantungan `tts_api_key` untuk hook TTS:

```python
self.tts_api_key = ""
```

- [ ] Hapus default model Gemini untuk hook jika tidak dipakai:

```python
self.tts_model = ""
```

## Task 5: Config/Settings Cleanup

- [ ] Di `config/config_manager.py`, cari semua:

```text
gemini-3.1-flash-tts-preview
Fenrir
hook_maker
```

- [ ] Ganti default voice:

```python
"voice": "id-ID-ArdiNeural"
```

- [ ] Hapus/default kosongkan model TTS jika cuma untuk Gemini:

```python
"model": ""
```

- [ ] Di `job_manager.py`, cari:

```text
hook_model
hook_voice
```

- [ ] Jika UI masih mengirim `hook_model`, simpan tapi abaikan supaya kompatibel.
- [ ] `hook_voice` tetap disimpan sebagai edge-tts voice string.

## Task 6: Tests

- [ ] Tambah test kecil jika test infra sudah ada.
- [ ] Minimal check import/compile:

```powershell
python -m compileall .
```

- [ ] Run backend tests:

```powershell
pytest
```

- [ ] Kalau frontend tersentuh:

```powershell
npm run build
npm run lint
```

Run from:

```text
frontend
```

## Acceptance Criteria

- Hook TTS pakai `edge-tts` tanpa API key.
- Gemini TTS code hilang dari hook path.
- Kalau edge-tts gagal, video tetap diproses tanpa hook.
- Cache TTS tetap jalan.
- Existing caption/transcript tidak berubah.
- Tests/compile pass.
