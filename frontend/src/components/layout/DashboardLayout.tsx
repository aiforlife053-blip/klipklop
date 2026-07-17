import { useState, useEffect, useCallback, useRef, type Dispatch, type SetStateAction } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { api } from '@/lib/api';

export type PipelineStatus = {
  status?: string;
  message?: string;
  progress?: number;
  error?: string;
  url?: string;
  queue_position?: number | null;
  logs?: string[];
};

export type DashboardOutletContext = {
  settings: any;
  setSettings: Dispatch<SetStateAction<any>>;
  status: PipelineStatus | null;
  refreshStatus: () => Promise<void>;
};

export default function DashboardLayout() {
  const location = useLocation();
  const activeTab = location.pathname.split('/')[1] || 'home';
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const profileButtonRef = useRef<HTMLButtonElement>(null);

  const [status, setStatus] = useState<any>(null);
  const [settings, setSettings] = useState<any>({
    base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
    api_key: '',
    model: 'gemini-2.5-flash',
    caption_base_url: 'https://api.groq.com/openai/v1',
    caption_api_key: '',
    caption_model: 'whisper-large-v3-turbo',
    hook_api_key: '',
    hook_model: 'gemini-3.1-flash-tts-preview',
    hook_voice: 'Fenrir',
    api_key_saved: false,
    caption_key_saved: false,
    output_dir: '',
    watermark: { enabled: false, image_path: "", position_x: 0.22, position_y: 0.17, opacity: 0.49, scale: 0.53 },
    credit_watermark: { enabled: true, text: "sc : {channel}", color: "#ffffff", size: 0.032, opacity: 0.55, position_x: 0.22, position_y: 0.17 },
    hook_style: { enabled: false, font_size: 0.054, font_family: "Plus Jakarta Sans", font_weight: 800, text_color: "#FFD700", outline_color: "#000000", outline_thickness: 1.5, duration: 5.0, position_x: 0.5, position_y: 0.2 },
    subtitle: { enabled: true, color: "#00BFFF", text_color: "#FFFFFF", size: 0.04, font_family: "Plus Jakarta Sans", font_weight: 800, outline_color: "#000000", outline_thickness: 1.0, position_x: 0.5, position_y: 0.85, text_transform: 'none', bg_box: false, bg_color: '#000000', bg_opacity: 0.0 },
    blur_background: { enabled: true, zoom: 1.08, strength: 10, scale: 1.6 }
  });

  const refreshStatus = useCallback(async () => {
    try {
      const data = await api('/api/status');
      setStatus(data);
    } catch (err) {
      console.error("Failed to fetch status", err);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();

    const fetchSettings = async () => {
      try {
        const data = await api('/api/settings');
        if (data && !data.error) {
          const { api_key: _apiKey, caption_api_key: _captionApiKey, ...safeSettings } = data;
          void _apiKey;
          void _captionApiKey;
          setSettings((prev: any) => ({
            ...prev,
            ...safeSettings,
            api_key: '',
            caption_api_key: '',
            watermark: { ...prev.watermark, ...(data.watermark || {}) },
            credit_watermark: { ...prev.credit_watermark, ...(data.credit_watermark || {}) },
            hook_style: { ...prev.hook_style, ...(data.hook_style || {}) },
            subtitle: { ...prev.subtitle, ...(data.subtitle || {}) },
            blur_background: { ...prev.blur_background, ...(data.blur_background || {}) }
          }));
        }
      } catch (err) {
        console.error("Failed to fetch settings", err);
      }
    };
    fetchSettings();
  }, [refreshStatus]);

  useEffect(() => {
    const active = status?.status && ['queued', 'running', 'stopping'].includes(status.status);
    if (!active) return;
    const interval = setInterval(() => void refreshStatus(), 2000);
    return () => clearInterval(interval);
  }, [status?.status, refreshStatus]);

  const handleLogout = async () => {
    try {
      await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' });
      sessionStorage.clear();
      window.location.href = '/login';
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="min-h-dvh flex flex-col bg-background font-sans text-foreground antialiased">
      <header className="sticky top-0 z-40 border-b border-line bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-6">
          <Link to="/" className="flex items-center gap-2.5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/></svg>
            </span>
            <span className="font-display text-lg font-bold tracking-tight">KlipKlop</span>
          </Link>
          <nav className="hidden items-center gap-1 md:flex" aria-label="Navigasi utama">
            <Link 
              to="/"
              className={`rounded-full px-4 py-2 text-sm transition-colors ${activeTab === 'home' || activeTab === '' ? 'bg-primary/15 font-medium text-primary' : 'text-muted hover:bg-secondary hover:text-foreground'}`}
            >
              Dashboard
            </Link>
            <Link 
              to="/console"
              className={`rounded-full px-4 py-2 text-sm transition-colors ${activeTab === 'console' ? 'bg-primary/15 font-medium text-primary' : 'text-muted hover:bg-secondary hover:text-foreground'}`}
            >
              Konsol
            </Link>
            <Link 
              to="/preview"
              className={`rounded-full px-4 py-2 text-sm transition-colors ${activeTab === 'preview' ? 'bg-primary/15 font-medium text-primary' : 'text-muted hover:bg-secondary hover:text-foreground'}`}
            >
              Preview
            </Link>
          </nav>
          <div className="flex items-center gap-2">
            <Link to="/settings" className="flex h-9 w-9 items-center justify-center rounded-full border border-line text-muted transition-colors hover:bg-secondary hover:text-foreground" aria-label="Pengaturan">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
            </Link>
            

            <div className="relative">
              <button 
                ref={profileButtonRef}
                onClick={() => setIsProfileOpen(!isProfileOpen)}
                type="button" 
                aria-expanded={isProfileOpen}
                aria-haspopup="menu"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-secondary text-muted transition-colors hover:text-foreground" aria-label="Akun"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              </button>
              
              {isProfileOpen && (
                <>
                  <button type="button" tabIndex={-1} aria-label="Tutup menu akun" className="fixed inset-0 z-40 cursor-default" onClick={() => { setIsProfileOpen(false); profileButtonRef.current?.focus(); }}></button>
                   <div role="menu" className="absolute right-0 z-50 mt-2 w-48 rounded-xl border border-line bg-card py-1 shadow-lg animate-in slide-in-from-top-2 duration-200">
                  <Link 
                    to="/settings"
                    onClick={() => setIsProfileOpen(false)}
                    className="flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium text-foreground hover:bg-secondary transition"
                  >
                    <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    Pengaturan
                  </Link>
                  <div className="my-1 h-px bg-line"></div>
                  <button 
                    onClick={() => {
                      setIsProfileOpen(false);
                      handleLogout();
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium text-destructive hover:bg-destructive/10 transition text-left"
                  >
                    <svg className="w-4 h-4 text-destructive" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                    Keluar
                  </button>
                </div>
                </>
              )}
            </div>
          </div>
        </div>
        <nav className="flex items-center gap-1 overflow-x-auto border-t border-line px-4 py-2 md:hidden" aria-label="Navigasi mobile">
          <Link to="/" className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm ${activeTab === 'home' || activeTab === '' ? 'bg-primary/15 font-medium text-primary' : 'text-muted'}`}>Dashboard</Link>
          <Link to="/console" className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm ${activeTab === 'console' ? 'bg-primary/15 font-medium text-primary' : 'text-muted'}`}>Konsol</Link>
          <Link to="/preview" className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm ${activeTab === 'preview' ? 'bg-primary/15 font-medium text-primary' : 'text-muted'}`}>Preview</Link>
        </nav>
      </header>

      <Outlet context={{ settings, setSettings, status, refreshStatus } satisfies DashboardOutletContext} />

    </div>
  );
}
