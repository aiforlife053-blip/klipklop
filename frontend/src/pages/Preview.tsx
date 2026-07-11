import { useState, useRef, useEffect, useCallback, type MouseEvent as ReactMouseEvent, type TouchEvent as ReactTouchEvent } from 'react';
import { useOutletContext, useBlocker } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { api } from '@/lib/api';

export default function Preview() {
  const { settings, setSettings } = useOutletContext<any>();
  const [dragging, setDragging] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [showBlockerModal, setShowBlockerModal] = useState(false);
  const lastSavedSettingsRef = useRef<string>('');
  const draggingRef = useRef<string | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);

  // Block navigation when dirty
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty && currentLocation.pathname !== nextLocation.pathname
  );

  useEffect(() => {
    if (blocker.state === 'blocked') {
      setShowBlockerModal(true);
    }
  }, [blocker.state]);

  // Block browser tab close/refresh when dirty
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);

  // --- Drag and Drop Handlers ---
  const handleDragStart = (e: ReactMouseEvent | ReactTouchEvent | MouseEvent | TouchEvent, element: string) => {
    if (e.cancelable) e.preventDefault();
    draggingRef.current = element;
    setDragging(element);
  };

  const handleDragMove = useCallback((e: MouseEvent | TouchEvent) => {
    if (!draggingRef.current || !previewRef.current) return;
    if ('touches' in e && e.touches.length === 0) return;

    const clientX = 'touches' in e ? e.touches[0].clientX : (e as MouseEvent).clientX;
    const clientY = 'touches' in e ? e.touches[0].clientY : (e as MouseEvent).clientY;

    const rect = previewRef.current.getBoundingClientRect();
    let x = (clientX - rect.left) / rect.width;
    let y = (clientY - rect.top) / rect.height;

    x = Math.max(0, Math.min(1, x));
    y = Math.max(0, Math.min(1, y));

    const currentDragging = draggingRef.current;
    
    setSettings((prev: any) => {
      if (currentDragging === 'watermark') {
        return { ...prev, watermark: { ...prev.watermark, position_x: x, position_y: y } };
      } else if (currentDragging === 'credit') {
        return { ...prev, credit_watermark: { ...prev.credit_watermark, position_x: x, position_y: y } };
      } else if (currentDragging === 'hook') {
        return { ...prev, hook_style: { ...prev.hook_style, position_x: x, position_y: y } };
      } else if (currentDragging === 'subtitle') {
        return { ...prev, subtitle: { ...prev.subtitle, position_x: x, position_y: y } };
      }
      return prev;
    });
  }, [setSettings]);

  const handleDragEnd = useCallback(() => {
    draggingRef.current = null;
    setDragging(null);
  }, []);

  useEffect(() => {
    const handleMove = (e: MouseEvent | TouchEvent) => handleDragMove(e);
    const handleEnd = () => handleDragEnd();

    window.addEventListener('mousemove', handleMove, { passive: false });
    window.addEventListener('touchmove', handleMove, { passive: false });
    window.addEventListener('mouseup', handleEnd);
    window.addEventListener('touchend', handleEnd);

    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('touchmove', handleMove);
      window.removeEventListener('mouseup', handleEnd);
      window.removeEventListener('touchend', handleEnd);
    };
  }, [handleDragMove, handleDragEnd]);

  const handleSaveSettings = async () => {
    setSaveState('saving');
    try {
      await api('/api/settings', {
        method: 'POST',
        body: JSON.stringify(settings),
      });
      setSaveState('saved');
      setLastSaved(new Date());
      setIsDirty(false);
      lastSavedSettingsRef.current = JSON.stringify(settings);
      setTimeout(() => setSaveState('idle'), 2000);
    } catch {
      setSaveState('error');
      setTimeout(() => setSaveState('idle'), 3000);
    }
  };

  // Track unsaved changes
  useEffect(() => {
    if (!lastSavedSettingsRef.current) {
      lastSavedSettingsRef.current = JSON.stringify(settings);
      return;
    }
    const current = JSON.stringify(settings);
    setIsDirty(current !== lastSavedSettingsRef.current);
  }, [settings]);

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10 min-h-[calc(100vh-53px)]">
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium uppercase tracking-widest text-primary">Preview Editor</p>
        <h1 className="font-display text-3xl font-bold tracking-tight md:text-4xl">Editor Klip</h1>
        <p className="text-muted">Atur watermark, teks, dan latar video — semua perubahan langsung terlihat di pratinjau.</p>
        
        <div className="flex items-center gap-2 mt-1">
          {isDirty ? (
            <>
              <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
              <span className="text-xs text-amber-600 font-semibold">Ada perubahan belum disimpan</span>
            </>
          ) : lastSaved ? (
            <>
              <svg className="w-3.5 h-3.5 text-emerald-500" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 13l4 4L19 7"/></svg>
              <span className="text-xs text-emerald-600 font-semibold">
                Tersimpan pukul {lastSaved.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            </>
          ) : (
            <span className="text-xs text-muted">Belum disimpan sesi ini</span>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,380px)_1fr]">
        {/* Pratinjau live */}
        <section className="flex flex-col gap-4 rounded-2xl border border-line bg-card/50 p-6 lg:sticky lg:top-24 lg:self-start" aria-label="Pratinjau klip">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-base font-bold">Pratinjau Live</h2>
            <span className="rounded-full border border-line bg-secondary px-3 py-1 text-xs text-muted">9:16</span>
          </div>

          <div 
            ref={previewRef}
            className="relative mx-auto aspect-[9/16] w-full max-w-[300px] overflow-hidden rounded-2xl border border-line bg-background select-none [container-type:inline-size]"
          >
            {/* Latar Blur */}
            {settings.blur_background.enabled ? (
              <img 
                src="https://placehold.co/800x450/24262c/8f929c?text=Video+Preview" 
                alt="blur background"
                className="absolute inset-0 size-full object-cover transition-all duration-75"
                style={{
                  transform: `scale(${settings.blur_background.zoom})`,
                  filter: `blur(${settings.blur_background.strength}px) brightness(0.6)`
                }}
              />
            ) : (
              <div className="absolute inset-0 size-full bg-black" />
            )}
            
            {/* Horizontal Video */}
            <div className="absolute inset-0 flex items-center justify-center">
              <img 
                src="https://placehold.co/800x450/24262c/8f929c?text=Video+Preview" 
                alt="horizontal video"
                className="w-full aspect-video object-cover shadow-2xl border-y border-line transition-all duration-75"
                style={{ transform: `scale(${settings.blur_background.scale || 1.0})` }}
                draggable={false}
              />
            </div>

            {/* Hook Title */}
            {settings.hook_style.enabled && (
              <div
                className="absolute z-10 hover:ring-2 ring-primary/50 rounded transition-opacity cursor-move"
                style={{
                  left: `${settings.hook_style.position_x * 100}%`,
                  top: `${settings.hook_style.position_y * 100}%`,
                  transform: 'translate(-50%, -50%)',
                  color: settings.hook_style.text_color || '#FFD700',
                  fontSize: `max(14px, ${(settings.hook_style.font_size || 0.054) * 300}px)`,
                  fontFamily: `'${['Plus Jakarta Sans', 'Poppins'].includes(settings.hook_style.font_family) ? settings.hook_style.font_family : 'Plus Jakarta Sans'}', sans-serif`,
                  fontWeight: settings.hook_style.font_weight || 800,
                  textAlign: 'center',
                  whiteSpace: 'pre-wrap',
                  lineHeight: '1.2',
                  WebkitTextStroke: `${(settings.hook_style.outline_thickness ?? 1.5) * 0.5}px ${settings.hook_style.outline_color || '#000000'}`,
                  textShadow: '0 2px 4px rgba(0,0,0,0.5)',
                  width: '90%',
                }}
                onMouseDown={(e) => handleDragStart(e, 'hook')}
                onTouchStart={(e) => handleDragStart(e, 'hook')}
              >
                JUDUL VIDEO VIRAL BIKIN PENASARAN
              </div>
            )}

            {/* Subtitle */}
            {settings.subtitle?.enabled && (
              <div
                className="absolute w-full z-10 hover:ring-2 ring-primary/50 transition-opacity cursor-move flex flex-col items-center justify-center"
                style={{
                  left: `${(settings.subtitle?.position_x ?? 0.5) * 100}%`,
                  top: `${(settings.subtitle?.position_y ?? 0.85) * 100}%`,
                  transform: 'translate(-50%, -50%)',
                  textAlign: 'center',
                  whiteSpace: 'normal',
                  pointerEvents: 'auto',
                  lineHeight: '1.2',
                }}
                onMouseDown={(e) => handleDragStart(e, 'subtitle')}
                onTouchStart={(e) => handleDragStart(e, 'subtitle')}
              >
                <div style={{
                  color: settings.subtitle?.text_color || '#FFFFFF',
                  fontSize: `max(12px, ${(settings.subtitle?.size || 0.04) * 300}px)`,
                  fontWeight: settings.subtitle?.font_weight || 800,
                  fontFamily: `'${['Plus Jakarta Sans', 'Poppins'].includes(settings.subtitle?.font_family) ? settings.subtitle.font_family : 'Plus Jakarta Sans'}', sans-serif`,
                  textTransform: settings.subtitle?.text_transform || 'uppercase',
                  WebkitTextStroke: `${(settings.subtitle?.outline_thickness ?? 1) * 0.5}px ${settings.subtitle?.outline_color || '#000000'}`,
                  textShadow: '0 1px 2px rgba(0,0,0,0.5)',
                }}>
                  CONTOH <span style={{ color: settings.subtitle?.color || '#00BFFF' }}>SUBTITLE KLIP</span> VIDEO
                </div>
              </div>
            )}

            {/* Watermark Logo */}
            {settings.watermark.enabled && (
              <div 
                className="absolute z-10 hover:ring-2 ring-primary/50 rounded transition-opacity cursor-move"
                style={{
                  left: `${settings.watermark.position_x * 100}%`,
                  top: `${settings.watermark.position_y * 100}%`,
                  transform: 'translate(-50%, -50%)',
                  opacity: settings.watermark.opacity,
                }}
                onMouseDown={(e) => handleDragStart(e, 'watermark')}
                onTouchStart={(e) => handleDragStart(e, 'watermark')}
              >
                <div 
                  className="bg-black/80 flex items-center justify-center rounded-md overflow-hidden"
                  style={{
                    width: `${settings.watermark.scale * 40}px`,
                    height: `${settings.watermark.scale * 40}px`,
                    boxShadow: '0 2px 4px rgba(0,0,0,0.5)'
                  }}
                >
                  <span className="font-bold text-white" style={{ fontSize: `${settings.watermark.scale * 10}px` }}>LOGO</span>
                </div>
              </div>
            )}

            {/* Credit Text */}
            {settings.credit_watermark.enabled && (
              <div 
                className="absolute z-10 hover:ring-2 ring-primary/50 rounded whitespace-nowrap transition-opacity cursor-move"
                style={{
                  left: `${settings.credit_watermark.position_x * 100}%`,
                  top: `${settings.credit_watermark.position_y * 100}%`,
                  transform: 'translate(-50%, -50%)',
                  opacity: settings.credit_watermark.opacity,
                  color: settings.credit_watermark.color,
                  fontSize: `max(10px, ${settings.credit_watermark.size * 200}px)`,
                  fontWeight: '600',
                  textShadow: '0px 1px 2px rgba(0,0,0,0.5)'
                }}
                onMouseDown={(e) => handleDragStart(e, 'credit')}
                onTouchStart={(e) => handleDragStart(e, 'credit')}
              >
                {settings.credit_watermark.text.replace('{channel}', '@klipklop')}
              </div>
            )}

            {/* Dragging Overlay */}
            {dragging && (
              <div className="absolute inset-0 border-2 border-dashed border-primary/50 pointer-events-none flex items-center justify-center bg-primary/5 z-20">
                <span className="bg-background/80 text-foreground px-3 py-1.5 rounded-full text-[10px] font-bold tracking-widest uppercase backdrop-blur-sm shadow-sm">
                  Menyeret {dragging}
                </span>
              </div>
            )}
          </div>

          <button 
            type="button" 
            onClick={handleSaveSettings}
            disabled={saveState === 'saving'}
            className={`flex h-12 items-center justify-center gap-2 rounded-xl font-display text-sm font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50 ${
              saveState === 'saved' ? 'bg-emerald-500' : saveState === 'error' ? 'bg-destructive' : isDirty ? 'bg-orange-600' : 'bg-primary'
            }`}
          >
            {saveState === 'saving' && (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
            )}
            {saveState === 'saved' && (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
            )}
            {(saveState === 'idle' || saveState === 'error') && (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
            )}
            {saveState === 'saving' ? 'Menyimpan...' : saveState === 'saved' ? 'Tersimpan!' : isDirty ? 'Simpan Perubahan' : 'Simpan Pengaturan'}
          </button>
        </section>

        {/* Kartu kontrol */}
        <div className="flex flex-col gap-5">
          <div className="grid gap-5 xl:grid-cols-2">
            
            {/* Watermark Logo */}
            <section className="flex flex-col gap-4 rounded-2xl border border-line bg-card p-5">
              <div className="flex items-center justify-between gap-3 border-b border-line pb-4">
                <div className="flex items-center gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>
                  </span>
                  <h2 className="font-display text-base font-bold">Watermark Logo</h2>
                </div>
                <button 
                  type="button" 
                  role="switch" 
                  aria-checked={settings.watermark.enabled} 
                  aria-label="Aktifkan Watermark Logo"
                  onClick={() => setSettings({...settings, watermark: {...settings.watermark, enabled: !settings.watermark.enabled}})}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${settings.watermark.enabled ? 'bg-primary' : 'bg-secondary'}`}
                >
                  <span className={`absolute left-0 top-0.5 size-5 rounded-full bg-white transition-transform ${settings.watermark.enabled ? 'translate-x-[22px]' : 'translate-x-0.5'}`}></span>
                </button>
              </div>
              <div className={`flex flex-col gap-4 transition-opacity ${settings.watermark.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <button type="button" className="flex h-12 items-center justify-center gap-2 rounded-xl border border-dashed border-line bg-secondary/50 text-sm font-medium text-muted transition-colors hover:border-primary/40 hover:text-primary">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>
                  Upload Image
                </button>
                <div className="flex flex-1 flex-col gap-2">
                  <div className="flex items-center justify-between text-xs"><span className="font-medium">Opacity</span><span className="text-muted">{Math.round(settings.watermark.opacity * 100)}%</span></div>
                  <input type="range" min="0" max="1" step="0.01" value={settings.watermark.opacity} onChange={(e) => setSettings({...settings, watermark: {...settings.watermark, opacity: parseFloat(e.target.value)}})} className="w-full accent-primary" />
                </div>
                <div className="flex flex-1 flex-col gap-2">
                  <div className="flex items-center justify-between text-xs"><span className="font-medium">Scale</span><span className="text-muted">{Math.round(settings.watermark.scale * 100)}%</span></div>
                  <input type="range" min="0.1" max="2" step="0.05" value={settings.watermark.scale} onChange={(e) => setSettings({...settings, watermark: {...settings.watermark, scale: parseFloat(e.target.value)}})} className="w-full accent-primary" />
                </div>
              </div>
            </section>

            {/* Credit Text */}
            <section className="flex flex-col gap-4 rounded-2xl border border-line bg-card p-5">
              <div className="flex items-center justify-between gap-3 border-b border-line pb-4">
                <div className="flex items-center gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.375 2.625a1 1 0 0 1 3 3l-9.013 9.014a2 2 0 0 1-.853.505l-2.873.84a.5.5 0 0 1-.62-.62l.84-2.873a2 2 0 0 1 .506-.852z"/></svg>
                  </span>
                  <h2 className="font-display text-base font-bold">Credit Text</h2>
                </div>
                <button 
                  type="button" 
                  role="switch" 
                  aria-checked={settings.credit_watermark.enabled} 
                  aria-label="Aktifkan Credit Text"
                  onClick={() => setSettings({...settings, credit_watermark: {...settings.credit_watermark, enabled: !settings.credit_watermark.enabled}})}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${settings.credit_watermark.enabled ? 'bg-primary' : 'bg-secondary'}`}
                >
                  <span className={`absolute left-0 top-0.5 size-5 rounded-full bg-white transition-transform ${settings.credit_watermark.enabled ? 'translate-x-[22px]' : 'translate-x-0.5'}`}></span>
                </button>
              </div>
              <div className={`flex flex-col gap-4 transition-opacity ${settings.credit_watermark.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <input 
                  type="text" 
                  value={settings.credit_watermark.text} 
                  onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, text: e.target.value}})} 
                  className="h-11 w-full rounded-xl border border-field bg-secondary px-4 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary" 
                  placeholder="sc : {channel}"
                />
                <div className="flex items-center gap-3">
                  <label className="relative flex size-11 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-xl border border-field" style={{ backgroundColor: settings.credit_watermark.color }}>
                    <span className="sr-only">Pilih warna teks kredit</span>
                    <input type="color" value={settings.credit_watermark.color} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, color: e.target.value}})} className="absolute inset-0 cursor-pointer opacity-0" />
                  </label>
                  <input type="text" value={settings.credit_watermark.color.toUpperCase()} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, color: e.target.value}})} className="h-11 w-full rounded-xl border border-field bg-secondary px-4 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary" />
                </div>
                <div className="flex gap-4">
                  <div className="flex flex-1 flex-col gap-2">
                    <div className="flex items-center justify-between text-xs"><span className="font-medium">Size</span><span className="text-muted">{Math.round(settings.credit_watermark.size * 1000)}%</span></div>
                    <input type="range" min="0.01" max="0.1" step="0.005" value={settings.credit_watermark.size} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, size: parseFloat(e.target.value)}})} className="w-full accent-primary" />
                  </div>
                  <div className="flex flex-1 flex-col gap-2">
                    <div className="flex items-center justify-between text-xs"><span className="font-medium">Opacity</span><span className="text-muted">{Math.round(settings.credit_watermark.opacity * 100)}%</span></div>
                    <input type="range" min="0" max="1" step="0.01" value={settings.credit_watermark.opacity} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, opacity: parseFloat(e.target.value)}})} className="w-full accent-primary" />
                  </div>
                </div>
              </div>
            </section>

            {/* Hook Title */}
            <section className="flex flex-col gap-4 rounded-2xl border border-line bg-card p-5">
              <div className="flex items-center justify-between gap-3 border-b border-line pb-4">
                <div className="flex items-center gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" x2="15" y1="20" y2="20"/><line x1="12" x2="12" y1="4" y2="20"/></svg>
                  </span>
                  <h2 className="font-display text-base font-bold">Hook Title</h2>
                </div>
                <button 
                  type="button" 
                  role="switch" 
                  aria-checked={settings.hook_style.enabled} 
                  aria-label="Aktifkan Hook Title"
                  onClick={() => setSettings({...settings, hook_style: {...settings.hook_style, enabled: !settings.hook_style.enabled}})}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${settings.hook_style.enabled ? 'bg-primary' : 'bg-secondary'}`}
                >
                  <span className={`absolute left-0 top-0.5 size-5 rounded-full bg-white transition-transform ${settings.hook_style.enabled ? 'translate-x-[22px]' : 'translate-x-0.5'}`}></span>
                </button>
              </div>
              <div className={`flex flex-col gap-4 transition-opacity ${settings.hook_style.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <p className="text-xs leading-relaxed text-muted">Geser hook title di preview untuk mengubah posisi.</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium">Font</label>
                    <select value={settings.hook_style.font_family} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, font_family: e.target.value}})} className="h-9 w-full rounded-lg border border-field bg-secondary px-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
                      <option value="Plus Jakarta Sans">Plus Jakarta Sans</option>
                      <option value="Poppins">Poppins</option>
                    </select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium">Ketebalan</label>
                    <select value={settings.hook_style.font_weight || 800} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, font_weight: Number(e.target.value)}})} className="h-9 w-full rounded-lg border border-field bg-secondary px-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
                      <option value={400}>Regular</option>
                      <option value={600}>Semi Bold</option>
                      <option value={800}>Bold</option>
                    </select>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="flex flex-1 flex-col gap-2">
                    <div className="flex items-center justify-between text-xs"><span className="font-medium">Ukuran</span><span className="text-muted">{Math.round((settings.hook_style.font_size || 0.054) * 500)}</span></div>
                    <input type="range" min="0.032" max="0.1" step="0.002" value={settings.hook_style.font_size || 0.054} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, font_size: Number(e.target.value)}})} className="w-full accent-primary" />
                  </div>
                  <div className="flex flex-1 flex-col gap-2">
                    <div className="flex items-center justify-between text-xs"><span className="font-medium">Outline</span><span className="text-muted">{settings.hook_style.outline_thickness ?? 1.5}</span></div>
                    <input type="range" min="0" max="6" step="0.25" value={settings.hook_style.outline_thickness ?? 1.5} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, outline_thickness: Number(e.target.value)}})} className="w-full accent-primary" />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium">Warna Teks</label>
                    <div className="flex items-center gap-2">
                      <label className="relative flex size-9 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-field" style={{ backgroundColor: settings.hook_style.text_color || '#FFD700' }}>
                        <input type="color" value={settings.hook_style.text_color || '#FFD700'} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, text_color: e.target.value}})} className="absolute inset-0 cursor-pointer opacity-0" />
                      </label>
                      <input type="text" value={(settings.hook_style.text_color || '#FFD700').toUpperCase()} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, text_color: e.target.value}})} className="h-9 w-full rounded-lg border border-field bg-secondary px-2 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary" />
                    </div>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium">Warna Outline</label>
                    <div className="flex items-center gap-2">
                      <label className="relative flex size-9 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-field" style={{ backgroundColor: settings.hook_style.outline_color || '#000000' }}>
                        <input type="color" value={settings.hook_style.outline_color || '#000000'} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, outline_color: e.target.value}})} className="absolute inset-0 cursor-pointer opacity-0" />
                      </label>
                      <input type="text" value={(settings.hook_style.outline_color || '#000000').toUpperCase()} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, outline_color: e.target.value}})} className="h-9 w-full rounded-lg border border-field bg-secondary px-2 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary" />
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {/* Subtitle */}
            <section className="flex flex-col gap-4 rounded-2xl border border-line bg-card p-5">
              <div className="flex items-center justify-between gap-3 border-b border-line pb-4">
                <div className="flex items-center gap-3">
                  <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="21" x2="3" y1="6" y2="6"/><line x1="15" x2="3" y1="12" y2="12"/><line x1="17" x2="3" y1="18" y2="18"/></svg>
                  </span>
                  <h2 className="font-display text-base font-bold">Subtitle</h2>
                </div>
                <button 
                  type="button" 
                  role="switch" 
                  aria-checked={settings.subtitle?.enabled} 
                  aria-label="Aktifkan Subtitle"
                  onClick={() => setSettings({...settings, subtitle: {...settings.subtitle, enabled: !settings.subtitle?.enabled}})}
                  className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${settings.subtitle?.enabled ? 'bg-primary' : 'bg-secondary'}`}
                >
                  <span className={`absolute left-0 top-0.5 size-5 rounded-full bg-white transition-transform ${settings.subtitle?.enabled ? 'translate-x-[22px]' : 'translate-x-0.5'}`}></span>
                </button>
              </div>
              <div className={`flex flex-col gap-4 transition-opacity ${settings.subtitle?.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
                <p className="text-xs leading-relaxed text-muted">Geser subtitle di preview untuk mengubah posisi.</p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium">Font</label>
                    <select value={settings.subtitle?.font_family} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, font_family: e.target.value}})} className="h-9 w-full rounded-lg border border-field bg-secondary px-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
                      <option value="Plus Jakarta Sans">Plus Jakarta Sans</option>
                      <option value="Poppins">Poppins</option>
                    </select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium">Ketebalan</label>
                    <select value={settings.subtitle?.font_weight || 800} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, font_weight: Number(e.target.value)}})} className="h-9 w-full rounded-lg border border-field bg-secondary px-2 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
                      <option value={400}>Regular</option>
                      <option value={600}>Semi Bold</option>
                      <option value={800}>Bold</option>
                    </select>
                  </div>
                </div>
                <div className="flex gap-4">
                  <div className="flex flex-1 flex-col gap-2">
                    <div className="flex items-center justify-between text-xs"><span className="font-medium">Ukuran</span><span className="text-muted">{Math.round((settings.subtitle?.size || 0.04) * 500)}</span></div>
                    <input type="range" min="0.024" max="0.1" step="0.002" value={settings.subtitle?.size || 0.04} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, size: Number(e.target.value)}})} className="w-full accent-primary" />
                  </div>
                  <div className="flex flex-1 flex-col gap-2">
                    <div className="flex items-center justify-between text-xs"><span className="font-medium">Outline</span><span className="text-muted">{settings.subtitle?.outline_thickness ?? 1}</span></div>
                    <input type="range" min="0" max="6" step="0.25" value={settings.subtitle?.outline_thickness ?? 1} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, outline_thickness: Number(e.target.value)}})} className="w-full accent-primary" />
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium">Teks</label>
                    <div className="flex items-center gap-2">
                      <label className="relative flex size-9 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-field" style={{ backgroundColor: settings.subtitle?.text_color || '#FFFFFF' }}>
                        <input type="color" value={settings.subtitle?.text_color || '#FFFFFF'} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, text_color: e.target.value}})} className="absolute inset-0 cursor-pointer opacity-0" />
                      </label>
                      <input type="text" value={(settings.subtitle?.text_color || '#FFFFFF').toUpperCase()} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, text_color: e.target.value}})} className="h-9 w-full rounded-lg border border-field bg-secondary px-2 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary" />
                    </div>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium">Highlight</label>
                    <div className="flex items-center gap-2">
                      <label className="relative flex size-9 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-field" style={{ backgroundColor: settings.subtitle?.color || '#00BFFF' }}>
                        <input type="color" value={settings.subtitle?.color || '#00BFFF'} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, color: e.target.value}})} className="absolute inset-0 cursor-pointer opacity-0" />
                      </label>
                      <input type="text" value={(settings.subtitle?.color || '#00BFFF').toUpperCase()} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, color: e.target.value}})} className="h-9 w-full rounded-lg border border-field bg-secondary px-2 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary" />
                    </div>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium">Outline</label>
                    <div className="flex items-center gap-2">
                      <label className="relative flex size-9 shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-lg border border-field" style={{ backgroundColor: settings.subtitle?.outline_color || '#000000' }}>
                        <input type="color" value={settings.subtitle?.outline_color || '#000000'} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, outline_color: e.target.value}})} className="absolute inset-0 cursor-pointer opacity-0" />
                      </label>
                      <input type="text" value={(settings.subtitle?.outline_color || '#000000').toUpperCase()} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, outline_color: e.target.value}})} className="h-9 w-full rounded-lg border border-field bg-secondary px-2 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary" />
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>

          {/* Latar Video */}
          <section className="flex flex-col gap-4 rounded-2xl border border-line bg-card p-5">
            <div className="flex items-center justify-between gap-3 border-b border-line pb-4">
              <div className="flex items-center gap-3">
                <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" x2="14" y1="3" y2="10"/><line x1="3" x2="10" y1="21" y2="14"/></svg>
                </span>
                <h2 className="font-display text-base font-bold">Latar Video</h2>
              </div>
              <button 
                type="button" 
                role="switch" 
                aria-checked={settings.blur_background.enabled} 
                aria-label="Aktifkan Latar Video"
                onClick={() => setSettings({...settings, blur_background: {...settings.blur_background, enabled: !settings.blur_background.enabled}})}
                className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${settings.blur_background.enabled ? 'bg-primary' : 'bg-secondary'}`}
              >
                <span className={`absolute left-0 top-0.5 size-5 rounded-full bg-white transition-transform ${settings.blur_background.enabled ? 'translate-x-[22px]' : 'translate-x-0.5'}`}></span>
              </button>
            </div>
            <div className={`flex flex-col gap-4 transition-opacity ${settings.blur_background.enabled ? '' : 'opacity-40 pointer-events-none'}`}>
              <div className="flex flex-col gap-4 sm:flex-row sm:gap-6">
                <div className="flex flex-1 flex-col gap-2">
                  <div className="flex items-center justify-between text-xs"><span className="font-medium">Video Scale</span><span className="text-muted">{Math.round((settings.blur_background.scale || 1.0) * 100)}%</span></div>
                  <input type="range" min="0.5" max="1.5" step="0.01" value={settings.blur_background.scale || 1.0} onChange={(e) => setSettings({...settings, blur_background: {...settings.blur_background, scale: parseFloat(e.target.value)}})} className="w-full accent-primary" />
                </div>
                <div className="flex flex-1 flex-col gap-2">
                  <div className="flex items-center justify-between text-xs"><span className="font-medium">Bg Zoom</span><span className="text-muted">{Math.round(settings.blur_background.zoom * 100)}%</span></div>
                  <input type="range" min="1.0" max="3.0" step="0.01" value={settings.blur_background.zoom} onChange={(e) => setSettings({...settings, blur_background: {...settings.blur_background, zoom: parseFloat(e.target.value)}})} className="w-full accent-primary" />
                </div>
                <div className="flex flex-1 flex-col gap-2">
                  <div className="flex items-center justify-between text-xs"><span className="font-medium">Blur Strength</span><span className="text-muted">{settings.blur_background.strength}</span></div>
                  <input type="range" min="0" max="100" step="1" value={settings.blur_background.strength} onChange={(e) => setSettings({...settings, blur_background: {...settings.blur_background, strength: parseInt(e.target.value)}})} className="w-full accent-primary" />
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>

      {/* Unsaved changes blocker modal */}
      {showBlockerModal && createPortal(
        <div className="fixed inset-0 z-[9999] bg-background/80 flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-card rounded-2xl w-full max-w-sm shadow-2xl border border-line overflow-hidden animate-in zoom-in-95 duration-150 p-6 flex flex-col gap-4 text-center">
            <h3 className="font-display font-bold text-lg">Ada perubahan belum disimpan!</h3>
            <p className="text-sm text-muted">Setting yang kamu ubah belum tersimpan ke server. Kalau kamu pindah halaman sekarang, semua perubahan akan hilang.</p>
            <div className="flex gap-3 justify-center mt-2">
              <button
                onClick={() => {
                  setShowBlockerModal(false);
                  blocker.reset?.();
                }}
                className="px-5 py-2 rounded-xl font-medium border border-line text-foreground hover:bg-secondary transition-colors"
              >
                Kembali & Simpan
              </button>
              <button
                onClick={() => {
                  setShowBlockerModal(false);
                  setIsDirty(false);
                  blocker.proceed?.();
                }}
                className="px-5 py-2 rounded-xl font-medium bg-destructive text-destructive-foreground transition-opacity hover:opacity-90"
              >
                Tinggalkan
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </main>
  );
}
