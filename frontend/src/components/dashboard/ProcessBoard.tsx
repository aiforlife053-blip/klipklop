export type ProcessClip = {
  clip_id: string;
  title?: string;
  status?: string;
  render_error?: string;
  render?: { progress?: number; stage?: string; elapsed_seconds?: number; error?: string };
  youtube_upload?: { error?: string; scheduled_at?: string } | null;
};

type Props = {
  clips: ProcessClip[];
  job?: { status?: string; message?: string; progress?: number; error?: string } | null;
  busy?: string;
  onGlobalCancel: () => void;
  onFacecam: (clip: ProcessClip) => void;
  onRetry: (clip: ProcessClip) => void;
  onCancel: (clip: ProcessClip) => void;
  onDelete: (clip: ProcessClip) => void;
};

const active = new Set(['needs_facecam', 'render_queued', 'rendering', 'scheduled', 'uploading']);
const result = new Set(['render_error', 'upload_error', 'cancelled']);

export function ProcessBoard({ clips, job, busy, onGlobalCancel, onFacecam, onRetry, onCancel, onDelete }: Props) {
  const visible = clips.filter((clip) => active.has(clip.status || '') || result.has(clip.status || ''));
  const jobActive = ['queued', 'running', 'stopping'].includes(job?.status || '');
  if (!jobActive && visible.length === 0) return null;
  return <section className="space-y-4" aria-label="Semua proses aktif">
    <div className="flex items-center justify-between gap-3">
      <div><h2 className="font-display text-xl font-bold">Proses</h2><p className="text-sm text-muted">Semua proses tersimpan dan tetap tampil setelah refresh.</p></div>
      {jobActive && <button type="button" onClick={onGlobalCancel} className="rounded-xl border border-destructive/50 px-4 py-2 text-sm font-bold text-destructive">Batalkan generate</button>}
    </div>
    {jobActive && <ProcessCard title="Generate video" status={job?.status || 'running'} stage={job?.message} progress={job?.progress} error={job?.error} />}
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {visible.map((clip) => {
        const status = clip.status || '';
        const failed = status.endsWith('_error');
        return <article key={clip.clip_id} className={`rounded-xl border p-4 ${failed ? 'border-destructive/60' : status === 'cancelled' ? 'border-muted/50' : 'border-line'} bg-card`}>
          <div className="flex items-start justify-between gap-3"><h3 className="line-clamp-2 text-sm font-bold">{clip.title || clip.clip_id}</h3><span className="rounded-full bg-secondary px-2 py-1 text-[11px] font-bold">{status}</span></div>
          <p className={`mt-2 text-xs ${failed ? 'text-destructive' : 'text-muted'}`}>{clip.render?.stage || clip.render?.error || clip.render_error || clip.youtube_upload?.error || statusText(status)}</p>
          {['render_queued', 'rendering'].includes(status) && <Progress value={clip.render?.progress} elapsed={clip.render?.elapsed_seconds} />}
          <div className="mt-3 flex flex-wrap gap-2">
            {status === 'needs_facecam' && <Action disabled={Boolean(busy)} onClick={() => onFacecam(clip)}>Pilih Facecam</Action>}
            {failed && <Action disabled={Boolean(busy)} onClick={() => onRetry(clip)}>Retry</Action>}
            {['render_queued', 'rendering', 'scheduled'].includes(status) && <Action disabled={Boolean(busy)} onClick={() => onCancel(clip)}>Batalkan</Action>}
            {result.has(status) && <Action disabled={Boolean(busy)} onClick={() => onDelete(clip)}>Hapus</Action>}
          </div>
        </article>;
      })}
    </div>
  </section>;
}

function ProcessCard({ title, status, stage, progress, error }: { title: string; status: string; stage?: string; progress?: number; error?: string }) {
  return <article className="rounded-xl border border-line bg-card p-4"><div className="flex justify-between gap-3"><h3 className="text-sm font-bold">{title}</h3><span className="text-xs text-muted">{status}</span></div><p className="mt-2 text-xs text-muted">{error || stage || 'Memproses'}</p><Progress value={progress} /></article>;
}
function Progress({ value = 0, elapsed }: { value?: number; elapsed?: number }) { const percent = Math.round(Math.max(0, Math.min(1, Number(value) || 0)) * 100); return <div className="mt-3"><div className="mb-1 flex justify-between text-[11px] text-muted"><span>{percent}%</span><span>{formatElapsed(elapsed)}</span></div><div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full bg-primary" style={{ width: `${percent}%` }} /></div></div>; }
function Action({ children, disabled, onClick }: { children: string; disabled: boolean; onClick: () => void }) { return <button type="button" disabled={disabled} onClick={onClick} className="rounded-lg border border-line px-3 py-2 text-xs font-bold disabled:opacity-50">{children}</button>; }
function statusText(status: string) { return ({ needs_facecam: 'Pilih area facecam untuk melanjutkan.', scheduled: 'Menunggu waktu tayang WIB.', uploading: 'Sedang mengunggah ke YouTube.', cancelled: 'Proses dibatalkan.' } as Record<string, string>)[status] || 'Memproses'; }
function formatElapsed(seconds = 0) { const total = Math.max(0, Math.round(seconds || 0)); return total ? `${Math.floor(total / 60)}m ${total % 60}s` : ''; }
