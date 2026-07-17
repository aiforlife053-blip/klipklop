import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api } from '@/lib/api';

type Roi = { x: number; y: number; width: number; height: number };

type Props = {
  clipId: string;
  durationSeconds?: number;
  initialRoi?: Partial<Roi> | null;
  onClose: () => void;
  onSaved: (roi: Roi) => void;
};

const ASPECT = 16 / 9; // facecam box aspect roughly landscape face area; locked ratio

function clampRoi(roi: Roi): Roi {
  const width = Math.max(0.05, Math.min(0.6, roi.width));
  const height = Math.max(0.05, Math.min(0.6, width / ASPECT));
  const x = Math.max(0, Math.min(1 - width, roi.x));
  const y = Math.max(0, Math.min(1 - height, roi.y));
  return { x, y, width, height };
}

export default function FacecamPickerModal({ clipId, durationSeconds = 0, initialRoi, onClose, onSaved }: Props) {
  const [seek, setSeek] = useState(0);
  const [roi, setRoi] = useState<Roi>(() => clampRoi({
    x: Number(initialRoi?.x ?? 0.05),
    y: Number(initialRoi?.y ?? 0.05),
    width: Number(initialRoi?.width ?? 0.22),
    height: Number(initialRoi?.height ?? 0.22 / ASPECT),
  }));
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const frameUrl = useMemo(
    () => `/api/clip/frame?clip_id=${encodeURIComponent(clipId)}&t=${seek.toFixed(2)}`,
    [clipId, seek],
  );
  const stageRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ mode: 'move' | 'resize'; startX: number; startY: number; origin: Roi } | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const onPointerDownMove = (event: React.PointerEvent) => {
    event.preventDefault();
    (event.target as HTMLElement).setPointerCapture?.(event.pointerId);
    dragRef.current = { mode: 'move', startX: event.clientX, startY: event.clientY, origin: roi };
  };

  const onPointerDownResize = (event: React.PointerEvent) => {
    event.preventDefault();
    event.stopPropagation();
    (event.target as HTMLElement).setPointerCapture?.(event.pointerId);
    dragRef.current = { mode: 'resize', startX: event.clientX, startY: event.clientY, origin: roi };
  };

  const onPointerMove = (event: React.PointerEvent) => {
    const drag = dragRef.current;
    const rect = stageRef.current?.getBoundingClientRect();
    if (!drag || !rect) return;
    const dx = (event.clientX - drag.startX) / rect.width;
    const dy = (event.clientY - drag.startY) / rect.height;
    if (drag.mode === 'move') {
      setRoi(clampRoi({ ...drag.origin, x: drag.origin.x + dx, y: drag.origin.y + dy }));
      return;
    }
    const nextWidth = drag.origin.width + dx;
    setRoi(clampRoi({ ...drag.origin, width: nextWidth, height: nextWidth / ASPECT }));
  };

  const onPointerUp = () => {
    dragRef.current = null;
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      const result = await api<{ status: string; message?: string; facecam?: Roi }>('/api/clip/facecam', {
        method: 'POST',
        body: JSON.stringify({
          clip_id: clipId,
          x: roi.x,
          y: roi.y,
          width: roi.width,
          height: roi.height,
          confidence: 1,
        }),
      });
      if (result.status !== 'ok' || !result.facecam) {
        setError(result.message || 'Gagal menyimpan facecam');
        return;
      }
      onSaved(result.facecam);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Gagal menyimpan facecam');
    } finally {
      setSaving(false);
    }
  };

  const maxSeek = Math.max(0, Number(durationSeconds) || 0);

  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-background/85 p-4" role="dialog" aria-modal="true" aria-label="Pilih Facecam">
      <div className="flex w-full max-w-3xl flex-col gap-4 rounded-2xl border border-line bg-card p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-lg font-bold">Pilih Facecam</h2>
            <p className="text-sm text-muted">Geser kotak ke wajah. Rasio terkunci. Preview 1:3 atas / 2:3 bawah.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg border border-line px-3 py-1.5 text-sm" aria-label="Tutup">Tutup</button>
        </div>

        <div
          ref={stageRef}
          className="relative aspect-video w-full overflow-hidden rounded-xl bg-secondary"
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
        >
          <img src={frameUrl} alt="Frame source" className="absolute inset-0 size-full object-contain" draggable={false} />
          <div
            role="slider"
            aria-label="Kotak facecam"
            tabIndex={0}
            className="absolute cursor-move border-2 border-primary bg-primary/10"
            style={{
              left: `${roi.x * 100}%`,
              top: `${roi.y * 100}%`,
              width: `${roi.width * 100}%`,
              height: `${roi.height * 100}%`,
            }}
            onPointerDown={onPointerDownMove}
          >
            <span
              className="absolute bottom-0 right-0 size-4 translate-x-1/2 translate-y-1/2 cursor-se-resize rounded-sm bg-primary"
              onPointerDown={onPointerDownResize}
              aria-hidden="true"
            />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
          <label className="flex flex-col gap-1 text-xs text-muted">
            Timeline
            <input
              type="range"
              min={0}
              max={maxSeek || 1}
              step={0.1}
              value={Math.min(seek, maxSeek || 1)}
              onChange={(event) => setSeek(Number(event.target.value))}
              disabled={!maxSeek}
              className="w-full"
            />
          </label>
          <div className="rounded-xl border border-line bg-secondary p-2 text-[0.7rem] text-muted">
            <div className="mb-1 font-medium text-foreground">Preview layout</div>
            <div className="flex h-24 flex-col overflow-hidden rounded-md border border-line">
              <div className="h-1/3 bg-primary/40" />
              <div className="h-2/3 bg-white/10" />
            </div>
            <p className="mt-1">1/3 facecam · 2/3 gameplay</p>
          </div>
        </div>

        {error && <p className="text-sm font-medium text-destructive" role="alert">{error}</p>}

        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="rounded-xl border border-line px-4 py-2 text-sm">Batal</button>
          <button type="button" onClick={handleSave} disabled={saving} className="rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground disabled:opacity-50">
            {saving ? 'Menyimpan...' : 'Simpan Facecam'}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
