import heapq
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class RenderAttempt:
    owner: str
    clip_id: str
    attempt_id: str
    snapshot: dict[str, Any]
    digest: str
    profile: str


@dataclass
class PreviewStatus:
    state: str = "queued"
    stage: str = "Menunggu render"
    progress: float = 0.0
    elapsed_seconds: float = 0.0
    stream_url: str = ""
    error: str = ""
    started_at: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)


class RenderScheduler:
    def __init__(self, max_workers: int = 1):
        self.max_workers = max(1, int(max_workers))
        self._lock = threading.RLock()
        self._queue: list[tuple[int, int, RenderAttempt, Callable]] = []
        self._attempts: dict[tuple[str, str, str], PreviewStatus] = {}
        self._latest: dict[tuple[str, str], str] = {}
        self._sequence = 0
        self._wake = threading.Condition(self._lock)
        for index in range(self.max_workers):
            threading.Thread(target=self._worker, daemon=True, name=f"clip-render-{index}").start()

    def submit(self, attempt: RenderAttempt, run: Callable[[RenderAttempt, threading.Event, Callable[[str, float], None]], Path], priority: int = 20) -> str:
        with self._wake:
            owner_clip = (attempt.owner, attempt.clip_id)
            prior_id = self._latest.get(owner_clip)
            if attempt.profile == "preview_fast" and prior_id:
                prior = self._attempts.get((attempt.owner, attempt.clip_id, prior_id))
                if prior and prior.state in {"queued", "rendering"}:
                    prior.cancel.set()
            self._latest[owner_clip] = attempt.attempt_id
            self._attempts[(attempt.owner, attempt.clip_id, attempt.attempt_id)] = PreviewStatus()
            self._sequence += 1
            heapq.heappush(self._queue, (priority, self._sequence, attempt, run))
            self._wake.notify()
        return attempt.attempt_id

    def status(self, owner: str, clip_id: str, attempt_id: str) -> dict[str, Any] | None:
        with self._lock:
            status = self._attempts.get((owner, clip_id, attempt_id))
            if status is None:
                return None
            elapsed = time.monotonic() - status.started_at if status.started_at else status.elapsed_seconds
            return {"state": status.state, "stage": status.stage, "progress": status.progress, "elapsed_seconds": round(elapsed, 3), "stream_url": status.stream_url, "error": status.error}

    def cancel(self, owner: str, clip_id: str, attempt_id: str) -> bool:
        with self._lock:
            status = self._attempts.get((owner, clip_id, attempt_id))
            if status is None or status.state in {"ready", "error", "cancelled"}:
                return False
            status.cancel.set()
            if status.state == "queued":
                status.state, status.stage = "cancelled", "Dibatalkan"
            return True

    def _worker(self):
        while True:
            with self._wake:
                while not self._queue:
                    self._wake.wait()
                _, _, attempt, run = heapq.heappop(self._queue)
                status = self._attempts[(attempt.owner, attempt.clip_id, attempt.attempt_id)]
                if status.cancel.is_set():
                    status.state, status.stage = "cancelled", "Dibatalkan"
                    continue
                status.state, status.stage, status.started_at = "rendering", "Menyusun video", time.monotonic()

            def progress(stage: str, value: float):
                with self._lock:
                    status.stage = str(stage)[:120]
                    status.progress = max(0.0, min(1.0, float(value)))

            try:
                output = run(attempt, status.cancel, progress)
                with self._lock:
                    status.elapsed_seconds = time.monotonic() - (status.started_at or time.monotonic())
                    if status.cancel.is_set():
                        status.state, status.stage = "cancelled", "Dibatalkan"
                    else:
                        status.state, status.stage, status.progress = "ready", "Selesai", 1.0
                        status.stream_url = str(output)
            except InterruptedError:
                with self._lock:
                    status.state, status.stage = "cancelled", "Dibatalkan"
            except Exception:
                with self._lock:
                    status.state, status.stage, status.error = "error", "Render gagal", "Preview gagal. Coba lagi."
