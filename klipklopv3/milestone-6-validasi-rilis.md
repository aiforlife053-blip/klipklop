# Milestone 6 — Validasi Rilis

## Tujuan

Membuktikan hasil visual, fungsi, keamanan, performa, dan regression V3 sebelum dianggap siap dipakai.

## Dependensi

- Milestone 1–5 selesai.
- `contoh_video.mp4` tersedia sebagai referensi hook, subtitle, dan perpindahan pembicara.
- Fixture landscape, portrait, gaming, dan akun YouTube test tersedia.

## Task

1. Render smoke ketiga mode dengan source representatif.
2. Bandingkan hook, subtitle, dan speaker tracking dengan `contoh_video.mp4`.
3. Uji Vertical Full landscape multi-speaker dan source portrait.
4. Uji Gaming auto-detect sukses dan fallback manual setelah restart.
5. Uji Split Middle serta rejection portrait untuk Gaming/Split.
6. Uji batch 3/5 klip dengan satu kegagalan.
7. Uji edit hook, rerender, schedule, upload sukses, upload gagal, retry, cancel, dan delete.
8. Benchmark waktu analisis/render, realtime factor, memory, temp storage, dan retry cache.
9. Jalankan seluruh backend/frontend test, lint, typecheck/build, compile, dan security checks.
10. Perbarui README dengan workflow V3 dan konfigurasi yang masih berlaku.
11. Review git diff agar tidak ada secret, media besar, build artifact, atau perubahan di luar V3.

## Testing Checklist

- [ ] Semua output beresolusi 1080x1920 dan playable.
- [ ] Audio, TTS, hook, subtitle, dan video sinkron.
- [ ] Hook maksimal 8 kata/2 baris dan slide kiri sesuai timing.
- [ ] Subtitle visual sesuai aturan V3.
- [ ] Vertical Full tidak goyang saat confidence rendah.
- [ ] Gaming menghasilkan 1/3 facecam dan 2/3 gameplay tengah.
- [ ] Split Middle menghasilkan kiri atas/kanan bawah.
- [ ] Job fallback, schedule, hasil, dan error bertahan setelah restart.
- [ ] Satu kegagalan tidak menghentikan sibling clip.
- [ ] Card hasil memiliki border dan aksi benar.
- [ ] Backend `pytest` lulus.
- [ ] Frontend Vitest, lint, dan build lulus.
- [ ] Python `compileall` dan dependency checks lulus.
- [ ] Tidak ada regression security atau bottleneck berarti.

## Perintah Verifikasi

```powershell
py -3.12 -m pytest -q
py -3.12 -m compileall -q .
```

Dari folder `frontend`:

```powershell
npm test -- --run
npm run lint
npm run build
```

## Acceptance Criteria

- Semua kebutuhan pada `plan.md` terbukti lewat test atau smoke test.
- Ketiga mode stabil pada input yang didukung dan menolak input tidak valid dengan pesan jelas.
- Pipeline lebih sederhana, tidak bergantung editor lama, dan tidak punya regression berarti.
- Dokumentasi sesuai perilaku aplikasi aktual.
- Rilis tidak memuat secret, file sementara, media fixture besar, atau dependency mati.
