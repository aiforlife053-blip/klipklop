import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';

export default function Dashboard() {
  const { status, settings } = useOutletContext<any>();
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [videoQuality, setVideoQuality] = useState('720');
  const [landscapeBlur, setLandscapeBlur] = useState(true);
  const [showJsonModal, setShowJsonModal] = useState(false);

  return (
    <div className="flex flex-row flex-1 items-stretch h-[calc(100vh-53px)] overflow-hidden">
      <section className="relative order-2 w-[60%] flex-none bg-muted border-l border-border p-0 h-full overflow-auto flex flex-col justify-between" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
        <button 
          type="button"
          onClick={() => setShowJsonModal(true)}
          className="absolute top-4 right-4 border border-border px-3.5 py-2 rounded-xl text-[12px] font-semibold text-slate-700 hover:bg-white bg-white/50 backdrop-blur-sm transition shadow-sm z-10"
        >
          JSON Payload
        </button>

        <div className="flex flex-1 h-full flex-col items-center justify-center text-center max-w-xl mx-auto w-full">
          <h3 className="text-[19px] font-semibold text-black mb-2.5 tracking-tight">Siap Membuat Klip Viral Terbaik?</h3>
          <p className="text-[13px] text-gray-500 leading-relaxed max-w-md">Tempel link YouTube di panel kiri. AI akan memilih 1 momen dengan potensi viral tertinggi.</p>
        </div>

        <div className="hidden text-[13px] text-gray-500 w-full">
          Status: {status?.status || 'Idle'}<br />Clip: - | Quality: {videoQuality}p | 9:16
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

      {/* JSON Payload Modal */}
      {showJsonModal && (
        <div className="fixed inset-0 z-[120] bg-black/50 flex items-center justify-center p-4" onClick={() => setShowJsonModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-2xl overflow-hidden shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-gray-100 p-4">
              <h2 className="text-[16px] font-bold text-slate-900">API Payload Configuration</h2>
              <button onClick={() => setShowJsonModal(false)} className="text-slate-400 hover:text-slate-900 transition-colors">
                Tutup
              </button>
            </div>
            <div className="p-4 bg-slate-900 overflow-auto max-h-[60vh] text-left">
              <pre className="text-[12px] text-emerald-400 font-mono whitespace-pre-wrap">
                {JSON.stringify({
                  settings: settings,
                  start: {
                    url: youtubeUrl,
                    num_clips: 1,
                    add_captions: settings.subtitle?.enabled ?? true,
                    enable_captions: settings.subtitle?.enabled ?? true,
                    add_hook: settings.hook_style?.enabled ?? false,
                    hook_mode: settings.hook_style?.enabled ?? false,
                    screen_size: "9:16",
                    subtitle_language: settings.subtitle_language || "id",
                    landscape_blur: landscapeBlur,
                    source_credit: settings.credit_watermark?.enabled ?? true,
                    instruction: ""
                  }
                }, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
