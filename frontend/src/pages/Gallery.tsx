import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { api } from '@/lib/api';

export default function Gallery() {
  const [showDetailModal, setShowDetailModal] = useState<any>(null);
  const [clips, setClips] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [uploadingId, setUploadingId] = useState<string | null>(null);

  const fetchSaved = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await api('/api/outputs');
      const saved: any[] = [];
      (data.groups || []).forEach((group: any) => {
        if (!group.saved) return;
        const savedPaths = new Set(group.saved_clips || []);
        (group.clips || group.files || []).forEach((clip: any) => {
          if (!savedPaths.size || savedPaths.has(clip.path)) {
            saved.push({ ...clip, groupPath: group.path });
          }
        });
      });
      setClips(saved);
    } catch (e) {
      console.error('Failed to fetch gallery', e);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSaved();
  }, [fetchSaved]);

  const handleDelete = async (clip: any) => {
    if (!confirm('Hapus klip ini dari galeri?')) return;
    try {
      await api('/api/delete', {
        method: 'POST',
        body: JSON.stringify({ path: clip.path }),
      });
      setShowDetailModal(null);
      setClips(prev => prev.filter(c => c.path !== clip.path));
    } catch (e: any) {
      alert('Gagal menghapus: ' + (e.message || ''));
    }
  };

  const handleUpload = async (clip: any) => {
    if (uploadingId === clip.path) return;
    setUploadingId(clip.path);
    try {
      const result = await api('/api/social/youtube/upload', {
        method: 'POST',
        body: JSON.stringify({
          path: clip.path,
          title: clip.title || clip.name,
          description: clip.description || '',
          privacy: 'private',
        }),
      });
      if (result.status === 'ok') {
        // Mark as uploaded locally
        setClips(prev => prev.map(c => c.path === clip.path ? { ...c, isUploaded: true } : c));
        if (showDetailModal?.path === clip.path) {
          setShowDetailModal((prev: any) => ({ ...prev, isUploaded: true }));
        }
      } else {
        alert('Upload gagal: ' + (result.message || ''));
      }
    } catch (e: any) {
      alert('Upload gagal: ' + (e.message || ''));
    } finally {
      setUploadingId(null);
    }
  };

  // Helpers
  const fmtDuration = (clip: any) => {
    if (clip.duration) return clip.duration;
    if (clip.duration_seconds != null) return `${Math.round(clip.duration_seconds)}s`;
    return '';
  };
  const fmtScore = (clip: any) => {
    if (clip.score) return clip.score;
    if (clip.virality_score != null) return `${Math.min(100, Math.round(clip.virality_score * 10))}%`;
    return '';
  };
  const fmtImg = (clip: any) => clip.img || '';

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

        {isLoading ? (
          <div className="flex items-center justify-center py-24 text-slate-400">
            <svg className="w-6 h-6 animate-spin mr-3" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
            <span className="text-[14px] font-medium">Memuat galeri...</span>
          </div>
        ) : clips.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-slate-400 gap-3">
            <svg className="w-16 h-16 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
            <p className="text-[14px] font-medium">Galeri masih kosong</p>
            <p className="text-[12px]">Proses klip di Dashboard, lalu klik "Simpan ke Gallery"</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {clips.map((clip) => {
              const img = fmtImg(clip);
              const duration = fmtDuration(clip);
              const score = fmtScore(clip);
              return (
                <div key={clip.path} className="bg-white rounded-2xl p-4 shadow-sm border border-slate-100 flex flex-col group hover:shadow-md transition">
                  <div className="relative w-full aspect-square bg-slate-900 rounded-xl overflow-hidden shadow-inner group">
                    {img ? (
                      <img src={img} alt={clip.title} className="w-full h-full object-cover opacity-90 group-hover:scale-105 transition-transform duration-500" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-slate-600">
                        <svg className="w-10 h-10 opacity-30" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                      </div>
                    )}
                    {duration && (
                      <div className="absolute top-1.5 right-1.5 bg-black/50 px-1.5 py-0.5 rounded text-[9px] font-medium text-white/90 border border-white/10">{duration}</div>
                    )}
                    {score && (
                      <div className="absolute top-1.5 left-1.5 bg-orange-500/90 backdrop-blur text-white px-1.5 py-0.5 rounded text-[10px] font-bold shadow-sm flex items-center gap-1 border border-orange-400/50">
                        <span className="text-[12px] leading-none">🔥</span> {score}
                      </div>
                    )}
                    {clip.isUploaded && (
                      <div className="absolute bottom-1.5 left-1.5 bg-emerald-500/90 backdrop-blur text-white px-2 py-0.5 rounded text-[10px] font-bold shadow-sm flex items-center gap-1 border border-emerald-400/50 z-10">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path></svg>
                        Uploaded
                      </div>
                    )}
                  </div>
                  
                  <div className="mt-3 text-left flex-1 flex flex-col">
                    <h4 className="font-bold text-[13px] leading-snug line-clamp-2 text-slate-900">{clip.title || clip.name}</h4>
                    <p className="text-[11px] text-slate-500 line-clamp-2 mt-1.5">{clip.description}</p>
                    <p className="text-[10px] text-slate-400 mt-2">Durasi: {duration}</p>
                  </div>
                  <button 
                    onClick={() => setShowDetailModal(clip)}
                    className="w-full mt-3 py-2 border border-slate-200 rounded-lg text-[12px] font-semibold text-slate-700 hover:bg-slate-50 transition"
                  >
                    Lihat detail
                  </button>
                </div>
              );
            })}
          </div>
        )}
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
              <video
                key={showDetailModal.path}
                className="w-full h-full object-contain"
                controls
                preload="metadata"
                poster={fmtImg(showDetailModal) || undefined}
                src={`/api/stream?path=${encodeURIComponent(showDetailModal.path)}`}
              />
            </div>
            
            {/* Right: Details */}
            <div className="flex-1 flex flex-col py-2 pr-4">
              <p className="text-[12px] text-slate-500 mb-1">Durasi: {fmtDuration(showDetailModal)}</p>
              <h2 className="text-[20px] font-bold text-slate-900 leading-tight">{showDetailModal.title || showDetailModal.name}</h2>
              {showDetailModal.isUploaded && (
                <a href="#" className="inline-flex items-center gap-1.5 text-[13px] text-emerald-500 hover:text-emerald-600 font-bold mt-2 hover:underline">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                  Tonton di YouTube
                </a>
              )}
              
              <p className="text-[12px] font-bold text-slate-700 mt-6 mb-2">Description</p>
              <div className="border border-slate-200 rounded-xl p-4 text-[13px] text-slate-600 bg-slate-50 min-h-[120px] leading-relaxed">
                {showDetailModal.description}
                <br/><br/>
                sc: @klipklop
              </div>
              
              <div className="mt-auto flex flex-wrap items-center gap-2 pt-6">
                <a 
                  href={`/api/download?path=${encodeURIComponent(showDetailModal.path)}`}
                  download
                  className="bg-[#ea580c] hover:bg-[#c2410c] text-white font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm border border-[#ea580c]"
                >Download</a>
                <button 
                  disabled={showDetailModal.isUploaded || uploadingId === showDetailModal.path}
                  onClick={() => handleUpload(showDetailModal)}
                  className={`font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm border ${
                    showDetailModal.isUploaded || uploadingId === showDetailModal.path
                      ? 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed'
                      : 'bg-white hover:bg-slate-50 text-slate-700 border-slate-200'
                  }`}
                >
                  {uploadingId === showDetailModal.path ? 'Uploading...' : showDetailModal.isUploaded ? 'Uploaded' : 'Upload'}
                </button>
                <button 
                  onClick={() => handleDelete(showDetailModal)}
                  className="bg-white border border-slate-200 hover:bg-red-50 hover:text-red-600 hover:border-red-200 text-slate-700 font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm"
                >Hapus</button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
