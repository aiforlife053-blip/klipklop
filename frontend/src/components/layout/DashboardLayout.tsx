import { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { api } from '@/lib/api';

export default function DashboardLayout() {
  const location = useLocation();
  const activeTab = location.pathname.split('/')[1] || 'home';
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [showTicketModal, setShowTicketModal] = useState(false);
  const [ticketSubject, setTicketSubject] = useState('');
  const [ticketMessage, setTicketMessage] = useState('');
  const [ticketStatus, setTicketStatus] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle');

  const [status, setStatus] = useState<any>(null);
  const [settings, setSettings] = useState<any>({
    base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
    api_key: '',
    model: 'gemini-2.5-flash',
    caption_base_url: 'https://api.groq.com/openai/v1',
    caption_api_key: '',
    caption_model: 'whisper-large-v3-turbo',
    api_key_saved: false,
    caption_key_saved: false,
    output_dir: '',
    watermark: { enabled: false, image_path: "", position_x: 0.22, position_y: 0.17, opacity: 0.49, scale: 0.53 },
    credit_watermark: { enabled: true, text: "sc : {channel}", color: "#ffffff", size: 0.032, opacity: 0.55, position_x: 0.22, position_y: 0.17 },
    hook_style: { enabled: false, font_size: 0.054, font_family: "Plus Jakarta Sans", font_weight: 800, text_color: "#FFD700", outline_color: "#000000", outline_thickness: 1.5, duration: 5.0, position_x: 0.5, position_y: 0.2 },
    subtitle: { enabled: true, color: "#00BFFF", text_color: "#FFFFFF", size: 0.04, font_family: "Plus Jakarta Sans", font_weight: 800, outline_color: "#000000", outline_thickness: 1.0, position_x: 0.5, position_y: 0.85, text_transform: 'uppercase', bg_box: false, bg_color: '#000000', bg_opacity: 0.0 },
    blur_background: { enabled: true, zoom: 1.08, strength: 31, scale: 1.0 }
  });

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

  const handleSendTicket = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticketMessage.trim()) return;
    setTicketStatus('sending');
    try {
      await api('/api/activity', {
        method: 'POST',
        body: JSON.stringify({
          action: 'ticket',
          detail: `[${ticketSubject || 'Keluh Kesah'}] ${ticketMessage}`
        })
      });
      setTicketStatus('sent');
      setTimeout(() => {
        setShowTicketModal(false);
        setTicketSubject('');
        setTicketMessage('');
        setTicketStatus('idle');
      }, 1500);
    } catch (err) {
      console.error('Failed to send ticket:', err);
      setTicketStatus('error');
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
              to="/gallery"
              className={`rounded-full px-4 py-2 text-sm transition-colors ${activeTab === 'gallery' ? 'bg-primary/15 font-medium text-primary' : 'text-muted hover:bg-secondary hover:text-foreground'}`}
            >
              Galeri
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
              Preview Editor
            </Link>
          </nav>
          <div className="flex items-center gap-2">
            <Link to="/settings" className="flex h-9 w-9 items-center justify-center rounded-full border border-line text-muted transition-colors hover:bg-secondary hover:text-foreground" aria-label="Pengaturan">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>
            </Link>
            
            {/* Profile Dropdown */}
            <div className="relative">
              <button 
                onClick={() => setIsProfileOpen(!isProfileOpen)}
                type="button" 
                className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-secondary text-muted transition-colors hover:text-foreground" aria-label="Akun"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              </button>
              
              {isProfileOpen && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setIsProfileOpen(false)}></div>
                  <div className="absolute right-0 mt-2 w-48 bg-card rounded-xl shadow-lg border border-line py-1 z-50 animate-in slide-in-from-top-2 duration-200">
                  <Link 
                    to="/settings"
                    onClick={() => setIsProfileOpen(false)}
                    className="flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium text-foreground hover:bg-secondary transition"
                  >
                    <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    Pengaturan
                  </Link>
                  <button 
                    onClick={() => {
                      setIsProfileOpen(false);
                      setShowTicketModal(true);
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium text-foreground hover:bg-secondary transition text-left"
                  >
                    <svg className="w-4 h-4 text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                    Ticket & Keluh Kesah
                  </button>
                  <div className="h-px bg-line my-1"></div>
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
          <Link to="/gallery" className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm ${activeTab === 'gallery' ? 'bg-primary/15 font-medium text-primary' : 'text-muted'}`}>Galeri</Link>
          <Link to="/console" className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm ${activeTab === 'console' ? 'bg-primary/15 font-medium text-primary' : 'text-muted'}`}>Konsol</Link>
          <Link to="/preview" className={`whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm ${activeTab === 'preview' ? 'bg-primary/15 font-medium text-primary' : 'text-muted'}`}>Preview Editor</Link>
        </nav>
      </header>

      <Outlet context={{ settings, setSettings, status }} />

      {/* Ticket / Keluh Kesah Modal */}
      {showTicketModal && createPortal(
        <div className="fixed inset-0 z-[9999] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 animate-in fade-in duration-200" onClick={() => setShowTicketModal(false)}>
          <div className="bg-white rounded-2xl w-full max-w-md overflow-hidden shadow-2xl border border-slate-100 p-6 space-y-4 animate-in zoom-in-95 duration-200" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-xl bg-orange-100 text-orange-600 flex items-center justify-center">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-[16px] leading-tight">Ticket & Keluh Kesah</h3>
                  <p className="text-[12px] text-slate-500">Masukanmu langsung ke tim developer KlipKlop</p>
                </div>
              </div>
              <button 
                type="button" 
                onClick={() => setShowTicketModal(false)}
                className="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-500 flex items-center justify-center transition"
              >
                ✕
              </button>
            </div>

            {ticketStatus === 'sent' ? (
              <div className="py-8 text-center space-y-2">
                <div className="w-12 h-12 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto text-xl animate-bounce">
                  ✅
                </div>
                <h4 className="font-bold text-slate-900 text-[15px]">Terima Kasih!</h4>
                <p className="text-[13px] text-slate-500">Keluh kesah dan saranmu berhasil dikirim.</p>
              </div>
            ) : (
              <form onSubmit={handleSendTicket} className="space-y-3 pt-1">
                <div>
                  <label className="block text-[12px] font-semibold text-slate-700 mb-1">Subjek / Kategori</label>
                  <input 
                    type="text"
                    value={ticketSubject}
                    onChange={(e) => setTicketSubject(e.target.value)}
                    placeholder="Contoh: Fitur Subtitle / Bug Export / Request Fitur"
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-[13px] focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 bg-slate-50/50"
                  />
                </div>
                <div>
                  <label className="block text-[12px] font-semibold text-slate-700 mb-1">Detail Keluh Kesah</label>
                  <textarea 
                    rows={4}
                    required
                    value={ticketMessage}
                    onChange={(e) => setTicketMessage(e.target.value)}
                    placeholder="Tuliskan kendala, kritik, atau saran yang kamu rasakan..."
                    className="w-full px-3.5 py-2.5 border border-slate-200 rounded-xl text-[13px] focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 bg-slate-50/50 resize-none"
                  />
                </div>
                {ticketStatus === 'error' && (
                  <p className="text-[12px] text-red-500 font-medium">Gagal mengirim ticket. Coba lagi ya.</p>
                )}
                <div className="flex justify-end gap-2 pt-2">
                  <button 
                    type="button" 
                    onClick={() => setShowTicketModal(false)}
                    className="px-4 py-2 border border-slate-200 rounded-xl font-semibold text-[13px] text-slate-700 hover:bg-slate-50 transition"
                  >
                    Batal
                  </button>
                  <button 
                    type="submit" 
                    disabled={ticketStatus === 'sending' || !ticketMessage.trim()}
                    className="px-4 py-2 bg-primary hover:bg-orange-600 disabled:opacity-50 text-white font-semibold rounded-xl text-[13px] transition shadow-sm"
                  >
                    {ticketStatus === 'sending' ? 'Mengirim...' : 'Kirim Ticket'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
