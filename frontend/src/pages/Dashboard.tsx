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

  const [settings, setSettings] = useState({
    base_url: '',
    api_key: '',
    model: '',
    output_dir: ''
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
          setSettings({
            base_url: data.base_url || '',
            api_key: data.api_key || '',
            model: data.model || '',
            output_dir: data.output_dir || ''
          });
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
    </div>
  );
}
