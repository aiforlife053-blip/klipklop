import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { api } from '@/lib/api';

const loadingPhrases = [
  'Sabar, biarkan AI memasak 🔥',
  'Mencari momen paling FYP 🚀',
  'Bikin klip yang bikin fyp meledak 💥',
  'Meracik visual biar makin estetik 🎨',
  'Tunggu bentar, lagi ngopi subtitle ☕',
];

export default function Dashboard() {
  const { status: globalStatus, settings } = useOutletContext<any>();
  const navigate = useNavigate();
  const [youtubeUrl, setYoutubeUrl] = useState(() => sessionStorage.getItem('klipklop.youtubeUrl') || '');
  const [videoQuality, setVideoQuality] = useState('720');
  const [numClips, setNumClips] = useState(1);
  const [landscapeBlur, setLandscapeBlur] = useState(true);
  const [showDetailModal, setShowDetailModal] = useState<any>(null);
  const [instruction, setInstruction] = useState('');
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [scheduleAt, setScheduleAt] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState<any>(null);
  const [stopConfirm, setStopConfirm] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);

  useEffect(() => {
    if (settings?.video_quality) setVideoQuality(String(settings.video_quality));
    if (settings?.blur_background?.enabled !== undefined) setLandscapeBlur(Boolean(settings.blur_background.enabled));
  }, [settings?.video_quality, settings?.blur_background?.enabled]);

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
      instruction: instruction,
      settings: syncedSettings,
    };
  };

  const [loadingPhraseIdx, setLoadingPhraseIdx] = useState(0);

  useEffect(() => {
    let interval: any;
    if (isProcessing || globalStatus?.status === 'running') {
      interval = setInterval(() => {
        setLoadingPhraseIdx((prev) => (prev + 1) % loadingPhrases.length);
      }, 8000);
    }
    return () => clearInterval(interval);
  }, [isProcessing, globalStatus?.status]);

  const [, setJobStatus] = useState<any>(null);
  const [clips, setClips] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [videoMeta, setVideoMeta] = useState<{title?: string, author_name?: string, thumbnail_url?: string, thumbnail?: string} | null>(() => {
    try {
      return JSON.parse(sessionStorage.getItem('klipklop.videoMeta') || 'null');
    } catch {
      return null;
    }
  });
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const getYoutubeId = (url: string) => {
    const match = url.match(/^.*(youtu.be\/|v\/|u\/\w\/|embed\/|watch\?v=|&v=)([^#&?]*).*/);
    return (match && match[2].length === 11) ? match[2] : null;
  };

  useEffect(() => {
    if (youtubeUrl) sessionStorage.setItem('klipklop.youtubeUrl', youtubeUrl);
    else sessionStorage.removeItem('klipklop.youtubeUrl');
    const vidId = getYoutubeId(youtubeUrl);
    if (vidId) {
      const cachedVideoId = sessionStorage.getItem('klipklop.videoId');
      if (cachedVideoId && cachedVideoId !== vidId) setVideoMeta(null);
      fetch(`/api/meta?url=${encodeURIComponent('https://www.youtube.com/watch?v=' + vidId)}`)
        .then(r => r.json())
        .then(data => {
          if (!data.error) {
            setVideoMeta(data);
            sessionStorage.setItem('klipklop.videoMeta', JSON.stringify(data));
            sessionStorage.setItem('klipklop.videoId', vidId);
          }
        }).catch(e => console.error(e));
    } else {
      setVideoMeta(null);
      sessionStorage.removeItem('klipklop.videoMeta');
      sessionStorage.removeItem('klipklop.videoId');
    }
  }, [youtubeUrl]);

  const fetchOutputs = useCallback(async () => {
    try {
      const data = await api('/api/outputs');
      const stagedGroup = (data?.groups || []).find((group: any) => {
        const savedPaths = new Set(group.saved_clips || []);
        return (group.clips || group.files || []).some((clip: any) => !savedPaths.has(clip.path));
      });
      const savedPaths = new Set(stagedGroup?.saved_clips || []);
      const outputClips = (stagedGroup?.clips || stagedGroup?.files || [])
        .filter((clip: any) => !savedPaths.has(clip.path))
        .map((clip: any) => ({ ...clip, groupPath: stagedGroup.path, groupUrl: stagedGroup.url }));
      setClips(outputClips);
    } catch (e) {
      console.error('Fetch outputs failed', e);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollingRef.current = setInterval(async () => {
      try {
        const data = await api('/api/status');
        setJobStatus(data);
        if (data.status === 'complete') {
          stopPolling();
          setIsProcessing(false);
          await fetchOutputs();
        } else if (data.status === 'error' || data.status === 'idle') {
          stopPolling();
          setIsProcessing(false);
          await fetchOutputs();
          if (data.status === 'error') setError(data.error || data.message || 'Terjadi kesalahan');
        }
      } catch (e) {
        console.error('Polling error', e);
      }
    }, 1500);
  }, [stopPolling, fetchOutputs]);

  useEffect(() => {
    const init = async () => {
      try {
        const data = await api('/api/status');
        setJobStatus(data);
        if (data.url) setYoutubeUrl((current) => current || data.url);
        if (data.status === 'queued' || data.status === 'running' || data.status === 'stopping') {
          setIsProcessing(true);
          startPolling();
        } else {
          await fetchOutputs();
        }
      } catch (e) {
        console.error('Init failed', e);
      }
    };
    init();
    return () => stopPolling();
  }, [fetchOutputs, startPolling, stopPolling]);

  const handleProcessClip = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!youtubeUrl.trim()) {
      alert('Masukkan URL YouTube terlebih dahulu.');
      return;
    }
    setError('');
    setIsProcessing(true);
    try {
      const result = await api('/api/start', {
        method: 'POST',
        body: JSON.stringify(buildStartPayload()),
      });
      if (result.status !== 'queued' && result.status !== 'started') {
        setError(result.message || 'Gagal memulai proses.');
        setIsProcessing(false);
        await fetchOutputs();
        return;
      }
      setClips([]);
      startPolling();
    } catch (e: any) {
      setError(e.message || 'Gagal memulai proses.');
      setIsProcessing(false);
    }
  };

  const handleStop = () => setStopConfirm(true);

  const confirmStop = async () => {
    setStopConfirm(false);
    try {
      const result = await api('/api/stop', { method: 'POST', body: JSON.stringify({}) });
      if (result.status === 'stopping') {
        setJobStatus(result);
        startPolling();
      } else {
        stopPolling();
        setIsProcessing(false);
        setJobStatus(result);
        await fetchOutputs();
      }
    } catch (e) {
      console.error('Stop failed', e);
      stopPolling();
      setIsProcessing(false);
    }
  };

  const handleSave = async (clip: any) => {
    setIsSaving(true);
    try {
      await api('/api/save', {
        method: 'POST',
        body: JSON.stringify({ path: clip.groupPath, clips: [clip.path] }),
      });
      await new Promise(r => setTimeout(r, 600));
      setShowDetailModal(null);
      setClips(prev => prev.filter(c => c.path !== clip.path));
    } catch (e: any) {
      alert('Gagal menyimpan: ' + (e.message || ''));
    } finally {
      setIsSaving(false);
    }
  };

  const confirmDeleteClip = async () => {
    if (!deleteConfirm) return;
    const clip = deleteConfirm;
    setDeleteConfirm(null);
    try {
      await api('/api/delete', {
        method: 'POST',
        body: JSON.stringify({ path: clip.path })
      });
      if (showDetailModal?.path === clip.path) {
        setShowDetailModal(null);
      }
      fetchOutputs();
    } catch (e: any) {
      alert('Gagal menghapus klip: ' + (e.message || ''));
    }
  };

  const handleUpload = async (clip: any) => {
    const clipId = clip.path;
    if (uploadProgress[clipId] !== undefined) return;
    setUploadProgress(prev => ({ ...prev, [clipId]: 0 }));
    try {
      const result = await api('/api/social/youtube/upload', {
        method: 'POST',
        body: JSON.stringify({
          path: clip.path,
          title: clip.title || clip.name,
          description: clip.description || '',
          privacy: 'private',
        }),
      });
      if (result.status === 'ok') {
        setUploadProgress(prev => ({ ...prev, [clipId]: 100 }));
      } else {
        alert('Upload gagal: ' + (result.message || ''));
        setUploadProgress(prev => { const n = { ...prev }; delete n[clipId]; return n; });
      }
    } catch (e: any) {
      alert('Upload gagal: ' + (e.message || ''));
      setUploadProgress(prev => { const n = { ...prev }; delete n[clipId]; return n; });
    }
  };

  const handleSchedule = async (clip: any) => {
    if (!scheduleAt) return;
    try {
      await api('/api/social/youtube/schedule', {
        method: 'POST',
        body: JSON.stringify({ path: clip.path, title: clip.title || clip.name, description: clip.description || '', scheduled_at: scheduleAt }),
      });
      setShowDetailModal((current: any) => current && current.path === clip.path ? { ...current, youtube_upload: { status: 'scheduled', scheduled_at: new Date(`${scheduleAt}:00+07:00`).toISOString() } } : current);
      await fetchOutputs();
    } catch (e: any) {
      alert('Gagal menjadwalkan: ' + (e.message || ''));
    }
  };

  const handleCancelSchedule = async (clip: any) => {
    try {
      await api('/api/social/youtube/schedule/cancel', { method: 'POST', body: JSON.stringify({ path: clip.path }) });
      setShowDetailModal((current: any) => current && current.path === clip.path ? { ...current, youtube_upload: null } : current);
      setScheduleAt('');
      await fetchOutputs();
    } catch (e: any) {
      alert('Gagal membatalkan jadwal: ' + (e.message || ''));
    }
  };

  const fmtDuration = (clip: any) => {
    if (clip.duration) return clip.duration;
    if (clip.duration_seconds != null) return `${Math.round(clip.duration_seconds)}s`;
    return "";
  };

  const fmtScore = (clip: any) => {
    if (clip.score) return clip.score;
    if (clip.virality_score != null) return `${Math.min(100, Math.round(clip.virality_score * 10))}%`;
    return "";
  };

  const fmtImg = (clip: any) => {
    return clip.img || "";
  };

  const parseTimestamp = (value: string) => {
    const parts = String(value || '').replace(',', '.').split(':').map(Number);
    if (parts.length !== 3 || parts.some(Number.isNaN)) return 0;
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  };

  const fmtClock = (seconds: number) => {
    const safeSeconds = Math.max(0, Math.round(seconds));
    const minutes = Math.floor(safeSeconds / 60);
    const secs = safeSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
  };

  const previewThumbnail = videoMeta?.thumbnail_url || videoMeta?.thumbnail || '';

  const viralityStats = (() => {
    if (!clips.length) return null;
    const scoredClips = clips.map((clip, index) => {
      const rawScore = Number(clip.virality_score ?? 5);
      const score = Math.max(0, Math.min(100, Math.round(rawScore <= 10 ? rawScore * 10 : rawScore)));
      return { clip, index, score };
    });
    const best = scoredClips.reduce((top, item) => item.score > top.score ? item : top, scoredClips[0]);
    const average = Math.round(scoredClips.reduce((sum, item) => sum + item.score, 0) / scoredClips.length);
    const totalDuration = clips.reduce((sum, clip) => sum + (Number(clip.duration_seconds) || 0), 0);
    const bars = Array.from({ length: 14 }, (_, index) => scoredClips[index % scoredClips.length]?.score || 0);
    const timeline = scoredClips.map((item) => ({ ...item, startSeconds: parseTimestamp(item.clip.start_time) }));
    const label = average >= 85 ? 'EXCELLENT' : average >= 70 ? 'GOOD' : average >= 50 ? 'FAIR' : 'LOW';
    const uploadWindow = best.score >= 85 ? '18.00–21.00' : average >= 70 ? '12.00–14.00 atau 18.00–20.00' : '19.00–21.00';
    return { best, average, totalDuration, bars, timeline, label, uploadWindow };
  })();

  const [showDirections, setShowDirections] = useState(false);

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
              <input type="url" placeholder="https://youtube.com/watch?v=..." aria-label="Link YouTube"
                value={youtubeUrl}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                className="h-12 w-full rounded-xl border border-field bg-secondary pl-10 pr-4 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <button type="submit" disabled={isProcessing} className="flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-6 font-display text-base font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50">
              {isProcessing ? 'Memproses...' : 'Proses Klip'}
              {!isProcessing && <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>}
            </button>
          </div>

          {error && <p className="text-sm font-medium text-destructive">{error}</p>}

          <div className="flex flex-wrap items-center gap-3 text-xs text-muted">
            <div className="relative">
              <label className="sr-only" htmlFor="quality">Kualitas Video</label>
              <select id="quality" value={videoQuality} onChange={(e) => setVideoQuality(e.target.value)} className="h-9 appearance-none rounded-full border border-field bg-secondary pl-3.5 pr-8 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
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
              <select id="clip-count" value={numClips} onChange={(e) => setNumClips(Number(e.target.value))} className="h-9 appearance-none rounded-full border border-field bg-secondary pl-3.5 pr-8 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
                <option value={1}>1 klip</option>
                <option value={3}>3 klip</option>
                <option value={5}>5 klip</option>
              </select>
              <svg className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m6 9 6 6 6-6"/></svg>
            </div>
            <button type="button" onClick={() => setShowDirections(!showDirections)} className="inline-flex items-center gap-1.5 self-center text-xs font-medium text-primary transition-opacity hover:opacity-80">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9"/><path d="M16.376 3.622a1 1 0 0 1 3.002 3.002L7.368 18.635a2 2 0 0 1-.855.506l-2.872.838a.5.5 0 0 1-.62-.62l.838-2.872a2 2 0 0 1 .506-.854z"/></svg>
              Tambah Arahan
            </button>
            <div className="ml-auto flex items-center gap-2">
              <span className={`size-2 rounded-full ${isProcessing ? 'bg-primary animate-pulse' : 'bg-muted/40'}`} aria-hidden="true"></span>
              <span>Status: {isProcessing ? 'Memproses...' : 'Idle'}</span>
            </div>
          </div>
          {showDirections && (
            <textarea rows={3} placeholder="Contoh: fokus pada momen lucu, sertakan hook di 3 detik pertama..."
              value={instruction} onChange={e => setInstruction(e.target.value)}
              className="w-full rounded-xl border border-field bg-secondary px-4 py-3 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary"></textarea>
          )}
        </form>

        <div className="group relative flex flex-col overflow-hidden rounded-2xl border border-line bg-card text-left">
          <div className="relative min-h-[240px] flex-1 overflow-hidden bg-secondary">
            {previewThumbnail ? (
              <>
                <img src={previewThumbnail} alt="Thumbnail" className="absolute inset-0 size-full object-cover transition-transform duration-300 group-hover:scale-[1.04]" />
                <span className="absolute inset-0 z-[2] flex items-center justify-center" aria-hidden="true">
                  <span className="flex size-14 items-center justify-center rounded-full bg-foreground/90 text-background backdrop-blur transition-transform duration-200 group-hover:scale-110">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor" className="ml-0.5"><polygon points="6 3 20 12 6 21 6 3"/></svg>
                  </span>
                </span>
              </>
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-muted/30 pb-8">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect width="15" height="14" x="1" y="5" rx="2" ry="2"/></svg>
              </div>
            )}
            <div className="absolute inset-0 bg-gradient-to-t from-card to-transparent" style={{ background: 'linear-gradient(to top, #1c1d22, transparent 55%)' }} aria-hidden="true"></div>
          </div>
          <div className="relative z-[2] -mt-10 flex flex-col gap-1.5 p-5">
            
            <p className="font-display text-xl font-bold tracking-tight line-clamp-1">{videoMeta?.title || 'Belum ada riwayat'}</p>
            <div className="flex flex-wrap items-center gap-1.5 text-[0.8125rem] text-muted">
              <span>{clips.length} klip dihasilkan</span>
            </div>
          </div>
        </div>
      </div>

      {isProcessing && (
        <section className="flex flex-col gap-6 rounded-2xl border border-line bg-card p-6" aria-label="Proses AI sedang berjalan">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex flex-col gap-1">
              <h2 className="font-display text-[1.0625rem] font-bold">AI sedang memproses "{videoMeta?.title || youtubeUrl}"</h2>
              <p className="text-[0.8125rem] text-muted">{loadingPhrases[loadingPhraseIdx]}</p>
            </div>
            <span className="inline-flex items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-4 py-1.5 text-xs font-bold text-primary">
              <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
              Memproses
            </span>
            <button onClick={handleStop} className="rounded-full border border-destructive/40 bg-destructive/10 px-4 py-1.5 text-xs font-bold text-destructive">Batalkan proses</button>
          </div>
          <div className="grid gap-4 min-[900px]:grid-cols-4 min-[900px]:gap-0">
             <div className="relative flex items-start gap-3 min-[900px]:pr-6 min-[900px]:after:absolute min-[900px]:after:right-4 min-[900px]:after:top-5 min-[900px]:after:h-px min-[900px]:after:w-[calc(100%-4.25rem)] min-[900px]:after:bg-primary min-[900px]:after:content-['']">
                <span className="flex size-10 flex-none items-center justify-center rounded-xl border border-primary bg-primary text-primary-foreground" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
                </span>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <p className="text-sm font-bold">Transkripsi</p>
                  <p className="truncate text-xs text-muted">Audio diproses</p>
                </div>
              </div>
              <div className="relative flex items-start gap-3 min-[900px]:pr-6 min-[900px]:after:absolute min-[900px]:after:right-4 min-[900px]:after:top-5 min-[900px]:after:h-px min-[900px]:after:w-[calc(100%-4.25rem)] min-[900px]:after:bg-line min-[900px]:after:content-['']">
                <span className="flex size-10 flex-none items-center justify-center rounded-xl border border-primary bg-primary text-primary-foreground" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
                </span>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <p className="text-sm font-bold">Mencari Hook</p>
                  <p className="truncate text-xs text-muted">Momen viral terdeteksi</p>
                </div>
              </div>
              <div className="relative flex items-start gap-3 min-[900px]:pr-6 min-[900px]:after:absolute min-[900px]:after:right-4 min-[900px]:after:top-5 min-[900px]:after:h-px min-[900px]:after:w-[calc(100%-4.25rem)] min-[900px]:after:bg-line min-[900px]:after:content-['']">
                <span className="flex size-10 flex-none items-center justify-center rounded-xl border border-primary bg-primary/20 text-primary animate-pulse" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/></svg>
                </span>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <p className="text-sm font-bold">Memotong Klip</p>
                  <p className="truncate text-xs text-muted">reframing ke 9:16</p>
                </div>
              </div>
              <div className="relative flex items-start gap-3">
                <span className="flex size-10 flex-none items-center justify-center rounded-xl border border-line bg-secondary text-muted" aria-hidden="true">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="14" x="3" y="5" rx="2" ry="2"/><path d="M7 15h4M15 15h2M7 11h2M13 11h4"/></svg>
                </span>
                <div className="flex min-w-0 flex-col gap-0.5">
                  <p className="text-sm font-bold text-muted">Caption</p>
                  <p className="truncate text-xs text-muted">Menambahkan gaya teks</p>
                </div>
              </div>
          </div>
        </section>
      )}

      {/* Hasil Generasi Klip Section */}
      <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
          <section className="flex flex-col items-center justify-center gap-4 rounded-2xl border border-line bg-card/50 p-10 text-center" aria-label="Klip siap diedit">
            <h2 className="font-display text-xl font-bold">{clips.length ? `${clips.length} klip siap diedit` : 'Belum ada klip siap diedit'}</h2>
            <p className="max-w-md text-sm text-muted">Generate hanya membuat reframe draft. Atur hook, subtitle, watermark, lalu render final dari Preview.</p>
            <button type="button" onClick={() => navigate('/preview')} className="rounded-xl bg-primary px-5 py-3 text-sm font-bold text-primary-foreground">Buka Preview</button>
          </section>


          <aside className={`flex flex-col gap-5 rounded-2xl border border-line bg-card p-6 xl:sticky xl:top-24 ${clips.length === 0 ? 'h-full' : 'h-fit'}`} aria-label="Analisis viralitas">
            <div className="flex items-center gap-2">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f2a33c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/></svg>
              <h2 className="text-xs font-bold uppercase tracking-[0.15em] text-muted">Virality Wave</h2>
            </div>
            {clips.length === 0 || !viralityStats ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 py-8 text-center text-muted">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted/50"><path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2"/></svg>
                <p className="text-sm font-medium">Belum ada data</p>
                <p className="text-xs text-muted/70">Selesaikan proses untuk melihat analisis.</p>
              </div>
            ) : (
              <>
                <div className="flex items-baseline justify-between">
                  <p className="font-display text-5xl font-bold text-foreground">{viralityStats.average}%</p>
                  <span className="rounded-full bg-primary/15 px-3 py-1 text-[0.6875rem] font-bold tracking-wider text-primary">{viralityStats.label}</span>
                </div>
                <div className="flex h-24 items-end gap-1.5" role="img" aria-label={`Grafik gelombang viralitas dengan skor rata-rata ${viralityStats.average} persen`}>
                  {viralityStats.bars.map((score, i) => (
                    <span key={i} className={`flex-1 rounded-full ${score >= viralityStats.average ? 'bg-primary' : 'bg-secondary'}`} style={{ height: `${Math.max(18, score)}%` }}></span>
                  ))}
                </div>
                <div className="flex flex-col gap-2 rounded-xl bg-secondary/45 p-3">
                  {viralityStats.timeline.map((item) => (
                    <div key={item.clip.path || item.index} className="grid grid-cols-[auto_1fr_auto] items-center gap-2 text-xs">
                      <span className="font-bold text-primary">Klip {item.index + 1}</span>
                      <span className="truncate text-muted">{fmtClock(item.startSeconds)} • {item.clip.title || item.clip.name}</span>
                      <span className="font-bold text-foreground">{item.score}%</span>
                    </div>
                  ))}
                </div>
                <p className="text-sm leading-relaxed text-muted">Semua klip di atas berasal dari link terakhir yang berhasil digenerate. Skor tertinggi ada pada <strong className="font-medium text-foreground">Klip {viralityStats.best.index + 1}</strong>.</p>
                <div className="flex flex-col gap-2.5 border-t border-line pt-4">
                  <div className="flex items-center justify-between text-sm"><span className="text-muted">Skor tertinggi</span><span className="font-bold text-primary">{viralityStats.best.score}%</span></div>
                  <div className="flex items-center justify-between text-sm"><span className="text-muted">Rata-rata skor</span><span className="font-bold">{viralityStats.average}%</span></div>
                  <div className="flex items-center justify-between text-sm"><span className="text-muted">Total durasi</span><span className="font-bold">{Math.round(viralityStats.totalDuration)}s</span></div>
                </div>
                <div className="flex items-start gap-2.5 rounded-xl border border-primary/30 bg-primary/10 p-3.5 text-primary">
                  <svg className="mt-0.5 flex-none" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg>
                  <p className="text-xs leading-relaxed">Tips upload: unggah <strong>Klip {viralityStats.best.index + 1}</strong> sekitar pukul <strong>{viralityStats.uploadWindow}</strong>. Pakai hook awal yang sama dengan judul: <strong>{viralityStats.best.clip.title || viralityStats.best.clip.name}</strong>.</p>
                </div>
              </>
            )}
          </aside>
        </div>
      {/* Modals */}
      {showDetailModal && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Detail klip">
          <button type="button" onClick={() => setShowDetailModal(null)} className="absolute inset-0 bg-background/80" aria-label="Tutup detail klip"></button>
          <div className="relative z-10 grid max-h-[90dvh] w-full max-w-3xl gap-6 overflow-y-auto rounded-2xl border border-line bg-card p-6 sm:grid-cols-[260px_1fr]">
            <button type="button" onClick={() => setShowDetailModal(null)} className="absolute right-4 top-4 z-10 flex size-9 items-center justify-center rounded-full border border-line bg-secondary text-muted transition-colors hover:text-foreground" aria-label="Tutup">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
             <div className="relative mx-auto aspect-[9/16] w-full max-w-[260px] overflow-hidden rounded-xl border border-line bg-black">
               <video className="absolute inset-0 size-full object-contain" controls preload="metadata" poster={fmtImg(showDetailModal) || undefined} src={`/api/stream?path=${encodeURIComponent(showDetailModal.path)}`} />
               <span className="pointer-events-none absolute left-2.5 top-2.5 flex items-center gap-1.5 rounded-full bg-primary px-2.5 py-1 text-xs font-bold text-primary-foreground">
                 <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>
                 <span>{fmtScore(showDetailModal)}</span>
               </span>
             </div>
            <div className="flex flex-col gap-4">
              <p className="text-sm text-muted">Durasi: {fmtDuration(showDetailModal)}</p>
              <h2 className="pr-10 font-display text-2xl font-bold leading-snug">{showDetailModal.title || showDetailModal.name}</h2>
              <div className="flex flex-col gap-2">
                <h3 className="text-sm font-bold">Description</h3>
                <div className="flex flex-col gap-3 rounded-xl border border-line bg-secondary p-4 text-sm leading-relaxed text-muted">
                  <p>{showDetailModal.description}</p>
                </div>
              </div>
               <div className="rounded-xl border border-line bg-secondary/50 p-4">
                 <p className="mb-3 text-sm font-bold">Jadwalkan YouTube <span className="font-normal text-muted">(WIB, langsung public)</span></p>
                 {showDetailModal.youtube_upload?.status === 'scheduled' ? (
                   <div className="flex flex-wrap items-center gap-3 text-sm"><span className="text-primary">Dijadwalkan: {new Date(showDetailModal.youtube_upload.scheduled_at).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Jakarta' })} WIB</span><button type="button" onClick={() => handleCancelSchedule(showDetailModal)} className="font-medium text-destructive hover:underline">Batalkan</button></div>
                 ) : showDetailModal.youtube_upload?.status === 'uploaded' ? (
                   <a href={showDetailModal.youtube_upload.url} target="_blank" rel="noreferrer" className="text-sm font-medium text-emerald-500 hover:underline">Sudah diupload ke YouTube</a>
                 ) : (
                   <div className="flex flex-wrap gap-2"><input type="datetime-local" value={scheduleAt} onChange={e => setScheduleAt(e.target.value)} className="h-10 rounded-lg border border-field bg-card px-3 text-sm" /><button type="button" disabled={!scheduleAt} onClick={() => handleSchedule(showDetailModal)} className="h-10 rounded-lg bg-primary px-4 text-sm font-bold text-primary-foreground disabled:opacity-50">Jadwalkan</button></div>
                 )}
                 {showDetailModal.youtube_upload?.status === 'error' && <p className="mt-2 text-xs text-destructive">{showDetailModal.youtube_upload.error}</p>}
               </div>
               <div className="mt-auto flex flex-wrap gap-2.5 pt-2">
                 <button type="button" onClick={() => handleSave(showDetailModal)} disabled={isSaving} className="flex h-10 items-center gap-2 rounded-xl bg-primary px-4 text-sm font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50">

                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/></svg>
                  {isSaving ? 'Menyimpan...' : 'Simpan ke Gallery'}
                </button>
                <button type="button" onClick={() => { window.location.href = `/api/download?path=${encodeURIComponent(showDetailModal.path)}`; }} className="flex h-10 items-center gap-2 rounded-xl border border-line bg-secondary px-4 text-sm font-medium transition-colors hover:border-primary/40 hover:text-primary">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                  Download
                </button>
                <button type="button" onClick={() => handleUpload(showDetailModal)} className="flex h-10 items-center gap-2 rounded-xl border border-line bg-secondary px-4 text-sm font-medium transition-colors hover:border-primary/40 hover:text-primary">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>
                  Upload YouTube
                </button>
                <button type="button" onClick={() => setDeleteConfirm(showDetailModal)} className="flex h-10 items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-4 text-sm font-medium text-destructive transition-opacity hover:opacity-80">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                  Hapus
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}

      {stopConfirm && createPortal(
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/80" onClick={() => setStopConfirm(false)}>
          <div className="bg-card rounded-2xl w-full max-w-sm overflow-hidden border border-line p-6 flex flex-col gap-4 text-center" onClick={e => e.stopPropagation()}>
             <h3 className="font-display font-bold text-lg">Yakin hentikan proses?</h3>
             <p className="text-sm text-muted">Video yang sudah diproses sejauh ini mungkin hilang.</p>
             <div className="flex gap-3 justify-center mt-2">
               <button onClick={() => setStopConfirm(false)} className="px-5 py-2 rounded-xl font-medium border border-line text-foreground hover:bg-secondary">Batal</button>
               <button onClick={confirmStop} className="px-5 py-2 rounded-xl font-medium bg-destructive text-destructive-foreground">Ya, Hentikan</button>
             </div>
          </div>
        </div>,
        document.body
      )}

      {deleteConfirm && createPortal(
        <div className="fixed inset-0 z-[101] flex items-center justify-center p-4 bg-background/80" onClick={() => setDeleteConfirm(null)}>
          <div className="bg-card rounded-2xl w-full max-w-sm overflow-hidden border border-line p-6 flex flex-col gap-4 text-center" onClick={e => e.stopPropagation()}>
             <h3 className="font-display font-bold text-lg">Hapus Klip ini?</h3>
             <p className="text-sm text-muted">Klip yang dihapus tidak bisa dikembalikan lagi.</p>
             <div className="flex gap-3 justify-center mt-2">
               <button onClick={() => setDeleteConfirm(null)} className="px-5 py-2 rounded-xl font-medium border border-line text-foreground hover:bg-secondary">Batal</button>
               <button onClick={confirmDeleteClip} className="px-5 py-2 rounded-xl font-medium bg-destructive text-destructive-foreground">Hapus</button>
             </div>
          </div>
        </div>,
        document.body
      )}
    </main>
  );
}
