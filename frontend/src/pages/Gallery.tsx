import { useState } from 'react';
import { createPortal } from 'react-dom';

export default function Gallery() {
  const [showDetailModal, setShowDetailModal] = useState<any>(null);

  const dummyClips = [
    { id: 1, title: 'Motivasi Sukses #1', desc: 'Podcast motivasi menceritakan rahasia sukses pengusaha muda dari nol tanpa modal besar.', duration: '00:58', img: 'https://images.unsplash.com/photo-1516280440503-6c9fa5c1b692?w=500&q=80', score: '99%', isUploaded: true },
    { id: 2, title: 'Fakta Unik Dunia', desc: '5 Fakta unik dunia yang jarang diketahui orang, no 3 bikin kaget!', duration: '00:34', img: 'https://images.unsplash.com/photo-1611162617213-7d7a39e9b1d7?w=500&q=80', score: '95%', isUploaded: false },
    { id: 3, title: 'Tips Produktif', desc: 'Cara mengatur waktu kerja supaya lebih produktif dan tidak gampang lelah saat WFH.', duration: '00:45', img: 'https://images.unsplash.com/photo-1499914485622-a88fac536970?w=500&q=80', score: '92%', isUploaded: true },
    { id: 4, title: 'Cerita Horor Pendek', desc: 'Kisah nyata penjaga malam yang bertemu makhluk tak kasat mata di pabrik kosong.', duration: '01:12', img: 'https://images.unsplash.com/photo-1505635552518-3448ff116af3?w=500&q=80', score: '88%', isUploaded: false },
  ];

  return (
    <div className="p-6 space-y-7 bg-muted flex-1 h-[calc(100vh-53px)] overflow-auto" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
      <section className="bg-transparent min-h-[460px] flex flex-col gap-6 w-full max-w-6xl mx-auto">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-[24px] font-bold text-slate-900 tracking-tight">Koleksi Klip</h2>
              <div 
                className="w-5 h-5 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center text-[12px] font-bold cursor-help border border-slate-200"
                title="Maks galeri 10 video"
              >
                i
              </div>
            </div>
            <p className="text-[13px] text-slate-500 mt-1">Semua klip viral yang pernah Anda proses tersimpan di sini.</p>
          </div>
          
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {dummyClips.map((clip) => (
            <div key={clip.id} className="bg-white rounded-2xl p-4 shadow-sm border border-slate-100 flex flex-col group hover:shadow-md transition">
              <div className="relative w-full aspect-square bg-slate-900 rounded-xl overflow-hidden shadow-inner group">
                <img src={clip.img} alt={clip.title} className="w-full h-full object-cover opacity-90 group-hover:scale-105 transition-transform duration-500" />
                <div className="absolute top-1.5 right-1.5 bg-black/50 px-1.5 py-0.5 rounded text-[9px] font-medium text-white/90 border border-white/10">{clip.duration}</div>
                <div className="absolute top-1.5 left-1.5 bg-orange-500/90 backdrop-blur text-white px-1.5 py-0.5 rounded text-[10px] font-bold shadow-sm flex items-center gap-1 border border-orange-400/50">
                  <span className="text-[12px] leading-none">🔥</span> {clip.score}
                </div>
                {clip.isUploaded && (
                  <div className="absolute bottom-1.5 left-1.5 bg-emerald-500/90 backdrop-blur text-white px-2 py-0.5 rounded text-[10px] font-bold shadow-sm flex items-center gap-1 border border-emerald-400/50 z-10">
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path></svg>
                    Uploaded
                  </div>
                )}
              </div>
              
              <div className="mt-3 text-left flex-1 flex flex-col">
                <h4 className="font-bold text-[13px] leading-snug line-clamp-2 text-slate-900">{clip.title}</h4>
                <p className="text-[11px] text-slate-500 line-clamp-2 mt-1.5">{clip.desc}</p>
                <p className="text-[10px] text-slate-400 mt-2">Durasi: {clip.duration}</p>
              </div>
              <button 
                onClick={() => setShowDetailModal(clip)}
                className="w-full mt-3 py-2 border border-slate-200 rounded-lg text-[12px] font-semibold text-slate-700 hover:bg-slate-50 transition"
              >
                Lihat detail
              </button>
            </div>
          ))}
        </div>
      </section>

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
              {showDetailModal.isUploaded && (
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
                <button className="bg-[#ea580c] hover:bg-[#c2410c] text-white font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm border border-[#ea580c]">Download</button>
                <button 
                  disabled={showDetailModal.isUploaded}
                  className={`font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm border ${
                    showDetailModal.isUploaded 
                      ? 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed'
                      : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200'
                  }`}
                >
                  {showDetailModal.isUploaded ? 'Uploaded' : 'Upload'}
                </button>
                <button className="bg-white border border-slate-200 hover:bg-red-50 hover:text-red-600 hover:border-red-200 text-slate-700 font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm">Hapus</button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
