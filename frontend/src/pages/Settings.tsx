import { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import { api } from '@/lib/api';

type ApiCheckState = 'idle' | 'checking' | 'ok' | 'error';
type ProviderName = 'highlight_finder' | 'caption_maker';

export default function Settings() {
  const { settings, setSettings } = useOutletContext<any>();
  const [isSaving, setIsSaving] = useState(false);
  const [clearingProvider, setClearingProvider] = useState<ProviderName | null>(null);
  const [saveMessage, setSaveMessage] = useState('');
  const [youtubeConnected, setYoutubeConnected] = useState(false);
  const [geminiCheckState, setGeminiCheckState] = useState<ApiCheckState>('idle');
  const [geminiCheckMessage, setGeminiCheckMessage] = useState('');
  const [groqCheckState, setGroqCheckState] = useState<ApiCheckState>('idle');
  const [groqCheckMessage, setGroqCheckMessage] = useState('');

  useEffect(() => {
    api('/api/social/youtube/oauth-status').then((res: any) => {
      setYoutubeConnected(res.connected);
    }).catch(() => {});
  }, []);

  const applySavedSettings = (savedSettings: any) => {
    const { api_key: _apiKey, caption_api_key: _captionApiKey, ...safeSettings } = savedSettings || {};
    void _apiKey;
    void _captionApiKey;
    setSettings((prev: any) => ({
      ...prev,
      ...safeSettings,
      api_key: '',
      caption_api_key: '',
    }));
  };

  const showSaveMessage = (message: string) => {
    setSaveMessage(message);
    setTimeout(() => setSaveMessage(''), 3000);
  };

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
      const res = await api('/api/settings', {
        method: 'POST',
        body: JSON.stringify(settings)
      });
      applySavedSettings(res.settings);
      showSaveMessage('Konfigurasi berhasil disimpan.');
    } catch {
      showSaveMessage('Gagal menyimpan konfigurasi.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCheckGemini = async () => {
    setGeminiCheckState('checking');
    setGeminiCheckMessage('');
    try {
      const res = await api('/api/check-api-key', {
        method: 'POST',
        body: JSON.stringify({
          provider_name: 'highlight_finder',
          base_url: settings.base_url,
          api_key: settings.api_key,
          model: settings.model,
        }),
      });
      setGeminiCheckState('ok');
      setGeminiCheckMessage(res.message || 'Gemini valid');
    } catch (e: any) {
      setGeminiCheckState('error');
      setGeminiCheckMessage(e.message || 'Gemini tidak valid');
    }
  };

  const handleCheckGroq = async () => {
    setGroqCheckState('checking');
    setGroqCheckMessage('');
    try {
      const res = await api('/api/check-api-key', {
        method: 'POST',
        body: JSON.stringify({
          provider_name: 'caption_maker',
          base_url: settings.caption_base_url,
          api_key: settings.caption_api_key,
          model: settings.caption_model,
        }),
      });
      setGroqCheckState('ok');
      setGroqCheckMessage(res.message || 'Groq valid');
    } catch (e: any) {
      setGroqCheckState('error');
      setGroqCheckMessage(e.message || 'Groq tidak valid');
    }
  };

  const handleClearProvider = async (providerName: ProviderName) => {
    setClearingProvider(providerName);
    setSaveMessage('');
    try {
      const clearSetting = providerName === 'highlight_finder'
        ? { clear_highlight_api_key: true }
        : { clear_caption_api_key: true };
      const res = await api('/api/settings', {
        method: 'POST',
        body: JSON.stringify({ ...settings, api_key: '', caption_api_key: '', ...clearSetting }),
      });
      applySavedSettings(res.settings);
      if (providerName === 'highlight_finder') {
        setGeminiCheckState('idle');
        setGeminiCheckMessage('');
        showSaveMessage('Gemini API key berhasil dihapus.');
      } else {
        setGroqCheckState('idle');
        setGroqCheckMessage('');
        showSaveMessage('Groq API key berhasil dihapus.');
      }
    } catch {
      showSaveMessage('Gagal menghapus API key.');
    } finally {
      setClearingProvider(null);
    }
  };

  return (
    <div className="p-6 space-y-7 bg-muted flex-1 h-[calc(100vh-53px)] overflow-auto" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
      <section className="bg-transparent w-full max-w-4xl mx-auto pb-12 animate-in fade-in duration-300">
        <div className="border-b border-gray-100 pb-5 mb-6">
          <h2 className="text-[22px] font-bold text-slate-900 tracking-tight">Konfigurasi Pengaturan</h2>
          <p className="text-[14px] text-slate-500 mt-1">Kelola API key, model pemrosesan, dan pengaturan subtitle untuk KlipKlop.</p>
        </div>
        
        <div className="grid grid-cols-1 gap-4 max-w-4xl mx-auto">
          <div className="bg-white rounded-2xl border border-border p-6 shadow-sm space-y-5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                <h3 className="font-bold text-slate-900 text-[15px]">Highlight Finder — Gemini</h3>
              </div>
              {settings.api_key_saved && (
                <span className="shrink-0 text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-100">API key tersimpan</span>
              )}
            </div>
            
            <div className="space-y-4">
              <div>
                <label htmlFor="gemini-base-url" className="block text-[13px] font-bold text-slate-700 mb-1.5">Base URL</label>
                <input
                  id="gemini-base-url"
                  type="url"
                  placeholder="https://generativelanguage.googleapis.com/v1beta/openai"
                  value={settings.base_url}
                  onChange={(e) => setSettings({ ...settings, base_url: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all placeholder:text-slate-500"
                />
              </div>

              <div>
                <label htmlFor="gemini-api-key" className="block text-[13px] font-bold text-slate-700 mb-1.5">Gemini API Key</label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    id="gemini-api-key"
                    type="password"
                    autoComplete="new-password"
                    placeholder={settings.api_key_saved ? 'Kosongkan untuk mempertahankan key tersimpan' : 'Masukkan Gemini API key'}
                    value={settings.api_key}
                    onChange={(e) => setSettings({ ...settings, api_key: e.target.value })}
                    aria-describedby={geminiCheckMessage ? 'gemini-check-result' : undefined}
                    className="min-w-0 flex-1 px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all font-mono placeholder:text-slate-500"
                  />
                  <button
                    type="button"
                    onClick={handleCheckGemini}
                    disabled={geminiCheckState === 'checking'}
                    className="px-4 py-2.5 rounded-xl border border-primary/30 bg-primary/10 text-primary text-[13px] font-bold hover:bg-primary/15 focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-60 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                  >
                    {geminiCheckState === 'checking' ? 'Memeriksa...' : 'Check Gemini'}
                  </button>
                </div>
                {geminiCheckMessage && (
                  <p id="gemini-check-result" role={geminiCheckState === 'error' ? 'alert' : 'status'} className={`mt-2 text-[12px] font-medium ${geminiCheckState === 'ok' ? 'text-emerald-600' : 'text-red-600'}`}>
                    {geminiCheckMessage}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="gemini-model" className="block text-[13px] font-bold text-slate-700 mb-1.5">Model</label>
                <input
                  id="gemini-model"
                  type="text"
                  placeholder="gemini-2.5-flash"
                  value={settings.model}
                  onChange={(e) => setSettings({ ...settings, model: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all placeholder:text-slate-500"
                />
              </div>

              <div className="flex justify-end pt-1">
                <button
                  type="button"
                  onClick={() => handleClearProvider('highlight_finder')}
                  disabled={!settings.api_key_saved || clearingProvider !== null}
                  className="px-4 py-2.5 border border-red-200 text-red-600 text-[13px] font-bold rounded-xl hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-200 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  {clearingProvider === 'highlight_finder' ? 'Menghapus...' : 'Hapus Gemini API Key'}
                </button>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-border p-6 shadow-sm space-y-5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v3m0 12v3M5.64 5.64l2.12 2.12m8.48 8.48 2.12 2.12M3 12h3m12 0h3M5.64 18.36l2.12-2.12m8.48-8.48 2.12-2.12"></path><circle cx="12" cy="12" r="3" strokeWidth="2"></circle></svg>
                <h3 className="font-bold text-slate-900 text-[15px]">Caption Maker — Groq</h3>
              </div>
              {settings.caption_key_saved && (
                <span className="shrink-0 text-[11px] font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-lg border border-emerald-100">API key tersimpan</span>
              )}
            </div>

            <div className="space-y-4">
              <div>
                <label htmlFor="groq-base-url" className="block text-[13px] font-bold text-slate-700 mb-1.5">Base URL</label>
                <input
                  id="groq-base-url"
                  type="url"
                  placeholder="https://api.groq.com/openai/v1"
                  value={settings.caption_base_url}
                  onChange={(e) => setSettings({ ...settings, caption_base_url: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all placeholder:text-slate-500"
                />
              </div>

              <div>
                <label htmlFor="groq-api-key" className="block text-[13px] font-bold text-slate-700 mb-1.5">Groq API Key</label>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    id="groq-api-key"
                    type="password"
                    autoComplete="new-password"
                    placeholder={settings.caption_key_saved ? 'Kosongkan untuk mempertahankan key tersimpan' : 'Masukkan Groq API key'}
                    value={settings.caption_api_key}
                    onChange={(e) => setSettings({ ...settings, caption_api_key: e.target.value })}
                    aria-describedby={groqCheckMessage ? 'groq-check-result' : undefined}
                    className="min-w-0 flex-1 px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all font-mono placeholder:text-slate-500"
                  />
                  <button
                    type="button"
                    onClick={handleCheckGroq}
                    disabled={groqCheckState === 'checking'}
                    className="px-4 py-2.5 rounded-xl border border-primary/30 bg-primary/10 text-primary text-[13px] font-bold hover:bg-primary/15 focus:outline-none focus:ring-2 focus:ring-primary/30 disabled:opacity-60 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
                  >
                    {groqCheckState === 'checking' ? 'Memeriksa...' : 'Check Groq'}
                  </button>
                </div>
                {groqCheckMessage && (
                  <p id="groq-check-result" role={groqCheckState === 'error' ? 'alert' : 'status'} className={`mt-2 text-[12px] font-medium ${groqCheckState === 'ok' ? 'text-emerald-600' : 'text-red-600'}`}>
                    {groqCheckMessage}
                  </p>
                )}
              </div>

              <div>
                <label htmlFor="groq-model" className="block text-[13px] font-bold text-slate-700 mb-1.5">Transcription Model</label>
                <input
                  id="groq-model"
                  type="text"
                  placeholder="whisper-large-v3-turbo"
                  value={settings.caption_model}
                  onChange={(e) => setSettings({ ...settings, caption_model: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-[13px] text-slate-900 bg-slate-50/50 transition-all placeholder:text-slate-500"
                />
              </div>

              <div className="flex justify-end pt-1">
                <button
                  type="button"
                  onClick={() => handleClearProvider('caption_maker')}
                  disabled={!settings.caption_key_saved || clearingProvider !== null}
                  className="px-4 py-2.5 border border-red-200 text-red-600 text-[13px] font-bold rounded-xl hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-200 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
                >
                  {clearingProvider === 'caption_maker' ? 'Menghapus...' : 'Hapus Groq API Key'}
                </button>
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
          <div role="status" aria-live="polite" className="text-[13px] font-medium text-emerald-600 bg-emerald-50 px-4 py-2 rounded-lg border border-emerald-100 animate-in fade-in data-[state=hidden]:animate-out data-[state=hidden]:fade-out transition-all" data-state={saveMessage ? 'visible' : 'hidden'}>
            {saveMessage}
          </div>
          <button
            onClick={handleSaveSettings}
            disabled={isSaving || clearingProvider !== null}
            type="button"
            className="w-full md:w-auto px-6 py-2.5 bg-orange-600 text-white text-[13px] font-bold rounded-xl hover:bg-orange-700 focus:outline-none focus:ring-2 focus:ring-orange-300 transition-all shadow-sm shadow-orange-600/20 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            {isSaving ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                Menyimpan...
              </>
            ) : 'Simpan Pengaturan'}
          </button>
        </div>
      </section>
    </div>
  );
}
