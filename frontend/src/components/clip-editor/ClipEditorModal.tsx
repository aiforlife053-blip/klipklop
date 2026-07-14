import { useEffect, useId, useRef, useState, type ChangeEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import * as Tabs from '@radix-ui/react-tabs';
import { apiPost } from '@/lib/api';
import { FONT_OPTIONS, WEIGHT_OPTIONS, type ClipEditorContract, type ClipSettings, type SettingValue } from '@/lib/clip-settings';
import { LiveClipPreview } from '@/components/clip-editor/LiveClipPreview';

export interface EditorClip {
  clip_id: string;
  title: string;
  status: string;
  stream_url: string;
  draft_url?: string;
  hook_text?: string;
  source_url?: string;
  source_geometry?: ClipEditorContract['source_geometry'];
  subtitle_cues?: ClipEditorContract['subtitle_cues'];
  subtitle_capability?: ClipEditorContract['subtitle_capability'];
  subtitle_reason?: string;
  watermark_url?: string;
  watermark_revision?: string;
  resolved_credit_text?: string;
}

interface ClipEditorModalProps {
  clip: EditorClip;
  settings: ClipSettings;
  previewUrl: string;
  previewBusy: boolean;
  actionBusy: boolean;
  error: string;
  invalid: boolean;
  hookText: string;
  backgroundVisible: boolean;
  onHookTextChange: (value: string) => void;
  onClose: () => void;
  onChange: (section: keyof ClipSettings, key: string, value: SettingValue) => void;
  onReset: (section: keyof ClipSettings) => void;
  onPreview: () => void;
  onSaveDefaults: () => void;
  onRender: () => void;
  previewState?: string;
  previewProgress?: number;
  previewElapsed?: number;
  previewStale?: boolean;
  onCancelPreview?: () => void;
}

const inputClass = 'h-11 w-full rounded-lg border border-field bg-secondary px-3 text-sm text-foreground transition-colors hover:border-white/20 focus:border-primary/60 focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:cursor-not-allowed disabled:opacity-50';
const focusButton = 'rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-card disabled:cursor-not-allowed disabled:opacity-50';
const rangeClass = 'h-2 w-full cursor-pointer appearance-none rounded-full bg-field accent-primary focus:outline-none focus:ring-2 focus:ring-primary/40 focus:ring-offset-2 focus:ring-offset-card';

export function ClipEditorModal(props: ClipEditorModalProps) {
  const { clip, settings, previewUrl, previewBusy, actionBusy, error, invalid, hookText, backgroundVisible, onHookTextChange, onClose, onChange, onReset, onPreview, onSaveDefaults, onRender, previewState, previewProgress, previewElapsed, previewStale, onCancelPreview } = props;
  const [currentTime, setCurrentTime] = useState(0);
  const contract: ClipEditorContract = { source_url: clip.source_url || clip.draft_url || clip.stream_url, source_geometry: clip.source_geometry || { width: 0, height: 0, is_landscape: false }, subtitle_cues: clip.subtitle_cues || [], subtitle_capability: clip.subtitle_capability || 'unavailable', subtitle_reason: clip.subtitle_reason || '', watermark_url: clip.watermark_url || '', watermark_revision: clip.watermark_revision || '', resolved_credit_text: clip.resolved_credit_text || '' };
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLElement>(null);
  const onCloseRef = useRef(onClose);
  const previewBusyRef = useRef(previewBusy);
  const actionBusyRef = useRef(actionBusy);
  onCloseRef.current = onClose;
  previewBusyRef.current = previewBusy;
  actionBusyRef.current = actionBusy;
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState('');

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !previewBusyRef.current && !actionBusyRef.current) onCloseRef.current();
      if (event.key !== 'Tab') return;
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), video[controls], a[href]') || []);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', closeOnEscape);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', closeOnEscape); document.body.style.overflow = previousOverflow; previousFocus?.focus(); };
  }, []);

  const uploadWatermark = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (file.size > 400_000) { setUploadError('Watermark maksimal 400KB.'); return; }
    setUploadBusy(true);
    setUploadError('');
    try {
      const content = await fileToBase64(file);
      const uploaded = await apiPost<{ status: string; asset: string; image_path: string }, { name: string; content: string }>('/api/watermark/upload', { name: file.name, content });
      onChange('watermark', 'image_path', uploaded.image_path);
      onChange('watermark', 'enabled', true);
    } catch (requestError) {
      setUploadError(requestError instanceof Error ? requestError.message : 'Upload watermark gagal.');
    } finally {
      setUploadBusy(false);
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-background/90 p-0 sm:p-4" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <section ref={dialogRef} className="flex h-full w-full flex-col overflow-hidden border-line bg-card sm:max-h-[94dvh] sm:max-w-6xl sm:rounded-2xl sm:border">
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-line px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id={titleId} className="truncate font-display text-lg font-bold sm:text-xl">{clip.title}</h2>
              <span className="rounded-full border border-primary/40 bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary">{clip.status === 'render_error' ? 'Perlu diperbaiki' : 'Sedang diedit'}</span>
            </div>
            <p className="mt-1 text-xs text-muted sm:text-sm">Preview memakai renderer final yang sama.</p>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} disabled={previewBusy || actionBusy} className={`${focusButton} shrink-0 border border-line px-3 py-2 text-sm font-bold text-foreground hover:bg-secondary`} aria-label="Tutup editor">Tutup</button>
        </header>

        <div className="grid min-h-0 flex-1 overflow-y-auto lg:grid-cols-[minmax(280px,0.8fr)_minmax(0,1.45fr)] lg:overflow-hidden">
          <div className="flex items-start justify-center border-b border-line bg-background p-4 lg:overflow-y-auto lg:border-b-0 lg:border-r lg:p-6">
            {previewUrl && !previewStale ? <video controls playsInline src={previewUrl} className="aspect-[9/16] max-h-[62dvh] w-auto max-w-full rounded-xl bg-black object-contain lg:max-h-full" aria-label={`Preview akurat ${clip.title}`} /> : <LiveClipPreview contract={contract} settings={settings} hookText={hookText} currentTime={currentTime} onTimeChange={setCurrentTime} source={contract.source_url} />}
          </div>
          <Tabs.Root defaultValue="hook" className="flex min-h-0 flex-col">
            <Tabs.List aria-label="Pengaturan klip" className="flex shrink-0 gap-1 overflow-x-auto border-b border-line px-3 pt-3 sm:px-5">
              <Tab value="hook">Hook</Tab><Tab value="subtitle">Subtitle</Tab><Tab value="watermark">Watermark</Tab><Tab value="credit">Credit</Tab>{backgroundVisible && <Tab value="background">Latar</Tab>}
            </Tabs.List>
            <div className="min-h-0 flex-1 bg-background/35 p-4 lg:overflow-y-auto lg:p-6">
              <Tabs.Content value="hook"><Section title="Hook" onReset={() => onReset('hook_style')}><Toggle label="Tampilkan hook" checked={Boolean(settings.hook_style.enabled)} onChange={(value) => onChange('hook_style', 'enabled', value)} /><Field label="Teks hook"><textarea rows={3} maxLength={180} value={hookText} onChange={(event) => onHookTextChange(event.target.value)} className={`${inputClass} h-auto py-2`} /></Field><FontControls section="hook_style" values={settings.hook_style} onChange={onChange} /><NumberField label="Ukuran" value={settings.hook_style.font_size} min={0.01} max={0.1} step={0.001} onChange={(value) => onChange('hook_style', 'font_size', value)} /><ColorField label="Warna teks" value={settings.hook_style.text_color} onChange={(value) => onChange('hook_style', 'text_color', value)} /><ColorField label="Warna outline" value={settings.hook_style.outline_color} onChange={(value) => onChange('hook_style', 'outline_color', value)} /><NumberField label="Ketebalan outline" value={settings.hook_style.outline_thickness} min={0} max={6} step={0.1} onChange={(value) => onChange('hook_style', 'outline_thickness', value)} /><RatioField label="Posisi X" value={settings.hook_style.position_x} onChange={(value) => onChange('hook_style', 'position_x', value)} /><RatioField label="Posisi Y" value={settings.hook_style.position_y} onChange={(value) => onChange('hook_style', 'position_y', value)} /></Section></Tabs.Content>
              <Tabs.Content value="subtitle"><Section title="Subtitle" onReset={() => onReset('subtitle')}><Toggle label="Tampilkan subtitle" checked={Boolean(settings.subtitle.enabled)} disabled={contract.subtitle_capability === 'unavailable'} onChange={(value) => onChange('subtitle', 'enabled', value)} />{contract.subtitle_capability === 'unavailable' && <p className="text-sm text-muted">{contract.subtitle_reason}</p>}<FontControls section="subtitle" values={settings.subtitle} onChange={onChange} /><NumberField label="Ukuran" value={settings.subtitle.size} min={0.01} max={0.1} step={0.001} onChange={(value) => onChange('subtitle', 'size', value)} /><ColorField label="Warna teks" value={settings.subtitle.text_color} onChange={(value) => onChange('subtitle', 'text_color', value)} /><ColorField label="Warna highlight" value={settings.subtitle.color} onChange={(value) => onChange('subtitle', 'color', value)} /><ColorField label="Warna outline" value={settings.subtitle.outline_color} onChange={(value) => onChange('subtitle', 'outline_color', value)} /><NumberField label="Ketebalan outline" value={settings.subtitle.outline_thickness} min={0} max={6} step={0.1} onChange={(value) => onChange('subtitle', 'outline_thickness', value)} /><RatioField label="Posisi X" value={settings.subtitle.position_x} onChange={(value) => onChange('subtitle', 'position_x', value)} /><RatioField label="Posisi Y" value={settings.subtitle.position_y} onChange={(value) => onChange('subtitle', 'position_y', value)} /></Section></Tabs.Content>
              <Tabs.Content value="watermark"><Section title="Watermark" onReset={() => onReset('watermark')}><Toggle label="Tampilkan watermark" checked={Boolean(settings.watermark.enabled)} onChange={(value) => onChange('watermark', 'enabled', value)} /><Field label="Gambar watermark"><input type="file" accept="image/png,image/jpeg,image/webp" onChange={uploadWatermark} disabled={uploadBusy} className="block w-full text-sm text-muted file:mr-3 file:rounded-lg file:border-0 file:bg-primary file:px-3 file:py-2 file:font-bold file:text-primary-foreground focus:outline-none focus:ring-2 focus:ring-primary" /><span className="text-xs text-muted">PNG, JPG, atau WEBP. Maksimal 400KB.</span></Field>{(uploadError || settings.watermark.image_path) && <p className={`text-sm ${uploadError ? 'text-destructive' : 'text-muted'}`}>{uploadError || 'Watermark siap digunakan.'}</p>}<NumberField label="Ukuran" value={settings.watermark.scale} min={0.1} max={2} step={0.01} onChange={(value) => onChange('watermark', 'scale', value)} /><RatioField label="Opacity" value={settings.watermark.opacity} onChange={(value) => onChange('watermark', 'opacity', value)} /><RatioField label="Posisi X" value={settings.watermark.position_x} onChange={(value) => onChange('watermark', 'position_x', value)} /><RatioField label="Posisi Y" value={settings.watermark.position_y} onChange={(value) => onChange('watermark', 'position_y', value)} /></Section></Tabs.Content>
              <Tabs.Content value="credit"><Section title="Credit" onReset={() => onReset('credit_watermark')}><Toggle label="Tampilkan credit" checked={Boolean(settings.credit_watermark.enabled)} onChange={(value) => onChange('credit_watermark', 'enabled', value)} /><Field label="Template teks"><input value={String(settings.credit_watermark.text ?? '')} maxLength={120} onChange={(event) => onChange('credit_watermark', 'text', event.target.value)} className={inputClass} /></Field><ColorField label="Warna" value={settings.credit_watermark.color} onChange={(value) => onChange('credit_watermark', 'color', value)} /><NumberField label="Ukuran" value={settings.credit_watermark.size} min={0.01} max={0.1} step={0.001} onChange={(value) => onChange('credit_watermark', 'size', value)} /><RatioField label="Opacity" value={settings.credit_watermark.opacity} onChange={(value) => onChange('credit_watermark', 'opacity', value)} /><RatioField label="Posisi X" value={settings.credit_watermark.position_x} onChange={(value) => onChange('credit_watermark', 'position_x', value)} /><RatioField label="Posisi Y" value={settings.credit_watermark.position_y} onChange={(value) => onChange('credit_watermark', 'position_y', value)} /></Section></Tabs.Content>
              {backgroundVisible && <Tabs.Content value="background"><Section title="Latar blur" onReset={() => onReset('blur_background')}><Toggle label="Aktifkan latar blur" checked={Boolean(settings.blur_background.enabled)} onChange={(value) => onChange('blur_background', 'enabled', value)} /><NumberField label="Ukuran video" value={settings.blur_background.scale} min={1} max={2} step={0.05} onChange={(value) => onChange('blur_background', 'scale', value)} /><NumberField label="Zoom background" value={settings.blur_background.zoom} min={1} max={3} step={0.01} onChange={(value) => onChange('blur_background', 'zoom', value)} /><NumberField label="Kekuatan blur" value={settings.blur_background.strength} min={0} max={100} step={1} onChange={(value) => onChange('blur_background', 'strength', value)} /></Section></Tabs.Content>}
            </div>
          </Tabs.Root>
        </div>

        <footer className="sticky bottom-0 z-10 flex shrink-0 flex-col gap-3 border-t border-line bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div aria-live="polite" className="min-h-5 text-sm"><span className={error ? 'font-medium text-destructive' : 'text-muted'}>{error || (invalid ? 'Periksa nilai pengaturan yang tidak valid.' : previewBusy ? `${previewState || 'Merender'} ${Math.round((previewProgress || 0) * 100)}% • ${Math.round(previewElapsed || 0)}d` : previewStale ? 'Preview akurat perlu diperbarui.' : previewUrl ? 'Preview akurat siap.' : 'Mode Live')}</span></div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={onPreview} disabled={previewBusy || actionBusy || uploadBusy || invalid} className={`${focusButton} border border-line px-4 py-2 text-sm font-bold text-foreground hover:bg-secondary`}>{previewBusy ? 'Merender preview...' : 'Render Preview Akurat'}</button>{previewBusy && onCancelPreview && <button type="button" onClick={onCancelPreview} className={`${focusButton} border border-destructive/50 px-4 py-2 text-sm font-bold text-destructive hover:bg-destructive/10`}>Batalkan Preview</button>}
            <button type="button" onClick={onSaveDefaults} disabled={previewBusy || actionBusy || uploadBusy || invalid} className={`${focusButton} border border-primary/50 px-4 py-2 text-sm font-bold text-primary hover:bg-primary/10`}>Simpan sebagai default</button>
            <button type="button" onClick={onRender} disabled={previewBusy || actionBusy || uploadBusy || invalid} className={`${focusButton} bg-primary px-4 py-2 text-sm font-bold text-primary-foreground hover:opacity-90`}>{actionBusy ? 'Menyiapkan render...' : 'Lanjut ke tahap berikutnya'}</button>
          </div>
        </footer>
      </section>
    </div>,
    document.body,
  );
}

function Tab({ value, children }: { value: string; children: ReactNode }) {
  return <Tabs.Trigger value={value} className="whitespace-nowrap border-b-2 border-transparent px-3 py-3 text-sm font-semibold text-muted transition-colors hover:text-foreground focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary data-[state=active]:border-primary data-[state=active]:text-primary">{children}</Tabs.Trigger>;
}

function Section({ title, onReset, children }: { title: string; onReset: () => void; children: ReactNode }) {
  return <fieldset><legend className="sr-only">{title}</legend><div className="mb-5 flex items-center justify-between gap-4 border-b border-line pb-4"><div><h3 className="text-lg font-bold text-foreground">{title}</h3><p className="mt-0.5 text-xs text-muted">Perubahan langsung tampil di preview Live.</p></div><button type="button" onClick={onReset} className={`${focusButton} shrink-0 px-3 py-2 text-xs font-bold text-primary hover:bg-primary/10`}>Reset default</button></div><div className="grid gap-x-5 gap-y-5 sm:grid-cols-2">{children}</div></fieldset>;
}

function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return <label className="flex min-w-0 flex-col gap-2 text-sm font-semibold text-foreground">{label}{children}</label>;
}

function Toggle({ label, checked, onChange, disabled = false }: { label: string; checked: boolean; onChange: (value: boolean) => void; disabled?: boolean }) {
  return <label className={`group flex min-h-14 items-center justify-between gap-4 rounded-xl border border-field bg-secondary px-4 py-3 transition-colors sm:col-span-2 ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer hover:border-white/20'}`}><span><span className="block text-sm font-semibold text-foreground">{label}</span><span className="mt-0.5 block text-xs text-muted">{disabled ? 'Tidak tersedia untuk klip ini' : checked ? 'Aktif di hasil video' : 'Tidak ditampilkan'}</span></span><input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} className="peer sr-only" /><span aria-hidden="true" className="relative h-7 w-12 shrink-0 rounded-full bg-white/15 transition-colors duration-200 peer-checked:bg-primary peer-checked:[&>span]:translate-x-5 peer-focus-visible:ring-2 peer-focus-visible:ring-primary peer-focus-visible:ring-offset-2 peer-focus-visible:ring-offset-card"><span className="absolute left-1 top-1 size-5 rounded-full bg-white shadow-sm transition-transform duration-200" /></span></label>;
}

function FontControls({ section, values, onChange }: { section: keyof ClipSettings; values: Record<string, SettingValue>; onChange: ClipEditorModalProps['onChange'] }) {
  return <><Field label="Font"><select value={String(values.font_family ?? FONT_OPTIONS[0])} onChange={(event) => onChange(section, 'font_family', event.target.value)} className={inputClass}>{FONT_OPTIONS.map((font) => <option key={font} value={font}>{font}</option>)}</select></Field><Field label="Ketebalan"><select value={Number(values.font_weight ?? 800)} onChange={(event) => onChange(section, 'font_weight', Number(event.target.value))} className={inputClass}>{WEIGHT_OPTIONS.map((weight) => <option key={weight.value} value={weight.value}>{weight.label}</option>)}</select></Field></>;
}

function NumberField({ label, value, min, max, step, onChange }: { label: string; value: SettingValue; min: number; max: number; step: number; onChange: (value: number) => void }) {
  const numeric = Number(value ?? min);
  const [draft, setDraft] = useState(String(numeric));
  useEffect(() => setDraft(String(numeric)), [numeric]);
  const commit = () => {
    const parsed = Number(draft.replace(',', '.'));
    const next = Number.isFinite(parsed) ? Math.max(min, Math.min(max, parsed)) : numeric;
    setDraft(String(next));
    if (next !== numeric) onChange(next);
  };
  return <Field label={label}><div className="grid grid-cols-[minmax(0,1fr)_5.5rem] items-center gap-3"><input type="range" value={numeric} min={min} max={max} step={step} onChange={(event) => onChange(Number(event.target.value))} className={rangeClass} aria-label={`${label} slider`} /><input type="text" inputMode="decimal" value={draft} onChange={(event) => setDraft(event.target.value)} onBlur={commit} onKeyDown={(event) => { if (event.key === 'Enter') event.currentTarget.blur(); }} className={`${inputClass} text-right font-mono tabular-nums`} aria-label={`${label} angka`} /></div><span className="text-xs font-normal text-muted">Rentang {min}–{max}</span></Field>;
}

function RatioField({ label, value, onChange }: { label: string; value: SettingValue; onChange: (value: number) => void }) {
  const percentage = Math.round(Number(value ?? 0) * 100);
  return <Field label={<span className="flex items-center justify-between"><span>{label}</span><span className="font-mono text-xs font-semibold tabular-nums text-primary">{percentage}%</span></span>}><input type="range" value={percentage} min={0} max={100} step={1} onChange={(event) => onChange(Number(event.target.value) / 100)} className={rangeClass} /></Field>;
}

function ColorField({ label, value, onChange }: { label: string; value: SettingValue; onChange: (value: string) => void }) {
  const color = String(value ?? '#FFFFFF').toUpperCase();
  return <Field label={label}><span className="flex gap-2"><input type="color" value={/^#[0-9A-F]{6}$/i.test(color) ? color : '#FFFFFF'} onChange={(event) => onChange(event.target.value.toUpperCase())} className="h-10 w-12 shrink-0 cursor-pointer rounded-lg border border-field bg-secondary p-1 focus:outline-none focus:ring-2 focus:ring-primary" aria-label={`Pilih ${label.toLowerCase()}`} /><input value={color} maxLength={7} pattern="#[0-9A-Fa-f]{6}" onChange={(event) => onChange(event.target.value.toUpperCase())} className={inputClass} aria-label={`${label} format hex`} /></span></Field>;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = () => reject(new Error('File watermark gagal dibaca.'));
    reader.readAsDataURL(file);
  });
}
