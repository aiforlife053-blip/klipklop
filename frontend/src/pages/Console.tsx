import { useEffect, useRef } from 'react';
import { useOutletContext } from 'react-router-dom';
import type { DashboardOutletContext } from '@/components/layout/DashboardLayout';
import { api } from '@/lib/api';

export default function Console() {
  const { status, refreshStatus } = useOutletContext<DashboardOutletContext>();
  const logs = Array.isArray(status?.logs) ? status.logs.slice(-200) : [];
  const logsEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  const handleClear = async () => {
    try {
      await api('/api/logs/clear', { method: 'POST', body: JSON.stringify({}) });
      await refreshStatus();
    } catch (error) {
      console.error('Failed to clear logs', error);
    }
  };

  return (
    <main className="mx-auto flex h-full min-h-[calc(100vh-53px)] w-full max-w-5xl flex-col gap-8 px-6 py-10">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-2">
          <p className="text-sm font-medium uppercase tracking-widest text-primary">Konsol</p>
          <h1 className="font-display text-3xl font-bold tracking-tight md:text-4xl">Log Pemrosesan</h1>
          <p className="leading-relaxed text-muted">Pantau aktivitas pipeline KlipKlop secara real-time.</p>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <span className="rounded-xl border border-primary/40 bg-primary/10 px-4 py-2 text-sm font-bold text-primary">Live</span>
          <button type="button" onClick={handleClear} className="rounded-xl border border-line px-4 py-2 text-sm font-medium text-muted transition-colors hover:bg-secondary hover:text-foreground">
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
              <li className="italic text-muted">Menunggu log pemrosesan...</li>
            ) : (
              logs.map((log, index) => {
                const isError = log.includes('[Error]') || log.includes('❌') || log.toLowerCase().includes('error');
                const isSuccess = log.includes('[Done]') || log.includes('✅') || log.includes('Complete');
                const level = isError ? 'error' : isSuccess ? 'success' : 'info';
                const levelClass = isError ? 'text-destructive font-bold' : isSuccess ? 'text-primary font-bold' : 'text-muted';

                return (
                  <li key={index} className="flex flex-col gap-2 rounded-lg px-2 py-1.5 hover:bg-secondary/50 sm:flex-row sm:gap-4">
                    <span className={`min-w-[70px] shrink-0 uppercase ${levelClass}`}>{level}</span>
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
