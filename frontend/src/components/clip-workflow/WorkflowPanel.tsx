import type { ReactNode } from 'react';
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
  duration_seconds?: number;
  virality_score?: number;
  stream_url: string;
  draft_url?: string;
  final_url?: string;
  thumbnail_url?: string;
  final_download_url?: string;
  final_file?: { exists: boolean; size: number };
  render?: { progress?: number; stage?: string; elapsed_seconds?: number; error?: string };
  render_error?: string;
  youtube_upload?: ClipUpload | null;
}

interface WorkflowPanelProps {
  clips: WorkflowClip[];
  busy: string;
  scheduleAt: Record<string, string>;
  uploadText: Record<string, { title: string; description: string }>;
  onScheduleAtChange: (clipId: string, value: string) => void;
  onUploadTextChange: (clipId: string, value: { title: string; description: string }) => void;
  onEdit: (clip: WorkflowClip) => void;
  onDelete: (clip: WorkflowClip) => void;
  onUpload: (clip: WorkflowClip) => void;
  onSchedule: (clip: WorkflowClip) => void;
  onCancelSchedule: (clip: WorkflowClip) => void;
  onEditAgain: (clip: WorkflowClip) => void;
  onRetryRender: (clip: WorkflowClip) => void;
  onRetryUpload: (clip: WorkflowClip) => void;
  onBackToSchedule: (clip: WorkflowClip) => void;
  onDashboard: () => void;
}

const primaryButton =
  'rounded-lg bg-primary px-3 py-2 text-xs font-bold text-primary-foreground hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-card disabled:cursor-not-allowed disabled:opacity-50';
const outlineButton =
  'rounded-lg border border-line px-3 py-2 text-xs font-bold text-foreground hover:bg-secondary focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-card disabled:cursor-not-allowed disabled:opacity-50';
const dangerButton =
  'rounded-lg border border-destructive/50 px-3 py-2 text-xs font-bold text-destructive hover:bg-destructive/10 focus:outline-none focus:ring-2 focus:ring-destructive focus:ring-offset-2 focus:ring-offset-card disabled:cursor-not-allowed disabled:opacity-50';
const fieldClass =
  'w-full rounded-lg border border-field bg-secondary px-3 py-2 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50';

export function WorkflowPanel(props: WorkflowPanelProps) {
  const queue = props.clips.filter((clip) => clip.status === 'needs_edit');
  const process = props.clips.filter((clip) =>
    ['render_queued', 'rendering', 'render_error'].includes(clip.status),
  );
  const schedule = props.clips.filter((clip) =>
    ['ready_to_schedule', 'scheduled', 'uploading'].includes(clip.status),
  );
  const result = props.clips.filter((clip) =>
    ['uploaded', 'upload_error'].includes(clip.status),
  );

  return (
    <section
      className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-4"
      aria-label="Workflow klip"
    >
      <Column
        title="Queue"
        subtitle="Draft siap diedit"
        empty={queue.length === 0 ? <EmptyQueue onDashboard={props.onDashboard} /> : null}
      >
        {queue.map((clip) => (
          <QueueCard
            key={clip.clip_id}
            clip={clip}
            disabled={Boolean(props.busy)}
            onEdit={props.onEdit}
            onDelete={props.onDelete}
          />
        ))}
      </Column>
      <Column
        title="Proses"
        subtitle="Final render"
        empty={process.length === 0 ? <Empty text="Belum ada render aktif." /> : null}
      >
        {process.map((clip) => (
          <ProcessCard
            key={clip.clip_id}
            clip={clip}
            disabled={Boolean(props.busy)}
            onEdit={props.onEdit}
            onRetry={props.onRetryRender}
            onDelete={props.onDelete}
          />
        ))}
      </Column>
      <Column
        title="Set Waktu"
        subtitle="Final siap ditayangkan"
        empty={
          schedule.length === 0 ? <Empty text="Belum ada final siap upload." /> : null
        }
      >
        {schedule.map((clip) => (
          <ScheduleCard
            key={clip.clip_id}
            clip={clip}
            disabled={Boolean(props.busy)}
            scheduleAt={props.scheduleAt[clip.clip_id] || ''}
            uploadText={
              props.uploadText[clip.clip_id] || {
                title: clip.title,
                description: clip.description,
              }
            }
            onScheduleAtChange={props.onScheduleAtChange}
            onUploadTextChange={props.onUploadTextChange}
            onUpload={props.onUpload}
            onSchedule={props.onSchedule}
            onCancelSchedule={props.onCancelSchedule}
            onEditAgain={props.onEditAgain}
            onDelete={props.onDelete}
          />
        ))}
      </Column>
      <Column
        title="Hasil"
        subtitle="Upload selesai atau perlu diulang"
        empty={
          result.length === 0 ? <Empty text="Hasil upload akan muncul di sini." /> : null
        }
      >
        {result.map((clip) => (
          <ResultCard
            key={clip.clip_id}
            clip={clip}
            disabled={Boolean(props.busy)}
            onRetry={props.onRetryUpload}
            onBack={props.onBackToSchedule}
            onEditAgain={props.onEditAgain}
            onDelete={props.onDelete}
          />
        ))}
      </Column>
    </section>
  );
}

function Column({
  title,
  subtitle,
  children,
  empty,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  empty: ReactNode;
}) {
  return (
    <section className="min-h-72 rounded-2xl border border-line bg-card p-4">
      <div className="mb-4">
        <h2 className="font-display text-lg font-bold">{title}</h2>
        <p className="text-xs text-muted">{subtitle}</p>
      </div>
      <div className="flex flex-col gap-3">{empty || children}</div>
    </section>
  );
}

function QueueCard({
  clip,
  disabled,
  onEdit,
  onDelete,
}: {
  clip: WorkflowClip;
  disabled: boolean;
  onEdit: (clip: WorkflowClip) => void;
  onDelete: (clip: WorkflowClip) => void;
}) {
  return (
    <article className="overflow-hidden rounded-xl border border-line bg-secondary/50">
      <Thumbnail clip={clip} />
      <div className="flex flex-col gap-3 p-3">
        <div>
          <span className="inline-flex rounded-full border border-primary/40 bg-primary/10 px-2 py-1 text-[0.6875rem] font-bold text-primary">
            Perlu diedit
          </span>
          <h3 className="mt-2 line-clamp-2 text-sm font-bold">{clip.title}</h3>
        </div>
        <div className="flex items-center justify-between text-xs text-muted">
          <span>{formatDuration(clip.duration_seconds)}</span>
          <span>Score {formatScore(clip.virality_score)}</span>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={disabled}
            onClick={() => onEdit(clip)}
            className={`${primaryButton} flex-1`}
          >
            Edit
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onDelete(clip)}
            className={dangerButton}
          >
            Hapus
          </button>
        </div>
      </div>
    </article>
  );
}

function ProcessCard({
  clip,
  disabled,
  onEdit,
  onRetry,
  onDelete,
}: {
  clip: WorkflowClip;
  disabled: boolean;
  onEdit: (clip: WorkflowClip) => void;
  onRetry: (clip: WorkflowClip) => void;
  onDelete: (clip: WorkflowClip) => void;
}) {
  const rawProgress = Number(clip.render?.progress || 0);
  const progress = Math.round(Math.max(0, Math.min(1, rawProgress)) * 100);
  const failed = clip.status === 'render_error';

  return (
    <article className="rounded-xl border border-line bg-secondary/50 p-3">
      <h3 className="line-clamp-2 text-sm font-bold">{clip.title}</h3>
      <div className="mt-3 flex items-center justify-between text-xs text-muted">
        <span>
          {clip.render?.stage ||
            (clip.status === 'render_queued' ? 'Menunggu render' : 'Rendering')}
        </span>
        <span>{formatElapsed(clip.render?.elapsed_seconds)}</span>
      </div>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full bg-background"
        role="progressbar"
        aria-label={`Progress render ${clip.title}`}
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`h-full rounded-full ${failed ? 'bg-destructive' : 'bg-primary'} transition-[width] duration-200`}
          style={{ width: `${failed ? Math.max(progress, 4) : progress}%` }}
        />
      </div>
      <p
        className={`mt-2 text-xs ${failed ? 'font-medium text-destructive' : 'text-muted'}`}
        aria-live="polite"
      >
        {failed
          ? clip.render?.error ||
            clip.render_error ||
            'Render gagal. Periksa setting lalu coba lagi.'
          : `${progress}% selesai`}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled}
          onClick={() => onEdit(clip)}
          className={outlineButton}
        >
          Edit setting
        </button>
        {failed && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onRetry(clip)}
            className={primaryButton}
          >
            Coba render lagi
          </button>
        )}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onDelete(clip)}
          className={dangerButton}
        >
          Hapus
        </button>
      </div>
    </article>
  );
}

type ScheduleCardProps = {
  clip: WorkflowClip;
  disabled: boolean;
  scheduleAt: string;
  uploadText: { title: string; description: string };
  onScheduleAtChange: (id: string, value: string) => void;
  onUploadTextChange: (id: string, value: { title: string; description: string }) => void;
  onUpload: (clip: WorkflowClip) => void;
  onSchedule: (clip: WorkflowClip) => void;
  onCancelSchedule: (clip: WorkflowClip) => void;
  onEditAgain: (clip: WorkflowClip) => void;
  onDelete: (clip: WorkflowClip) => void;
};

function ScheduleCard(props: ScheduleCardProps) {
  const { clip, disabled, scheduleAt, uploadText } = props;
  const ready = clip.status === 'ready_to_schedule';
  const scheduled = clip.status === 'scheduled';

  return (
    <article className="overflow-hidden rounded-xl border border-line bg-secondary/50">
      <video
        controls
        playsInline
        src={clip.final_url || clip.stream_url}
        className="aspect-video w-full bg-black object-contain"
        aria-label={`Final ${clip.title}`}
      />
      <div className="flex flex-col gap-3 p-3">
        <span
          className={`w-fit rounded-full border px-2 py-1 text-[0.6875rem] font-bold ${ready ? 'border-primary/40 bg-primary/10 text-primary' : 'border-line bg-background text-muted'}`}
        >
          {ready ? 'Siap upload' : scheduled ? 'Terjadwal' : 'Sedang upload'}
        </span>
        {ready ? (
          <>
            <label className="flex flex-col gap-1 text-xs font-bold">
              Judul YouTube
              <input
                maxLength={100}
                value={uploadText.title}
                onChange={(event) =>
                  props.onUploadTextChange(clip.clip_id, {
                    ...uploadText,
                    title: event.target.value,
                  })
                }
                className={fieldClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-bold">
              Deskripsi YouTube
              <textarea
                rows={3}
                value={uploadText.description}
                onChange={(event) =>
                  props.onUploadTextChange(clip.clip_id, {
                    ...uploadText,
                    description: event.target.value,
                  })
                }
                className={fieldClass}
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-bold">
              Waktu tayang WIB
              <input
                type="datetime-local"
                value={scheduleAt}
                onChange={(event) =>
                  props.onScheduleAtChange(clip.clip_id, event.target.value)
                }
                className={fieldClass}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={disabled || !uploadText.title.trim()}
                onClick={() => props.onUpload(clip)}
                className={primaryButton}
              >
                Upload public
              </button>
              <button
                type="button"
                disabled={disabled || !scheduleAt || !uploadText.title.trim()}
                onClick={() => props.onSchedule(clip)}
                className={outlineButton}
              >
                Jadwalkan WIB
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={() => props.onEditAgain(clip)}
                className={outlineButton}
              >
                Edit ulang
              </button>
              <button
                type="button"
                disabled={disabled}
                onClick={() => props.onDelete(clip)}
                className={dangerButton}
              >
                Hapus
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="text-xs text-muted">
              {scheduled
                ? `Tayang pada ${formatWib(clip.youtube_upload?.scheduled_at)}`
                : 'Upload sedang diproses. Status akan diperbarui otomatis.'}
            </p>
            {scheduled && (
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => props.onCancelSchedule(clip)}
                  className={dangerButton}
                >
                  Batalkan jadwal
                </button>
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => props.onEditAgain(clip)}
                  className={outlineButton}
                >
                  Edit ulang
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </article>
  );
}

type ResultCardProps = {
  clip: WorkflowClip;
  disabled: boolean;
  onRetry: (clip: WorkflowClip) => void;
  onBack: (clip: WorkflowClip) => void;
  onEditAgain: (clip: WorkflowClip) => void;
  onDelete: (clip: WorkflowClip) => void;
};

function ResultCard({
  clip,
  disabled,
  onRetry,
  onBack,
  onEditAgain,
  onDelete,
}: ResultCardProps) {
  const upload = clip.youtube_upload;
  const failed = clip.status === 'upload_error';
  const link = upload?.url || youtubeUrl(upload?.video_id);

  return (
    <article className="rounded-xl border border-line bg-secondary/50 p-3">
      <span
        className={`inline-flex rounded-full border px-2 py-1 text-[0.6875rem] font-bold ${failed ? 'border-destructive/40 bg-destructive/10 text-destructive' : 'border-primary/40 bg-primary/10 text-primary'}`}
      >
        {failed ? 'Upload gagal' : 'Sudah tayang'}
      </span>
      <h3 className="mt-2 line-clamp-2 text-sm font-bold">{clip.title}</h3>
      {failed ? (
        <p className="mt-2 text-xs font-medium text-destructive">
          {upload?.error || 'Upload YouTube gagal. Coba lagi.'}
        </p>
      ) : (
        <dl className="mt-3 space-y-1 text-xs">
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Video ID</dt>
            <dd className="break-all text-right">{upload?.video_id || '-'}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">Upload WIB</dt>
            <dd className="text-right">{formatWib(upload?.uploaded_at)}</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted">File lokal</dt>
            <dd>{clip.final_file?.exists ? formatBytes(clip.final_file.size) : 'Tidak ada'}</dd>
          </div>
        </dl>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {link && (
          <a href={link} target="_blank" rel="noreferrer" className={outlineButton}>
            Buka YouTube
          </a>
        )}
        {clip.final_download_url && (
          <a href={clip.final_download_url} download className={outlineButton}>
            Download final
          </a>
        )}
        {failed ? (
          <>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onRetry(clip)}
              className={primaryButton}
            >
              Coba upload lagi
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onBack(clip)}
              className={outlineButton}
            >
              Kembali ke Set Waktu
            </button>
          </>
        ) : (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onEditAgain(clip)}
            className={outlineButton}
          >
            Edit ulang
          </button>
        )}
        <button
          type="button"
          disabled={disabled}
          onClick={() => onDelete(clip)}
          className={dangerButton}
        >
          Hapus lokal
        </button>
      </div>
    </article>
  );
}

function Thumbnail({ clip }: { clip: WorkflowClip }) {
  return clip.thumbnail_url ? (
    <img
      src={clip.thumbnail_url}
      alt=""
      className="aspect-video w-full bg-background object-cover"
    />
  ) : (
    <div className="flex aspect-video items-center justify-center bg-background text-xs text-muted">
      Thumbnail belum tersedia
    </div>
  );
}

function EmptyQueue({ onDashboard }: { onDashboard: () => void }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-line p-5 text-center">
      <p className="text-sm font-bold">Belum ada draft klip</p>
      <p className="text-xs text-muted">Buat klip dari video panjang di Dashboard.</p>
      <button type="button" onClick={onDashboard} className={primaryButton}>
        Kembali ke Dashboard
      </button>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return (
    <p className="rounded-xl border border-dashed border-line px-4 py-10 text-center text-xs text-muted">
      {text}
    </p>
  );
}

function formatDuration(seconds = 0) {
  const total = Math.max(0, Math.round(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
}

function formatScore(score = 0) {
  const normalized = score <= 1 ? score * 100 : score <= 10 ? score * 10 : score;
  return `${Math.round(normalized)}%`;
}

function formatElapsed(seconds = 0) {
  const total = Math.max(0, Math.round(seconds));
  return `${Math.floor(total / 60)}m ${total % 60}s`;
}

function formatWib(value?: string) {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '-'
    : new Intl.DateTimeFormat('id-ID', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: 'Asia/Jakarta',
      }).format(date) + ' WIB';
}

function formatBytes(bytes = 0) {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}
