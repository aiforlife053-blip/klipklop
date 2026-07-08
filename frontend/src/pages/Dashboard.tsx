import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState('home');
  const [status, setStatus] = useState<any>(null);
  
  // --- Form & Settings State ---
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [videoQuality, setVideoQuality] = useState('720');
  const [landscapeBlur, setLandscapeBlur] = useState(true);
  const [showJsonModal, setShowJsonModal] = useState(false);
  const [editingEffect, setEditingEffect] = useState<string | null>(null);

  const [settings, setSettings] = useState<any>({
    base_url: '',
    api_key: '',
    model: '',
    output_dir: '',
    watermark: { enabled: false, image_path: "", position_x: 0.22, position_y: 0.17, opacity: 0.49, scale: 0.53 },
    credit_watermark: { enabled: true, text: "sc : {channel}", color: "#ffffff", size: 0.032, opacity: 0.55, position_x: 0.22, position_y: 0.17 },
    hook_style: { enabled: false, font_size: 0.025, text_color: "#0033ff", background_color: "#ffffff", corner_radius: 22, duration: 5.0, position_x: 0.22, position_y: 0.17 },
    blur_background: { enabled: true, zoom: 1.08, strength: 31, scale: 1.0 }
  });
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');

  useEffect(() => {
    // Fetch initial status
    const fetchStatus = async () => {
      try {
        const data = await api('/api/status');
        setStatus(data);
      } catch (err) {
        console.error("Failed to fetch status", err);
      }
    };
    fetchStatus();

    // Fetch initial settings
    const fetchSettings = async () => {
      try {
        const data = await api('/api/settings');
        if (data && !data.error) {
          setSettings((prev: any) => ({
            ...prev,
            base_url: data.base_url || '',
            api_key: data.api_key || '',
            model: data.model || '',
            output_dir: data.output_dir || '',
            watermark: data.watermark || prev.watermark,
            credit_watermark: data.credit_watermark || prev.credit_watermark,
            hook_style: data.hook_style || prev.hook_style,
            blur_background: data.blur_background || prev.blur_background
          }));
        }
      } catch (err) {
        console.error("Failed to fetch settings", err);
      }
    };
    fetchSettings();
    
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleLogout = async () => {
    try {
      await fetch('/api/logout', { method: 'POST' });
      window.location.href = '/login';
    } catch (err) {
      console.error(err);
    }
  };

  const handleSaveSettings = async () => {
    setIsSaving(true);
    setSaveMessage('');
    try {
      await api('/api/settings', {
        method: 'POST',
        body: JSON.stringify(settings)
      });
      setSaveMessage('Konfigurasi berhasil disimpan! ✨');
      setTimeout(() => setSaveMessage(''), 3000);
    } catch (err) {
      setSaveMessage('Gagal menyimpan konfigurasi.');
      setTimeout(() => setSaveMessage(''), 3000);
    } finally {
      setIsSaving(false);
    }
  };

  const handleClearApiKey = () => {
    setSettings(prev => ({ ...prev, api_key: '' }));
  };

  return (
    <div className="bg-background text-foreground h-screen overflow-hidden flex flex-col antialiased">
      <header className="bg-white border-b border-border px-4 py-3 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-2 text-black font-extrabold text-[16px] tracking-tight">
          <img src="/logo%20klipklop.png?v=3" className="h-8 w-8 rounded-md object-contain" alt="KlipKlop Logo" />
          <span className="text-black leading-none">KlipKlop</span>
        </div>
        <nav className="flex items-center gap-1 text-[13px] font-semibold">
          <button 
            onClick={() => setActiveTab('home')}
            className={`px-3 py-2 rounded-xl transition ${activeTab === 'home' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900'}`}
          >
            Dashboard
          </button>
          <button 
            onClick={() => setActiveTab('history')}
            className={`px-3 py-2 rounded-xl transition ${activeTab === 'history' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900'}`}
          >
            Galeri
          </button>
          <button 
            onClick={() => setActiveTab('console')}
            className={`px-3 py-2 rounded-xl transition ${activeTab === 'console' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900'}`}
          >
            Konsol
          </button>
          <button 
            onClick={() => setActiveTab('settings')}
            className={`px-3 py-2 rounded-xl transition ${activeTab === 'settings' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900'}`}
          >
            Pengaturan
          </button>
          <button 
            onClick={handleLogout}
            type="button" 
            className="ml-2 min-h-11 rounded-xl border border-red-400/30 px-3 py-2 text-red-400 hover:bg-red-500/10 hover:text-red-500 transition"
          >
            Keluar
          </button>
        </nav>
      </header>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <main className="flex-1 min-w-0 flex flex-col">
          {activeTab === 'home' && (
            <div className="flex flex-row flex-1 items-stretch h-[calc(100vh-53px)] overflow-hidden">
              <section className="relative order-2 w-[60%] flex-none bg-muted border-l border-border p-0 h-full overflow-auto flex flex-col justify-between" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
                <button 
                  type="button"
                  onClick={() => setShowJsonModal(true)}
                  className="absolute top-4 right-4 border border-border px-3.5 py-2 rounded-xl text-[12px] font-semibold text-slate-700 hover:bg-white bg-white/50 backdrop-blur-sm transition shadow-sm z-10"
                >
                  JSON Payload
                </button>
                <div className="hidden">
                  <h2 className="text-[20px] font-semibold text-black mb-0.5 tracking-tight">Hasil Klip</h2>
                  <p className="text-[13px] text-gray-500">Lihat klip yang sudah jadi dan pantau progress yang sedang diproses.</p>
                </div>

                <div className="flex flex-1 h-full flex-col items-center justify-center text-center max-w-xl mx-auto w-full">
                  <h3 className="text-[19px] font-semibold text-black mb-2.5 tracking-tight">Siap Membuat Klip Viral Terbaik?</h3>
                  <p className="text-[13px] text-gray-500 leading-relaxed max-w-md">Tempel link YouTube di panel kiri. AI akan memilih 1 momen dengan potensi viral tertinggi.</p>
                </div>

                <div className="hidden text-[13px] text-gray-500 w-full">
                  Status: Idle<br />Clip: - | Quality: 720p | 9:16
                </div>
              </section>

              {/* Left Panel: Settings & Creation Form */}
              <aside className="order-1 w-[40%] shrink-0 bg-white border-r border-border p-5 h-full overflow-auto flex flex-col gap-5">
                <div className="space-y-5">
                  <div className="space-y-4">
                    <div>
                      <label className="block text-[12px] font-semibold text-black mb-1">Link YouTube</label>
                      <input 
                        type="text" 
                        placeholder="https://www.youtube.com/watch?v=..." 
                        value={youtubeUrl}
                        onChange={(e) => setYoutubeUrl(e.target.value)}
                        className="w-full px-3.5 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 text-[13px] text-gray-700 bg-white" 
                      />
                      <p className="text-[11px] text-gray-400 mt-1">Durasi optimal: 5 - 120 menit.</p>
                    </div>

                    <div>
                      <label className="block text-[12px] font-semibold text-black mb-1.5">Kualitas Video</label>
                      <select 
                        value={videoQuality}
                        onChange={(e) => setVideoQuality(e.target.value)}
                        className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-[13px] bg-white focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500"
                      >
                        <option value="480">480p</option>
                        <option value="720">720p</option>
                        <option value="1080">1080p</option>
                      </select>
                      <p className="text-[11px] text-gray-400 mt-1">Sekali proses menghasilkan 1 klip terbaik dengan potensi viral tertinggi.</p>
                    </div>

                    <div>
                      <label className="block text-[12px] font-semibold text-black mb-1.5">Background</label>
                      <div className="border border-gray-200 rounded-xl p-2.5 flex items-center justify-between bg-white">
                        <div>
                          <span className="text-[13px] font-semibold text-gray-800 block">Blur Bergerak</span>
                          <span className="text-[10px] text-gray-400 block">Video horizontal di tengah 9:16</span>
                        </div>
                        <label className="relative inline-flex items-center cursor-pointer">
                          <input type="checkbox" className="sr-only peer" checked={landscapeBlur} onChange={() => setLandscapeBlur(!landscapeBlur)} />
                          <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                        </label>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center">
                    <button type="button" className="text-[12px] text-primary font-semibold hover:text-orange-700 flex items-center space-x-1.5 transition">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                      </svg>
                      <span>Tambah Arahan (Opsional)</span>
                    </button>
                  </div>
                </div>

                <div className="space-y-2 pt-4 border-t border-gray-200/60 mt-auto">
                  <div className="flex gap-2">
                    <button className="flex-1 bg-primary hover:bg-orange-700 text-white font-semibold py-2.5 rounded-xl text-[14px] transition shadow-sm">
                      Proses Klip
                    </button>
                  </div>
                  <div className="text-[12px] text-gray-500 mt-2">
                    Status: {status?.status || 'Idle'}
                  </div>
                </div>
              </aside>
            </div>
          )}

          {activeTab === 'history' && (
            <div className="p-6 space-y-7 bg-muted flex-1 h-[calc(100vh-53px)] overflow-auto" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
              <section className="bg-transparent min-h-[460px] flex flex-col gap-6 w-full">
                <div>
                  <h2 className="text-[20px] font-semibold text-black mb-0.5 tracking-tight">Galeri</h2>
                  <p className="text-[13px] text-gray-500">Klip yang sudah kamu simpan.</p>
                </div>
                <div className="p-12 border border-dashed border-gray-300 rounded-2xl flex flex-col items-center justify-center text-center bg-white">
                  <h3 className="text-[16px] font-semibold text-gray-700 mb-1">Galeri Kosong</h3>
                  <p className="text-[13px] text-gray-500">Belum ada klip yang disimpan. (Fitur sedang dimigrasi ke React)</p>
                </div>
              </section>
            </div>
          )}

          {activeTab === 'console' && (
            <div className="p-6 space-y-7 bg-muted flex-1 h-[calc(100vh-53px)] overflow-auto" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
              <section className="bg-transparent min-h-[460px] flex flex-col gap-5 w-full">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h2 className="text-[20px] font-semibold text-black mb-0.5 tracking-tight">Konsol</h2>
                    <p className="text-[13px] text-gray-500">Log pemrosesan sistem.</p>
                  </div>
                  <button type="button" className="rounded-xl border border-gray-200 px-4 py-2 text-[13px] font-semibold text-gray-700 hover:bg-gray-50 bg-white">
                    Clear
                  </button>
                </div>
                <div className="min-h-[360px] max-h-[70vh] overflow-auto rounded-2xl bg-[#f8fafc] border border-gray-200 p-4 font-mono text-[12px] leading-relaxed text-gray-800">
                  <p className="text-gray-400 italic">Console output akan muncul di sini... (Fitur sedang dimigrasi)</p>
                </div>
              </section>
            </div>
          )}

          {activeTab === 'settings' && (
            <div className="p-6 space-y-7 bg-muted flex-1 h-[calc(100vh-53px)] overflow-auto" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
              <section className="bg-transparent w-full max-w-4xl mx-auto pb-12 animate-in fade-in duration-300">
                <div className="border-b border-gray-100 pb-5 mb-6">
                  <h2 className="text-[22px] font-bold text-slate-900 tracking-tight">Konfigurasi Pengaturan</h2>
                  <p className="text-[14px] text-slate-500 mt-1">Kelola API key, model pemrosesan, dan pengaturan subtitle untuk KlipKlop.</p>
                </div>
                
                <div className="grid grid-cols-1 gap-4 max-w-4xl mx-auto">
                  {/* LLM Config */}
                  <div className="bg-white rounded-2xl border border-border p-6 shadow-sm space-y-5">
                    <div className="flex items-center gap-2 mb-2">
                      <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                      <h3 className="font-bold text-slate-900 text-[15px]">Core Engine</h3>
                    </div>
                    
                    <div className="space-y-4">
                      <div>
                        <label className="block text-[13px] font-bold text-slate-700 mb-1.5">Base URL / Provider</label>
                        <input 
                          type="text" 
                          placeholder="https://generativelanguage.googleapis.com/v1beta/openai" 
                          value={settings.base_url}
                          onChange={(e) => setSettings({ ...settings, base_url: e.target.value })}
                          className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all placeholder:text-slate-400" 
                        />
                      </div>

                      <div>
                        <label className="block text-[13px] font-bold text-slate-700 mb-1.5">API Key</label>
                        <input 
                          type="password" 
                          placeholder="Gemini API key" 
                          value={settings.api_key}
                          onChange={(e) => setSettings({ ...settings, api_key: e.target.value })}
                          className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all font-mono placeholder:text-slate-400" 
                        />
                      </div>

                      <div>
                        <label className="block text-[13px] font-bold text-slate-700 mb-1.5">Model LLM / Pemrosesan</label>
                        <input 
                          type="text" 
                          placeholder="gemini-2.5-flash" 
                          value={settings.model}
                          onChange={(e) => setSettings({ ...settings, model: e.target.value })}
                          className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all placeholder:text-slate-400" 
                        />
                      </div>
                    </div>
                  </div>

                  {/* Storage Config */}
                  <div className="bg-white rounded-2xl border border-border p-6 shadow-sm">
                    <div className="flex items-center gap-2 mb-4">
                      <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"></path></svg>
                      <h3 className="font-bold text-slate-900 text-[15px]">Penyimpanan</h3>
                    </div>
                    
                    <div>
                      <div className="flex justify-between items-center mb-1.5">
                        <label className="block text-[13px] font-bold text-slate-700">Folder Output</label>
                        <span className="text-[11px] text-slate-400 font-medium bg-slate-100 px-2 py-0.5 rounded-md">Opsional</span>
                      </div>
                      <input 
                        type="text" 
                        placeholder="Contoh: /Downloads/KlipKlop-Output" 
                        value={settings.output_dir}
                        onChange={(e) => setSettings({ ...settings, output_dir: e.target.value })}
                        className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all placeholder:text-slate-400" 
                      />
                    </div>
                  </div>

                  {/* Video Effects Config */}
                  <div className="bg-white rounded-2xl border border-border p-6 shadow-sm space-y-6">
                    {/* Watermark */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-11 h-11 rounded-xl bg-orange-50 flex items-center justify-center text-orange-500">
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                        </div>
                        <div>
                          <h4 className="text-[14px] font-bold text-slate-900">Watermark</h4>
                          <p className="text-[12px] text-slate-500 mt-0.5">Overlay a logo on each clip</p>
                        </div>
                      </div>
                      <button type="button" onClick={() => setEditingEffect('watermark')} className="rounded-full border border-slate-200 bg-white px-5 py-1.5 text-[12px] font-bold text-slate-700 hover:bg-slate-50 transition-all shadow-sm">
                        Edit
                      </button>
                    </div>

                    {/* Credit Text */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-11 h-11 rounded-xl bg-orange-50 flex items-center justify-center text-orange-500">
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg>
                        </div>
                        <div>
                          <h4 className="text-[14px] font-bold text-slate-900">Credit Text</h4>
                          <p className="text-[12px] text-slate-500 mt-0.5">Credit overlay on each clip</p>
                        </div>
                      </div>
                      <button type="button" onClick={() => setEditingEffect('credit')} className="rounded-full border border-slate-200 bg-white px-5 py-1.5 text-[12px] font-bold text-slate-700 hover:bg-slate-50 transition-all shadow-sm">
                        Edit
                      </button>
                    </div>

                    {/* Hook Style */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-11 h-11 rounded-xl bg-orange-50 flex items-center justify-center text-orange-500">
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01"></path></svg>
                        </div>
                        <div>
                          <h4 className="text-[14px] font-bold text-slate-900">Hook Style</h4>
                          <p className="text-[12px] text-slate-500 mt-0.5">Colors and shape of opening hook</p>
                        </div>
                      </div>
                      <button type="button" onClick={() => setEditingEffect('hook')} className="rounded-full border border-slate-200 bg-white px-5 py-1.5 text-[12px] font-bold text-slate-700 hover:bg-slate-50 transition-all shadow-sm">
                        Edit
                      </button>
                    </div>

                    {/* Background Blur */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className="w-11 h-11 rounded-xl bg-orange-50 flex items-center justify-center text-orange-500">
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path></svg>
                        </div>
                        <div>
                          <h4 className="text-[14px] font-bold text-slate-900">Background Blur</h4>
                          <p className="text-[12px] text-slate-500 mt-0.5">Horizontal video zoom blur in 9:16</p>
                        </div>
                      </div>
                      <button type="button" onClick={() => setEditingEffect('blur')} className="rounded-full border border-slate-200 bg-white px-5 py-1.5 text-[12px] font-bold text-slate-700 hover:bg-slate-50 transition-all shadow-sm">
                        Edit
                      </button>
                    </div>
                  </div>

                  {/* Social Integration */}
                  <div className="bg-white rounded-2xl border border-border p-6 shadow-sm space-y-4">
                    <div className="flex items-center gap-2 mb-2">
                      <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"></path></svg>
                      <h3 className="font-bold text-slate-900 text-[15px]">Integrasi Sosial</h3>
                    </div>

                    <div className="border border-slate-100 rounded-xl p-4 bg-slate-50/50 hover:bg-slate-50 transition-all">
                      <div className="flex items-start justify-between gap-3 mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-red-100 flex items-center justify-center text-red-500">
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M19.615 3.184c-3.604-.246-11.631-.245-15.23 0-3.897.266-4.356 2.62-4.385 8.816.029 6.185.484 8.549 4.385 8.816 3.6.245 11.626.246 15.23 0 3.897-.266 4.356-2.62 4.385-8.816-.029-6.185-.484-8.549-4.385-8.816zm-10.615 12.816v-8l8 3.993-8 4.007z"></path></svg>
                          </div>
                          <div>
                            <h4 className="text-[14px] font-bold text-slate-900">YouTube</h4>
                            <p className="text-[12px] text-slate-500 mt-0.5">Upload ke channel YouTube.</p>
                          </div>
                        </div>
                        <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-bold text-slate-500">Belum connect</span>
                      </div>
                      <button type="button" className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2 text-[13px] font-bold text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition-all shadow-sm">
                        Connect YouTube
                      </button>
                    </div>

                    <div className="border border-slate-100 rounded-xl p-4 bg-slate-50/50 hover:bg-slate-50 transition-all">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-700">
                            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M19.59 6.69a4.83 4.83 0 0 1-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 0 1-5.2 1.74 2.89 2.89 0 0 1 2.31-4.64 2.93 2.93 0 0 1 .88.13V9.4a6.84 6.84 0 0 0-1-.05A6.33 6.33 0 0 0 5 20.1a6.34 6.34 0 0 0 10.86-4.43v-7a8.16 8.16 0 0 0 4.77 1.52v-3.4a4.85 4.85 0 0 1-1-.1z"></path></svg>
                          </div>
                          <div>
                            <h4 className="text-[14px] font-bold text-slate-900">TikTok</h4>
                            <p className="text-[12px] text-slate-500 mt-0.5">API belum disambungkan.</p>
                          </div>
                        </div>
                        <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[10px] font-bold text-slate-500">Coming soon</span>
                      </div>
                    </div>
                  </div>

                  {/* Settings Grid */}
                  <div className="bg-white rounded-2xl border border-border p-2 shadow-sm flex flex-col">
                    {[
                      { title: 'Watermark', desc: 'Overlay a logo on each clip', icon: 'M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z' },
                      { title: 'Credit Text', desc: 'Credit overlay on each clip', icon: 'M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z' },
                      { title: 'Hook Style', desc: 'Colors and shape of opening hook', icon: 'M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01' },
                      { title: 'Background Blur', desc: 'Horizontal video zoom blur in 9:16', icon: 'M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4' }
                    ].map((item, idx) => (
                      <div key={idx} className="flex items-center justify-between p-4 rounded-xl hover:bg-slate-50 transition-all cursor-pointer group">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-lg bg-orange-50 flex items-center justify-center text-primary group-hover:bg-orange-100 group-hover:scale-105 transition-all">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d={item.icon}></path></svg>
                          </div>
                          <div>
                            <h4 className="text-[14px] font-bold text-slate-900">{item.title}</h4>
                            <p className="text-[12px] text-slate-500">{item.desc}</p>
                          </div>
                        </div>
                        <button type="button" className="px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-[12px] font-bold text-slate-600 group-hover:bg-slate-50 group-hover:border-slate-300 transition-all flex items-center gap-1 shadow-sm">
                          Edit
                        </button>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="border-t border-slate-200 pt-6 mt-8 flex flex-col md:flex-row items-center justify-between gap-4">
                  <div className="text-[13px] font-medium text-emerald-600 bg-emerald-50 px-4 py-2 rounded-lg border border-emerald-100 animate-in fade-in data-[state=hidden]:animate-out data-[state=hidden]:fade-out transition-all" data-state={saveMessage ? 'visible' : 'hidden'}>
                    {saveMessage}
                  </div>
                  <div className="flex items-center space-x-3 w-full md:w-auto">
                    <button 
                      onClick={handleClearApiKey}
                      type="button" 
                      className="flex-1 md:flex-none px-4 py-2.5 border border-slate-200 text-slate-700 text-[13px] font-bold rounded-xl hover:bg-slate-50 hover:border-slate-300 transition-all shadow-sm"
                    >
                      Hapus API Key
                    </button>
                    <button 
                      onClick={handleSaveSettings}
                      disabled={isSaving}
                      type="button" 
                      className="flex-1 md:flex-none px-6 py-2.5 bg-orange-600 text-white text-[13px] font-bold rounded-xl hover:bg-orange-700 transition-all shadow-sm shadow-orange-600/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {isSaving ? (
                        <>
                          <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                          Menyimpan...
                        </>
                      ) : 'Simpan Konfigurasi'}
                    </button>
                  </div>
                </div>
              </section>
            </div>
          )}
        </main>
      </div>

      {showJsonModal && (
        <div className="fixed inset-0 z-[110] bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white border border-gray-100 w-full max-w-2xl rounded-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-gray-100 p-4">
              <h2 className="text-[16px] font-semibold text-black">
                Payload JSON
              </h2>
              <button
                type="button"
                onClick={() => setShowJsonModal(false)}
                className="text-gray-400 hover:text-black text-[20px] leading-none"
              >
                ×
              </button>
            </div>
            <pre className="bg-[#f8fafc] border-t border-gray-200 p-4 text-[12px] leading-relaxed text-gray-800 overflow-auto max-h-[70vh] whitespace-pre-wrap break-all">
{JSON.stringify({
  settings: settings,
  start: {
    url: youtubeUrl,
    quality: videoQuality,
    landscape_blur: landscapeBlur,
    num_clips: 1
  }
}, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Video Effects Edit Modal */}
      {editingEffect && (
        <div className="fixed inset-0 z-[120] bg-black/50 flex items-center justify-center p-4 animate-in fade-in duration-200">
          <div className={`bg-white border border-gray-100 w-full ${['watermark', 'credit', 'blur', 'hook'].includes(editingEffect || '') ? 'max-w-4xl bg-slate-50' : 'max-w-md'} rounded-2xl overflow-hidden shadow-xl animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]`}>
            
            {/* Conditional Render for Wide vs Narrow Modals */}
            {['watermark', 'credit', 'blur', 'hook'].includes(editingEffect || '') ? (
              <div className="flex flex-col min-h-0 h-full">
                {/* Header */}
                <div className="px-8 py-6 border-b border-gray-200 bg-white flex flex-col gap-4 shrink-0">
                  <button type="button" onClick={() => setEditingEffect(null)} className="flex items-center gap-2 text-[14px] font-semibold text-slate-500 hover:text-slate-900 transition-colors w-fit">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
                    Back to Settings
                  </button>
                  <div className="flex items-start justify-between">
                    <div>
                      <h2 className="text-[22px] font-bold text-slate-900">
                        {editingEffect === 'watermark' ? 'Watermark' : 
                         editingEffect === 'credit' ? 'Credit Watermark' : 
                         editingEffect === 'blur' ? 'Background Blur' : 'Hook Style'}
                      </h2>
                      <p className="text-[13px] text-slate-500 mt-1">
                        {editingEffect === 'watermark' 
                          ? 'Overlay a logo on every clip. Drag it on the preview to position it.'
                          : editingEffect === 'credit'
                          ? 'Overlay a text credit for the source channel. Use {channel} to auto-insert the channel name.'
                          : editingEffect === 'blur'
                          ? 'Isi ruang kosong vertikal dengan video utama yang diperbesar dan diblur.'
                          : 'Ubah font, warna, bentuk, dan posisi teks pembuka video.'}
                      </p>
                    </div>
                    {/* Toggle */}
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={
                          editingEffect === 'watermark' ? settings.watermark.enabled : 
                          editingEffect === 'credit' ? settings.credit_watermark.enabled :
                          editingEffect === 'blur' ? settings.blur_background.enabled :
                          settings.hook_style.enabled
                        } 
                        onChange={(e) => {
                          if (editingEffect === 'watermark') {
                            setSettings({...settings, watermark: {...settings.watermark, enabled: e.target.checked}});
                          } else if (editingEffect === 'credit') {
                            setSettings({...settings, credit_watermark: {...settings.credit_watermark, enabled: e.target.checked}});
                          } else if (editingEffect === 'blur') {
                            setSettings({...settings, blur_background: {...settings.blur_background, enabled: e.target.checked}});
                          } else {
                            setSettings({...settings, hook_style: {...settings.hook_style, enabled: e.target.checked}});
                          }
                        }} 
                        className="sr-only peer" 
                      />
                      <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                  </div>
                </div>

                {/* 2-Panel Body */}
                <div className="p-5 grid grid-cols-1 md:grid-cols-2 gap-5 overflow-y-auto flex-1 min-h-0">
                  {/* Left Panel - Settings */}
                  <div className="space-y-4">
                    {editingEffect === 'watermark' ? (
                      <>
                        {/* Image Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-3">Image</h3>
                          <button type="button" onClick={() => {
                            const path = prompt("Masukkan path logo (Contoh: /path/logo.png):", settings.watermark.image_path);
                            if(path !== null) setSettings({...settings, watermark: {...settings.watermark, image_path: path}});
                          }} className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border-2 border-dashed border-slate-200 bg-white text-slate-700 font-semibold text-[13px] hover:bg-slate-50 hover:border-slate-300 transition-all mb-2">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path></svg>
                            Replace image
                          </button>
                          <p className="text-[12px] text-slate-400 truncate">{settings.watermark.image_path || "Belum ada gambar yang dipilih"}</p>
                        </div>

                        {/* Appearance Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100 space-y-4">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-1">Appearance</h3>
                          
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Opacity</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round(settings.watermark.opacity * 100)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.05" value={settings.watermark.opacity} onChange={(e) => setSettings({...settings, watermark: {...settings.watermark, opacity: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>

                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Size</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round((settings.watermark.scale / 2.0) * 100)}%</span>
                            </div>
                            <input type="range" min="0.1" max="2.0" step="0.05" value={settings.watermark.scale} onChange={(e) => setSettings({...settings, watermark: {...settings.watermark, scale: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>
                        </div>

                        {/* Position Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100 space-y-4">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-1">Position</h3>
                          
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Pos X</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round(settings.watermark.position_x * 100)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.01" value={settings.watermark.position_x} onChange={(e) => setSettings({...settings, watermark: {...settings.watermark, position_x: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>

                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Pos Y</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round(settings.watermark.position_y * 100)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.01" value={settings.watermark.position_y} onChange={(e) => setSettings({...settings, watermark: {...settings.watermark, position_y: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>
                        </div>
                      </>
                    ) : editingEffect === 'blur' ? (
                      <>
                        {/* Adjustments Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100 space-y-5">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-1">Adjustments</h3>
                          
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Video Scale</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round((settings.blur_background.scale || 1.0) * 100)}%</span>
                            </div>
                            <input type="range" min="0.5" max="1.5" step="0.01" value={settings.blur_background.scale || 1.0} onChange={(e) => setSettings({...settings, blur_background: {...settings.blur_background, scale: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                            <p className="text-[11px] text-slate-400 leading-relaxed mt-1">Atur ukuran video horizontal utama di tengah. Semakin besar, semakin memakan area background blur.</p>
                          </div>

                          <div className="space-y-2 pt-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Blur Intensity</label>
                              <span className="text-[12px] font-medium text-slate-400">{settings.blur_background.strength}</span>
                            </div>
                            <input type="range" min="5" max="50" step="1" value={settings.blur_background.strength} onChange={(e) => setSettings({...settings, blur_background: {...settings.blur_background, strength: parseInt(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>
                        </div>
                      </>
                    ) : editingEffect === 'hook' ? (
                      <>
                        {/* Font Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100 space-y-4">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-1">Font</h3>
                          
                          <div className="space-y-2">
                            <select value={settings.hook_style.font_family || 'Capo Sfogliato'} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, font_family: e.target.value}})} className="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-[13px] font-medium focus:outline-none focus:border-primary bg-white appearance-none cursor-pointer shadow-sm">
                              <option value="Capo Sfogliato">Capo Sfogliato</option>
                              <option value="Super Hockey">Super Hockey</option>
                              <option value="Super Kidpop">Super Kidpop</option>
                              <option value="Super Starfish">Super Starfish</option>
                              <option value="Inter">Inter</option>
                            </select>
                          </div>

                          <div className="space-y-2 pt-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Font Size</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round((settings.hook_style.font_size || 0.05) * 1000)}%</span>
                            </div>
                            <input type="range" min="0.01" max="0.1" step="0.005" value={settings.hook_style.font_size} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, font_size: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>
                        </div>

                        {/* Colors Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100 space-y-4">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-1">Colors</h3>
                          
                          <div className="space-y-3">
                            <div className="flex items-center gap-3">
                              <label className="text-[12px] font-semibold text-slate-600 w-20">Text</label>
                              <input type="color" value={settings.hook_style.text_color} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, text_color: e.target.value}})} className="w-8 h-8 rounded cursor-pointer border border-slate-200 p-0.5 bg-white shrink-0" />
                              <input type="text" value={settings.hook_style.text_color.toUpperCase()} readOnly className="flex-1 px-3 py-1.5 border border-gray-200 rounded-lg text-[12px] font-medium bg-slate-50 text-slate-600 focus:outline-none" />
                            </div>
                            <div className="flex items-center gap-3">
                              <label className="text-[12px] font-semibold text-slate-600 w-20">Background</label>
                              <input type="color" value={settings.hook_style.background_color || settings.hook_style.bg_color} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, background_color: e.target.value, bg_color: e.target.value}})} className="w-8 h-8 rounded cursor-pointer border border-slate-200 p-0.5 bg-white shrink-0" />
                              <input type="text" value={(settings.hook_style.background_color || settings.hook_style.bg_color || '#ffffff').toUpperCase()} readOnly className="flex-1 px-3 py-1.5 border border-gray-200 rounded-lg text-[12px] font-medium bg-slate-50 text-slate-600 focus:outline-none" />
                            </div>
                          </div>
                        </div>

                        {/* Shape & Position Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100 space-y-4">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-1">Shape & Position</h3>
                          
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Shape</label>
                            </div>
                            <select value={settings.hook_style.shape || 'rectangle'} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, shape: e.target.value}})} className="w-full px-3 py-2 border border-gray-200 rounded-lg text-[13px] font-medium focus:outline-none focus:border-primary bg-white appearance-none cursor-pointer shadow-sm">
                              <option value="rectangle">Rectangle</option>
                              <option value="pill">Pill (Full Rounded)</option>
                            </select>
                          </div>

                          <div className="space-y-2 pt-1">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Corner Radius</label>
                              <span className="text-[12px] font-medium text-slate-400">{settings.hook_style.corner_radius}px</span>
                            </div>
                            <input type="range" min="0" max="100" step="1" value={settings.hook_style.corner_radius} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, corner_radius: parseInt(e.target.value)}})} className={`w-full h-1.5 rounded-lg appearance-none cursor-pointer ${settings.hook_style.shape === 'pill' ? 'bg-slate-200 accent-slate-400 opacity-50' : 'bg-orange-100 accent-primary'}`} disabled={settings.hook_style.shape === 'pill'} />
                          </div>

                          <div className="space-y-2 pt-1">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Pos X</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round(settings.hook_style.position_x * 100)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.01" value={settings.hook_style.position_x} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, position_x: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>

                          <div className="space-y-2 pt-1">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Pos Y</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round(settings.hook_style.position_y * 100)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.01" value={settings.hook_style.position_y} onChange={(e) => setSettings({...settings, hook_style: {...settings.hook_style, position_y: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>
                        </div>
                      </>
                    ) : (
                      <>
                        {/* Text Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-3">Text</h3>
                          <input type="text" value={settings.credit_watermark.text} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, text: e.target.value}})} className="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-[13px] font-medium focus:outline-none focus:border-primary mb-2" />
                          <p className="text-[12px] text-slate-400">{`{channel}`} will be replaced with the YouTube channel name.</p>
                        </div>

                        {/* Appearance Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100 space-y-5">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-1">Appearance</h3>
                          
                          <div className="space-y-2">
                            <label className="text-[12px] font-semibold text-slate-600 block">Color</label>
                            <div className="flex items-center gap-3">
                              <input type="color" value={settings.credit_watermark.color} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, color: e.target.value}})} className="w-10 h-10 rounded cursor-pointer border border-slate-200 p-0.5 bg-white" />
                              <input type="text" value={settings.credit_watermark.color.toUpperCase()} readOnly className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-[13px] font-medium bg-slate-50 text-slate-600 focus:outline-none" />
                            </div>
                          </div>

                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Font Size</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round(settings.credit_watermark.size * 320)}px</span>
                            </div>
                            <input type="range" min="0.01" max="0.1" step="0.001" value={settings.credit_watermark.size} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, size: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>

                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Transparency</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round((1 - settings.credit_watermark.opacity) * 100)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.05" value={1 - settings.credit_watermark.opacity} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, opacity: 1 - parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>
                        </div>

                        {/* Position Card */}
                        <div className="bg-white rounded-xl p-4 shadow-sm border border-slate-100 space-y-4">
                          <h3 className="text-[14px] font-bold text-slate-900 mb-1">Position</h3>
                          
                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Pos X</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round(settings.credit_watermark.position_x * 100)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.01" value={settings.credit_watermark.position_x} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, position_x: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>

                          <div className="space-y-2">
                            <div className="flex items-center justify-between">
                              <label className="text-[12px] font-semibold text-slate-600">Pos Y</label>
                              <span className="text-[12px] font-medium text-slate-400">{Math.round(settings.credit_watermark.position_y * 100)}%</span>
                            </div>
                            <input type="range" min="0" max="1" step="0.01" value={settings.credit_watermark.position_y} onChange={(e) => setSettings({...settings, credit_watermark: {...settings.credit_watermark, position_y: parseFloat(e.target.value)}})} className="w-full h-1.5 bg-orange-100 rounded-lg appearance-none cursor-pointer accent-primary" />
                          </div>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Right Panel - Preview */}
                  <div className="flex h-full items-center justify-center gap-6 relative">
                    <div className="bg-[#0f172a] rounded-2xl relative overflow-hidden flex items-center justify-center shadow-inner" style={{ aspectRatio: '9/16', height: '100%', maxHeight: '100%' }}>
                      {/* Placeholder Video Text */}
                      {editingEffect !== 'blur' && <span className="text-slate-500 font-medium text-[13px]">9:16 Video</span>}

                      {/* Blur Effect Preview */}
                      {editingEffect === 'blur' && (
                        <>
                          {/* Blurred Background */}
                          <div 
                            className="absolute inset-0 bg-cover bg-center transition-all duration-300"
                            style={{
                              backgroundImage: 'url("https://images.unsplash.com/photo-1534438327276-14e5300c3a48?q=80&w=600&auto=format&fit=crop")',
                              filter: settings.blur_background.enabled ? `blur(${settings.blur_background.strength / 2}px)` : 'none',
                              transform: `scale(${settings.blur_background.zoom || 1.2})`,
                              opacity: settings.blur_background.enabled ? 0.6 : 0.2
                            }}
                          />
                          
                          {/* Center Horizontal Video */}
                          <div 
                            className="relative shadow-2xl flex items-center justify-center overflow-hidden transition-all duration-300 ring-1 ring-white/10"
                            style={{
                              width: '100%',
                              aspectRatio: '16/9',
                              transform: `scale(${settings.blur_background.scale || 1.0})`,
                              zIndex: 10,
                              opacity: settings.blur_background.enabled ? 1 : 0.5
                            }}
                          >
                            <div 
                              className="absolute inset-0 bg-cover bg-center"
                              style={{
                                backgroundImage: 'url("https://images.unsplash.com/photo-1534438327276-14e5300c3a48?q=80&w=600&auto=format&fit=crop")'
                              }}
                            />
                            {/* Play Button Icon */}
                            <div className="absolute inset-0 bg-black/20 flex items-center justify-center">
                              <div className="w-10 h-10 rounded-full bg-black/50 backdrop-blur-sm flex items-center justify-center text-white/90">
                                <svg className="w-4 h-4 ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                              </div>
                            </div>
                          </div>
                        </>
                      )}
                      
                      {/* Watermark/Credit Overlay Element */}
                      {editingEffect === 'watermark' ? (
                        <div 
                          className={`absolute flex items-center justify-center cursor-move transition-opacity ${settings.watermark.enabled ? 'border border-dashed border-white/40' : 'border border-dashed border-white/10 grayscale opacity-50'}`}
                          style={{
                            left: `${settings.watermark.position_x * 100}%`,
                            top: `${settings.watermark.position_y * 100}%`,
                            transform: 'translate(-50%, -50%)',
                            opacity: settings.watermark.enabled ? settings.watermark.opacity : (settings.watermark.opacity * 0.5),
                            width: `${settings.watermark.scale * 100}px`,
                            height: `${settings.watermark.scale * 100}px`,
                            backgroundImage: settings.watermark.image_path ? `url(${settings.watermark.image_path})` : 'none',
                            backgroundSize: 'contain',
                            backgroundRepeat: 'no-repeat',
                            backgroundPosition: 'center',
                            backgroundColor: settings.watermark.image_path ? 'transparent' : 'rgba(255,255,255,0.1)',
                            borderRadius: '8px'
                          }}
                        >
                          {!settings.watermark.image_path && (
                            <svg className="w-8 h-8 text-white/50" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                          )}
                        </div>
                      ) : editingEffect === 'credit' ? (
                        <div 
                          className={`absolute whitespace-nowrap cursor-move transition-opacity ${settings.credit_watermark.enabled ? '' : 'opacity-50'}`}
                          style={{
                            left: `${settings.credit_watermark.position_x * 100}%`,
                            top: `${settings.credit_watermark.position_y * 100}%`,
                            transform: 'translate(-50%, -50%)',
                            opacity: settings.credit_watermark.enabled ? settings.credit_watermark.opacity : (settings.credit_watermark.opacity * 0.5),
                            color: settings.credit_watermark.color,
                            fontSize: `${Math.max(10, settings.credit_watermark.size * 320)}px`,
                            fontWeight: '600',
                            textShadow: '0px 1px 3px rgba(0,0,0,0.5)'
                          }}
                        >
                          {settings.credit_watermark.text}
                        </div>
                      ) : editingEffect === 'hook' ? (
                        <div 
                          className={`absolute flex items-center justify-center cursor-move transition-all ${settings.hook_style.enabled ? '' : 'opacity-50 grayscale'}`}
                          style={{
                            left: `${settings.hook_style.position_x * 100}%`,
                            top: `${settings.hook_style.position_y * 100}%`,
                            transform: 'translate(-50%, -50%)',
                            opacity: settings.hook_style.enabled ? 1 : 0.5,
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
                        >
                          WAIT FOR IT!
                        </div>
                      ) : null}
                    </div>
                    
                    {/* Vertical Title on the Right */}
                    <h3 
                      className="text-[28px] font-black text-slate-300 opacity-70 uppercase tracking-widest whitespace-nowrap"
                      style={{ writingMode: 'vertical-rl' }}
                    >
                      Preview (9:16)
                    </h3>
                  </div>
                </div>

                {/* Bottom Save Button Container */}
                <div className="p-5 bg-white border-t border-slate-200 shrink-0">
                  <button type="button" onClick={() => setEditingEffect(null)} className="w-full bg-primary hover:bg-orange-600 text-white font-bold py-3.5 px-4 rounded-xl text-[14px] flex items-center justify-center gap-2 shadow-sm transition-all">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"></path></svg>
                    Save {editingEffect === 'watermark' ? 'watermark' : editingEffect === 'credit' ? 'credit watermark' : editingEffect === 'blur' ? 'background blur' : 'hook style'} settings
                  </button>
                </div>
              </div>
            ) : null}

          </div>
        </div>
      )}
    </div>
  );
}
