import { useEffect, useRef } from 'react';
import type { ClipEditorContract, ClipSettings } from '@/lib/clip-settings';

interface Props {
  contract: ClipEditorContract;
  settings: ClipSettings;
  hookText: string;
  currentTime: number;
  source: string;
  onTimeChange: (time: number) => void;
}

const ratio = (value: unknown, fallback: number) => Number.isFinite(Number(value)) ? Number(value) : fallback;

export function LiveClipPreview({ contract, settings, hookText, currentTime, source, onTimeChange }: Props) {
  const foreground = useRef<HTMLVideoElement>(null);
  const background = useRef<HTMLVideoElement>(null);
  const onTimeChangeRef = useRef(onTimeChange);
  onTimeChangeRef.current = onTimeChange;
  const gaming = settings.video_layout.mode === 'gaming';
  const blur = Boolean(!gaming && settings.blur_background.enabled && contract.source_geometry.is_landscape && settings.screen_size !== '16:9');
  const cue = [...contract.subtitle_cues].reverse().find((item) => currentTime >= item.start && currentTime < item.end);
  useEffect(() => {
    const front = foreground.current;
    const back = background.current;
    if (!front) return;
    let frame = 0;
    let videoFrame = 0;
    let stopped = false;
    const sync = () => {
      if (back) {
        if (Math.abs(back.currentTime - front.currentTime) > 0.08) back.currentTime = front.currentTime;
        back.playbackRate = front.playbackRate;
        if (!front.paused && back.paused) void back.play().catch(() => undefined);
        if (front.paused && !back.paused) back.pause();
      }
      if (!front.paused && !front.ended) onTimeChangeRef.current(front.currentTime);
    };
    const tick = () => {
      if (stopped) return;
      sync();
      if (front.requestVideoFrameCallback) videoFrame = front.requestVideoFrameCallback(tick);
      else frame = requestAnimationFrame(tick);
    };
    front.addEventListener('timeupdate', sync);
    front.addEventListener('play', sync);
    front.addEventListener('pause', sync);
    front.addEventListener('seeked', sync);
    tick();
    return () => {
      stopped = true;
      front.removeEventListener('timeupdate', sync);
      front.removeEventListener('play', sync);
      front.removeEventListener('pause', sync);
      front.removeEventListener('seeked', sync);
      if (videoFrame && front.cancelVideoFrameCallback) front.cancelVideoFrameCallback(videoFrame);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [blur, gaming]);
  const layerStyle = (x: unknown, y: unknown) => ({ left: `${ratio(x, 0.5) * 100}%`, top: `${ratio(y, 0.5) * 100}%`, transform: 'translate(-50%, -50%)' });
  const facecamWidth = ratio(settings.video_layout.facecam_width, 1);
  const facecamHeight = ratio(settings.video_layout.facecam_height, 1);
  const facecamStyle = gaming ? { left: `${-ratio(settings.video_layout.facecam_x, 0) / facecamWidth * 100}%`, top: `${-ratio(settings.video_layout.facecam_y, 0) / facecamHeight * 100}%`, width: `${100 / facecamWidth}%`, height: `${100 / facecamHeight}%` } : undefined;
  return <div className="relative aspect-[9/16] h-[62dvh] max-h-full w-auto max-w-full overflow-hidden rounded-xl bg-black lg:h-[calc(94dvh-12rem)]" data-testid="live-preview">
    {blur && <video ref={background} muted playsInline src={source} className="absolute inset-0 size-full scale-110 object-cover blur-2xl brightness-50" aria-hidden="true" />}
    {gaming && <div className="absolute inset-x-0 top-0 h-1/3 overflow-hidden"><video ref={background} muted playsInline src={source} className="absolute max-w-none object-fill" style={facecamStyle} aria-label="Facecam preview" /></div>}
    <video ref={foreground} controls playsInline src={source} onTimeUpdate={(event) => onTimeChange(event.currentTarget.currentTime)} className={gaming ? 'absolute inset-x-0 bottom-0 h-2/3 w-full object-cover' : 'absolute inset-0 size-full object-contain'} style={{ transform: blur ? `scale(${ratio(settings.blur_background.scale, 1.6)})` : undefined }} aria-label={gaming ? 'Gameplay preview' : 'Live preview'} />
    {settings.hook_style.enabled && currentTime <= ratio(settings.hook_style.duration, 5) && <div data-testid="live-hook" className="pointer-events-none absolute w-[90%] text-center font-renderer font-extrabold leading-tight" style={{ ...layerStyle(settings.hook_style.position_x, settings.hook_style.position_y), fontSize: `${ratio(settings.hook_style.font_size, 0.054) * 500}px`, color: String(settings.hook_style.text_color), WebkitTextStroke: `${ratio(settings.hook_style.outline_thickness, 1.5)}px ${String(settings.hook_style.outline_color)}` }}>{hookText}</div>}
    {settings.subtitle.enabled && cue && <div data-testid="live-subtitle" className="pointer-events-none absolute w-[92%] text-center font-renderer font-extrabold leading-tight" style={{ ...layerStyle(settings.subtitle.position_x, settings.subtitle.position_y), fontSize: `${ratio(settings.subtitle.size, 0.04) * 500}px`, color: String(settings.subtitle.text_color), WebkitTextStroke: `${ratio(settings.subtitle.outline_thickness, 1)}px ${String(settings.subtitle.outline_color)}` }}>{cue.words.length ? cue.words.map((word, index) => <span key={`${word.start}-${index}`} style={{ color: currentTime >= word.active_from && currentTime <= word.active_until ? String(settings.subtitle.color) : String(settings.subtitle.text_color) }}>{word.text}{index + 1 < cue.words.length ? ' ' : ''}</span>) : cue.text}</div>}
    {settings.watermark.enabled && contract.watermark_url && <img data-testid="live-watermark" src={contract.watermark_url} className="pointer-events-none absolute h-auto" style={{ ...layerStyle(settings.watermark.position_x, settings.watermark.position_y), width: `${ratio(settings.watermark.scale, 0.15) * 100}%`, opacity: ratio(settings.watermark.opacity, 0.8) }} alt="Watermark" />}
    {settings.credit_watermark.enabled && contract.resolved_credit_text && <div data-testid="live-credit" className="pointer-events-none absolute font-renderer font-semibold" style={{ ...layerStyle(settings.credit_watermark.position_x, settings.credit_watermark.position_y), fontSize: `${ratio(settings.credit_watermark.size, 0.032) * 500}px`, color: String(settings.credit_watermark.color), opacity: ratio(settings.credit_watermark.opacity, 0.55) }}>{contract.resolved_credit_text}</div>}
  </div>;
}
