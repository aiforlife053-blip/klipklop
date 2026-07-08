import { useState, useEffect } from 'react';
import { useOutletContext, useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';

export default function Settings() {
  const { settings, setSettings } = useOutletContext<any>();
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  const [youtubeConnected, setYoutubeConnected] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    // Check YT connection status
    api('/api/social/youtube/oauth-status').then((res: any) => {
      setYoutubeConnected(res.connected);
    }).catch(() => {});
  }, []);

  const handleConnectYoutube = async () => {
    try {
      const res = await api('/api/social/youtube/connect', { method: 'POST' });
      if (res.auth_url) {
        window.open(res.auth_url, '_blank');
        alert('Selesaikan login di tab baru, lalu refresh halaman ini.');
      } else {
        alert('Gagal mendapatkan URL login YouTube.');
      }
    } catch (e: any) {
      alert('Error: ' + e.message);
    }
  };

  const handleDisconnectYoutube = async () => {
    try {
      await api('/api/social/youtube/disconnect', { method: 'POST' });
      setYoutubeConnected(false);
      alert('YouTube berhasil diputuskan.');
    } catch (e: any) {
      alert('Error: ' + e.message);
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
    setSettings((prev: any) => ({ ...prev, api_key: '' }));
  };

  return (
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

          {/* Social Auth */}
          <div className="bg-white rounded-2xl border border-border p-6 shadow-sm space-y-5">
            <div className="flex items-center gap-2 mb-2">
              <svg className="w-5 h-5 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
              <h3 className="font-bold text-slate-900 text-[15px]">Koneksi Sosial Media</h3>
            </div>
            
            <p className="text-[13px] text-slate-500 mb-4">Hubungkan akun sosial media untuk mempublikasikan klip langsung dari dashboard.</p>
            
            <div className="space-y-3">
              {/* YouTube */}
              <div className="flex items-center justify-between p-4 border border-slate-100 rounded-xl bg-slate-50/50">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-red-100 text-red-600 flex items-center justify-center rounded-full">
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.547 12 3.547 12 3.547s-7.505 0-9.377.503A3.014 3.014 0 0 0 .501 6.186C0 8.07 0 12 0 12s0 3.93.501 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>
                  </div>
                  <div>
                    <p className="text-[13px] font-bold text-slate-900">YouTube</p>
                    <p className="text-[11px] text-slate-500">{youtubeConnected ? 'Tersambung (Siap untuk auto-upload)' : 'Belum tersambung'}</p>
                  </div>
                </div>
                {youtubeConnected ? (
                  <button onClick={handleDisconnectYoutube} className="px-4 py-2 bg-red-50 hover:bg-red-100 text-red-600 font-bold rounded-lg text-[12px] transition">
                    Putuskan
                  </button>
                ) : (
                  <button onClick={handleConnectYoutube} className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white font-bold rounded-lg text-[12px] transition">
                    Sambungkan
                  </button>
                )}
              </div>

              {/* TikTok */}
              <div className="flex items-center justify-between p-4 border border-slate-100 rounded-xl bg-slate-50/50 opacity-60">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-black text-white flex items-center justify-center rounded-full">
                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 448 512"><path d="M448,209.91a210.06,210.06,0,0,1-122.77-39.25V349.38A162.55,162.55,0,1,1,185,188.31V278.2a74.62,74.62,0,1,0,52.23,71.18V0l88,0a121.18,121.18,0,0,0,1.86,22.17h0A122.18,122.18,0,0,0,381,102.39a121.43,121.43,0,0,0,67,20.14Z"/></svg>
                  </div>
                  <div>
                    <p className="text-[13px] font-bold text-slate-900">TikTok</p>
                    <p className="text-[11px] text-slate-500">Coming soon (Segera Hadir)</p>
                  </div>
                </div>
                <button disabled className="px-4 py-2 bg-slate-200 text-slate-400 font-bold rounded-lg text-[12px] cursor-not-allowed">
                  Sambungkan
                </button>
              </div>
            </div>
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
              ) : 'Simpan Pengaturan'}
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
