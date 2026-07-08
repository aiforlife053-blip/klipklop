import { useState } from 'react';
import { useOutletContext, useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';

export default function Settings() {
  const { settings, setSettings } = useOutletContext<any>();
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');
  const navigate = useNavigate();

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
