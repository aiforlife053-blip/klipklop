import { useState, useEffect, useRef, useCallback } from 'react';
import { useOutletContext } from 'react-router-dom';
import { createPortal } from 'react-dom';
import { api } from '@/lib/api';

export default function Dashboard() {
  const { status: globalStatus, settings } = useOutletContext<any>();
  const [youtubeUrl, setYoutubeUrl] = useState('');
  const [videoQuality, setVideoQuality] = useState('720');
  const [numClips, setNumClips] = useState(1);
  const [landscapeBlur, setLandscapeBlur] = useState(true);
  const [showJsonModal, setShowJsonModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState<any>(null);
  const [showInstructionModal, setShowInstructionModal] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [toastMessage, setToastMessage] = useState('');

  // Real state
  const [isProcessing, setIsProcessing] = useState(false);
  const [jobStatus, setJobStatus] = useState<any>(null);
  const [clips, setClips] = useState<any[]>([]);
  const [logs, setLogs] = useState<string[]>([]);
  const [error, setError] = useState('');
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);


  // Derive current status string
  const currentStatus = jobStatus?.status || globalStatus?.status || 'idle';
  const currentProgress = jobStatus?.progress ?? 0;

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const fetchOutputs = useCallback(async () => {
    try {
      const data = await api('/api/outputs');
      const allClips: any[] = [];
      (data.groups || []).forEach((group: any) => {
        if (group.saved) return;
        (group.clips || group.files || []).forEach((clip: any) => {
          allClips.push({ ...clip, groupPath: group.path, saved: group.saved });
        });
      });
      setClips(allClips);
    } catch (e) {
      console.error('Failed to fetch outputs', e);
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollingRef.current = setInterval(async () => {
      try {
        const data = await api('/api/status');
        setJobStatus(data);
        if (data.logs) setLogs(data.logs.slice(-100));
        if (data.status === 'complete') {
          stopPolling();
          setIsProcessing(false);
          await fetchOutputs();
        } else if (data.status === 'error' || data.status === 'idle') {
          stopPolling();
          setIsProcessing(false);
          if (data.status === 'error') setError(data.error || data.message || 'Terjadi kesalahan');
        }
      } catch (e) {
        console.error('Polling error', e);
      }
    }, 1500);
  }, [stopPolling, fetchOutputs]);

  // On mount: check current status and fetch any existing outputs
  useEffect(() => {
    const init = async () => {
      try {
        const data = await api('/api/status');
        setJobStatus(data);
        if (data.logs) setLogs(data.logs.slice(-100));
        if (data.status === 'running' || data.status === 'stopping') {
          setIsProcessing(true);
          startPolling();
        } else {
          await fetchOutputs();
        }
      } catch (e) {
        console.error('Init failed', e);
      }
    };
    init();
    return () => stopPolling();
  }, []);



  const handleProcessClip = async () => {
    if (!youtubeUrl.trim()) {
      alert('Masukkan URL YouTube terlebih dahulu.');
      return;
    }
    setError('');
    setClips([]);
    setLogs([]);
    setIsProcessing(true);
    try {
      const result = await api('/api/start', {
        method: 'POST',
        body: JSON.stringify({
          url: youtubeUrl.trim(),
          num_clips: numClips,
          add_captions: settings?.subtitle?.enabled ?? true,
          enable_captions: settings?.subtitle?.enabled ?? true,
          add_hook: settings?.hook_style?.enabled ?? false,
          hook_mode: settings?.hook_style?.enabled ?? false,
          screen_size: '9:16',
          subtitle_language: settings?.subtitle_language || 'id',
          landscape_blur: landscapeBlur,
          source_credit: settings?.credit_watermark?.enabled ?? true,
          instruction: instruction,
        }),
      });
      if (result.status === 'error') {
        setError(result.message || 'Gagal memulai proses.');
        setIsProcessing(false);
        return;
      }
      startPolling();
    } catch (e: any) {
      setError(e.message || 'Gagal memulai proses.');
      setIsProcessing(false);
    }
  };

  const handleStop = async () => {
    try {
      await api('/api/stop', { method: 'POST', body: JSON.stringify({}) });
    } catch (e) {
      console.error('Stop failed', e);
    }
  };

  const handleSave = async (clip: any) => {
    setIsSaving(true);
    console.log('[Dashboard] Menyimpan klip ke galeri:', clip);
    try {
      await api('/api/save', {
        method: 'POST',
        body: JSON.stringify({ path: clip.groupPath, clips: [clip.path] }),
      });
      console.log('[Dashboard] Berhasil menyimpan klip:', clip.path);
      
      // Delay sedikit agar user merasa ini berproses (tidak terlalu instan/patah)
      await new Promise(r => setTimeout(r, 600)); 
      
      setToastMessage('Klip berhasil disimpan ke Galeri! 🎉');
      setTimeout(() => setToastMessage(''), 3000);
      
      setShowDetailModal(null);
      setClips(prev => prev.filter(c => c.path !== clip.path));
    } catch (e: any) {
      console.error('[Dashboard] Gagal menyimpan klip:', e);
      alert('Gagal menyimpan: ' + (e.message || ''));
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (clip: any) => {
    if (!confirm('Hapus klip ini?')) return;
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
    const clipId = clip.path;
    if (uploadProgress[clipId] !== undefined) return;
    setUploadProgress(prev => ({ ...prev, [clipId]: 0 }));
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
        setUploadProgress(prev => ({ ...prev, [clipId]: 100 }));
      } else {
        alert('Upload gagal: ' + (result.message || ''));
        setUploadProgress(prev => { const n = { ...prev }; delete n[clipId]; return n; });
      }
    } catch (e: any) {
      alert('Upload gagal: ' + (e.message || ''));
      setUploadProgress(prev => { const n = { ...prev }; delete n[clipId]; return n; });
    }
  };

  // Helper: format duration display
  const fmtDuration = (clip: any) => {
    if (clip.duration) return clip.duration;
    if (clip.duration_seconds != null) return `${Math.round(clip.duration_seconds)}s`;
    return '';
  };

  // Helper: format score display
  const fmtScore = (clip: any) => {
    if (clip.score) return clip.score;
    if (clip.virality_score != null) return `${Math.min(100, Math.round(clip.virality_score * 10))}%`;
    return '';
  };

  // Helper: get thumbnail img src
  const fmtImg = (clip: any) => {
    return clip.img || '';
  };

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

        <div className="w-full max-w-5xl mx-auto space-y-3 mt-1 pb-4">
          <div className="text-center mb-2">
            <h3 className="text-[18px] font-bold text-slate-900 tracking-tight">Hasil Generasi Klip</h3>
            <p className="text-[12px] text-slate-500 mt-0.5">
              {currentStatus === 'idle' && clips.length === 0 && 'Masukkan URL YouTube lalu klik Proses Klip.'}
              {currentStatus === 'error' && `Error: ${error}`}
              {currentStatus === 'idle' && clips.length > 0 && 'Klip siap. Simpan atau hapus sebelum proses baru.'}
            </p>
          </div>

          {/* Professional Loading Animation — tampil saat running, stopping, complete, DAN idle+ada klip */}
          {(currentStatus === 'running' || currentStatus === 'stopping' || (currentStatus === 'complete' && clips.length > 0) || (currentStatus === 'idle' && clips.length > 0)) && (() => {
            const isComplete = currentStatus === 'complete' || (currentStatus === 'idle' && clips.length > 0);
            const displayProgress = isComplete ? 1 : currentProgress;
            return (
              <div className="flex flex-col items-center justify-center py-2 gap-3">
                {/* Circular progress */}
                <div className="relative w-28 h-28">
                  {/* Outer glow ring */}
                  <div className={`absolute inset-0 rounded-full ${isComplete ? 'bg-gradient-to-tr from-emerald-400/20 to-emerald-600/10' : 'bg-gradient-to-tr from-orange-400/20 to-orange-600/10 animate-pulse'}`} />
                  <svg className="w-full h-full -rotate-90" viewBox="0 0 144 144">
                    {/* Track */}
                    <circle cx="72" cy="72" r="60" fill="none" stroke="#f1f5f9" strokeWidth="10" />
                    {/* Progress arc */}
                    <circle
                      cx="72" cy="72" r="60"
                      fill="none"
                      stroke={isComplete ? 'url(#completeGrad)' : 'url(#progressGrad)'}
                      strokeWidth="10"
                      strokeLinecap="round"
                      strokeDasharray={`${2 * Math.PI * 60}`}
                      strokeDashoffset={`${2 * Math.PI * 60 * (1 - displayProgress)}`}
                      style={{ transition: 'stroke-dashoffset 0.6s cubic-bezier(0.4,0,0.2,1)' }}
                    />
                    <defs>
                      <linearGradient id="progressGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#f97316" />
                        <stop offset="100%" stopColor="#ea580c" />
                      </linearGradient>
                      <linearGradient id="completeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#10b981" />
                        <stop offset="100%" stopColor="#059669" />
                      </linearGradient>
                    </defs>
                  </svg>
                  {/* Center text */}
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    {isComplete ? (
                      <span className="text-[32px]">✅</span>
                    ) : (
                      <span className="text-[22px] font-black text-slate-900 leading-none tabular-nums">
                        {Math.round(displayProgress * 100)}<span className="text-[14px] font-bold text-orange-500">%</span>
                      </span>
                    )}
                  </div>
                </div>

                {/* Step label */}
                <div className="text-center space-y-0.5">
                  <p className={`text-[13px] font-semibold ${isComplete ? 'text-emerald-600' : 'text-slate-800'}`}>
                    {isComplete
                      ? `🎉 ${clips.length} klip berhasil dibuat!`
                      : currentStatus === 'stopping'
                      ? '⏹ Menghentikan proses...'
                      : (jobStatus?.message || 'Memproses video...')}
                  </p>
                  <p className="text-[11px] text-slate-400">
                    {isComplete ? 'Klip siap di bawah. Simpan atau download.' : 'Harap tunggu, jangan tutup halaman ini'}
                  </p>
                </div>

                {/* Step indicators */}
                <div className="flex items-center gap-2">
                  {[
                    { label: 'Download', pct: 0.2 },
                    { label: 'Analisis AI', pct: 0.55 },
                    { label: 'Render', pct: 0.85 },
                    { label: 'Selesai', pct: 1 },
                  ].map((step, i) => {
                    const done = displayProgress >= step.pct;
                    const active = !done && (i === 0 ? true : displayProgress >= [0, 0.2, 0.55, 0.85][i]);
                    return (
                      <div key={i} className="flex items-center gap-2">
                        {i > 0 && <div className={`w-8 h-px transition-colors duration-500 ${displayProgress >= [0, 0.2, 0.55, 0.85][i] ? (isComplete ? 'bg-emerald-400' : 'bg-orange-400') : 'bg-slate-200'}`} />}
                        <div className="flex flex-col items-center gap-1">
                          <div className={`w-6 h-6 rounded-full flex items-center justify-center transition-all duration-500 ${
                            done
                              ? isComplete ? 'bg-emerald-500 shadow-md shadow-emerald-200' : 'bg-orange-500 shadow-md shadow-orange-200'
                              : active ? 'bg-orange-100 border-2 border-orange-400 animate-pulse'
                              : 'bg-slate-100 border border-slate-200'
                          }`}>
                            {done ? (
                              <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7"/></svg>
                            ) : (
                              <span className={`text-[9px] font-bold ${active ? 'text-orange-500' : 'text-slate-400'}`}>{i + 1}</span>
                            )}
                          </div>
                          <span className={`text-[10px] font-semibold whitespace-nowrap ${
                            done ? (isComplete ? 'text-emerald-500' : 'text-orange-500') : active ? 'text-slate-700' : 'text-slate-400'
                          }`}>{step.label}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Skeleton saat masih loading / Klip asli saat complete */}
                <div className={`w-full grid gap-3 mt-1 ${
                  numClips === 1 ? 'grid-cols-1 max-w-xs mx-auto' :
                  numClips === 2 ? 'grid-cols-2' :
                  'grid-cols-3'
                }`}>
                  {isComplete
                    ? null  /* klip real ditampilkan di bawah blok ini */
                    : Array.from({ length: numClips }).map((_, i) => (
                        <div key={i} className="rounded-xl overflow-hidden bg-white border border-slate-100 shadow-sm">
                          <div className="w-full aspect-[4/3] bg-gradient-to-r from-slate-100 via-slate-50 to-slate-100 bg-[length:200%_100%] animate-[shimmer_1.5s_infinite]" />
                          <div className="p-2.5 space-y-1.5">
                            <div className="h-2.5 rounded-full bg-gradient-to-r from-slate-100 via-slate-50 to-slate-100 bg-[length:200%_100%] animate-[shimmer_1.5s_infinite]" />
                            <div className="h-2 w-2/3 rounded-full bg-gradient-to-r from-slate-100 via-slate-50 to-slate-100 bg-[length:200%_100%] animate-[shimmer_1.5s_infinite]" />
                          </div>
                        </div>
                      ))
                  }
                </div>
              </div>
            );
          })()}


          {/* Clips grid — muncul di bawah loading saat proses & setelah selesai */}
          {clips.length > 0 && (
            <div className={`grid gap-4 mt-2 ${
              clips.length === 1 ? 'grid-cols-1 max-w-xs mx-auto' :
              clips.length === 2 ? 'grid-cols-2' :
              'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3'
            }`}>
              {clips.map((clip, idx) => {
                const clipId = clip.path;
                const img = fmtImg(clip);
                const duration = fmtDuration(clip);
                const score = fmtScore(clip);
                return (
                  <div key={clipId || idx} className="relative bg-white rounded-xl p-3 shadow-sm border border-slate-100 flex flex-col group hover:shadow-md transition overflow-hidden pb-3.5">
                    <div className="relative w-full aspect-[4/3] bg-slate-900 rounded-lg overflow-hidden shadow-inner group">
                      {img ? (
                        <img src={img} alt="Thumbnail" className="w-full h-full object-cover opacity-90 group-hover:scale-105 transition-transform duration-500" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-slate-600">
                          <svg className="w-8 h-8 opacity-30" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
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
                      {uploadProgress[clipId] === 100 && (
                        <div className="absolute bottom-1.5 left-1.5 bg-emerald-500/90 backdrop-blur text-white px-2 py-0.5 rounded text-[10px] font-bold shadow-sm flex items-center gap-1 border border-emerald-400/50 z-10">
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path></svg>
                          Uploaded
                        </div>
                      )}
                    </div>
                    <div className="mt-2 text-left flex-1 flex flex-col">
                      <h4 className="font-bold text-[12px] leading-snug line-clamp-1 text-slate-900">{clip.title || clip.name}</h4>
                      <p className="text-[11px] text-slate-500 line-clamp-1 mt-1">{clip.description}</p>
                    </div>
                    <button 
                      onClick={() => setShowDetailModal(clip)}
                      className="w-full mt-2 py-1.5 border border-slate-200 rounded-lg text-[11px] font-semibold text-slate-700 hover:bg-slate-50 transition"
                    >
                      Lihat detail
                    </button>

                    {uploadProgress[clipId] !== undefined && (
                      <>
                        <div className="absolute bottom-0 left-0 w-full h-1.5 bg-slate-100">
                          <div 
                            className="h-full bg-blue-500 transition-all duration-200" 
                            style={{ width: `${uploadProgress[clipId]}%` }}
                          />
                        </div>
                        <div className="text-center text-[10px] font-bold text-blue-600 mt-2">
                          {uploadProgress[clipId] === 100 ? 'Selesai (100%)' : `Uploading ${uploadProgress[clipId]}%`}
                        </div>
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Empty state */}
          {clips.length === 0 && (currentStatus === 'idle' || currentStatus === 'complete') && (
            <div className="flex flex-col items-center justify-center mt-20 text-slate-400 gap-3">
              <svg className="w-20 h-20 opacity-20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h10a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z"/></svg>
              <p className="text-[16px] font-bold text-slate-500">Belum ada klip</p>
              <p className="text-[13px] text-slate-400 text-center max-w-sm leading-relaxed">Masukkan URL YouTube di sebelah kiri lalu klik <strong className="font-bold">Proses Klip</strong> untuk mulai membuat video vertikal.</p>
            </div>
          )}
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
                disabled={isProcessing}
                className="w-full px-3.5 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 text-[13px] text-gray-700 bg-white disabled:opacity-50" 
              />
              <p className="text-[11px] text-gray-400 mt-1">Durasi optimal: 5 - 120 menit.</p>
            </div>

            <div>
              <label className="block text-[12px] font-semibold text-black mb-1.5">Kualitas Video</label>
              <select 
                value={videoQuality}
                onChange={(e) => setVideoQuality(e.target.value)}
                disabled={isProcessing}
                className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-[13px] bg-white focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 disabled:opacity-50"
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
                disabled={isProcessing}
                className="w-full px-3 py-2.5 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-orange-500/20 focus:border-orange-500 text-[13px] text-gray-700 bg-white disabled:opacity-50" 
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
                  <input type="checkbox" className="sr-only peer" checked={landscapeBlur} onChange={() => setLandscapeBlur(!landscapeBlur)} disabled={isProcessing} />
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
          {error && (
            <div className="mb-3 text-[12px] text-red-600 bg-red-50 border border-red-100 rounded-xl px-3 py-2">
              {error}
            </div>
          )}
          <div className="flex gap-2 mb-3">
            <button 
              className="flex-1 bg-primary hover:bg-orange-700 text-white font-semibold py-2.5 rounded-xl text-[14px] transition shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={handleProcessClip}
              disabled={isProcessing}
            >
              {isProcessing ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                  Memproses...
                </span>
              ) : 'Proses Klip'}
            </button>
            {isProcessing && (
              <button 
                className="flex-none bg-red-500 hover:bg-red-600 text-white p-2.5 rounded-xl transition shadow-sm flex items-center justify-center group" 
                title="Berhenti"
                onClick={handleStop}
              >
                <svg className="w-5 h-5 group-hover:scale-110 transition-transform" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z"/></svg>
              </button>
            )}
          </div>
          <div className="text-[12px] text-gray-500 mt-2">
            Status: {currentStatus === 'running' ? `Berjalan (${Math.round(currentProgress * 100)}%)` : currentStatus === 'complete' ? 'Selesai' : currentStatus === 'error' ? 'Error' : currentStatus === 'stopping' ? 'Menghentikan...' : 'Idle'}
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
              {uploadProgress[showDetailModal.path] === 100 && (
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
                <button 
                  onClick={() => handleSave(showDetailModal)}
                  disabled={isSaving}
                  className="bg-[#ea580c] hover:bg-[#c2410c] text-white font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm border border-[#ea580c] flex items-center gap-2 disabled:opacity-70 disabled:cursor-wait"
                >
                  {isSaving && (
                    <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                    </svg>
                  )}
                  {isSaving ? 'Menyimpan...' : 'Simpan ke Gallery'}
                </button>
                <a 
                  href={`/api/download?path=${encodeURIComponent(showDetailModal.path)}`}
                  download
                  className="bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm"
                >Download</a>
                <button 
                  onClick={() => handleUpload(showDetailModal)}
                  disabled={uploadProgress[showDetailModal.path] !== undefined}
                  className={`font-semibold py-2.5 px-4 rounded-xl text-[13px] transition shadow-sm border ${
                    uploadProgress[showDetailModal.path] !== undefined
                      ? 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed'
                      : 'bg-white border-slate-200 hover:bg-slate-50 text-slate-700'
                  }`}
                >
                  {uploadProgress[showDetailModal.path] !== undefined 
                    ? (uploadProgress[showDetailModal.path] === 100 ? 'Uploaded' : `Uploading...`) 
                    : 'Upload'}
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

      {/* Toast Notification */}
      {toastMessage && createPortal(
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[9999] animate-in slide-in-from-bottom-5 fade-in duration-300">
          <div className="bg-slate-900 text-white px-5 py-3 rounded-full shadow-2xl shadow-slate-900/20 text-[13px] font-medium flex items-center gap-3">
            <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            {toastMessage}
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
