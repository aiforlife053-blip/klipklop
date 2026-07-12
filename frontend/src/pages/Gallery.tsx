import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { api } from '@/lib/api';

export default function Gallery() {
  const [showDetailModal, setShowDetailModal] = useState<any>(null);
  const [clips, setClips] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<any>(null);

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
    setDeleteConfirm(clip);
  };

  const confirmDelete = async () => {
    if (!deleteConfirm) return;
    const clip = deleteConfirm;
    setDeleteConfirm(null);
    try {
      await api('/api/delete', {
        method: 'POST',
        body: JSON.stringify({ path: clip.path }),
      });
      if (showDetailModal?.path === clip.path) {
        setShowDetailModal(null);
      }
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
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-6 py-10">
      <div className="flex flex-col gap-2">
        <p className="text-sm font-medium uppercase tracking-widest text-primary">Galeri</p>
        <h1 className="font-display text-3xl font-bold tracking-tight md:text-4xl">Koleksi Klip</h1>
        <p className="text-muted">Semua klip viral yang pernah Anda proses tersimpan di sini.</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-24 text-muted">
          <svg className="w-6 h-6 animate-spin mr-3 text-primary" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
          <span className="text-sm font-medium">Memuat galeri...</span>
        </div>
      ) : clips.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-muted gap-3">
          <svg className="w-16 h-16 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
          <p className="text-sm font-medium">Galeri masih kosong</p>
          <p className="text-xs">Proses klip di Dashboard, lalu klik "Simpan ke Gallery"</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {clips.map((clip) => {
            const img = fmtImg(clip);
            const duration = fmtDuration(clip);
            const score = fmtScore(clip);
            const date = clip.modified ? new Date(clip.modified).toLocaleString('id-ID', {day: 'numeric', month: 'short', year: '2-digit', hour: '2-digit', minute:'2-digit'}) : '-';
            
            return (
              <article key={clip.path} className="group flex flex-col overflow-hidden rounded-2xl border border-line bg-card transition-colors hover:border-primary/40">
                <button type="button" onClick={() => setShowDetailModal(clip)} className="relative aspect-[4/5] w-full overflow-hidden p-0 text-left" aria-label={`Lihat detail klip: ${clip.title}`}>
                   {img ? <img src={img} alt={`Thumbnail klip: ${clip.title}`} loading="lazy" className="size-full object-cover transition-transform duration-300 group-hover:scale-105" /> : <span className="block size-full bg-secondary" aria-hidden="true" />}
                  <span className="absolute inset-x-0 top-0 flex items-start justify-between p-3">
                    <span className="flex items-center gap-1.5 rounded-full bg-primary px-2.5 py-1 text-xs font-bold text-primary-foreground">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>
                      {score}
                    </span>
                    <span className="flex items-center gap-1 rounded-full bg-background/70 px-2.5 py-1 text-xs font-medium backdrop-blur">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                      {duration}
                    </span>
                  </span>
                  <span className="absolute inset-0 flex flex-col items-center justify-center gap-2.5 bg-background/60 opacity-0 transition-opacity group-hover:opacity-100">
                    <span className="flex size-11 items-center justify-center rounded-full bg-primary text-primary-foreground">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" className="ml-0.5"><polygon points="6 3 20 12 6 21 6 3"/></svg>
                    </span>
                    <span className="rounded-full bg-primary px-3.5 py-1 text-xs font-bold text-primary-foreground">Lihat Detail</span>
                  </span>
                  {clip.isUploaded && (
                    <span className="absolute bottom-2.5 left-2.5 z-[2] rounded-full bg-emerald-500/90 px-2.5 py-1 text-[10px] font-bold text-white backdrop-blur">Uploaded</span>
                  )}
                </button>
                <div className="flex flex-1 flex-col gap-1.5 p-3.5">
                  <h2 className="line-clamp-2 font-display text-sm font-bold leading-snug">{clip.title || clip.name}</h2>
                  <p className="mt-auto text-xs text-muted">{duration} &bull; {date}</p>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Modal detail klip */}
      {showDetailModal && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-8" role="dialog" aria-modal="true" aria-label="Detail klip">
          <button type="button" onClick={() => setShowDetailModal(null)} className="absolute inset-0 bg-background/80" aria-label="Tutup detail klip"></button>
          <div className="relative z-10 grid max-h-[90dvh] w-full max-w-3xl gap-6 overflow-y-auto rounded-2xl border border-line bg-card p-6 shadow-2xl md:grid-cols-[280px_1fr] md:p-8">
            <button type="button" onClick={() => setShowDetailModal(null)} className="absolute right-4 top-4 z-10 flex size-9 items-center justify-center rounded-full border border-line bg-secondary text-muted transition-colors hover:text-foreground" aria-label="Tutup">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
            <div className="relative mx-auto aspect-[9/16] w-full max-w-[280px] overflow-hidden rounded-xl border border-line bg-black">
              <video
                 className="absolute inset-0 size-full object-contain"

                controls
                preload="metadata"
                poster={fmtImg(showDetailModal) || undefined}
                src={`/api/stream?path=${encodeURIComponent(showDetailModal.path)}`}
              />
              <span className="pointer-events-none absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-primary px-2.5 py-1 text-xs font-bold text-primary-foreground">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>
                <span>{fmtScore(showDetailModal)}</span>
              </span>
            </div>
            <div className="flex flex-col gap-5 md:pr-8">
              <p className="text-sm text-muted">Durasi: {fmtDuration(showDetailModal)}</p>
              <h2 className="font-display text-[1.75rem] font-bold leading-tight tracking-tight">{showDetailModal.title || showDetailModal.name}</h2>
              <div className="flex flex-col gap-2">
                <h3 className="text-sm font-bold">Description</h3>
                <div className="flex flex-col gap-3 rounded-xl border border-line bg-secondary/50 p-4 text-sm leading-relaxed text-muted">
                  <p>{showDetailModal.description}</p>
                </div>
              </div>
              <div className="mt-auto flex flex-wrap gap-3 pt-4">
                <button type="button" onClick={() => window.open(`/api/download?path=${encodeURIComponent(showDetailModal.path)}`, '_blank')} className="flex h-11 items-center gap-2 rounded-xl bg-primary px-5 text-sm font-bold text-primary-foreground transition-opacity hover:opacity-90">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                  Download
                </button>
                <button type="button" disabled={uploadingId === showDetailModal.path} onClick={() => handleUpload(showDetailModal)} className="flex h-11 items-center gap-2 rounded-xl border border-line bg-secondary px-5 text-sm font-medium transition-colors hover:bg-secondary/70 disabled:opacity-50">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/></svg>
                  {uploadingId === showDetailModal.path ? 'Uploading...' : 'Upload YouTube'}
                </button>
                <button type="button" onClick={() => handleDelete(showDetailModal)} className="flex h-11 items-center gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-5 text-sm font-medium text-destructive transition-colors hover:bg-destructive/20">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/></svg>
                  Hapus
                </button>
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}

      {deleteConfirm && createPortal(
        <div className="fixed inset-0 z-[101] flex items-center justify-center p-4 bg-background/80" onClick={() => setDeleteConfirm(null)}>
          <div className="bg-card rounded-2xl w-full max-w-sm overflow-hidden border border-line p-6 flex flex-col gap-4 text-center" onClick={e => e.stopPropagation()}>
             <h3 className="font-display font-bold text-lg">Hapus Klip ini?</h3>
             <p className="text-sm text-muted">Klip yang dihapus tidak bisa dikembalikan lagi.</p>
             <div className="flex gap-3 justify-center mt-2">
               <button onClick={() => setDeleteConfirm(null)} className="px-5 py-2 rounded-xl font-medium border border-line text-foreground hover:bg-secondary">Batal</button>
               <button onClick={confirmDelete} className="px-5 py-2 rounded-xl font-medium bg-destructive text-destructive-foreground">Hapus</button>
             </div>
          </div>
        </div>,
        document.body
      )}
    </main>
  );
}
