# Plan 5

1. Riwayat: card mengikuti panel masing-masing, bukan melebar bebas.
2. Riwayat panel Berhasil: tombol Hapus untuk klip yang sudah upload YouTube harus masuk panel Terhapus.
3. Riwayat panel Berhasil: Hapus juga menghapus video di YouTube, bukan hanya menghilangkan dari UI.
4. Riwayat panel Terhapus: tampilkan klip yang status upload-nya `deleted`.
5. Page Sosmed: ganti ikon teks `YT` dengan logo YouTube asli.
6. Page Sosmed: ganti ikon teks `TT` dengan logo TikTok asli.
7. Console: catat aktivitas tambah video ke queue.
8. Console: catat aktivitas hapus klip lokal.
9. Console: catat aktivitas hapus video YouTube.
10. Console: catat aktivitas upload YouTube.
11. Console: catat aktivitas klik download.
12. Console: catat semua aktivitas penting aplikasi.
13. Settings: hapus field subtitle `Posisi`.
14. Settings: hapus field subtitle `Margin`.
15. Card klip hasil generate: hapus tombol download, sisakan tambah ke queue dan hapus.
16. Backend: gunakan endpoint YouTube delete yang sudah ada untuk hapus video dari YouTube.
17. Frontend: tambah handler `data-youtube-delete`.
18. Frontend: tambah helper activity log minimal, kirim ke backend.
19. Backend: tambah endpoint activity log minimal, masuk ke log console.
20. Verifikasi lint/typecheck/test sesuai command yang tersedia.
21. Hosting security: proteksi app dengan Cloudflare Access.
22. Cloudflare Access: hanya email pribadi yang boleh login.
23. Cloudflare Access: lindungi seluruh domain dan semua `/api/*`.
24. Dokumentasikan setup Cloudflare Tunnel/Access untuk deployment simpan dalam file cloudflare.md
