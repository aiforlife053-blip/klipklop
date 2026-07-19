import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useOutletContext } from 'react-router-dom';
import type { DashboardOutletContext } from '@/components/layout/DashboardLayout';
import FacecamPickerModal from '@/components/facecam/FacecamPickerModal';
import { ProcessBoard, type ProcessClip } from '@/components/dashboard/ProcessBoard';
import { api } from '@/lib/api';

const MODES = [
  { id: 'vertical_full', label: 'Vertical Full' },
  { id: 'gaming', label: 'Gaming' },
  { id: 'split_middle', label: 'Split Middle' },
] as const;

type ModeId = (typeof MODES)[number]['id'];
type VideoMeta = {
  title?: string;
  author_name?: string;
  author?: string;
  thumbnail_url?: string;
  thumbnail?: string;
  width?: number;
  height?: number;
  is_landscape?: boolean;
  is_portrait?: boolean;
  orientation?: string;
};

export default function Dashboard() {
  const { status, refreshStatus } = useOutletContext<DashboardOutletContext>();
  const navigate = useNavigate();
  const [youtubeUrl, setYoutubeUrl] = useState(() => sessionStorage.getItem('klipklop.youtubeUrl') || '');
  const [mode, setMode] = useState<ModeId>('vertical_full');
  const [videoQuality, setVideoQuality] = useState('1080');
  const [numClips, setNumClips] = useState(1);
  const [instruction, setInstruction] = useState('');
  const [showDirections, setShowDirections] = useState(false);
  const [stopConfirm, setStopConfirm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [videoMeta, setVideoMeta] = useState<VideoMeta | null>(() => {
    try { return JSON.parse(sessionStorage.getItem('klipklop.videoMeta') || 'null'); } catch { return null; }
  });
  const [clips, setClips] = useState<ProcessClip[]>([]);
  const [facecamClip, setFacecamClip] = useState<ProcessClip | null>(null);

  const loadClips = useCallback(async () => {
    try {
      const data = await api<{ clips?: ProcessClip[] }>('/api/clips');
      setClips(data.clips || []);
    } catch {
      setClips([]);
    }
  }, []);

  const isProcessing = isSubmitting || ['queued', 'running', 'stopping'].includes(status?.status || '');
  const orientationBlocked = Boolean(
    videoMeta && (mode === 'gaming' || mode === 'split_middle') && (videoMeta.is_portrait || videoMeta.orientation === 'portrait'),
  );

  useEffect(() => { void loadClips(); }, [loadClips]);
  useEffect(() => {
    if (!isProcessing && !clips.some((clip) => ['needs_facecam', 'render_queued', 'rendering', 'scheduled', 'uploading'].includes(clip.status || ''))) return;
    const timer = window.setInterval(() => { void loadClips(); void refreshStatus(); }, 2000);
    return () => window.clearInterval(timer);
  }, [isProcessing, clips, loadClips, refreshStatus]);

  useEffect(() => {
    if (youtubeUrl) sessionStorage.setItem('klipklop.youtubeUrl', youtubeUrl);
    else sessionStorage.removeItem('klipklop.youtubeUrl');
    const match = youtubeUrl.match(/^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/);
    const videoId = match && match[2].length === 11 ? match[2] : null;
    const controller = new AbortController();
    if (!videoId) {
      setVideoMeta(null);
      sessionStorage.removeItem('klipklop.videoMeta');
      return () => controller.abort();
    }
    void (async () => {
      try {
        const response = await fetch(`/api/meta?url=${encodeURIComponent(`https://www.youtube.com/watch?v=${videoId}`)}`, {
          credentials: 'same-origin',
          signal: controller.signal,
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        if (data.error) return;
        setVideoMeta(data);
        sessionStorage.setItem('klipklop.videoMeta', JSON.stringify(data));
      } catch (requestError) {
        if (requestError instanceof DOMException && requestError.name === 'AbortError') return;
      }
    })();
    return () => controller.abort();
  }, [youtubeUrl]);

  const handleProcessClip = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!youtubeUrl.trim()) { setError('Masukkan URL YouTube terlebih dahulu.'); return; }
    if (orientationBlocked) {
      setError('Mode Gaming/Split hanya mendukung source landscape.');
      return;
    }
    setError('');
    setIsSubmitting(true);
    try {
      const result = await api('/api/start', {
        method: 'POST',
        body: JSON.stringify({
          url: youtubeUrl.trim(),
          mode,
          num_clips: numClips,
          video_quality: videoQuality,
          instruction,
        }),
      });
      if (result.status !== 'queued' && result.status !== 'started') setError(result.message || 'Gagal memulai proses.');
      await Promise.all([refreshStatus(), loadClips()]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Gagal memulai proses.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const runClipAction = async (path: string, body: object, fallback: string) => {
    setBusy(path);
    setError('');
    try {
      await api(path, { method: 'POST', body: JSON.stringify(body) });
      await loadClips();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : fallback);
    } finally {
      setBusy('');
    }
  };

  const confirmStop = async () => {
    setStopConfirm(false);
    await runClipAction('/api/stop', {}, 'Gagal menghentikan proses.');
    await refreshStatus();
  };

  const readyCount = useMemo(() => clips.filter((clip) => ['ready_to_schedule', 'scheduled', 'uploading', 'uploaded', 'upload_error', 'render_error', 'cancelled'].includes(clip.status || '')).length, [clips]);
  const previewThumbnail = videoMeta?.thumbnail_url || videoMeta?.thumbnail || '';

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10">
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <form onSubmit={handleProcessClip} className="flex flex-col justify-center gap-6 rounded-2xl border border-dashed border-line bg-card p-8 lg:p-10">
          <h1 className="font-display text-3xl font-bold leading-tight tracking-tight md:text-[2.75rem] md:leading-[1.15]">
            Generate klip V3 otomatis.
          </h1>
          <p className="max-w-xl text-[0.9375rem] leading-relaxed text-muted">URL, mode layout, jumlah klip, kualitas. Render final jalan sendiri.</p>

          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <input type="url" placeholder="https://youtube.com/watch?v=..." aria-label="Link YouTube" value={youtubeUrl} onChange={(event) => setYoutubeUrl(event.target.value)} className="h-12 w-full rounded-xl border border-field bg-secondary px-4 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <button type="submit" disabled={isProcessing || orientationBlocked} className="flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 font-display text-base font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50">
              {isProcessing ? 'Memproses...' : 'Proses Klip'}
            </button>
          </div>

          {(error || status?.error || orientationBlocked) && (
            <p className="text-sm font-medium text-destructive" role="alert">
              {orientationBlocked ? 'Mode Gaming/Split hanya mendukung source landscape.' : (error || status?.error)}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
            <label className="sr-only" htmlFor="mode">Mode layout</label>
            <select id="mode" value={mode} onChange={(event) => setMode(event.target.value as ModeId)} className="h-9 rounded-full border border-field bg-secondary px-3.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
              {MODES.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
            </select>
            <label className="sr-only" htmlFor="quality">Kualitas Video</label>
            <select id="quality" value={videoQuality} onChange={(event) => setVideoQuality(event.target.value)} className="h-9 rounded-full border border-field bg-secondary px-3.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
              <option value="480">480p</option>
              <option value="720">720p</option>
              <option value="1080">1080p</option>
              <option value="1440">1440p (2K)</option>
            </select>
            <label className="sr-only" htmlFor="clip-count">Jumlah Klip</label>
            <select id="clip-count" value={numClips} onChange={(event) => setNumClips(Number(event.target.value))} className="h-9 rounded-full border border-field bg-secondary px-3.5 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
              <option value={1}>1 klip</option>
              <option value={3}>3 klip</option>
              <option value={5}>5 klip</option>
            </select>
            <button type="button" onClick={() => setShowDirections(!showDirections)} className="inline-flex items-center gap-1.5 self-center text-xs font-medium text-primary">Tambah Arahan</button>
            <div className="ml-auto flex items-center gap-2">
              <span className={`size-2 rounded-full ${isProcessing ? 'animate-pulse bg-primary' : 'bg-muted/40'}`} aria-hidden="true" />
              <span>Status: {status?.status || 'idle'}</span>
            </div>
          </div>
          {showDirections && <textarea rows={3} placeholder="Arahan AI opsional..." value={instruction} onChange={(event) => setInstruction(event.target.value)} className="w-full rounded-xl border border-field bg-secondary px-4 py-3 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />}
          {videoMeta?.orientation && videoMeta.orientation !== 'unknown' && (
            <p className="text-xs text-muted">Orientasi terdeteksi: {videoMeta.orientation}{videoMeta.width && videoMeta.height ? ` (${videoMeta.width}×${videoMeta.height})` : ''}</p>
          )}
        </form>

        <div className="group relative flex flex-col overflow-hidden rounded-2xl border border-line bg-card text-left">
          <div className="relative min-h-[240px] flex-1 overflow-hidden bg-secondary">
            {previewThumbnail ? (
              <img src={previewThumbnail} alt="Thumbnail" className="absolute inset-0 size-full object-cover" />
            ) : (
              <div className="absolute inset-0 flex items-center justify-center text-muted/30">Belum ada video</div>
            )}
            <div className="absolute inset-0" style={{ background: 'linear-gradient(to top, #1c1d22, transparent 55%)' }} aria-hidden="true" />
          </div>
          <div className="relative z-[2] -mt-10 flex flex-col gap-1.5 p-5">
            <p className="line-clamp-1 font-display text-xl font-bold tracking-tight">{videoMeta?.title || 'Belum ada video'}</p>
            {(videoMeta?.author_name || videoMeta?.author) && <p className="text-[0.8125rem] text-muted">{videoMeta.author_name || videoMeta.author}</p>}
          </div>
        </div>
      </div>

      <ProcessBoard
        clips={clips}
        job={status}
        busy={busy}
        onGlobalCancel={() => setStopConfirm(true)}
        onFacecam={setFacecamClip}
        onRetry={(clip) => runClipAction(clip.status === 'upload_error' ? '/api/clip/upload/retry' : '/api/clip/render/retry', { clip_id: clip.clip_id }, 'Retry gagal.')}
        onCancel={(clip) => runClipAction(clip.status === 'scheduled' ? '/api/clip/schedule/cancel' : '/api/clip/cancel', { clip_id: clip.clip_id }, 'Batal gagal.')}
        onDelete={(clip) => runClipAction('/api/clip/delete', { clip_id: clip.clip_id }, 'Hapus gagal.')}
      />

      <section className="rounded-2xl border border-line bg-card p-6" aria-label="Hasil workflow">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="font-display text-xl font-bold">Set Waktu & Hasil</h2>
            <p className="text-sm text-muted">{readyCount} klip di workflow. Upload hanya lewat jadwal WIB.</p>
          </div>
          <button type="button" onClick={() => navigate('/preview')} className="rounded-xl bg-primary px-5 py-3 text-sm font-bold text-primary-foreground">Buka Workflow</button>
        </div>
      </section>

      {stopConfirm && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 p-4" onClick={() => setStopConfirm(false)}>
          <div className="flex w-full max-w-sm flex-col gap-4 rounded-2xl border border-line bg-card p-6 text-center" onClick={(event) => event.stopPropagation()}>
            <h3 className="font-display text-lg font-bold">Yakin hentikan generate?</h3>
            <p className="text-sm text-muted">Proses aktif untuk URL ini akan dihentikan.</p>
            <div className="mt-2 flex justify-center gap-3">
              <button type="button" onClick={() => setStopConfirm(false)} className="rounded-xl border border-line px-5 py-2 font-medium">Batal</button>
              <button type="button" onClick={confirmStop} className="rounded-xl bg-destructive px-5 py-2 font-medium text-destructive-foreground">Ya, Hentikan</button>
            </div>
          </div>
        </div>,
        document.body,
      )}

      {facecamClip && (
        <FacecamPickerModal
          clipId={facecamClip.clip_id}
          durationSeconds={undefined}
          onClose={() => setFacecamClip(null)}
          onSaved={async () => { setFacecamClip(null); await loadClips(); }}
        />
      )}
    </main>
  );
}
