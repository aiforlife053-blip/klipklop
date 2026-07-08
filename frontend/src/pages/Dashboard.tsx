import { useState } from 'react';
import { useOutletContext } from 'react-router-dom';
import { createPortal } from 'react-dom';

export default function Dashboard() {
  const { status, settings } = useOutletContext<any>();
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [videoQuality, setVideoQuality] = useState('720');
  const [numClips, setNumClips] = useState(1);
  const [landscapeBlur, setLandscapeBlur] = useState(true);
  const [showJsonModal, setShowJsonModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState<any>(null);
  const [showInstructionModal, setShowInstructionModal] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [uploadProgress, setUploadProgress] = useState<Record<number, number>>({});

  const handleUpload = (clipId: number) => {
    if (uploadProgress[clipId] !== undefined) return;
    
    setUploadProgress(prev => ({ ...prev, [clipId]: 0 }));
    
    const interval = setInterval(() => {
      setUploadProgress(prev => {
        const current = prev[clipId] || 0;
        if (current >= 100) {
          clearInterval(interval);
          return prev;
        }
        return { ...prev, [clipId]: current + 5 };
      });
    }, 200);
  };

  const dummyClips = [
    { id: 1, title: 'Rahasia Sukses di Usia Muda - Podcast Klip', desc: 'Host menjawab pertanyaan umum soal aplikasi gratis tapi AI-nya berbayar...', duration: '45s', img: 'https://images.unsplash.com/photo-1611162617474-5b21e879e113?auto=format&fit=crop&w=800&q=80', score: '99%' },
    { id: 2, title: 'Cara Kerja Algoritma TikTok 2024', desc: 'Tips jitu agar video cepat FYP dengan memanfaatkan retensi penonton.', duration: '60s', img: 'https://images.unsplash.com/photo-1611162616305-c69b3fa7fbe0?auto=format&fit=crop&w=800&q=80', score: '95%' },
    { id: 3, title: 'Review Gadget Unik Harga 100 Ribuan', desc: 'Mencoba berbagai barang unik dari e-commerce yang harganya murah banget.', duration: '30s', img: 'https://images.unsplash.com/photo-1526406915894-7bcd65f60845?auto=format&fit=crop&w=800&q=80', score: '88%' }
  ];

  return (
    <div className="flex flex-row flex-1 items-stretch h-[calc(100vh-53px)] overflow-hidden">
      <section className="relative order-2 w-[65%] flex-none bg-muted border-l border-border p-6 h-full overflow-y-auto" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
        <button 
          type="button"
          onClick={() => setShowJsonModal(true)}
          className="absolute top-4 right-4 border border-border px-3.5 py-2 rounded-xl text-[12px] font-semibold text-slate-700 hover:bg-white bg-white/50 backdrop-blur-sm transition shadow-sm z-10"
        >
          JSON Payload
        </button>

        <div className="w-full max-w-5xl mx-auto space-y-6 mt-4 pb-12">
          <div className="text-center mb-6">
            <h3 className="text-[20px] font-bold text-slate-900 tracking-tight">Hasil Generasi Klip</h3>
            <p className="text-[13px] text-slate-500 mt-1">Ini adalah contoh tampilan jika klip sudah selesai diproses.</p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mt-14">
            {dummyClips.map(clip => (
              <div key={clip.id} className="relative bg-white rounded-2xl p-4 shadow-sm border border-slate-100 flex flex-col group hover:shadow-md transition overflow-hidden pb-5">
                <div className="relative w-full aspect-[4/3] bg-slate-900 rounded-xl overflow-hidden shadow-inner group">
                  <img src={clip.img} alt="Thumbnail" className="w-full h-full object-cover opacity-90 group-hover:scale-105 transition-transform duration-500" />
                  <div className="absolute top-1.5 right-1.5 bg-black/50 px-1.5 py-0.5 rounded text-[9px] font-medium text-white/90 border border-white/10">{clip.duration}</div>
                  <div className="absolute top-1.5 left-1.5 bg-orange-500/90 backdrop-blur text-white px-1.5 py-0.5 rounded text-[10px] font-bold shadow-sm flex items-center gap-1 border border-orange-400/50">
                    <span className="text-[12px] leading-none">🔥</span> {clip.score}
                  </div>
                  {uploadProgress[clip.id] === 100 && (
                    <div className="absolute bottom-1.5 left-1.5 bg-emerald-500/90 backdrop-blur text-white px-2 py-0.5 rounded text-[10px] font-bold shadow-sm flex items-center gap-1 border border-emerald-400/50 z-10">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path></svg>
                      Uploaded
                    </div>
                  )}
                </div>
                <div className="mt-3 text-left flex-1 flex flex-col">
                  <h4 className="font-bold text-[13px] leading-snug line-clamp-2 text-slate-900">{clip.title}</h4>
                  <p className="text-[11px] text-slate-500 line-clamp-2 mt-1.5">{clip.desc}</p>
                  <p className="text-[10px] text-slate-400 mt-auto pt-3">Durasi: {clip.duration}</p>
                </div>
                <button 
                  onClick={() => setShowDetailModal(clip)}
                  className="w-full mt-3 py-2 border border-slate-200 rounded-lg text-[12px] font-semibold text-slate-700 hover:bg-slate-50 transition"
                >
                  Lihat detail
                </button>

                {uploadProgress[clip.id] !== undefined && (
                  <>
                    <div className="absolute bottom-0 left-0 w-full h-1.5 bg-slate-100">
                      <div 
                        className="h-full bg-blue-500 transition-all duration-200" 
                        style={{ width: `${uploadProgress[clip.id]}%` }}
                      />
                    </div>
                    <div className="text-center text-[10px] font-bold text-blue-600 mt-2">
                      {uploadProgress[clip.id] === 100 ? 'Selesai (100%)' : `Uploading ${uploadProgress[clip.id]}%`}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="mt-48 pb-12 text-center w-full">
          <p className="text-[14px] text-gray-500 font-medium">
            Butuh bantuan? Email <a href="mailto:bfrotok@youclip.id" className="text-blue-500 hover:underline">bfrotok@youclip.id</a>
          </p>
        </div>
      </section>

      {/* Left Panel: Settings & Creation Form */}
      <aside className="order-1 w-[35%] shrink-0 bg-white border-r border-border p-5 h-full overflow-auto flex flex-col gap-5">
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
            </div>

            <div>
              <label className="block text-[12px] font-semibold text-black mb-1.5">Jumlah Klip</label>
              <input 
                type="number" 
                min="1" max="10"
                value={numClips}
                onChange={(e) => setNumClips(parseInt(e.target.value) || 1)}
                className="w-full px-3 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 text-[13px] text-gray-700 bg-white" 
              />
              <p className="text-[11px] text-gray-400 mt-1">Berapa klip viral yang ingin dihasilkan dari video ini.</p>
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
            <button 
              type="button" 
              onClick={() => setShowInstructionModal(true)}
              className="text-[12px] text-primary font-semibold hover:text-orange-700 flex items-center space-x-1.5 transition"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2.2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
              </svg>
              <span>Tambah Arahan (Opsional)</span>
            </button>
          </div>
        </div>

        <div className="pt-4 border-t border-gray-200/60 mt-auto">
          <div className="flex gap-2 mb-3">
            <button className="flex-1 bg-primary hover:bg-orange-700 text-white font-semibold py-2.5 rounded-xl text-[14px] transition shadow-sm">
              Proses Klip
            </button>
            <button className="flex-none bg-red-500 hover:bg-red-600 text-white p-2.5 rounded-xl transition shadow-sm flex items-center justify-center group" title="Berhenti">
              <svg className="w-5 h-5 group-hover:scale-110 transition-transform" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>
            </button>
          </div>
          <div className="text-[12px] text-gray-500 mt-2">
            Status: {status?.status || 'Idle'}
          </div>
        </div>
      </aside>

      {/* JSON Payload Modal */}
      {showJsonModal && createPortal(
        <div className="fixed inset-0 z-[9999] bg-black/50 flex items-center justify-center p-4" onClick={() => setShowJsonModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-2xl overflow-hidden shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-gray-100 p-4">
              <h2 className="text-[16px] font-bold text-slate-900">API Payload Configuration</h2>
              <button onClick={() => setShowJsonModal(false)} className="w-8 h-8 flex items-center justify-center rounded-full border border-slate-200 text-slate-400 hover:text-slate-900 hover:bg-slate-50 transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
              </button>
            </div>
            <div className="p-4 bg-slate-900 overflow-auto max-h-[60vh] text-left">
              <pre className="text-[12px] text-emerald-400 font-mono whitespace-pre-wrap">
                {JSON.stringify({
                  settings: settings,
                  start: {
                    url: youtubeUrl,
                    num_clips: numClips,
                    add_captions: settings.subtitle?.enabled ?? true,
                    enable_captions: settings.subtitle?.enabled ?? true,
                    add_hook: settings.hook_style?.enabled ?? false,
                    hook_mode: settings.hook_style?.enabled ?? false,
                    screen_size: "9:16",
                    subtitle_language: settings.subtitle_language || "id",
                    landscape_blur: landscapeBlur,
                    source_credit: settings.credit_watermark?.enabled ?? true,
                    instruction: instruction
                  }
                }, null, 2)}
              </pre>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Detail Modal */}
      {showDetailModal && createPortal(
        <div className="fixed inset-0 z-[9999] bg-black/50 flex items-center justify-center p-4" onClick={() => setShowDetailModal(null)}>
          <div className="bg-white rounded-2xl flex max-w-4xl w-full p-4 gap-6 relative shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => setShowDetailModal(null)} className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-full border border-slate-200 text-slate-400 hover:text-slate-900 hover:bg-slate-50 transition-colors z-10">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
            
            {/* Left: Video */}
            <div className="w-[300px] shrink-0 bg-black rounded-xl overflow-hidden aspect-[9/16] relative shadow-inner">
              <img src={showDetailModal.img} alt="Video" className="w-full h-full object-cover opacity-80" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-14 h-14 bg-white/20 backdrop-blur-md rounded-full flex items-center justify-center border border-white/30 text-white cursor-pointer hover:bg-primary/90 hover:scale-110 transition-all shadow-lg">
                  <svg className="w-6 h-6 ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                </div>
              </div>
            </div>
            
            {/* Right: Details */}
            <div className="flex-1 flex flex-col py-2 pr-4">
              <p className="text-[12px] text-slate-500 mb-1">Durasi: {showDetailModal.duration}</p>
              <h2 className="text-[20px] font-bold text-slate-900 leading-tight">{showDetailModal.title}</h2>
              {uploadProgress[showDetailModal.id] === 100 && (
                <a href="#" className="inline-flex items-center gap-1.5 text-[13px] text-emerald-500 hover:text-emerald-600 font-bold mt-2 hover:underline">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                  Tonton di YouTube
                </a>
              )}
              
              <p className="text-[12px] font-bold text-slate-700 mt-6 mb-2">Description</p>
              <div className="border border-slate-200 rounded-xl p-4 text-[13px] text-slate-600 bg-slate-50 min-h-[120px] leading-relaxed">
                {showDetailModal.desc}
                <br/><br/>
                sc: @klipklop
              </div>
              
              <div className="mt-auto flex flex-wrap items-center gap-2 pt-6">
                <button className="bg-[#ea580c] hover:bg-[#c2410c] text-white font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm border border-[#ea580c]">Simpan ke Gallery</button>
                <button className="bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm">Download</button>
                <button 
                  onClick={() => handleUpload(showDetailModal.id)}
                  disabled={uploadProgress[showDetailModal.id] !== undefined}
                  className={`font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm border ${
                    uploadProgress[showDetailModal.id] !== undefined
                      ? 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed'
                      : 'bg-white border-slate-200 hover:bg-slate-50 text-slate-700'
                  }`}
                >
                  {uploadProgress[showDetailModal.id] !== undefined 
                    ? (uploadProgress[showDetailModal.id] === 100 ? 'Uploaded' : `Uploading ${uploadProgress[showDetailModal.id]}%`) 
                    : 'Upload'}
                </button>
                <button className="bg-white border border-slate-200 hover:bg-red-50 hover:text-red-600 hover:border-red-200 text-slate-700 font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm">Hapus</button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}

      {/* Instruction Modal */}
      {showInstructionModal && createPortal(
        <div className="fixed inset-0 z-[9999] bg-black/50 flex items-center justify-center p-4" onClick={() => setShowInstructionModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-lg overflow-hidden shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-gray-100 p-4">
              <h2 className="text-[16px] font-bold text-slate-900">Tambah Arahan Khusus</h2>
              <button onClick={() => setShowInstructionModal(false)} className="w-8 h-8 flex items-center justify-center rounded-full border border-slate-200 text-slate-400 hover:text-slate-900 hover:bg-slate-50 transition-colors">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12"></path></svg>
              </button>
            </div>
            <div className="p-5">
              <p className="text-[12px] text-slate-500 mb-3">Tambahkan arahan atau konteks spesifik untuk AI saat memotong video ini (opsional).</p>
              <textarea 
                className="w-full h-32 px-3.5 py-3 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 text-[13px] text-gray-700 bg-slate-50 resize-none"
                placeholder="Misalnya: Fokus pada bagian saat host membahas tentang investasi saham..."
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
              ></textarea>
              <div className="flex justify-end gap-2 mt-5">
                <button 
                  onClick={() => setShowInstructionModal(false)}
                  className="px-4 py-2 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold rounded-xl text-[12px] transition shadow-sm"
                >
                  Batal
                </button>
                <button 
                  onClick={() => setShowInstructionModal(false)}
                  className="px-4 py-2 bg-primary hover:bg-orange-700 text-white font-semibold rounded-xl text-[12px] transition shadow-sm"
                >
                  Simpan Arahan
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
