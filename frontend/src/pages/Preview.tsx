import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { WorkflowPanel, type WorkflowClip } from '@/components/clip-workflow/WorkflowPanel';
import { ConfirmModal } from '@/components/ui/ConfirmModal';
import { apiGet, apiPost } from '@/lib/api';
import { defaultWibScheduleTime, validateWibSchedule } from '@/lib/schedule';

type ClipsResponse = { status: string; clips: WorkflowClip[] };
type ActionResponse = { status: string; message?: string };

export default function Preview() {
  const navigate = useNavigate();
  const [clips, setClips] = useState<WorkflowClip[]>([]);
  const [busy, setBusy] = useState('');
  const [pageError, setPageError] = useState('');
  const [scheduleAt, setScheduleAt] = useState<Record<string, string>>({});
  const [uploadText, setUploadText] = useState<Record<string, { title: string; description: string; hook_text: string }>>({});
  const [scheduleError, setScheduleError] = useState<Record<string, string>>({});
  const [deleteTarget, setDeleteTarget] = useState<WorkflowClip | null>(null);
  const previousActive = useRef(false);
  const loadSequence = useRef(0);

  const load = useCallback(async () => {
    const sequence = ++loadSequence.current;
    try {
      const data = await apiGet<ClipsResponse>('/api/clips');
      if (sequence !== loadSequence.current) return;
      setClips(data.clips || []);
      setUploadText((current) => {
        const next = { ...current };
        data.clips.forEach((clip) => {
          if (!next[clip.clip_id]) {
            next[clip.clip_id] = {
              title: clip.youtube_upload?.title || clip.title,
              description: clip.youtube_upload?.description || clip.description,
              hook_text: clip.hook_text || '',
            };
          }
        });
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

  const scheduleClip = async (clip: WorkflowClip) => {
    const scheduledAt = scheduleAt[clip.clip_id];
    const text = uploadText[clip.clip_id] || { title: clip.title, description: clip.description, hook_text: clip.hook_text || '' };
    const localError = validateWibSchedule(scheduledAt);
    setScheduleError((current) => ({ ...current, [clip.clip_id]: localError }));
    if (localError) return;
    const result = await run('/api/clip/schedule', {
      clip_id: clip.clip_id,
      scheduled_at: scheduledAt,
      title: text.title,
      description: text.description,
    }, 'Jadwal gagal disimpan.');
    if (result) {
      setScheduleAt((current) => ({ ...current, [clip.clip_id]: '' }));
      await load();
    }
  };

  const editHook = async (clip: WorkflowClip) => {
    const text = uploadText[clip.clip_id] || { title: clip.title, description: clip.description, hook_text: clip.hook_text || '' };
    const words = text.hook_text.trim().split(/\s+/).filter(Boolean);
    if (words.length > 8) {
      setPageError('Hook maksimal 8 kata.');
      return;
    }
    const result = await run('/api/clip/hook', { clip_id: clip.clip_id, hook_text: text.hook_text }, 'Render ulang hook gagal.');
    if (result) navigate('/');
  };

  const actionAndLoad = async (path: string, clip: WorkflowClip, fallback: string, body: object = {}) => {
    if (await run(path, { clip_id: clip.clip_id, ...body }, fallback)) await load();
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    if (await run('/api/clip/delete', { clip_id: deleteTarget.clip_id }, 'Klip gagal dihapus.')) {
      setDeleteTarget(null);
      await load();
    }
  };

  return <main className="mx-auto flex w-full max-w-[90rem] flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
    <header className="flex flex-col gap-2">
      <p className="text-sm font-bold text-primary">Workflow V3</p>
      <h1 className="font-display text-3xl font-bold tracking-tight">Set Waktu & Hasil</h1>
      <p className="max-w-2xl text-sm leading-relaxed text-muted">Edit hook teks saja, jadwalkan upload WIB, lalu pantau hasil. Tidak ada upload langsung.</p>
    </header>
    {pageError && <div role="alert" className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-sm font-medium text-destructive">{pageError}</div>}
    <WorkflowPanel
      clips={clips}
      busy={busy}
      scheduleAt={scheduleAt}
      uploadText={uploadText}
      scheduleError={scheduleError}
      onScheduleAtChange={(clipId, value) => {
        setScheduleAt((current) => ({ ...current, [clipId]: value }));
        setScheduleError((current) => ({ ...current, [clipId]: '' }));
      }}
      onUploadTextChange={(clipId, value) => setUploadText((current) => ({ ...current, [clipId]: value }))}
      onSchedule={scheduleClip}
      onEditHook={editHook}
      onCancelSchedule={(clip) => actionAndLoad('/api/clip/schedule/cancel', clip, 'Jadwal gagal dibatalkan.')}
      onRetryRender={(clip) => actionAndLoad('/api/clip/render/retry', clip, 'Render gagal dimulai ulang.')}
      onRetryUpload={(clip) => actionAndLoad('/api/clip/upload/retry', clip, 'Upload gagal dikembalikan ke Set Waktu.')}
      onDelete={setDeleteTarget}
    />
    <ConfirmModal
      isOpen={Boolean(deleteTarget)}
      title="Hapus klip lokal?"
      message={deleteTarget ? `File lokal “${deleteTarget.title}” akan dihapus permanen. Video YouTube yang sudah tayang tidak ikut dihapus.` : ''}
      onConfirm={confirmDelete}
      onCancel={() => setDeleteTarget(null)}
      busy={busy === '/api/clip/delete'}
    />
  </main>;
}

function messageOf(error: unknown, fallback: string) {
  return error instanceof Error && error.message ? error.message : fallback;
}
