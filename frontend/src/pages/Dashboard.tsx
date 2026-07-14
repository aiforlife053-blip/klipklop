import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate, useOutletContext } from 'react-router-dom';
import type { DashboardOutletContext } from '@/components/layout/DashboardLayout';
import { api } from '@/lib/api';

const activeStatuses = new Set(['queued', 'running', 'stopping']);

type DashboardClip = {
  clip_id: string;
  generation_id?: string;
  title: string;
  virality_score?: number;
  thumbnail_url?: string;
};

type ClipsResponse = { clips?: DashboardClip[] };

export default function Dashboard() {
  const { status, settings, refreshStatus } = useOutletContext<DashboardOutletContext>();
  const navigate = useNavigate();
  const [youtubeUrl, setYoutubeUrl] = useState(() => sessionStorage.getItem('klipklop.youtubeUrl') || '');
  const [videoQuality, setVideoQuality] = useState('720');
  const [numClips, setNumClips] = useState(1);
  const [landscapeBlur, setLandscapeBlur] = useState(true);
  const [instruction, setInstruction] = useState('');
  const [stopConfirm, setStopConfirm] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [videoMeta, setVideoMeta] = useState<{ title?: string; author_name?: string; thumbnail_url?: string; thumbnail?: string } | null>(() => {
    try {
      return JSON.parse(sessionStorage.getItem('klipklop.videoMeta') || 'null');
    } catch {
      return null;
    }
  });
  const [showDirections, setShowDirections] = useState(false);
  const [clips, setClips] = useState<DashboardClip[]>([]);

  const loadClips = useCallback(async () => {
    try {
      const data = await api<ClipsResponse>('/api/clips');
      setClips(data.clips || []);
    } catch {
      setClips([]);
    }
  }, []);

  const latestGenerationId = clips[0]?.generation_id || clips[0]?.clip_id || '';
  const latestGenerationClips = useMemo(() => {
    if (!latestGenerationId) return [];
    if (!clips[0]?.generation_id) return clips.slice(0, 1);
    return clips.filter((clip) => clip.generation_id === latestGenerationId);
  }, [clips, latestGenerationId]);

  const isProcessing = isSubmitting || activeStatuses.has(status?.status || '');
  const progress = typeof status?.progress === 'number' && Number.isFinite(status.progress)
    ? Math.max(0, Math.min(100, Math.round(status.progress <= 1 ? status.progress * 100 : status.progress)))
    : null;

  useEffect(() => { void loadClips(); }, [loadClips]);

  useEffect(() => {
    if (!isProcessing) void loadClips();
  }, [isProcessing, loadClips]);

  useEffect(() => {
    if (settings?.video_quality) setVideoQuality(String(settings.video_quality));
    if (settings?.blur_background?.enabled !== undefined) setLandscapeBlur(Boolean(settings.blur_background.enabled));
  }, [settings?.video_quality, settings?.blur_background?.enabled]);

  useEffect(() => {
    if (status?.url) setYoutubeUrl((current) => current || status.url || '');
  }, [status?.url]);

  useEffect(() => {
    if (youtubeUrl) sessionStorage.setItem('klipklop.youtubeUrl', youtubeUrl);
    else sessionStorage.removeItem('klipklop.youtubeUrl');

    const match = youtubeUrl.match(/^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/);
    const videoId = match && match[2].length === 11 ? match[2] : null;
    const controller = new AbortController();

    if (!videoId) {
      setVideoMeta(null);
      sessionStorage.removeItem('klipklop.videoMeta');
      sessionStorage.removeItem('klipklop.videoId');
      return () => controller.abort();
    }

    const cachedVideoId = sessionStorage.getItem('klipklop.videoId');
    if (cachedVideoId && cachedVideoId !== videoId) setVideoMeta(null);

    const fetchMeta = async () => {
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
        sessionStorage.setItem('klipklop.videoId', videoId);
      } catch (requestError) {
        if (requestError instanceof DOMException && requestError.name === 'AbortError') return;
        console.error('Failed to fetch video metadata', requestError);
      }
    };

    void fetchMeta();
    return () => controller.abort();
  }, [youtubeUrl]);

  const buildStartPayload = () => {
    const syncedSettings = {
      ...settings,
      video_quality: videoQuality,
      landscape_blur: landscapeBlur,
      blur_background: {
        ...(settings?.blur_background || {}),
        enabled: landscapeBlur,
      },
    };
    return {
      url: youtubeUrl.trim(),
      num_clips: numClips,
      video_quality: videoQuality,
      add_captions: syncedSettings?.subtitle?.enabled ?? true,
      add_hook: syncedSettings?.hook_style?.enabled ?? false,
      screen_size: '9:16',
      subtitle_language: syncedSettings?.subtitle_language || 'id',
      landscape_blur: landscapeBlur,
      source_credit: syncedSettings?.credit_watermark?.enabled ?? true,
      instruction,
      settings: syncedSettings,
    };
  };

  const handleProcessClip = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!youtubeUrl.trim()) {
      alert('Masukkan URL YouTube terlebih dahulu.');
      return;
    }
    setError('');
    setIsSubmitting(true);
    try {
      const result = await api('/api/start', {
        method: 'POST',
        body: JSON.stringify(buildStartPayload()),
      });
      if (result.status !== 'queued' && result.status !== 'started') {
        setError(result.message || 'Gagal memulai proses.');
      }
      await refreshStatus();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Gagal memulai proses.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const confirmStop = async () => {
    setStopConfirm(false);
    try {
      await api('/api/stop', { method: 'POST', body: JSON.stringify({}) });
      await refreshStatus();
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Gagal menghentikan proses.');
    }
  };

  const previewThumbnail = videoMeta?.thumbnail_url || videoMeta?.thumbnail || '';

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10">
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <form onSubmit={handleProcessClip} className="flex flex-col justify-center gap-6 rounded-2xl border border-dashed border-line bg-card p-8 lg:p-10">
          <h1 className="font-display text-3xl font-bold leading-tight tracking-tight md:text-[2.75rem] md:leading-[1.15]">
            Satu video panjang, disulap jadi puluhan klip viral.
          </h1>
          <p className="max-w-xl text-[0.9375rem] leading-relaxed text-muted">Tempel link YouTube. AI mencari hook, memotong klip, dan menambahkan caption.</p>

          <div className="flex flex-col gap-3 sm:flex-row">
            <div className="relative flex-1">
              <svg className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/></svg>
              <input type="url" placeholder="https://youtube.com/watch?v=..." aria-label="Link YouTube" value={youtubeUrl} onChange={(event) => setYoutubeUrl(event.target.value)} className="h-12 w-full rounded-xl border border-field bg-secondary pl-10 pr-4 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <button type="submit" disabled={isProcessing} className="flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 font-display text-base font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50">
              {isProcessing ? 'Memproses...' : 'Proses Klip'}
              {!isProcessing && <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>}
            </button>
          </div>

          {(error || status?.error) && <p className="text-sm font-medium text-destructive">{error || status?.error}</p>}

          <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
            <div className="relative">
              <label className="sr-only" htmlFor="quality">Kualitas Video</label>
              <select id="quality" value={videoQuality} onChange={(event) => setVideoQuality(event.target.value)} className="h-9 appearance-none rounded-full border border-field bg-secondary pl-3.5 pr-8 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
                <option value="480">480p</option>
                <option value="720">720p</option>
                <option value="1080">1080p</option>
                <option value="1440">1440p (2K)</option>
                <option value="2160">2160p (4K)</option>
              </select>
              <svg className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
            </div>
            <div className="relative">
              <label className="sr-only" htmlFor="clip-count">Jumlah Klip</label>
              <select id="clip-count" value={numClips} onChange={(event) => setNumClips(Number(event.target.value))} className="h-9 appearance-none rounded-full border border-field bg-secondary pl-3.5 pr-8 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
                <option value={1}>1 klip</option>
                <option value={3}>3 klip</option>
                <option value={5}>5 klip</option>
              </select>
              <svg className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
            </div>
            <label className="group inline-flex min-h-11 cursor-pointer items-center gap-3 rounded-full bg-secondary px-3.5 text-sm font-medium text-foreground">
              <span>Blur background</span>
              <input type="checkbox" role="switch" checked={landscapeBlur} onChange={(event) => setLandscapeBlur(event.target.checked)} className="peer sr-only" />
              <span aria-hidden="true" className="relative h-6 w-10 shrink-0 rounded-full bg-white/15 transition-colors duration-200 peer-checked:bg-primary peer-checked:[&>span]:translate-x-4 peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-secondary">
                <span className="absolute left-1 top-1 size-4 rounded-full bg-white transition-transform duration-200" />
              </span>
            </label>
            <button type="button" onClick={() => setShowDirections(!showDirections)} className="inline-flex items-center gap-1.5 self-center text-xs font-medium text-primary transition-opacity hover:opacity-80">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z"/></svg>
              Tambah Arahan
            </button>
            <div className="ml-auto flex items-center gap-2">
              <span className={`size-2 rounded-full ${isProcessing ? 'animate-pulse bg-primary' : 'bg-muted/40'}`} aria-hidden="true"></span>
              <span>Status: {status?.status || 'idle'}</span>
            </div>
          </div>
          {showDirections && <textarea rows={3} placeholder="Contoh: fokus pada momen lucu, sertakan hook di 3 detik pertama..." value={instruction} onChange={(event) => setInstruction(event.target.value)} className="w-full rounded-xl border border-field bg-secondary px-4 py-3 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary"></textarea>}
        </form>

        <div className="group relative flex flex-col overflow-hidden rounded-2xl border border-line bg-card text-left">
          <div className="relative min-h-[240px] flex-1 overflow-hidden bg-secondary">
            {previewThumbnail ? (
              <img src={previewThumbnail} alt="Thumbnail" className="absolute inset-0 size-full object-cover transition-transform duration-300 group-hover:scale-[1.04]" />
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center pb-8 text-muted/30">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect width="15" height="14" x="1" y="5" rx="2" ry="2"/></svg>
              </div>
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-card to-transparent" style={{ background: 'linear-gradient(to top, #1c1d22, transparent 55%)' }} aria-hidden="true"></div>
          </div>
          <div className="relative z-[2] -mt-10 flex flex-col gap-1.5 p-5">
            <p className="line-clamp-1 font-display text-xl font-bold tracking-tight">{videoMeta?.title || 'Belum ada video'}</p>
            {videoMeta?.author_name && <p className="text-[0.8125rem] text-muted">{videoMeta.author_name}</p>}
          </div>
        </div>
      </div>

      {isProcessing && (
        <section className="flex flex-col gap-5 rounded-2xl border border-line bg-card p-6" aria-label="Proses AI sedang berjalan">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <h2 className="font-display text-[1.0625rem] font-bold">Proses klip sedang berjalan</h2>
              {status?.message && <p className="break-words text-[0.8125rem] text-muted">{status.message}</p>}
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-4 py-1.5 text-xs font-bold text-primary">
              <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
              {status?.status || 'queued'}
            </span>
            <button type="button" onClick={() => setStopConfirm(true)} className="rounded-full border border-destructive/40 bg-destructive/10 px-4 py-1.5 text-xs font-bold text-destructive">Batalkan proses</button>
          </div>
          {progress !== null && (
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between text-xs text-muted"><span>Progress</span><span>{progress}%</span></div>
              <div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${progress}%` }}></div></div>
            </div>
          )}
        </section>
      )}

      <section className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]" aria-label="Klip terbaru">
        <div className="flex min-h-56 flex-col justify-between gap-6 rounded-2xl border border-line bg-card p-6">
          <div className="flex flex-col gap-2">
            <h2 className="font-display text-xl font-bold">Klip siap diedit</h2>
            <p className="text-sm leading-relaxed text-muted">Generate membuat draft reframe. Atur hook, subtitle, dan watermark sebelum render final.</p>
          </div>
          <div className="flex items-end justify-between gap-4">
            <p className="text-sm font-medium">{latestGenerationClips.length} klip terbaru</p>
            <button type="button" onClick={() => navigate(latestGenerationId ? `/preview?generation_id=${encodeURIComponent(latestGenerationId)}` : '/preview')} className="rounded-xl bg-primary px-5 py-3 text-sm font-bold text-primary-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-card">Buka Preview</button>
          </div>
        </div>
        <div className="rounded-2xl border border-line bg-card p-6">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <h2 className="font-display text-xl font-bold">Potensi viral</h2>
              <p className="mt-1 text-sm text-muted">Perbandingan skor klip terbaru</p>
            </div>
            <span className="rounded-full bg-secondary px-3 py-1.5 text-xs font-medium text-muted">Skala 10</span>
          </div>
          {latestGenerationClips.length ? (
            <ol className="space-y-4" aria-label="Peringkat potensi viral klip terbaru">
              {[...latestGenerationClips]
                .sort((left, right) => (Number(right.virality_score) || 0) - (Number(left.virality_score) || 0))
                .map((clip, index) => {
                  const numericScore = Number(clip.virality_score);
                  const validScore = Number.isFinite(numericScore) && numericScore > 0;
                  const score = validScore ? Math.max(1, Math.min(10, numericScore)) : 0;
                  return <li key={clip.clip_id} className="grid grid-cols-[1.75rem_minmax(0,1fr)_2rem] items-center gap-x-3 gap-y-2">
                    <span className="row-span-2 flex size-7 items-center justify-center rounded-full bg-secondary text-xs font-bold text-muted">{index + 1}</span>
                    <span className="truncate text-sm font-medium text-foreground" title={clip.title}>{clip.title}</span>
                    <span className={`text-right text-sm font-bold ${validScore ? 'text-primary' : 'text-muted'}`}>{validScore ? score : '–'}</span>
                    <span className="relative h-2 overflow-hidden rounded-full bg-secondary" aria-hidden="true">
                      <span className="absolute inset-y-0 left-0 rounded-full bg-primary transition-[width] duration-300 motion-reduce:transition-none" style={{ width: `${score * 10}%` }} />
                    </span>
                    <span className="text-right text-[0.6875rem] text-muted">/10</span>
                  </li>;
                })}
            </ol>
          ) : <div className="flex min-h-36 items-center justify-center rounded-xl bg-secondary/50 px-6 text-center text-sm text-muted">Skor potensi viral muncul setelah klip pertama selesai dibuat.</div>}
        </div>
      </section>

      {stopConfirm && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 p-4" onClick={() => setStopConfirm(false)}>
          <div className="flex w-full max-w-sm flex-col gap-4 overflow-hidden rounded-2xl border border-line bg-card p-6 text-center" onClick={(event) => event.stopPropagation()}>
            <h3 className="font-display text-lg font-bold">Yakin hentikan proses?</h3>
            <p className="text-sm text-muted">Video yang sudah diproses sejauh ini mungkin hilang.</p>
            <div className="mt-2 flex justify-center gap-3">
              <button type="button" onClick={() => setStopConfirm(false)} className="rounded-xl border border-line px-5 py-2 font-medium text-foreground hover:bg-secondary">Batal</button>
              <button type="button" onClick={confirmStop} className="rounded-xl bg-destructive px-5 py-2 font-medium text-destructive-foreground">Ya, Hentikan</button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </main>
  );
}
