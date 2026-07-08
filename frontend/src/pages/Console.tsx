import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '@/lib/api';

export default function Console() {
  const [logs, setLogs] = useState<string[]>([]);
  const [isPolling, setIsPolling] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      const data = await api('/api/status');
      if (data.logs && Array.isArray(data.logs)) {
        setLogs(data.logs.slice(-200));
      }
    } catch (e) {
      console.error('Failed to fetch logs', e);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  useEffect(() => {
    if (isPolling) {
      pollingRef.current = setInterval(fetchLogs, 2000);
    } else {
      if (pollingRef.current) clearInterval(pollingRef.current);
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [isPolling, fetchLogs]);

  // Auto-scroll to bottom when logs update
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleClear = async () => {
    try {
      await api('/api/logs/clear', { method: 'POST', body: JSON.stringify({}) });
      setLogs([]);
    } catch (e) {
      console.error('Failed to clear logs', e);
    }
  };

  return (
    <div className="p-6 space-y-7 bg-muted flex-1 h-[calc(100vh-53px)] overflow-auto" style={{ backgroundImage: 'radial-gradient(rgba(0, 0, 0, 0.05) 1.5px, transparent 1.5px)', backgroundSize: '20px 20px', backgroundPosition: '10px 10px' }}>
      <section className="bg-transparent min-h-[460px] flex flex-col gap-5 w-full">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-[20px] font-semibold text-black mb-0.5 tracking-tight">Konsol</h2>
            <p className="text-[13px] text-gray-500">Log pemrosesan sistem.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsPolling(p => !p)}
              className={`rounded-xl border px-4 py-2 text-[13px] font-semibold transition ${isPolling ? 'border-orange-300 bg-orange-50 text-orange-600 hover:bg-orange-100' : 'border-gray-200 bg-white text-gray-700 hover:bg-gray-50'}`}
            >
              {isPolling ? '⏸ Live' : '▶ Paused'}
            </button>
            <button type="button" onClick={handleClear} className="rounded-xl border border-gray-200 px-4 py-2 text-[13px] font-semibold text-gray-700 hover:bg-gray-50 bg-white">
              Clear
            </button>
          </div>
        </div>
        <div className="min-h-[360px] max-h-[70vh] overflow-auto rounded-2xl bg-[#0f172a] border border-gray-200 p-4 font-mono text-[12px] leading-relaxed">
          {logs.length === 0 ? (
            <p className="text-slate-500 italic">Console output akan muncul di sini saat proses berjalan...</p>
          ) : (
            logs.map((log, i) => {
              // Color-code log lines by level
              const isError = log.includes('[Error]') || log.includes('❌');
              const isDone = log.includes('[Done]') || log.includes('✅') || log.includes('Complete');
              const isTask = log.includes('[Task]');
              let colorClass = 'text-slate-300';
              if (isError) colorClass = 'text-red-400';
              else if (isDone) colorClass = 'text-emerald-400';
              else if (isTask) colorClass = 'text-yellow-300 font-bold';
              return (
                <div key={i} className={`${colorClass} whitespace-pre-wrap break-words`}>
                  {log}
                </div>
              );
            })
          )}
          <div ref={logsEndRef} />
        </div>
        {isPolling && (
          <p className="text-[11px] text-gray-400 flex items-center gap-1.5">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            Memperbarui setiap 2 detik
          </p>
        )}
      </section>
    </div>
  );
}
