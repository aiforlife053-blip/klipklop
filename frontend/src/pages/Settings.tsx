import { useState, useEffect } from 'react';
import { useOutletContext } from 'react-router-dom';
import { api } from '@/lib/api';

type ApiCheckState = 'idle' | 'checking' | 'ok' | 'error';
type ProviderName = 'highlight_finder' | 'caption_maker' | 'hook_maker';

const settingsPayload = (settings: any) => ({
  base_url: settings.base_url,
  model: settings.model,
  caption_base_url: settings.caption_base_url,
  caption_model: settings.caption_model,
  hook_model: settings.hook_model,
  hook_voice: settings.hook_voice,
  output_dir: settings.output_dir,
  ...(settings.api_key ? { api_key: settings.api_key } : {}),
  ...(settings.caption_api_key ? { caption_api_key: settings.caption_api_key } : {}),
  ...(settings.hook_api_key ? { hook_api_key: settings.hook_api_key } : {}),
});

export default function Settings() {
  const { settings, setSettings } = useOutletContext<any>();
  const [isSaving, setIsSaving] = useState(false);
  const [isUploadingCookies, setIsUploadingCookies] = useState(false);
  const [clearingProvider, setClearingProvider] = useState<ProviderName | null>(null);
  const [saveMessage, setSaveMessage] = useState('');
  const [saveError, setSaveError] = useState(false);
  const [youtubeConnected, setYoutubeConnected] = useState(false);
  const [youtubeChannelTitle, setYoutubeChannelTitle] = useState('');
  const [geminiCheckState, setGeminiCheckState] = useState<ApiCheckState>('idle');
  const [geminiCheckMessage, setGeminiCheckMessage] = useState('');
  const [groqCheckState, setGroqCheckState] = useState<ApiCheckState>('idle');
  const [groqCheckMessage, setGroqCheckMessage] = useState('');

  useEffect(() => {
    api('/api/social/status').then((res: any) => {
      setYoutubeConnected(res.connected);
      setYoutubeChannelTitle(res.channel_title || '');
    }).catch(() => {});
  }, []);

  const applySavedSettings = (savedSettings: any) => {
    const { api_key: _apiKey, caption_api_key: _captionApiKey, hook_api_key: _hookApiKey, ...safeSettings } = savedSettings || {};
    void _apiKey;
    void _captionApiKey;
    void _hookApiKey;
    setSettings((prev: any) => ({
      ...prev,
      ...safeSettings,
      api_key: '',
      caption_api_key: '',
      hook_api_key: '',
    }));
  };

  const showSaveMessage = (message: string, isError = false) => {
    setSaveError(isError);
    setSaveMessage(message);
    setTimeout(() => setSaveMessage(''), 3000);
  };

  const handleConnectYoutube = async () => {
    const popup = window.open('', '_blank');
    if (!popup) {
      alert('Error: Popup diblokir browser');
      return;
    }
    popup.opener = null;
    try {
      const res = await api('/api/social/youtube/connect', { method: 'POST' });
      if (res.auth_url) {
        const authUrl = new URL(res.auth_url);
        if (authUrl.protocol !== 'https:') throw new Error('URL login YouTube tidak aman');
        popup.location.replace(authUrl.href);
        alert('Selesaikan login di tab baru, lalu refresh halaman ini.');
      } else {
        throw new Error('Gagal mendapatkan URL login YouTube');
      }
    } catch (e: any) {
      popup.close();
      alert('Error: ' + e.message);
    }
  };

  const handleDisconnectYoutube = async () => {
    try {
      await api('/api/social/youtube/disconnect', { method: 'POST' });
      setYoutubeConnected(false);
      setYoutubeChannelTitle('');
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
        body: JSON.stringify(settingsPayload(settings))
      });
      applySavedSettings(res.settings);
      showSaveMessage('Konfigurasi berhasil disimpan.');
    } catch {
      showSaveMessage('Gagal menyimpan konfigurasi.', true);
    } finally {
      setIsSaving(false);
    }
  };

  const handleCookiesUpload = async (file?: File) => {
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      showSaveMessage('File cookies.txt maksimal 10 MB.', true);
      return;
    }
    setIsUploadingCookies(true);
    try {
      const res = await api('/api/cookies', {
        method: 'POST',
        body: JSON.stringify({ content: await file.text() }),
      });
      if (res.status !== 'saved') throw new Error(res.message || 'Upload gagal');
      setSettings((prev: any) => ({ ...prev, cookie_exists: true, cookies: res.cookies }));
      showSaveMessage('cookies.txt berhasil disimpan untuk akun ini.');
    } catch (e: any) {
      showSaveMessage(e.message || 'Gagal mengunggah cookies.txt.', true);
    } finally {
      setIsUploadingCookies(false);
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
        : providerName === 'caption_maker'
          ? { clear_caption_api_key: true }
          : { clear_hook_api_key: true };
      const res = await api('/api/settings', {
        method: 'POST',
        body: JSON.stringify({ ...settingsPayload(settings), api_key: undefined, caption_api_key: undefined, hook_api_key: undefined, ...clearSetting }),
      });
      applySavedSettings(res.settings);
      if (providerName === 'highlight_finder') {
        setGeminiCheckState('idle');
        setGeminiCheckMessage('');
        showSaveMessage('Gemini API key berhasil dihapus.');
      } else if (providerName === 'caption_maker') {
        setGroqCheckState('idle');
        setGroqCheckMessage('');
        showSaveMessage('Groq API key berhasil dihapus.');
      } else {
        showSaveMessage('Gemini TTS API key berhasil dihapus.');
      }
    } catch {
      showSaveMessage('Gagal menghapus API key.', true);
    } finally {
      setClearingProvider(null);
    }
  };

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-6 py-10 min-h-[calc(100vh-53px)]">
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium uppercase tracking-widest text-primary">Pengaturan</p>
        <h1 className="font-display text-3xl font-bold tracking-tight md:text-4xl">Konfigurasi Pengaturan</h1>
        <p className="leading-relaxed text-muted">Kelola API key, model pemrosesan, dan pengaturan subtitle untuk KlipKlop.</p>
      </div>

      <form className="flex flex-col gap-6" onSubmit={(e) => { e.preventDefault(); handleSaveSettings(); }}>
        {/* Core Engine - Gemini */}
        <section className="flex flex-col gap-5 rounded-2xl border border-line bg-card p-6">
          <div className="flex items-center gap-3 justify-between">
            <div className="flex items-center gap-3">
              <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/></svg>
              </span>
              <h2 className="font-display text-lg font-bold">Highlight Finder (Gemini)</h2>
            </div>
            {settings.api_key_saved && (
              <span className="shrink-0 text-[11px] font-bold text-emerald-500 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20">Tersimpan</span>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="gemini-base-url" className="text-sm font-medium">Base URL</label>
            <input id="gemini-base-url" type="url" placeholder="https://generativelanguage.googleapis.com/v1beta/openai"
              value={settings.base_url} onChange={(e) => { setGeminiCheckState('idle'); setGeminiCheckMessage(''); setSettings({ ...settings, base_url: e.target.value }); }}
              className="h-11 w-full rounded-xl border border-field bg-secondary px-4 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="gemini-api-key" className="text-sm font-medium">API Key</label>
            <div className="flex gap-3">
              <input id="gemini-api-key" type="password" autoComplete="new-password"
                placeholder={settings.api_key_saved ? 'Kosongkan untuk mempertahankan key tersimpan' : 'Gemini API key'}
                 value={settings.api_key} onChange={(e) => { setGeminiCheckState('idle'); setGeminiCheckMessage(''); setSettings({ ...settings, api_key: e.target.value }); }}
                className="h-11 min-w-0 flex-1 rounded-xl border border-field bg-secondary px-4 font-mono text-sm text-foreground placeholder:font-sans placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
              <button type="button" onClick={handleCheckGemini} disabled={geminiCheckState === 'checking'}
                className="h-11 shrink-0 rounded-xl border border-primary/40 bg-primary/15 px-5 text-sm font-medium text-primary transition-colors hover:bg-primary/25 disabled:opacity-50">
                {geminiCheckState === 'checking' ? 'Memeriksa...' : 'Check API'}
              </button>
            </div>
            {geminiCheckMessage && (
              <p className={`text-xs font-medium mt-1 ${geminiCheckState === 'ok' ? 'text-emerald-500' : 'text-destructive'}`}>
                {geminiCheckMessage}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="gemini-model" className="text-sm font-medium">Model LLM</label>
            <input id="gemini-model" type="text" placeholder="gemini-2.5-flash"
              value={settings.model} onChange={(e) => { setGeminiCheckState('idle'); setGeminiCheckMessage(''); setSettings({ ...settings, model: e.target.value }); }}
              className="h-11 w-full rounded-xl border border-field bg-secondary px-4 font-mono text-sm text-foreground placeholder:font-sans placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
          </div>
          <div className="border-t border-line pt-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div><h3 className="text-sm font-bold">Hook TTS (Gemini)</h3><p className="mt-1 text-xs text-muted">API key terpisah dari Highlight Finder.</p></div>
              {settings.hook_key_saved && <span className="shrink-0 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-500">Tersimpan</span>}
            </div>
            <label htmlFor="hook-api-key" className="mb-2 block text-sm font-medium">Gemini TTS API Key</label>
            <input id="hook-api-key" type="password" autoComplete="new-password" placeholder={settings.hook_key_saved ? 'Kosongkan untuk mempertahankan key TTS tersimpan' : 'Gemini API key khusus TTS'} value={settings.hook_api_key || ''} onChange={(e) => setSettings({ ...settings, hook_api_key: e.target.value })} className="h-11 w-full rounded-xl border border-field bg-secondary px-4 font-mono text-sm text-foreground placeholder:font-sans placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <label htmlFor="hook-model" className="text-sm font-medium">Model suara hook</label>
              <input id="hook-model" type="text" value={settings.hook_model || 'gemini-3.1-flash-tts-preview'} onChange={(e) => setSettings({ ...settings, hook_model: e.target.value })} className="h-11 w-full rounded-xl border border-field bg-secondary px-4 font-mono text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary" />
            </div>
            <div className="flex flex-col gap-2">
              <label htmlFor="hook-voice" className="text-sm font-medium">Suara hook</label>
              <select id="hook-voice" value={settings.hook_voice || 'Fenrir'} onChange={(e) => setSettings({ ...settings, hook_voice: e.target.value })} className="h-11 w-full rounded-xl border border-field bg-secondary px-4 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary">
                <option value="Fenrir">Fenrir — pria energik</option>
                <option value="Puck">Puck — pria upbeat</option>
                <option value="Charon">Charon — pria tegas</option>
                <option value="Orus">Orus — pria formal</option>
              </select>
            </div>
          </div>
          <p className="text-xs leading-relaxed text-muted">Video dibekukan sampai narasi TTS selesai.</p>
          <div className="flex justify-end pt-2">
            <button type="button" onClick={() => handleClearProvider('hook_maker')} disabled={!settings.hook_key_saved || clearingProvider !== null} className="text-xs font-medium text-destructive transition-colors hover:text-destructive/80 disabled:opacity-50">
              {clearingProvider === 'hook_maker' ? 'Menghapus...' : 'Hapus TTS API Key'}
            </button>
          </div>
        </section>

        {/* Core Engine - Groq */}
        <section className="flex flex-col gap-5 rounded-2xl border border-line bg-card p-6">
          <div className="flex items-center gap-3 justify-between">
            <div className="flex items-center gap-3">
              <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v3m0 12v3M5.64 5.64l2.12 2.12m8.48 8.48 2.12 2.12M3 12h3m12 0h3M5.64 18.36l2.12-2.12m8.48-8.48 2.12-2.12"></path><circle cx="12" cy="12" r="3"></circle></svg>
              </span>
              <h2 className="font-display text-lg font-bold">Caption Maker (Groq)</h2>
            </div>
            {settings.caption_key_saved && (
              <span className="shrink-0 text-[11px] font-bold text-emerald-500 bg-emerald-500/10 px-2.5 py-1 rounded-lg border border-emerald-500/20">Tersimpan</span>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="groq-base-url" className="text-sm font-medium">Base URL</label>
            <input id="groq-base-url" type="url" placeholder="https://api.groq.com/openai/v1"
              value={settings.caption_base_url} onChange={(e) => { setGroqCheckState('idle'); setGroqCheckMessage(''); setSettings({ ...settings, caption_base_url: e.target.value }); }}
              className="h-11 w-full rounded-xl border border-field bg-secondary px-4 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="groq-api-key" className="text-sm font-medium">API Key</label>
            <div className="flex gap-3">
              <input id="groq-api-key" type="password" autoComplete="new-password"
                placeholder={settings.caption_key_saved ? 'Kosongkan untuk mempertahankan key tersimpan' : 'Groq API key'}
                 value={settings.caption_api_key} onChange={(e) => { setGroqCheckState('idle'); setGroqCheckMessage(''); setSettings({ ...settings, caption_api_key: e.target.value }); }}
                className="h-11 min-w-0 flex-1 rounded-xl border border-field bg-secondary px-4 font-mono text-sm text-foreground placeholder:font-sans placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
              <button type="button" onClick={handleCheckGroq} disabled={groqCheckState === 'checking'}
                className="h-11 shrink-0 rounded-xl border border-primary/40 bg-primary/15 px-5 text-sm font-medium text-primary transition-colors hover:bg-primary/25 disabled:opacity-50">
                {groqCheckState === 'checking' ? 'Memeriksa...' : 'Check API'}
              </button>
            </div>
            {groqCheckMessage && (
              <p className={`text-xs font-medium mt-1 ${groqCheckState === 'ok' ? 'text-emerald-500' : 'text-destructive'}`}>
                {groqCheckMessage}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2">
            <label htmlFor="groq-model" className="text-sm font-medium">Transcription Model</label>
            <input id="groq-model" type="text" placeholder="whisper-large-v3-turbo"
              value={settings.caption_model} onChange={(e) => { setGroqCheckState('idle'); setGroqCheckMessage(''); setSettings({ ...settings, caption_model: e.target.value }); }}
              className="h-11 w-full rounded-xl border border-field bg-secondary px-4 font-mono text-sm text-foreground placeholder:font-sans placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-primary" />
          </div>
          <div className="flex justify-end pt-2">
            <button type="button" onClick={() => handleClearProvider('caption_maker')} disabled={!settings.caption_key_saved || clearingProvider !== null}
              className="text-xs font-medium text-destructive transition-colors hover:text-destructive/80 disabled:opacity-50">
              {clearingProvider === 'caption_maker' ? 'Menghapus...' : 'Hapus API Key'}
            </button>
          </div>
        </section>

        <section className="flex flex-col gap-5 rounded-2xl border border-line bg-card p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-lg font-bold">YouTube cookies.txt</h2>
              <p className="mt-1 text-sm text-muted">{settings.cookie_exists ? 'Tersimpan khusus untuk akun ini.' : 'Opsional untuk video yang meminta login YouTube.'}</p>
            </div>
            {settings.cookie_exists && <span className="shrink-0 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-500">Tersimpan</span>}
          </div>
          <label className="flex cursor-pointer items-center justify-center rounded-xl border border-line bg-secondary px-5 py-3 text-sm font-medium transition-colors hover:border-primary/40 hover:text-primary has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-50">
            {isUploadingCookies ? 'Mengunggah...' : 'Pilih cookies.txt'}
            <input
              type="file"
              accept=".txt,text/plain"
              disabled={isUploadingCookies}
              onChange={(e) => {
                void handleCookiesUpload(e.target.files?.[0]);
                e.currentTarget.value = '';
              }}
              className="sr-only"
            />
          </label>
          <p className="text-xs leading-relaxed text-muted">Cookie bersifat sensitif. Ekspor dari browser yang login ke YouTube; jangan bagikan file.</p>
        </section>

        {/* Koneksi Sosial Media */}
        <section className="flex flex-col gap-5 rounded-2xl border border-line bg-card p-6">
          <div className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-lg bg-primary/15 text-primary">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/></svg>
            </span>
            <h2 className="font-display text-lg font-bold">Koneksi Sosial Media</h2>
          </div>
          <p className="text-sm leading-relaxed text-muted">Hubungkan akun sosial media untuk mempublikasikan klip langsung dari dashboard.</p>
          {youtubeConnected && (
            <div className="flex items-center gap-2 rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm">
              <span className="size-2 rounded-full bg-emerald-500" />
              <span className="text-muted">Terhubung ke</span>
              <strong className="font-semibold text-foreground">{youtubeChannelTitle || 'Channel YouTube'}</strong>
            </div>
          )}
          <div className="flex flex-wrap gap-3">
            {youtubeConnected ? (
              <button type="button" onClick={handleDisconnectYoutube} className="rounded-xl border border-destructive/40 bg-destructive/10 px-5 py-2.5 text-sm font-medium text-destructive transition-colors hover:bg-destructive/20">Putuskan YouTube</button>
            ) : (
              <button type="button" onClick={handleConnectYoutube} className="rounded-xl border border-line bg-secondary px-5 py-2.5 text-sm font-medium transition-colors hover:border-primary/40 hover:text-primary">Hubungkan YouTube</button>
            )}
            <button type="button" disabled className="rounded-xl border border-line bg-secondary px-5 py-2.5 text-sm font-medium text-muted/50 cursor-not-allowed">Hubungkan TikTok (Segera)</button>
            <button type="button" disabled className="rounded-xl border border-line bg-secondary px-5 py-2.5 text-sm font-medium text-muted/50 cursor-not-allowed">Hubungkan Instagram (Segera)</button>
          </div>
        </section>

        <div className="flex items-center gap-4 mt-2">
          <button type="submit" disabled={isSaving || clearingProvider !== null} className="flex h-12 items-center justify-center gap-2 rounded-xl bg-primary px-8 font-display text-base font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/></svg>
            {isSaving ? 'Menyimpan...' : 'Simpan Pengaturan'}
          </button>
          {saveMessage && (
             <span role={saveError ? 'alert' : 'status'} className={`text-sm font-medium ${saveError ? 'text-destructive' : 'text-emerald-500'}`}>{saveMessage}</span>
           )}
        </div>
      </form>
    </main>
  );
}
