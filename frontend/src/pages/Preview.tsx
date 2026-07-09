import { useState, useRef, useEffect, type MouseEvent as ReactMouseEvent, type TouchEvent as ReactTouchEvent } from 'react';
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

  const handleDragMove = (e: MouseEvent | TouchEvent) => {
    if (!draggingRef.current || !previewRef.current) return;

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
  };

  const handleDragEnd = () => {
    draggingRef.current = null;
    setDragging(null);
  };

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
  }, []);

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
    } catch (e) {
      setSaveState('error');
      setTimeout(() => setSaveState('idle'), 3000);
    }
  };

  // Track unsaved changes
  useEffect(() => {
    if (!lastSavedSettingsRef.current) {
      // First load — mark as clean baseline
      lastSavedSettingsRef.current = JSON.stringify(settings);
      return;
    }
    const current = JSON.stringify(settings);
    setIsDirty(current !== lastSavedSettingsRef.current);
  }, [settings]);

  const SectionHeader = ({ title, icon, enabled }: any) => (
    <div className="flex items-center justify-between p-4 bg-orange-50/20 border-b border-slate-100">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-orange-100 text-primary">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d={icon}></path></svg>
        </div>
        <h4 className="text-[14px] font-bold text-slate-900">{title}</h4>
      </div>
      <div className="flex items-center gap-3">
        {enabled && <span className="w-2 h-2 rounded-full bg-emerald-500"></span>}
      </div>
    </div>
  );

  return (
    <div className="flex flex-row-reverse w-full h-[calc(100vh-53px)] overflow-hidden bg-slate-50/50">
      
      {/* Settings Panel: Configuration Accordions (50%) */}
      <div className="w-[50%] shrink-0 border-l border-slate-200 bg-white h-full overflow-y-auto flex flex-col z-10 shadow-[-4px_0_24px_rgba(0,0,0,0.02)]">
        <div className="p-5 border-b border-slate-100 sticky top-0 bg-white z-20">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-[20px] font-bold text-slate-900 tracking-tight">Studio Editor</h2>
              <p className="text-[13px] text-slate-500 mt-0.5">Konfigurasi overlay dan efek klip. Drag elemen langsung di preview!</p>
              <div className="flex items-center gap-1.5 mt-1.5">
                {isDirty ? (
                  <>
                    <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse"></span>
                    <span className="text-[11px] text-amber-600 font-semibold">Ada perubahan belum disimpan</span>
                  </>
                ) : lastSaved ? (
                  <>
                    <svg className="w-3 h-3 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7"/></svg>
                    <span className="text-[11px] text-emerald-600 font-semibold">
                      Tersimpan pukul {lastSaved.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                    </span>
                  </>
                ) : (
                  <span className="text-[11px] text-slate-400">Belum disimpan sesi ini</span>
                )}
              </div>
            </div>
            <button
              onClick={handleSaveSettings}
              disabled={saveState === 'saving'}
              className={`shrink-0 flex items-center gap-2 px-4 py-2 rounded-xl text-[13px] font-semibold transition shadow-sm border ${
                saveState === 'saved'
                  ? 'bg-emerald-500 text-white border-emerald-500'
                  : saveState === 'error'
                  ? 'bg-red-500 text-white border-red-500'
                  : isDirty
                  ? 'bg-orange-600 hover:bg-orange-700 text-white border-orange-600 shadow-orange-200 shadow-md disabled:opacity-60'
                  : 'bg-primary hover:bg-orange-700 text-white border-primary disabled:opacity-60'
              }`}
            >
              {saveState === 'saving' && (
                <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </svg>
              )}
              {saveState === 'saved' && (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7"/>
                </svg>
              )}
              {saveState === 'error' && (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M6 18L18 6M6 6l12 12"/>
                </svg>
              )}
              {(saveState === 'idle') && (
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/>
                </svg>
              )}
              <span>
                {saveState === 'saving' ? 'Menyimpan...' : saveState === 'saved' ? 'Tersimpan!' : saveState === 'error' ? 'Gagal!' : isDirty ? 'Simpan Sekarang' : 'Simpan'}
              </span>
            </button>
          </div>
        </div>

      {/* Unsaved changes blocker modal */}
      {showBlockerModal && createPortal(
        <div className="fixed inset-0 z-[9999] bg-black/60 flex items-center justify-center p-4 animate-in fade-in duration-150">
          <div className="bg-white rounded-2xl w-full max-w-sm shadow-2xl border border-slate-100 overflow-hidden animate-in zoom-in-95 duration-150">
            <div className="p-6 space-y-3">
              <div className="w-11 h-11 bg-orange-100 rounded-xl flex items-center justify-center">
                <svg className="w-6 h-6 text-orange-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
              </div>
              <h3 className="text-[17px] font-bold text-slate-900">Ada perubahan belum disimpan!</h3>
              <p className="text-[13px] text-slate-500 leading-relaxed">Setting yang kamu ubah belum tersimpan ke server. Kalau kamu pindah halaman sekarang, semua perubahan akan hilang.</p>
            </div>
            <div className="px-6 pb-6 flex gap-2.5">
              <button
                onClick={() => {
                  setShowBlockerModal(false);
                  blocker.reset?.();
                }}
                className="flex-1 py-2.5 border border-slate-200 rounded-xl text-[13px] font-semibold text-slate-700 hover:bg-slate-50 transition"
              >
                Kembali & Simpan
              </button>
              <button
                onClick={() => {
                  setShowBlockerModal(false);
                  setIsDirty(false);
                  blocker.proceed?.();
                }}
                className="flex-1 py-2.5 bg-red-500 hover:bg-red-600 text-white rounded-xl text-[13px] font-semibold transition shadow-sm"
              >
                Tinggalkan
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

        <div className="flex-1 p-3 grid grid-cols-2 gap-3 overflow-y-auto content-start bg-slate-50">
          
          {/* Watermark Section */}
          <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm flex flex-col gap-2.5">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h4 className="text-[13px] font-bold text-slate-900 flex items-center gap-2">
                <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                Watermark Logo
              </h4>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" className="sr-only peer" checked={settings.watermark.enabled} onChange={(e) => setSettings({...settings, watermark: {...settings.watermark, enabled: e.target.checked}})} />
                <div className="w-8 h-4 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>
            {settings.watermark.enabled && (
              <div className="space-y-3 pt-1">
                <div className="border border-slate-200 border-dashed rounded-lg p-2 flex items-center justify-center gap-2 hover:bg-slate-50 transition cursor-pointer">
                  <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
                  <span className="text-[11px] font-semibold text-slate-700">Upload Image</span>
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-semibold text-slate-600">Opacity</label>
                    <span className="text-[10px] font-medium text-slate-400">{Math.round(settings.watermark.opacity * 100)}%</span>
                  </div>
                  <input type="range" min="0" max="1" step="0.01" value={settings.watermark.opacity} onChange={(e) => setSettings({...settings, watermark: {...settings.watermark, opacity: parseFloat(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-semibold text-slate-600">Scale</label>
                    <span className="text-[10px] font-medium text-slate-400">{Math.round(settings.watermark.scale * 100)}%</span>
                  </div>
                  <input type="range" min="0.1" max="2" step="0.05" value={settings.watermark.scale} onChange={(e) => setSettings({...settings, watermark: {...settings.watermark, scale: parseFloat(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                </div>
              </div>
            )}
          </div>

          {/* Credit Section */}
          <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm flex flex-col gap-2.5">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h4 className="text-[13px] font-bold text-slate-900 flex items-center gap-2">
                <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                Credit Text
              </h4>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" className="sr-only peer" checked={settings.credit_watermark.enabled} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, enabled: e.target.checked}})} />
                <div className="w-8 h-4 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>
            {settings.credit_watermark.enabled && (
              <div className="space-y-3 pt-1">
                <div>
                  <input type="text" value={settings.credit_watermark.text} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, text: e.target.value}})} className="w-full px-2 py-1.5 border border-slate-200 rounded-lg text-[11px] focus:outline-none focus:border-primary font-mono text-slate-700 bg-slate-50" placeholder="sc : {channel}" />
                </div>
                <div className="flex items-center gap-2">
                  <input type="color" value={settings.credit_watermark.color} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, color: e.target.value}})} className="w-6 h-6 rounded cursor-pointer border border-slate-200 p-0.5 bg-white shrink-0" />
                  <input type="text" value={settings.credit_watermark.color.toUpperCase()} readOnly className="flex-1 px-2 py-1 border border-slate-200 rounded-lg text-[11px] font-medium bg-slate-50 text-slate-600 focus:outline-none" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[10px] font-semibold text-slate-600">Size</label>
                      <span className="text-[9px] font-medium text-slate-400">{Math.round(settings.credit_watermark.size * 1000)}%</span>
                    </div>
                    <input type="range" min="0.01" max="0.1" step="0.005" value={settings.credit_watermark.size} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, size: parseFloat(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[10px] font-semibold text-slate-600">Opacity</label>
                      <span className="text-[9px] font-medium text-slate-400">{Math.round(settings.credit_watermark.opacity * 100)}%</span>
                    </div>
                    <input type="range" min="0" max="1" step="0.01" value={settings.credit_watermark.opacity} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, opacity: parseFloat(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Hook Section */}
          <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm flex flex-col gap-2.5">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h4 className="text-[13px] font-bold text-slate-900 flex items-center gap-2">
                <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"></path></svg>
                Hook Style
              </h4>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" className="sr-only peer" checked={settings.hook_style.enabled} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, enabled: e.target.checked}})} />
                <div className="w-8 h-4 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>
            {settings.hook_style.enabled && (
              <div className="space-y-3 pt-1">
                <div className="grid grid-cols-2 gap-2">
                  <select value={settings.hook_style.font_family || 'Capo Sfogliato'} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, font_family: e.target.value}})} className="w-full px-2 py-1.5 border border-slate-200 rounded-lg text-[11px] font-medium focus:outline-none focus:border-primary bg-slate-50">
                    <option value="Capo Sfogliato">Capo Sfogliato</option>
                    <option value="Super Hockey">Super Hockey</option>
                    <option value="Super Kidpop">Super Kidpop</option>
                    <option value="Inter">Inter</option>
                  </select>
                  <select value={settings.hook_style.shape || 'rectangle'} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, shape: e.target.value}})} className="w-full px-2 py-1.5 border border-slate-200 rounded-lg text-[11px] font-medium focus:outline-none focus:border-primary bg-slate-50">
                    <option value="rectangle">Rectangle</option>
                    <option value="pill">Pill</option>
                  </select>
                </div>
                <div className="flex gap-2">
                  <div className="flex-1 flex items-center gap-1.5 bg-slate-50 border border-slate-100 p-1.5 rounded-lg">
                    <input type="color" value={settings.hook_style.text_color} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, text_color: e.target.value}})} className="w-5 h-5 rounded cursor-pointer border border-slate-200 p-0.5 bg-white shrink-0" />
                    <label className="text-[10px] font-semibold text-slate-600">Text</label>
                  </div>
                  <div className="flex-1 flex items-center gap-1.5 bg-slate-50 border border-slate-100 p-1.5 rounded-lg">
                    <input type="color" value={settings.hook_style.background_color || settings.hook_style.bg_color} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, background_color: e.target.value, bg_color: e.target.value}})} className="w-5 h-5 rounded cursor-pointer border border-slate-200 p-0.5 bg-white shrink-0" />
                    <label className="text-[10px] font-semibold text-slate-600">Bg</label>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[10px] font-semibold text-slate-600">Size</label>
                      <span className="text-[9px] font-medium text-slate-400">{Math.round((settings.hook_style.font_size || 0.05) * 1000)}%</span>
                    </div>
                    <input type="range" min="0.01" max="0.1" step="0.005" value={settings.hook_style.font_size} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, font_size: parseFloat(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[10px] font-semibold text-slate-600">Radius</label>
                      <span className="text-[9px] font-medium text-slate-400">{settings.hook_style.corner_radius}px</span>
                    </div>
                    <input type="range" min="0" max="100" step="1" value={settings.hook_style.corner_radius} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, corner_radius: parseInt(e.target.value)}})} className={`w-full h-1 rounded-lg appearance-none cursor-pointer ${settings.hook_style.shape === 'pill' ? 'bg-slate-200 accent-slate-400 opacity-50' : 'bg-orange-100 accent-primary'}`} disabled={settings.hook_style.shape === 'pill'} />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Subtitle Section */}
          <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm flex flex-col gap-2.5">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h4 className="text-[13px] font-bold text-slate-900 flex items-center gap-2">
                <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16m-7 6h7"></path></svg>
                Subtitle Style
              </h4>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" className="sr-only peer" checked={settings.subtitle?.enabled} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, enabled: e.target.checked}})} />
                <div className="w-8 h-4 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>
            {settings.subtitle?.enabled && (
              <div className="space-y-3 pt-1">
                <div className="flex gap-2">
                  <div className="flex-1 flex items-center gap-1.5 bg-slate-50 border border-slate-100 p-1.5 rounded-lg">
                    <input type="color" value={settings.subtitle?.color || '#ffff00'} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, color: e.target.value}})} className="w-5 h-5 rounded cursor-pointer border border-slate-200 p-0.5 bg-white shrink-0" />
                    <label className="text-[10px] font-semibold text-slate-600">Text</label>
                  </div>
                  <div className="flex-1 flex items-center gap-1.5 bg-slate-50 border border-slate-100 p-1.5 rounded-lg">
                    <input type="color" value={settings.subtitle?.bg_color || '#000000'} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, bg_color: e.target.value}})} className="w-5 h-5 rounded cursor-pointer border border-slate-200 p-0.5 bg-white shrink-0" />
                    <label className="text-[10px] font-semibold text-slate-600">Bg</label>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <select value={settings.subtitle?.font_family || 'Plus Jakarta Sans'} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, font_family: e.target.value}})} className="w-full px-2 py-1.5 border border-slate-200 rounded-lg text-[11px] font-medium focus:outline-none focus:border-primary bg-slate-50">
                    <option value="Plus Jakarta Sans">Plus Jakarta</option>
                    <option value="Poppins">Poppins</option>
                    <option value="Inter">Inter</option>
                  </select>
                  <select value={settings.subtitle?.text_transform || 'none'} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, text_transform: e.target.value}})} className="w-full px-2 py-1.5 border border-slate-200 rounded-lg text-[11px] font-medium focus:outline-none focus:border-primary bg-slate-50">
                    <option value="none">Normal</option>
                    <option value="uppercase">UPPERCASE</option>
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[10px] font-semibold text-slate-600">Size</label>
                      <span className="text-[9px] font-medium text-slate-400">{Math.round((settings.subtitle?.size || 0.04) * 1000)}%</span>
                    </div>
                    <input type="range" min="0.01" max="0.1" step="0.005" value={settings.subtitle?.size || 0.04} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, size: parseFloat(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <label className="text-[10px] font-semibold text-slate-600">Weight</label>
                      <span className="text-[9px] font-medium text-slate-400">{settings.subtitle?.font_weight || 800}</span>
                    </div>
                    <input type="range" min="100" max="900" step="100" value={settings.subtitle?.font_weight || 800} onChange={(e) => setSettings({...settings, subtitle: {...settings.subtitle, font_weight: parseInt(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Background Blur Section */}
          <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-sm flex flex-col gap-2.5">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <h4 className="text-[13px] font-bold text-slate-900 flex items-center gap-2">
                <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path></svg>
                Bg Blur
              </h4>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" className="sr-only peer" checked={settings.blur_background.enabled} onChange={(e) => setSettings({...settings, blur_background: {...settings.blur_background, enabled: e.target.checked}})} />
                <div className="w-8 h-4 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-primary"></div>
              </label>
            </div>
            {settings.blur_background.enabled && (
              <div className="space-y-3 pt-1">
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-semibold text-slate-600">Video Scale</label>
                    <span className="text-[10px] font-medium text-slate-400">{Math.round((settings.blur_background.scale || 1.0) * 100)}%</span>
                  </div>
                  <input type="range" min="0.5" max="1.5" step="0.01" value={settings.blur_background.scale || 1.0} onChange={(e) => setSettings({...settings, blur_background: {...settings.blur_background, scale: parseFloat(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-semibold text-slate-600">Bg Zoom</label>
                    <span className="text-[10px] font-medium text-slate-400">{Math.round(settings.blur_background.zoom * 100)}%</span>
                  </div>
                  <input type="range" min="1.0" max="2.0" step="0.01" value={settings.blur_background.zoom} onChange={(e) => setSettings({...settings, blur_background: {...settings.blur_background, zoom: parseFloat(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-semibold text-slate-600">Blur Strength</label>
                    <span className="text-[10px] font-medium text-slate-400">{settings.blur_background.strength}</span>
                  </div>
                  <input type="range" min="0" max="100" step="1" value={settings.blur_background.strength} onChange={(e) => setSettings({...settings, blur_background: {...settings.blur_background, strength: parseInt(e.target.value)}})} className="w-full h-1 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                </div>
              </div>
            )}
          </div>
          
        </div>
      </div>

      {/* Preview Panel: Interactive 9:16 Preview (50%) */}
      <div className="w-[50%] flex flex-col items-center justify-center p-6 relative overflow-hidden bg-muted" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
        
        {/* Aspect Ratio Container */}
        <div 
          ref={previewRef}
          className="relative w-full max-w-[340px] aspect-[9/16] bg-black rounded-[2rem] shadow-2xl overflow-hidden ring-8 ring-white/50 group select-none"
        >
          {/* 1. Background Blur Layer */}
          <div className="absolute inset-0 w-full h-full">
            {settings.blur_background.enabled ? (
              <img 
                src="https://images.unsplash.com/photo-1581009146145-b5ef050c2e1e?auto=format&fit=crop&w=800&q=80" 
                alt="blur background"
                className="w-full h-full object-cover transition-all duration-75"
                style={{
                  transform: `scale(${settings.blur_background.zoom})`,
                  filter: `blur(${settings.blur_background.strength}px) brightness(0.6)`
                }}
              />
            ) : (
              <div className="w-full h-full bg-slate-900" />
            )}
          </div>

          {/* 2. Main Horizontal Video Layer */}
          <div className="absolute inset-0 flex items-center justify-center">
            <img 
              src="https://images.unsplash.com/photo-1581009146145-b5ef050c2e1e?auto=format&fit=crop&w=800&q=80" 
              alt="horizontal video"
              className="w-full aspect-video object-cover shadow-2xl transition-all duration-75"
              style={{
                transform: `scale(${settings.blur_background.scale || 1.0})`
              }}
              draggable={false}
            />
          </div>

          {/* 3. Watermark Layer (Draggable) */}
          <div 
            className={`absolute z-10 hover:ring-2 ring-primary/50 rounded transition-opacity ${settings.watermark.enabled ? 'cursor-move' : 'opacity-0 pointer-events-none'}`}
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
              className="bg-black/80 flex items-center justify-center rounded-xl overflow-hidden"
              style={{
                width: `${settings.watermark.scale * 150}px`,
                height: `${settings.watermark.scale * 150}px`,
                boxShadow: '0 4px 12px rgba(0,0,0,0.5)'
              }}
            >
              <span className="text-white font-bold" style={{ fontSize: `${settings.watermark.scale * 24}px` }}>LOGO</span>
            </div>
          </div>

          {/* 4. Credit Layer (Draggable) */}
          <div 
            className={`absolute z-10 hover:ring-2 ring-primary/50 rounded whitespace-nowrap transition-opacity ${settings.credit_watermark.enabled ? 'cursor-move' : 'opacity-0 pointer-events-none'}`}
            style={{
              left: `${settings.credit_watermark.position_x * 100}%`,
              top: `${settings.credit_watermark.position_y * 100}%`,
              transform: 'translate(-50%, -50%)',
              opacity: settings.credit_watermark.opacity,
              color: settings.credit_watermark.color,
              fontSize: `${Math.max(10, settings.credit_watermark.size * 320)}px`,
              fontWeight: '600',
              textShadow: '0px 1px 3px rgba(0,0,0,0.5)'
            }}
            onMouseDown={(e) => handleDragStart(e, 'credit')}
            onTouchStart={(e) => handleDragStart(e, 'credit')}
          >
            {settings.credit_watermark.text.replace('{channel}', '@klipklop')}
          </div>

          {/* 5. Hook Layer (Draggable) */}
          <div 
            className={`absolute z-10 flex items-center justify-center hover:ring-2 ring-primary/50 transition-opacity ${settings.hook_style.enabled ? 'cursor-move' : 'opacity-0 pointer-events-none'}`}
            style={{
              left: `${settings.hook_style.position_x * 100}%`,
              top: `${settings.hook_style.position_y * 100}%`,
              transform: 'translate(-50%, -50%)',
              color: settings.hook_style.text_color,
              backgroundColor: settings.hook_style.background_color || settings.hook_style.bg_color,
              fontSize: `${Math.max(12, (settings.hook_style.font_size || 0.05) * 500)}px`,
              fontFamily: settings.hook_style.font_family || 'sans-serif',
              fontWeight: '900',
              padding: '12px 28px',
              borderRadius: settings.hook_style.shape === 'pill' ? '999px' : `${settings.hook_style.corner_radius}px`,
              boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
              whiteSpace: 'nowrap',
              textTransform: 'uppercase',
              letterSpacing: '1px'
            }}
            onMouseDown={(e) => handleDragStart(e, 'hook')}
            onTouchStart={(e) => handleDragStart(e, 'hook')}
          >
            WAIT FOR IT!
          </div>

          {/* 6. Subtitle Layer (Draggable) */}
          <div 
            className={`absolute z-10 hover:ring-2 ring-primary/50 rounded transition-opacity ${settings.subtitle?.enabled ? 'cursor-move' : 'opacity-0 pointer-events-none'}`}
            style={{
              left: `${(settings.subtitle?.position_x ?? 0.5) * 100}%`,
              top: `${(settings.subtitle?.position_y ?? 0.85) * 100}%`,
              transform: 'translate(-50%, -50%)',
              color: settings.subtitle?.color || '#ffff00',
              fontSize: `${Math.max(12, (settings.subtitle?.size || 0.04) * 500)}px`,
              fontWeight: settings.subtitle?.font_weight || 800,
              textShadow: '0px 2px 4px rgba(0,0,0,0.8)',
              whiteSpace: 'nowrap',
              fontFamily: `'${settings.subtitle?.font_family || 'Plus Jakarta Sans'}', sans-serif`,
              textAlign: 'center',
              textTransform: (settings.subtitle?.text_transform as any) || 'none',
              backgroundColor: `${settings.subtitle?.bg_color || '#000000'}${Math.round((settings.subtitle?.bg_opacity ?? 0.8) * 255).toString(16).padStart(2, '0')}`,
              padding: '0.2em 0.5em',
              borderRadius: '0.2em',
              userSelect: 'none',
              WebkitUserSelect: 'none'
            }}
            onMouseDown={(e) => handleDragStart(e, 'subtitle')}
            onTouchStart={(e) => handleDragStart(e, 'subtitle')}
          >
            {(() => {
              const t = 'Contoh subtitle klip video';
              const transform = settings.subtitle?.text_transform || 'none';
              if (transform === 'uppercase') return t.toUpperCase();
              if (transform === 'lowercase') return t.toLowerCase();
              if (transform === 'capitalize') return t.replace(/\b\w/g, c => c.toUpperCase());
              return t;
            })()}
          </div>

          {/* Overlay Helper text when dragging */}
          {dragging && (
            <div className="absolute inset-0 border-4 border-dashed border-primary/50 pointer-events-none flex items-center justify-center bg-primary/5 z-0">
              <span className="bg-black/50 text-white px-3 py-1.5 rounded-full text-[12px] backdrop-blur-sm shadow-sm font-semibold">
                Dragging {dragging.toUpperCase()}...
              </span>
            </div>
          )}

        </div>
        
        {/* Helper Badge */}
        <div className="absolute bottom-6 bg-white/80 backdrop-blur-md px-4 py-2 rounded-full border border-slate-200 shadow-sm text-[12px] font-semibold text-slate-600 flex items-center gap-2">
          <svg className="w-4 h-4 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"></path></svg>
          Akktifkan setting lalu klik & tahan elemen di dalam preview untuk memindahkannya
        </div>

      </div>
    </div>
  );
}
