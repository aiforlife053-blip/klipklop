import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ClipEditorModal, type EditorClip } from '@/components/clip-editor/ClipEditorModal';
import { WorkflowPanel, type WorkflowClip } from '@/components/clip-workflow/WorkflowPanel';
import { ConfirmModal } from '@/components/ui/ConfirmModal';
import { apiGet, apiPost } from '@/lib/api';
import { cloneSettings, mergeSettings, validateSettings, type ClipSettings, type SettingValue } from '@/lib/clip-settings';

type ClipsResponse = { status: string; clips: WorkflowClip[] };
type ClipResponse = { status: string; clip: WorkflowClip & EditorClip & { render_settings?: Partial<ClipSettings>; draft_settings?: Partial<ClipSettings>; hook_text?: string }; defaults: ClipSettings };
type ActionResponse = { status: string; message?: string; stream_url?: string; preview_id?: string };
type GamingDetectionResponse = { status: string; message?: string; facecam?: { x: number; y: number; width: number; height: number }; confidence?: number };
type PreviewStatus = { state: 'queued' | 'rendering' | 'ready' | 'cancelled' | 'error'; stage: string; progress: number; elapsed_seconds: number; stream_url?: string; error?: string };
type DeleteTarget = WorkflowClip | null;
type GenerationClip = WorkflowClip & { generation_id?: string };

export function defaultWibScheduleTime(now = new Date()): string {
  const target = new Date(now.getTime() + 15 * 60_000);
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Jakarta',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(target).map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

export default function Preview() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const requestedGenerationId = searchParams.get('generation_id') || '';
  const [clips, setClips] = useState<GenerationClip[]>([]);
  const [selected, setSelected] = useState<ClipResponse['clip'] | null>(null);
  const [settings, setSettings] = useState<ClipSettings | null>(null);
  const [defaults, setDefaults] = useState<ClipSettings | null>(null);
  const [hookText, setHookText] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewState, setPreviewState] = useState('');
  const [previewProgress, setPreviewProgress] = useState(0);
  const [previewElapsed, setPreviewElapsed] = useState(0);
  const [previewStale, setPreviewStale] = useState(false);
  const previewId = useRef('');
  const [busy, setBusy] = useState('');
  const [pageError, setPageError] = useState('');
  const [editorError, setEditorError] = useState('');
  const [gamingDetectionStatus, setGamingDetectionStatus] = useState('');
  const [gamingDetectionBusy, setGamingDetectionBusy] = useState(false);
  const [scheduleAt, setScheduleAt] = useState<Record<string, string>>({});
  const [uploadText, setUploadText] = useState<Record<string, { title: string; description: string }>>({});
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget>(null);
  const previousActive = useRef(false);
  const loadSequence = useRef(0);
  const detectionSequence = useRef(0);
  const selectedClipId = useRef('');

  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    try {
      const data = await apiGet<ClipsResponse>('/api/clips');
      if (sequence !== loadSequence.current) return;
      setClips(data.clips || []);
      setUploadText((current) => {
        const next = { ...current };
        data.clips.forEach((clip) => { if (!next[clip.clip_id]) next[clip.clip_id] = { title: clip.youtube_upload?.title || clip.title, description: clip.youtube_upload?.description || clip.description }; });
        return next;
      });
      setScheduleAt((current) => {
        const next = { ...current };
        data.clips.forEach((clip) => {
          if (clip.status === 'ready_to_schedule' && !next[clip.clip_id]) next[clip.clip_id] = defaultWibScheduleTime();
        });
        return next;
      });
      setPageError('');
    } catch (requestError) {
      setPageError(messageOf(requestError, 'Gagal memuat klip.'));
    }
  }, []);

  const active = clips.some((clip) => ['render_queued', 'rendering', 'scheduled', 'uploading'].includes(clip.status));

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    if (!active) {
      if (previousActive.current) void load();
      previousActive.current = false;
      return;
    }
    previousActive.current = true;
    const timer = window.setInterval(() => void load(), 2000);
    return () => window.clearInterval(timer);
  }, [active, load]);

  const run = async <T extends ActionResponse>(path: string, body: object, fallback: string): Promise<T | null> => {
    setBusy(path);
    setPageError('');
    try {
      return await apiPost<T, object>(path, body);
    } catch (requestError) {
      setPageError(messageOf(requestError, fallback));
      return null;
    } finally {
      setBusy('');
    }
  };

  const openEditor = async (clip: WorkflowClip) => {
    detectionSequence.current += 1;
    selectedClipId.current = clip.clip_id;
    setBusy('editor');
    setPageError('');
    try {
      const data = await apiGet<ClipResponse>(`/api/clip?clip_id=${encodeURIComponent(clip.clip_id)}`);
      const snapshot = data.clip.render_settings || data.clip.draft_settings;
      const merged = mergeSettings(data.defaults, snapshot);
      if (data.clip.subtitle_capability === 'unavailable') merged.subtitle.enabled = false;
      const snapshotBlur = data.clip.draft_settings?.blur_background;
      if (snapshotBlur) merged.blur_background = { ...merged.blur_background, ...snapshotBlur };
      setSelected(data.clip);
      setDefaults(cloneSettings(data.defaults));
      setSettings(merged);
      setHookText(data.clip.hook_text || '');
      setPreviewUrl('');
      setPreviewStale(false);
      setPreviewState('');
      previewId.current = '';
      setEditorError('');
      setGamingDetectionStatus(merged.video_layout.mode === 'gaming' ? 'Facecam terdeteksi.' : '');
      setGamingDetectionBusy(false);
    } catch (requestError) {
      setPageError(messageOf(requestError, 'Editor gagal dibuka.'));
    } finally {
      setBusy('');
    }
  };

  const changeSetting = (section: keyof ClipSettings, key: string, value: SettingValue) => {
    setSettings((current) => current ? { ...current, [section]: { ...(typeof current[section] === 'object' ? current[section] : {}), [key]: value } } : current);
    setEditorError('');
    setPreviewStale(true);
  };

  const resetSection = (section: keyof ClipSettings) => {
    if (!defaults) return;
    setSettings((current) => current ? { ...current, [section]: typeof defaults[section] === 'object' ? { ...defaults[section] } : defaults[section] } : current);
    setEditorError('');
    setPreviewStale(true);
  };

  const detectGaming = async (force = false) => {
    if (!selected || gamingDetectionBusy) return;
    const clipId = selected.clip_id;
    const sequence = ++detectionSequence.current;
    const currentRequest = () => detectionSequence.current === sequence && selectedClipId.current === clipId;
    setSettings((current) => current ? { ...current, video_layout: { mode: 'gaming' } } : current);
    setGamingDetectionBusy(true);
    setGamingDetectionStatus('Mendeteksi facecam…');
    setEditorError('');
    setPreviewStale(true);
    try {
      const data = await apiPost<GamingDetectionResponse, object>('/api/clip/gaming/detect', { clip_id: clipId, ...(force ? { force: true } : {}) });
      if (!currentRequest()) return;
      if (data.status !== 'ok' || !data.facecam) throw new Error(data.message || 'Facecam tidak ditemukan.');
      setSettings((current) => current ? { ...current, video_layout: { mode: 'gaming', facecam_x: data.facecam?.x, facecam_y: data.facecam?.y, facecam_width: data.facecam?.width, facecam_height: data.facecam?.height, facecam_confidence: data.confidence } } : current);
      setGamingDetectionStatus('Facecam terdeteksi.');
    } catch (requestError) {
      if (!currentRequest()) return;
      setGamingDetectionStatus('Deteksi facecam gagal.');
      setEditorError(messageOf(requestError, 'Facecam tidak ditemukan. Coba deteksi ulang.'));
    } finally {
      if (currentRequest()) setGamingDetectionBusy(false);
    }
  };

  const changeVideoLayout = (mode: 'normal' | 'gaming') => {
    if (mode === 'normal') {
      setSettings((current) => current ? { ...current, video_layout: { ...current.video_layout, mode } } : current);
      setGamingDetectionStatus('');
      setEditorError('');
      setPreviewStale(true);
      return;
    }
    void detectGaming();
  };

  const renderPreview = async () => {
    if (!selected || !settings) return;
    setPreviewBusy(true);
    setPreviewProgress(0);
    setPreviewElapsed(0);
    setPreviewState('Menunggu render');
    setPreviewStale(false);
    setEditorError('');
    try {
      const data = await apiPost<ActionResponse, object>('/api/clip/preview', { clip_id: selected.clip_id, settings, hook_text: hookText });
      if (data.stream_url) { setPreviewUrl(data.stream_url); setPreviewBusy(false); return; }
      if (!data.preview_id) throw new Error('Preview ID tidak tersedia');
      const activeId = data.preview_id;
      previewId.current = activeId;
      const poll = async (): Promise<void> => {
        const status = await apiGet<PreviewStatus>(`/api/clip/preview/status?clip_id=${encodeURIComponent(selected.clip_id)}&preview_id=${encodeURIComponent(activeId)}`);
        if (previewId.current !== activeId) return;
        setPreviewState(status.stage);
        setPreviewProgress(status.progress);
        setPreviewElapsed(status.elapsed_seconds);
        if (status.state === 'ready') { setPreviewUrl(status.stream_url || ''); setPreviewBusy(false); return; }
        if (status.state === 'cancelled') { setPreviewBusy(false); setPreviewStale(true); return; }
        if (status.state === 'error') throw new Error(status.error || 'Preview gagal.');
        window.setTimeout(() => void poll().catch((error) => { if (previewId.current === activeId) { setEditorError(messageOf(error, 'Preview gagal.')); setPreviewBusy(false); } }), 1000);
      };
      await poll();
    } catch (requestError) {
      setEditorError(messageOf(requestError, 'Preview gagal. Periksa pengaturan lalu coba lagi.'));
      setPreviewBusy(false);
    }
  };

  const cancelPreview = async () => {
    if (!selected || !previewId.current) return;
    try { await apiPost('/api/clip/preview/cancel', { clip_id: selected.clip_id, preview_id: previewId.current }); } catch (error) { setEditorError(messageOf(error, 'Preview tidak dapat dibatalkan.')); }
  };

  const saveDefaults = async () => {
    if (!selected || !settings) return;
    setBusy('defaults');
    setEditorError('');
    try {
      await apiPost<ActionResponse, object>('/api/clip/defaults', { clip_id: selected.clip_id, settings });
      setDefaults(cloneSettings(settings));
    } catch (requestError) {
      setEditorError(messageOf(requestError, 'Default gagal disimpan.'));
    } finally {
      setBusy('');
    }
  };

  const renderFinal = async () => {
    if (!selected || !settings) return;
    setBusy('render');
    setEditorError('');
    try {
      await apiPost<ActionResponse, object>('/api/clip/render', { clip_id: selected.clip_id, settings, hook_text: hookText });
      setSelected(null);
      setSettings(null);
      await load();
    } catch (requestError) {
      setEditorError(messageOf(requestError, 'Render final gagal dimulai.'));
    } finally {
      setBusy('');
    }
  };

  const uploadNow = async (clip: WorkflowClip) => {
    const text = uploadText[clip.clip_id] || { title: clip.title, description: clip.description };
    if (await run('/api/clip/upload', { clip_id: clip.clip_id, ...text }, 'Upload gagal.')) await load();
  };

  const scheduleClip = async (clip: WorkflowClip) => {
    const scheduledAt = scheduleAt[clip.clip_id];
    const text = uploadText[clip.clip_id] || { title: clip.title, description: clip.description };
    if (!scheduledAt) return;
    if (await run('/api/clip/schedule', { clip_id: clip.clip_id, scheduled_at: scheduledAt, ...text }, 'Jadwal gagal disimpan.')) {
      setScheduleAt((current) => ({ ...current, [clip.clip_id]: '' }));
      await load();
    }
  };

  const actionAndLoad = async (path: string, clip: WorkflowClip, fallback: string, body: object = {}) => {
    if (await run(path, { clip_id: clip.clip_id, ...body }, fallback)) await load();
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    if (await run('/api/clip/delete', { clip_id: target.clip_id }, 'Klip gagal dihapus.')) {
      setDeleteTarget(null);
      await load();
    }
  };

  const invalid = useMemo(() => settings ? validateSettings(settings).length > 0 : true, [settings]);
  const prioritizedClips = useMemo(() => {
    if (!requestedGenerationId) return clips;
    const newestQueue = clips.filter((clip) => clip.status === 'needs_edit' && (clip.generation_id || clip.clip_id) === requestedGenerationId);
    const otherWorkflow = clips.filter((clip) => clip.status !== 'needs_edit');
    return [...newestQueue, ...otherWorkflow];
  }, [clips, requestedGenerationId]);

  return <main className="mx-auto flex w-full max-w-[90rem] flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
    <header className="flex flex-col gap-2">
      <p className="text-sm font-bold text-primary">Workflow Klip</p>
      <h1 className="font-display text-3xl font-bold tracking-tight">Preview & Render</h1>
      <p className="max-w-2xl text-sm leading-relaxed text-muted">Edit draft, pantau render final, lalu upload atau jadwalkan ke YouTube.</p>
    </header>
    {pageError && <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-sm font-medium text-destructive">{pageError}</div>}
    <WorkflowPanel clips={prioritizedClips} busy={busy} scheduleAt={scheduleAt} uploadText={uploadText} onScheduleAtChange={(clipId, value) => setScheduleAt((current) => ({ ...current, [clipId]: value }))} onUploadTextChange={(clipId, value) => setUploadText((current) => ({ ...current, [clipId]: value }))} onEdit={openEditor} onDelete={setDeleteTarget} onUpload={uploadNow} onSchedule={scheduleClip} onCancelSchedule={(clip) => actionAndLoad('/api/clip/schedule/cancel', clip, 'Jadwal gagal dibatalkan.')} onEditAgain={(clip) => actionAndLoad('/api/clip/edit', clip, 'Klip gagal dikembalikan ke editor.')} onRetryRender={(clip) => actionAndLoad('/api/clip/render/retry', clip, 'Render gagal dimulai ulang.')} onRetryUpload={(clip) => actionAndLoad('/api/clip/upload/retry', clip, 'Upload gagal diulang.', { upload_now: true })} onBackToSchedule={(clip) => actionAndLoad('/api/clip/upload/retry', clip, 'Klip gagal dikembalikan ke Set Waktu.')} onDashboard={() => navigate('/')} />
    {selected && settings && defaults && <ClipEditorModal clip={selected} settings={settings} previewUrl={previewUrl} previewBusy={previewBusy} actionBusy={Boolean(busy)} error={editorError} invalid={invalid} hookText={hookText} backgroundVisible={settings.screen_size !== '16:9' && settings.video_layout.mode !== 'gaming'} gamingDetectionStatus={gamingDetectionStatus} gamingDetectionBusy={gamingDetectionBusy} previewState={previewState} previewProgress={previewProgress} previewElapsed={previewElapsed} previewStale={previewStale} onHookTextChange={(value) => { setHookText(value); setPreviewStale(true); }} onClose={() => { detectionSequence.current += 1; selectedClipId.current = ''; setSelected(null); setSettings(null); setEditorError(''); setGamingDetectionBusy(false); }} onChange={changeSetting} onVideoLayoutChange={changeVideoLayout} onRedetectGaming={() => void detectGaming(true)} onClearError={() => setEditorError('')} onReset={resetSection} onPreview={renderPreview} onCancelPreview={cancelPreview} onSaveDefaults={saveDefaults} onRender={renderFinal} />}
    <ConfirmModal isOpen={Boolean(deleteTarget)} title="Hapus klip lokal?" message={deleteTarget ? `File lokal “${deleteTarget.title}” akan dihapus permanen. Video YouTube yang sudah tayang tidak ikut dihapus.` : ''} onConfirm={confirmDelete} onCancel={() => setDeleteTarget(null)} busy={busy === '/api/clip/delete'} />
  </main>;
}

function messageOf(error: unknown, fallback: string) { return error instanceof Error && error.message ? error.message : fallback; }
