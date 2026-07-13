import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';

type Clip = {
  clip_id: string;
  status: string;
  title: string;
  description: string;
  duration_seconds?: number;
  virality_score?: number;
  stream_url: string;
  thumbnail_url?: string;
  render_error?: string;
  render_revision?: number;
  youtube_upload?: { status: string; scheduled_at?: string; url?: string; error?: string } | null;
};

const panelStates: Record<string, string[]> = {
  queue: ['needs_edit', 'preview_rendering'],
  processing: ['render_queued', 'rendering', 'render_error'],
  schedule: ['ready_to_schedule', 'scheduled', 'uploading'],
  result: ['uploaded', 'upload_error'],
};

export default function Preview() {
  const navigate = useNavigate();
  const [clips, setClips] = useState<Clip[]>([]);
  const [selected, setSelected] = useState<Clip | null>(null);
  const [draft, setDraft] = useState<any>(null);
  const [previewUrl, setPreviewUrl] = useState('');
  const [scheduleAt, setScheduleAt] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const response = await api('/api/clips');
      setClips(response.clips || []);
      setSelected(current => (current ? (response.clips || []).find((clip: Clip) => clip.clip_id === current.clip_id) || null : null));
    } catch (e: any) {
      setError(e.message || 'Gagal memuat klip');
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const active = clips.some(clip => panelStates.processing.includes(clip.status) || clip.status === 'uploading');
    if (!active) return;
    const timer = window.setInterval(load, 2000);
    return () => window.clearInterval(timer);
  }, [clips, load]);

  const openEditor = async (clip: Clip) => {
    setBusy('load');
    setError('');
    try {
      const response = await api(`/api/clip?clip_id=${encodeURIComponent(clip.clip_id)}`);
      setSelected({ ...clip, ...response.clip });
      setDraft(response.clip.render_settings || response.defaults || {});
      setPreviewUrl('');
    } catch (e: any) {
      setError(e.message || 'Gagal membuka editor');
    } finally {
      setBusy('');
    }
  };

  const update = (section: string, key: string, value: any) => setDraft((current: any) => ({ ...current, [section]: { ...(current?.[section] || {}), [key]: value } }));
  const request = async (path: string, body: any) => {
    if (!selected) return null;
    setBusy(path);
    setError('');
    try { return await api(path, { method: 'POST', body: JSON.stringify({ clip_id: selected.clip_id, ...body }) }); }
    catch (e: any) { setError(e.message || 'Proses gagal'); return null; }
    finally { setBusy(''); }
  };
  const renderPreview = async () => {
    const response = await request('/api/clip/preview', { settings: draft });
    if (response?.stream_url) setPreviewUrl(response.stream_url);
  };
  const renderFinal = async () => { if (await request('/api/clip/render', { settings: draft })) { setSelected(null); await load(); } };
  const saveDefaults = async () => { await request('/api/clip/defaults', { settings: draft }); };
  const schedule = async (clip: Clip) => {
    if (!scheduleAt) return;
    setBusy('schedule');
    try {
      await api('/api/social/youtube/schedule', { method: 'POST', body: JSON.stringify({ path: clip.stream_url.split('path=')[1]?.split('&')[0] ? decodeURIComponent(clip.stream_url.split('path=')[1].split('&')[0]) : '', title: clip.title, description: clip.description, scheduled_at: scheduleAt }) });
      await load();
    } catch (e: any) { setError(e.message || 'Gagal menjadwalkan'); }
    finally { setBusy(''); }
  };

  const panels = useMemo(() => Object.fromEntries(Object.entries(panelStates).map(([key, states]) => [key, clips.filter(clip => states.includes(clip.status))])), [clips]);
  const label = (clip: Clip) => `${clip.title} · ${Math.round(clip.duration_seconds || 0)}s`;

  return <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-10">
    <header><p className="text-sm font-medium uppercase tracking-widest text-primary">Workflow Klip</p><h1 className="font-display text-3xl font-bold">Preview & Render</h1><p className="text-muted">Preview FFmpeg dan final render memakai renderer yang sama.</p></header>
    {error && <p className="rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">{error}</p>}
    <section className="grid gap-4 lg:grid-cols-4">
      <Panel title="Queue" subtitle="Klip siap diedit" clips={panels.queue} action={clip => <button onClick={() => openEditor(clip)} className="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground">Edit</button>} label={label} />
      <Panel title="Proses" subtitle="Final render" clips={panels.processing} action={clip => <span className="text-xs text-muted">{clip.status === 'render_error' ? clip.render_error || 'Gagal' : 'Memproses...'}</span>} label={label} />
      <Panel title="Set Waktu" subtitle="Final siap upload" clips={panels.schedule} action={clip => clip.status === 'ready_to_schedule' ? <div className="flex flex-col gap-2"><input type="datetime-local" value={scheduleAt} onChange={e => setScheduleAt(e.target.value)} className="rounded-lg border border-field bg-secondary p-2 text-xs" /><button disabled={!scheduleAt || !!busy} onClick={() => schedule(clip)} className="rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground">Jadwalkan WIB</button></div> : <span className="text-xs text-primary">{clip.status === 'uploading' ? 'Uploading...' : 'Terjadwal'}</span>} label={label} />
      <Panel title="Hasil" subtitle="Upload berhasil/gagal" clips={panels.result} action={clip => clip.youtube_upload?.url ? <a className="text-xs text-primary hover:underline" href={clip.youtube_upload.url} target="_blank" rel="noreferrer">Buka YouTube</a> : <span className="text-xs text-destructive">{clip.youtube_upload?.error || 'Gagal upload'}</span>} label={label} />
    </section>
    {selected && draft && createPortal(<div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Edit klip"><button type="button" onClick={() => setSelected(null)} className="absolute inset-0 bg-background/80" aria-label="Tutup editor" /><section className="relative z-10 grid max-h-[90dvh] w-full max-w-4xl gap-6 overflow-y-auto rounded-2xl border border-line bg-card p-6 lg:grid-cols-[300px_1fr]"><button type="button" onClick={() => setSelected(null)} className="absolute right-4 top-4 rounded-full border border-line px-3 py-1 text-sm text-muted">Tutup</button><div><video controls className="aspect-[9/16] w-full rounded-xl bg-black object-contain" src={previewUrl || selected.stream_url} /></div><div className="flex flex-col gap-5 pt-8 lg:pt-0"><div><h2 className="font-display text-xl font-bold">{selected.title}</h2><p className="text-sm text-muted">Atur klip ini. Perubahan tidak mengubah default akun kecuali disimpan.</p></div><div className="grid gap-4 md:grid-cols-2"><EditorToggle label="Hook" value={draft.hook_style?.enabled} onChange={value => update('hook_style', 'enabled', value)} /><EditorToggle label="Subtitle" value={draft.subtitle?.enabled} onChange={value => update('subtitle', 'enabled', value)} /><EditorToggle label="Watermark" value={draft.watermark?.enabled} onChange={value => update('watermark', 'enabled', value)} /><EditorToggle label="Source credit" value={draft.credit_watermark?.enabled} onChange={value => update('credit_watermark', 'enabled', value)} /><EditorNumber label="Posisi Hook Y" value={draft.hook_style?.position_y ?? .2} onChange={value => update('hook_style', 'position_y', value)} /><EditorNumber label="Posisi Subtitle Y" value={draft.subtitle?.position_y ?? .85} onChange={value => update('subtitle', 'position_y', value)} /><EditorNumber label="Ukuran Hook" value={draft.hook_style?.font_size ?? .054} step="0.001" onChange={value => update('hook_style', 'font_size', value)} /><EditorNumber label="Ukuran Subtitle" value={draft.subtitle?.size ?? .04} step="0.001" onChange={value => update('subtitle', 'size', value)} /></div><div className="flex flex-wrap gap-3"><button disabled={!!busy} onClick={renderPreview} className="rounded-xl border border-line px-4 py-2 text-sm font-bold disabled:opacity-50">{busy === '/api/clip/preview' ? 'Merender...' : 'Render Preview'}</button><button disabled={!!busy} onClick={saveDefaults} className="rounded-xl border border-line px-4 py-2 text-sm font-bold disabled:opacity-50">Simpan sebagai default</button><button disabled={!!busy} onClick={renderFinal} className="rounded-xl bg-primary px-4 py-2 text-sm font-bold text-primary-foreground disabled:opacity-50">Lanjut ke tahap berikutnya</button></div></div></section></div>, document.body)}
    {!selected && clips.length === 0 && <section className="rounded-2xl border border-dashed border-line p-12 text-center"><p className="font-bold">Belum ada klip.</p><button onClick={() => navigate('/')} className="mt-3 text-sm font-bold text-primary">Kembali ke Dashboard</button></section>}
  </main>;
}

function Panel({ title, subtitle, clips, action, label }: { title: string; subtitle: string; clips: Clip[]; action: (clip: Clip) => ReactNode; label: (clip: Clip) => string }) {
  return <section className="min-h-64 rounded-2xl border border-line bg-card p-4"><h2 className="font-display text-lg font-bold">{title}</h2><p className="mb-4 text-xs text-muted">{subtitle}</p><div className="flex flex-col gap-3">{clips.length ? clips.map(clip => <article key={clip.clip_id} className="rounded-xl border border-line bg-secondary/50 p-3"><p className="line-clamp-2 text-sm font-bold">{label(clip)}</p><div className="mt-3">{action(clip)}</div></article>) : <p className="py-8 text-center text-xs text-muted">Kosong</p>}</div></section>;
}
function EditorToggle({ label, value, onChange }: { label: string; value: boolean; onChange: (value: boolean) => void }) { return <label className="flex items-center justify-between rounded-xl border border-line p-3 text-sm font-medium">{label}<input type="checkbox" checked={!!value} onChange={e => onChange(e.target.checked)} /></label>; }
function EditorNumber({ label, value, step = '0.01', onChange }: { label: string; value: number; step?: string; onChange: (value: number) => void }) { return <label className="flex flex-col gap-1 rounded-xl border border-line p-3 text-sm font-medium">{label}<input type="number" min="0" max="1" step={step} value={value} onChange={e => onChange(Number(e.target.value))} className="rounded-lg border border-field bg-secondary p-2" /></label>; }
