import React, { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import { Link } from 'react-router-dom';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    const pendingToast = sessionStorage.getItem('klipklop_toast');
    if (pendingToast) {
      sessionStorage.removeItem('klipklop_toast');
      console.log(pendingToast);
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      await api('/api/login', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      sessionStorage.setItem('klipklop_toast', 'Berhasil login');
      window.location.href = '/';
    } catch (err: any) {
      setError(err.message || 'Gagal');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-svh bg-background font-sans text-foreground antialiased">
      <main className="flex min-h-svh flex-col lg:flex-row">
        {/* Left: hero */}
        <section className="relative flex flex-1 flex-col justify-between gap-12 overflow-hidden border-b border-line bg-card/50 p-8 lg:border-b-0 lg:border-r lg:p-14" aria-label="Tentang KlipKlop">
          <div className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full bg-primary/15 blur-3xl" aria-hidden="true"></div>
          <div className="pointer-events-none absolute -bottom-40 -left-24 h-80 w-80 rounded-full bg-primary/10 blur-3xl" aria-hidden="true"></div>
          <div className="pointer-events-none absolute inset-0 opacity-15 [background-image:radial-gradient(circle,#a39e93_1px,transparent_1px)] [background-size:28px_28px]" aria-hidden="true"></div>

          <Link to="/" className="relative flex w-fit items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="6" cy="6" r="3"/><path d="M8.12 8.12 12 12"/><path d="M20 4 8.12 15.88"/><circle cx="6" cy="18" r="3"/><path d="M14.8 14.8 20 20"/></svg>
            </span>
            <span className="font-display text-xl font-bold">KlipKlop</span>
          </Link>

          <div className="relative flex flex-col gap-6">
            <span className="inline-flex w-fit items-center gap-2 rounded-full border border-primary/40 bg-primary/10 px-4 py-1.5 text-xs font-bold text-primary">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/></svg>
              AI Klip Generator
            </span>
            <h2 className="font-display text-4xl font-bold leading-[1.15] text-balance lg:text-5xl">Upload videomu, biar KlipKlop cari momen <span className="italic text-primary">terbaiknya.</span></h2>

            <dl className="flex max-w-md items-center justify-between gap-4 border-t border-line pt-6">
              <div className="flex flex-col gap-1">
                <dd className="m-0 font-display text-2xl font-bold text-primary">12K+</dd>
                <dt className="text-xs text-muted">Klip dihasilkan</dt>
              </div>
              <div className="flex flex-col gap-1">
                <dd className="m-0 font-display text-2xl font-bold text-primary">92%</dd>
                <dt className="text-xs text-muted">Skor viral tertinggi</dt>
              </div>
              <div className="flex flex-col gap-1">
                <dd className="m-0 font-display text-2xl font-bold text-primary">3 mnt</dd>
                <dt className="text-xs text-muted">Rata-rata proses</dt>
              </div>
            </dl>
          </div>

          <p className="relative text-xs text-muted">KlipKlop Web</p>
        </section>

        {/* Right: auth form */}
        <section className="flex flex-1 items-center justify-center p-8 lg:p-14" aria-label="Formulir masuk">
          <div className="flex w-full max-w-md flex-col gap-6 rounded-2xl border border-line bg-card p-8">
            <div className="flex flex-col gap-2">
              <h1 className="font-display text-2xl font-bold">Masuk</h1>
              <p className="text-sm leading-relaxed text-muted">Lanjutkan ke dashboard KlipKlop.</p>
            </div>

            <form className="flex flex-col gap-4" onSubmit={handleSubmit}>

              <div className="flex flex-col gap-2">
                <label htmlFor="auth-email" className="text-sm font-medium">Email</label>
                <input 
                  id="auth-email" 
                  type="email" 
                  placeholder="nama@email.com" 
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="h-11 w-full rounded-xl border border-line bg-secondary px-4 text-sm text-foreground placeholder:text-muted focus:border-transparent focus:outline-none focus:ring-2 focus:ring-primary" 
                />
              </div>

              <div className="flex flex-col gap-2">
                <label htmlFor="auth-password" className="text-sm font-medium">Password</label>
                <div className="relative">
                  <input 
                    id="auth-password" 
                    type={showPassword ? 'text' : 'password'}
                    placeholder="Minimal 6 karakter" 
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    className="h-11 w-full rounded-xl border border-line bg-secondary pl-4 pr-11 text-sm text-foreground placeholder:text-muted focus:border-transparent focus:outline-none focus:ring-2 focus:ring-primary" 
                  />
                  <button 
                    type="button" 
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 flex -translate-y-1/2 p-1 text-muted transition-colors hover:text-foreground" 
                    aria-label="Tampilkan password"
                  >
                    {!showPassword ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/></svg>
                    )}
                  </button>
                </div>
              </div>

              <div className="flex justify-end">
                <button type="button" className="p-0 text-xs font-medium text-primary transition-opacity hover:opacity-80">Lupa password?</button>
              </div>

              {error && (
                <div className="rounded-lg bg-destructive/10 p-3 text-sm font-medium text-destructive border border-destructive/20">
                  {error}
                </div>
              )}

              <button 
                type="submit" 
                disabled={isLoading}
                className="mt-2 flex h-12 items-center justify-center gap-2 rounded-xl bg-primary font-display text-base font-bold text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {isLoading ? (
                  <span>Memproses...</span>
                ) : (
                  <>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m10 17 5-5-5-5"/><path d="M15 12H3"/><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/></svg>
                    <span>Masuk</span>
                  </>
                )}
              </button>
            </form>

            <p className="text-center text-xs leading-relaxed text-muted">Dengan melanjutkan, kamu menyetujui <a href="#" className="font-medium text-foreground hover:underline hover:underline-offset-2">Syarat & Ketentuan</a> KlipKlop.</p>
          </div>
        </section>
      </main>
    </div>
  );
}
