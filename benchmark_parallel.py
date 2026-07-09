#!/usr/bin/env python3
"""
KlipKlop Parallel vs Sequential FFmpeg Benchmark
=================================================
Jalankan di VPS/machine produksi:
    python benchmark_parallel.py

Script ini membuat video sintetis sendiri (tidak butuh file asli).
Output: tabel perbandingan waktu + rekomendasi.
"""

import subprocess
import tempfile
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ── Konfigurasi ───────────────────────────────────────────
CLIP_DURATION_SEC = 30   # Durasi tiap test clip (sama dg rata-rata klip asli)
NUM_CLIPS = 3            # Simulasikan 3 clips
REPEAT = 2               # Berapa kali tiap skenario diulang (untuk avg)
RESOLUTION = "720x1280"  # Portrait 720p
# ──────────────────────────────────────────────────────────


def find_ffmpeg():
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from utils.helpers import get_ffmpeg_path
        p = get_ffmpeg_path()
        if p and Path(p).exists():
            return p
    except Exception:
        pass
    return "ffmpeg"


FFMPEG = find_ffmpeg()


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("FFmpeg error:\n" + r.stderr[-500:])


def create_test_video(path, duration=CLIP_DURATION_SEC):
    """Buat video sintetis: warna solid + tone audio."""
    _run([
        FFMPEG, "-y",
        "-f", "lavfi", "-i",
        "color=c=blue:size=" + RESOLUTION + ":rate=30:duration=" + str(duration),
        "-f", "lavfi", "-i",
        "sine=frequency=1000:duration=" + str(duration),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-c:a", "aac", "-b:a", "64k",
        "-t", str(duration), path,
    ])


def encode_clip(input_path, output_path, worker_id):
    """Satu unit kerja: re-encode + scale (simulasi portrait conversion)."""
    t0 = time.perf_counter()
    _run([
        FFMPEG, "-y", "-i", input_path,
        "-vf", "scale=" + RESOLUTION,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ])
    elapsed = time.perf_counter() - t0
    return worker_id, elapsed


def run_sequential(input_files, output_dir):
    t_total = time.perf_counter()
    for i, inp in enumerate(input_files):
        _, elapsed = encode_clip(inp, str(output_dir / ("seq_" + str(i) + ".mp4")), i + 1)
        print("    Clip " + str(i + 1) + ": " + str(round(elapsed, 1)) + "s")
    return time.perf_counter() - t_total


def run_parallel(input_files, output_dir, max_workers):
    t_total = time.perf_counter()
    futures_map = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for i, inp in enumerate(input_files):
            out = str(output_dir / ("par" + str(max_workers) + "_" + str(i) + ".mp4"))
            f = executor.submit(encode_clip, inp, out, i + 1)
            futures_map[f] = i
        for f in as_completed(futures_map):
            wid, elapsed = f.result()
            print("    Clip " + str(wid) + ": " + str(round(elapsed, 1)) + "s")
    return time.perf_counter() - t_total


def get_cpu_count():
    try:
        import multiprocessing
        return multiprocessing.cpu_count()
    except Exception:
        return "?"


def pct_vs(avg, baseline):
    diff = avg - baseline
    pct = abs(diff) / baseline * 100
    if diff < 0:
        return "LEBIH CEPAT -" + str(round(pct)) + "%"
    elif diff > 0:
        return "LEBIH LAMBAT +" + str(round(pct)) + "%"
    return "sama"


def main():
    print("=" * 58)
    print("  KlipKlop Parallel FFmpeg Benchmark")
    print("=" * 58)
    print("  FFmpeg    : " + FFMPEG)
    print("  CPU cores : " + str(get_cpu_count()))
    print("  Clips     : " + str(NUM_CLIPS) + " x " + str(CLIP_DURATION_SEC) + "s @ " + RESOLUTION)
    print("  Repeats   : " + str(REPEAT) + "x per skenario")
    print()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        print("Membuat test videos...", end=" ", flush=True)
        input_files = []
        for i in range(NUM_CLIPS):
            p = str(tmp / ("input_" + str(i) + ".mp4"))
            create_test_video(p)
            input_files.append(p)
        print("done.\n")

        results = {}

        scenarios = [
            ("Sequential", lambda d: run_sequential(input_files, d)),
            ("Parallel-2", lambda d: run_parallel(input_files, d, 2)),
            ("Parallel-3", lambda d: run_parallel(input_files, d, 3)),
        ]

        for label, fn in scenarios:
            print("Skenario: " + label)
            totals = []
            for r in range(REPEAT):
                print("  Run " + str(r + 1) + "/" + str(REPEAT) + ":")
                total = fn(tmp)
                totals.append(total)
                print("  => Total: " + str(round(total, 1)) + "s\n")
            results[label] = totals

    print("=" * 58)
    print("  HASIL BENCHMARK")
    print("=" * 58)
    avgs = {k: sum(v) / len(v) for k, v in results.items()}
    seq_avg = avgs["Sequential"]
    for name, avg in avgs.items():
        if name == "Sequential":
            tag = "(baseline)"
        else:
            tag = pct_vs(avg, seq_avg)
        print("  " + name.ljust(14) + str(round(avg, 1)).rjust(7) + "s  " + tag)

    best = min(avgs, key=avgs.get)
    print()
    print("  REKOMENDASI: Gunakan " + best)
    print("=" * 58)


if __name__ == "__main__":
    main()
