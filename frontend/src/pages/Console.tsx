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
    <main className="mx-auto flex max-w-5xl flex-col gap-8 px-6 py-10 w-full h-full min-h-[calc(100vh-53px)]">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium uppercase tracking-widest text-primary">Konsol</p>
          <h1 className="font-display text-3xl font-bold tracking-tight md:text-4xl">Log Pemrosesan</h1>
          <p className="leading-relaxed text-muted">Pantau aktivitas pipeline KlipKlop secara real-time.</p>
        </div>
        <div className="flex items-center gap-2 mt-2">
          <button
            type="button"
            onClick={() => setIsPolling(p => !p)}
            className={`rounded-xl border px-4 py-2 text-sm font-bold transition-colors ${isPolling ? 'border-primary/40 bg-primary/10 text-primary hover:bg-primary/20' : 'border-line bg-secondary text-muted hover:text-foreground'}`}
          >
            {isPolling ? 'Live Polling Aktif' : 'Polling Berhenti'}
          </button>
          <button type="button" onClick={handleClear} className="rounded-xl border border-line px-4 py-2 text-sm font-medium text-muted hover:bg-secondary hover:text-foreground transition-colors">
            Clear
          </button>
        </div>
      </div>

      <section className="flex max-h-[min(620px,calc(100vh-220px))] min-h-[360px] flex-col overflow-hidden rounded-2xl border border-line bg-card" aria-label="Log konsol">
        <div className="flex items-center gap-2 border-b border-line bg-secondary/50 px-5 py-3">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f2a33c" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/></svg>
          <span className="font-mono text-xs text-muted">klipklop — pipeline.log</span>
        </div>
        <div className="min-h-0 flex-1 overflow-auto overscroll-contain p-5">
          <ul className="flex list-none flex-col gap-1 font-mono text-sm">
            {logs.length === 0 ? (
              <li className="text-muted italic">Menunggu log pemrosesan...</li>
            ) : (
              logs.map((log, i) => {
                const isError = log.includes('[Error]') || log.includes('❌') || log.toLowerCase().includes('error');
                const isSuccess = log.includes('[Done]') || log.includes('✅') || log.includes('Complete');
                
                let level = 'info';
                let levelClass = 'text-muted';
                
                if (isError) {
                  level = 'error';
                  levelClass = 'text-destructive font-bold';
                } else if (isSuccess) {
                  level = 'success';
                  levelClass = 'text-primary font-bold';
                }

                return (
                  <li key={i} className="flex flex-col sm:flex-row gap-2 sm:gap-4 rounded-lg px-2 py-1.5 hover:bg-secondary/50">
                    <span className={`shrink-0 uppercase ${levelClass} min-w-[70px]`}>{level}</span>
                    <span className="min-w-0 flex-1 whitespace-pre-wrap break-all leading-relaxed text-foreground/90">{log}</span>
                  </li>
                );
              })
            )}
            <div ref={logsEndRef} />
          </ul>
        </div>
      </section>
    </main>
  );
}
