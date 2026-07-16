export type SettingValue = string | number | boolean | undefined;
export type SettingSection = Record<string, SettingValue>;
export type VideoLayoutMode = 'normal' | 'gaming';

export interface VideoLayout extends SettingSection {
  mode: VideoLayoutMode;
  facecam_x?: number;
  facecam_y?: number;
  facecam_width?: number;
  facecam_height?: number;
  facecam_confidence?: number;
}

export interface ClipSettings {
  hook_style: SettingSection;
  subtitle: SettingSection;
  watermark: SettingSection;
  credit_watermark: SettingSection;
  blur_background: SettingSection;
  video_layout: VideoLayout;
  landscape_blur?: boolean;
  video_quality?: string;
  screen_size?: string;
}

export interface SourceGeometry { width: number; height: number; sample_aspect_ratio?: string; display_aspect_ratio?: string; rotation?: number; is_landscape: boolean; }
export type SubtitleCapability = 'word_highlight' | 'static_segments' | 'unavailable';
export interface CueWord { text: string; start: number; end: number; active_from: number; active_until: number; }
export interface SubtitleCue { start: number; end: number; text: string; words: CueWord[]; active_word_indexes: number[]; capability: Exclude<SubtitleCapability, 'unavailable'>; }
export interface ClipEditorContract { source_url: string; source_geometry: SourceGeometry; subtitle_cues: SubtitleCue[]; subtitle_capability: SubtitleCapability; subtitle_reason: string; watermark_url: string; watermark_revision: string; resolved_credit_text: string; }

export const FONT_OPTIONS = ['Plus Jakarta Sans', 'Poppins'] as const;
export const WEIGHT_OPTIONS = [{ value: 400, label: 'Regular' }, { value: 500, label: 'Medium' }, { value: 600, label: 'Semibold' }, { value: 700, label: 'Bold' }, { value: 800, label: 'Extrabold' }] as const;
export const cloneSettings = (settings: ClipSettings): ClipSettings => structuredClone(settings);
export function mergeSettings(defaults: ClipSettings, current?: Partial<ClipSettings>): ClipSettings { return { ...cloneSettings(defaults), ...current, hook_style: { ...defaults.hook_style, ...current?.hook_style }, subtitle: { ...defaults.subtitle, ...current?.subtitle }, watermark: { ...defaults.watermark, ...current?.watermark }, credit_watermark: { ...defaults.credit_watermark, ...current?.credit_watermark }, blur_background: { ...defaults.blur_background, ...current?.blur_background }, video_layout: { ...defaults.video_layout, ...current?.video_layout } }; }
const ranges: Record<string, Record<string, [number, number]>> = { hook_style: { font_size: [0.01, 0.1], outline_thickness: [0, 6], position_x: [0, 1], position_y: [0, 1] }, subtitle: { size: [0.01, 0.1], outline_thickness: [0, 6], position_x: [0, 1], position_y: [0, 1] }, watermark: { scale: [0.1, 2], opacity: [0, 1], position_x: [0, 1], position_y: [0, 1] }, credit_watermark: { size: [0.01, 0.1], opacity: [0, 1], position_x: [0, 1], position_y: [0, 1] }, blur_background: { scale: [1, 2], zoom: [1, 3], strength: [0, 100] } };
export function validateSettings(settings: ClipSettings): string[] { const errors: string[] = []; Object.entries(ranges).forEach(([section, fields]) => Object.entries(fields).forEach(([field, [min, max]]) => { const value = settings[section as keyof ClipSettings]; const numeric = typeof value === 'object' && value ? Number((value as SettingSection)[field]) : Number.NaN; if (!Number.isFinite(numeric) || numeric < min || numeric > max) errors.push(`${section}.${field}`); })); const colors = [settings.hook_style.text_color, settings.hook_style.outline_color, settings.subtitle.text_color, settings.subtitle.color, settings.subtitle.outline_color, settings.credit_watermark.color]; if (colors.some((color) => typeof color !== 'string' || !/^#[0-9A-F]{6}$/i.test(color))) errors.push('color'); if (!FONT_OPTIONS.includes(String(settings.hook_style.font_family) as typeof FONT_OPTIONS[number])) errors.push('hook_style.font_family'); if (!FONT_OPTIONS.includes(String(settings.subtitle.font_family) as typeof FONT_OPTIONS[number])) errors.push('subtitle.font_family'); if (!['normal', 'gaming'].includes(settings.video_layout.mode)) errors.push('video_layout.mode'); if (settings.video_layout.mode === 'gaming') { const { facecam_x: x, facecam_y: y, facecam_width: width, facecam_height: height, facecam_confidence: confidence } = settings.video_layout; if (![x, y, width, height, confidence].every((value) => Number.isFinite(value))) errors.push('video_layout.facecam'); else if (Number(x) < 0 || Number(y) < 0 || Number(width) <= 0 || Number(height) <= 0 || Number(x) + Number(width) > 1 || Number(y) + Number(height) > 1 || Number(confidence) < 0 || Number(confidence) > 1) errors.push('video_layout.facecam'); } return errors; }
