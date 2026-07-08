import { useState, useEffect } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { api } from '@/lib/api';

export default function DashboardLayout() {
  const location = useLocation();
  const activeTab = location.pathname.split('/')[1] || 'home';
  const [isProfileOpen, setIsProfileOpen] = useState(false);

  const [status, setStatus] = useState<any>(null);
  const [settings, setSettings] = useState<any>({
    base_url: '',
    api_key: '',
    model: '',
    output_dir: '',
    watermark: { enabled: false, image_path: "", position_x: 0.22, position_y: 0.17, opacity: 0.49, scale: 0.53 },
    credit_watermark: { enabled: true, text: "sc : {channel}", color: "#ffffff", size: 0.032, opacity: 0.55, position_x: 0.22, position_y: 0.17 },
    hook_style: { enabled: false, font_size: 0.025, text_color: "#0033ff", background_color: "#ffffff", corner_radius: 22, duration: 5.0, position_x: 0.22, position_y: 0.17 },
    subtitle: { enabled: true, color: "#ffff00", size: 0.035, position_x: 0.5, position_y: 0.85, text_transform: 'uppercase', bg_box: false, bg_color: '#000000', bg_opacity: 0.8 },
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
          setSettings((prev: any) => ({
            ...prev,
            ...data,
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

  return (
    <div className="bg-background text-foreground h-screen overflow-hidden flex flex-col antialiased">
      <header className="bg-white border-b border-border px-4 py-3 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-2 text-black font-extrabold text-[20px] tracking-tight">
          <img src="/logo%20klipklop.png?v=3" className="h-10 w-10 rounded-md object-contain" alt="KlipKlop Logo" />
          <span className="text-black leading-none">KlipKlop</span>
        </div>
        <nav className="flex items-center gap-1 text-[13px] font-semibold">
          <Link 
            to="/"
            className={`px-3 py-2 rounded-xl transition ${activeTab === 'home' || activeTab === '' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900'}`}
          >
            Dashboard
          </Link>
          <Link 
            to="/gallery"
            className={`px-3 py-2 rounded-xl transition ${activeTab === 'gallery' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900'}`}
          >
            Galeri
          </Link>
          <Link 
            to="/console"
            className={`px-3 py-2 rounded-xl transition ${activeTab === 'console' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900'}`}
          >
            Konsol
          </Link>
         
          <Link 
            to="/preview"
            className={`px-3 py-2 rounded-xl transition ${activeTab === 'preview' ? 'bg-primary/10 text-primary' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-900'}`}
          >
            Preview Editor
          </Link>
          
          {/* Profile Dropdown */}
          <div className="relative ml-2">
            <button 
              onClick={() => setIsProfileOpen(!isProfileOpen)}
              type="button" 
              className="flex items-center justify-center w-10 h-10 rounded-full bg-slate-100 hover:bg-slate-200 border border-slate-200 transition focus:outline-none"
            >
              <svg className="w-5 h-5 text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>
            </button>
            
            {isProfileOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setIsProfileOpen(false)}></div>
                <div className="absolute right-0 mt-2 w-48 bg-white rounded-xl shadow-lg border border-slate-100 py-1 z-50 animate-in slide-in-from-top-2 duration-200">
                <Link 
                  to="/settings"
                  onClick={() => setIsProfileOpen(false)}
                  className="flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium text-slate-700 hover:bg-slate-50 transition"
                >
                  <svg className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                  Pengaturan
                </Link>
                <div className="h-px bg-slate-100 my-1"></div>
                <button 
                  onClick={() => {
                    setIsProfileOpen(false);
                    handleLogout();
                  }}
                  className="w-full flex items-center gap-2 px-4 py-2.5 text-[13px] font-medium text-red-600 hover:bg-red-50 transition text-left"
                >
                  <svg className="w-4 h-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                  Keluar
                </button>
              </div>
              </>
            )}
          </div>
        </nav>
      </header>

      <div className="flex flex-1 min-h-0 overflow-hidden">
        <main className="flex-1 min-w-0 flex flex-col">
          <Outlet context={{ settings, setSettings, status }} />
        </main>
      </div>
    </div>
  );
}
