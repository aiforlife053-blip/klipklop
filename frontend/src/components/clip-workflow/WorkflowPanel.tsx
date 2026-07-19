import { youtubeUrl } from '@/lib/api';

export interface ClipUpload {
  status: string;
  scheduled_at?: string;
  uploaded_at?: string;
  video_id?: string;
  url?: string;
  error?: string;
  title?: string;
  description?: string;
}

export interface WorkflowClip {
  clip_id: string;
  status: string;
  title: string;
  description: string;
  hook_text?: string;
  final_url?: string;
  stream_url: string;
  final_download_url?: string;
  render_error?: string;
  youtube_upload?: ClipUpload | null;
}

type Props = {
  clips: WorkflowClip[];
  busy: string;
  scheduleAt: Record<string, string>;
  uploadText: Record<string, { title: string; description: string; hook_text: string }>;
  scheduleError: Record<string, string>;
  onScheduleAtChange: (id: string, value: string) => void;
  onUploadTextChange: (id: string, value: { title: string; description: string; hook_text: string }) => void;
  onSchedule: (clip: WorkflowClip) => void;
  onEditHook: (clip: WorkflowClip) => void;
  onCancelSchedule: (clip: WorkflowClip) => void;
  onRetryRender: (clip: WorkflowClip) => void;
  onRetryUpload: (clip: WorkflowClip) => void;
  onDelete: (clip: WorkflowClip) => void;
};

const button = 'rounded-lg border border-line px-3 py-2 text-xs font-bold hover:bg-secondary disabled:opacity-50';
const primary = 'rounded-lg bg-primary px-3 py-2 text-xs font-bold text-primary-foreground disabled:opacity-50';
const danger = 'rounded-lg border border-destructive/50 px-3 py-2 text-xs font-bold text-destructive disabled:opacity-50';
const field = 'w-full rounded-lg border border-field bg-secondary px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary';

export function WorkflowPanel(props: Props) {
  const schedule = props.clips.filter((clip) => ['ready_to_schedule', 'scheduled', 'uploading'].includes(clip.status));
  const results = props.clips.filter((clip) => ['uploaded', 'render_error', 'upload_error', 'cancelled'].includes(clip.status));
  return <section className="grid items-start gap-5 lg:grid-cols-2" aria-label="Workflow dua panel">
    <Panel title="Set Waktu" subtitle="Final siap dijadwalkan dalam WIB">
      {schedule.length ? schedule.map((clip) => <ScheduleCard key={clip.clip_id} clip={clip} {...props} />) : <Empty text="Belum ada final siap dijadwalkan." />}
    </Panel>
    <Panel title="Hasil" subtitle="Sukses, gagal, dan dibatalkan">
      {results.length ? results.map((clip) => <ResultCard key={clip.clip_id} clip={clip} {...props} />) : <Empty text="Belum ada hasil." />}
    </Panel>
  </section>;
}

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return <section className="rounded-2xl border border-line bg-card p-4"><h2 className="font-display text-xl font-bold">{title}</h2><p className="mb-4 text-xs text-muted">{subtitle}</p><div className="space-y-4">{children}</div></section>;
}

function ScheduleCard({ clip, ...props }: { clip: WorkflowClip } & Props) {
  const ready = clip.status === 'ready_to_schedule';
  const text = props.uploadText[clip.clip_id] || { title: clip.title, description: clip.description, hook_text: clip.hook_text || '' };
  const words = text.hook_text.trim().split(/\s+/).filter(Boolean).length;
  return <article className="overflow-hidden rounded-xl border border-line bg-secondary/40">
    <video controls playsInline src={clip.final_url || clip.stream_url} className="aspect-[9/16] max-h-[34rem] w-full bg-black object-contain" aria-label={`Final ${clip.title}`} />
    <div className="space-y-3 p-4">
      <span className="text-xs font-bold text-primary">{ready ? 'Siap dijadwalkan' : clip.status === 'scheduled' ? 'Terjadwal' : 'Uploading'}</span>
      {ready ? <>
        <label className="block text-xs font-bold">Judul<input maxLength={100} value={text.title} onChange={(e) => props.onUploadTextChange(clip.clip_id, { ...text, title: e.target.value })} className={field} /></label>
        <label className="block text-xs font-bold">Deskripsi<textarea rows={3} value={text.description} onChange={(e) => props.onUploadTextChange(clip.clip_id, { ...text, description: e.target.value })} className={field} /></label>
        <label className="block text-xs font-bold">Hook text — maksimal 6 kata<input value={text.hook_text} onChange={(e) => props.onUploadTextChange(clip.clip_id, { ...text, hook_text: e.target.value })} className={field} aria-invalid={words > 6} /></label>
        {words > 6 && <p role="alert" className="text-xs text-destructive">Hook maksimal 6 kata.</p>}
        <label className="block text-xs font-bold">Waktu tayang WIB<input type="datetime-local" value={props.scheduleAt[clip.clip_id] || ''} onChange={(e) => props.onScheduleAtChange(clip.clip_id, e.target.value)} className={field} /></label>
        {props.scheduleError[clip.clip_id] && <p role="alert" className="text-xs text-destructive">{props.scheduleError[clip.clip_id]}</p>}
        <div className="flex flex-wrap gap-2"><button type="button" disabled={Boolean(props.busy) || !text.title.trim() || !props.scheduleAt[clip.clip_id]} onClick={() => props.onSchedule(clip)} className={primary}>Jadwalkan WIB</button><button type="button" disabled={Boolean(props.busy) || words > 6 || !text.hook_text.trim()} onClick={() => props.onEditHook(clip)} className={button}>Render ulang hook</button><button type="button" disabled={Boolean(props.busy)} onClick={() => props.onDelete(clip)} className={danger}>Hapus</button></div>
      </> : <div className="space-y-3"><p className="text-xs text-muted">{clip.status === 'scheduled' ? `Tayang ${formatWib(clip.youtube_upload?.scheduled_at)}` : 'Upload sedang berjalan.'}</p>{clip.status === 'scheduled' && <button type="button" disabled={Boolean(props.busy)} onClick={() => props.onCancelSchedule(clip)} className={danger}>Batalkan jadwal</button>}</div>}
    </div>
  </article>;
}

function ResultCard({ clip, ...props }: { clip: WorkflowClip } & Props) {
  const success = clip.status === 'uploaded';
  const cancelled = clip.status === 'cancelled';
  const failed = !success && !cancelled;
  const link = clip.youtube_upload?.url || youtubeUrl(clip.youtube_upload?.video_id);
  const border = success ? 'border-green-500/70' : failed ? 'border-destructive/70' : 'border-muted/60';
  return <article className={`rounded-xl border ${border} bg-secondary/40 p-4`}><span className="text-xs font-bold">{success ? 'Sukses' : cancelled ? 'Dibatalkan' : 'Gagal'}</span><h3 className="mt-2 text-sm font-bold">{clip.title}</h3>{failed && <p className="mt-2 text-xs text-destructive">{clip.render_error || clip.youtube_upload?.error || 'Proses gagal.'}</p>}<div className="mt-3 flex flex-wrap gap-2">{success && link && <a href={link} target="_blank" rel="noreferrer" className={button}>Buka YouTube</a>}{success && clip.final_download_url && <a href={clip.final_download_url} download className={button}>Download final</a>}{clip.status === 'render_error' && <button type="button" disabled={Boolean(props.busy)} onClick={() => props.onRetryRender(clip)} className={primary}>Retry</button>}{clip.status === 'upload_error' && <button type="button" disabled={Boolean(props.busy)} onClick={() => props.onRetryUpload(clip)} className={primary}>Retry</button>}<button type="button" disabled={Boolean(props.busy)} onClick={() => props.onDelete(clip)} className={danger}>Hapus</button></div></article>;
}
function Empty({ text }: { text: string }) { return <p className="rounded-xl border border-dashed border-line p-10 text-center text-sm text-muted">{text}</p>; }
function formatWib(value?: string) { if (!value) return '-'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '-' : new Intl.DateTimeFormat('id-ID', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Jakarta' }).format(date) + ' WIB'; }
