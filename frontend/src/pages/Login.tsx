import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { api } from '@/lib/api';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const pendingToast = sessionStorage.getItem('klipklop_toast');
    if (pendingToast) {
      sessionStorage.removeItem('klipklop_toast');
      console.log(pendingToast);
    }
  }, []);

  const handleSubmit = async (mode: 'login' | 'signup', e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      await api(mode === 'login' ? '/api/login' : '/api/signup', {
        method: 'POST',
        body: JSON.stringify({ email, password })
      });
      sessionStorage.setItem('klipklop_toast', mode === 'login' ? 'Berhasil login' : 'Berhasil daftar');
      window.location.href = '/';
    } catch (err: any) {
      setError(err.message || 'Gagal');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-sans antialiased selection:bg-primary/30">
      <main className="grid min-h-screen lg:grid-cols-[1.05fr_.95fr]">
        {/* Left Section - Hero */}
        <section className="hidden lg:flex relative overflow-hidden flex-col justify-between border-r border-border bg-card p-10 before:absolute before:-right-32 before:top-24 before:h-96 before:w-96 before:rounded-full before:bg-primary/10 before:blur-3xl after:absolute after:left-10 after:bottom-20 after:h-40 after:w-40 after:rounded-full after:bg-primary/5 after:blur-2xl">
          <div className="relative z-10 flex items-center gap-3 font-extrabold text-2xl text-card-foreground">
            <img src="/logo%20klipklop.png?v=3" className="h-10 w-10 rounded-xl object-contain shadow-lg shadow-primary/10" alt="KlipKlop" />
            <span>KlipKlop</span>
          </div>
          
          <div className="relative z-10 max-w-xl space-y-6">
            <h1 className="text-5xl font-extrabold tracking-tight leading-tight text-card-foreground">
              Upload videomu, biar KlipKlop cari momen <span className="text-transparent bg-clip-text bg-gradient-to-r from-primary to-orange-600 font-black italic pr-1">terbaiknya.</span>
            </h1>
            <p className="text-lg leading-relaxed tracking-[0.5px] text-muted-foreground">
              KlipKlop membantu mengubah video panjang menjadi klip pendek yang menarik, lengkap dengan caption, dan siap kamu upload ke YouTube.
            </p>
          </div>
          <p className="relative z-10 text-sm font-medium text-muted-foreground">KlipKlop Web</p>
        </section>

        {/* Right Section - Login Form */}
        <section className="flex items-center justify-center p-6 bg-secondary/50 relative overflow-hidden">
          {/* Subtle background glow for mobile */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-orange-600/5 blur-[100px] rounded-full pointer-events-none lg:hidden"></div>
          
          <Card className="w-full max-w-sm shadow-2xl shadow-slate-200/50 rounded-2xl border-slate-100 bg-white relative z-10">
            <CardHeader className="pb-4">
              <div className="mb-6 lg:hidden flex items-center gap-3 font-extrabold text-2xl text-slate-900">
                <img src="/logo%20klipklop.png?v=3" className="h-10 w-10 rounded-xl object-contain shadow-sm" alt="KlipKlop" />
                <span>KlipKlop</span>
              </div>
              <CardTitle className="text-2xl font-extrabold tracking-tight text-slate-900">Masuk</CardTitle>
              <CardDescription className="text-slate-500 text-sm">Lanjutkan ke dashboard KlipKlop.</CardDescription>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="login" className="w-full">
                <TabsList className="grid w-full grid-cols-2 mb-6 h-12 rounded-xl bg-slate-100/80 p-1 border border-slate-100">
                  <TabsTrigger value="login" className="rounded-lg font-bold text-slate-500 data-[state=active]:bg-orange-600 data-[state=active]:text-white transition-all">Masuk</TabsTrigger>
                  <TabsTrigger value="signup" className="rounded-lg font-bold text-slate-500 data-[state=active]:bg-orange-600 data-[state=active]:text-white transition-all">Daftar</TabsTrigger>
                </TabsList>
                
                <TabsContent value="login" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                  <form onSubmit={(e) => handleSubmit('login', e)} className="space-y-5">
                    <div className="space-y-2.5">
                      <Label htmlFor="email-login" className="text-sm font-bold text-slate-700">Email</Label>
                      <Input 
                        id="email-login" 
                        type="email" 
                        required 
                        placeholder="nama@email.com" 
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="rounded-xl px-4 py-6 bg-white border-slate-200 text-slate-900 placeholder:text-slate-400 placeholder:font-normal focus-visible:ring-orange-500/50 focus-visible:border-orange-500 transition-all shadow-sm"
                      />
                    </div>
                    <div className="space-y-2.5">
                      <Label htmlFor="password-login" className="text-sm font-bold text-slate-700">Password</Label>
                      <Input 
                        id="password-login" 
                        type="password" 
                        required 
                        placeholder="Minimal 6 karakter"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="rounded-xl px-4 py-6 bg-white border-slate-200 text-slate-900 placeholder:text-slate-400 placeholder:font-normal focus-visible:ring-orange-500/50 focus-visible:border-orange-500 transition-all shadow-sm"
                      />
                    </div>
                    <Button type="submit" disabled={isLoading} className="w-full rounded-xl h-12 font-extrabold bg-orange-600 hover:bg-orange-700 text-white shadow-lg shadow-orange-600/20 border-0 transition-all">
                      {isLoading ? 'Memproses...' : 'Masuk'}
                    </Button>
                    {error && <p className="text-sm font-semibold text-red-500 mt-2 bg-red-50 p-3 rounded-lg border border-red-100">{error}</p>}
                  </form>
                </TabsContent>

                <TabsContent value="signup" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
                  <form onSubmit={(e) => handleSubmit('signup', e)} className="space-y-5">
                    <div className="space-y-2.5">
                      <Label htmlFor="email-signup" className="text-sm font-bold text-slate-700">Email</Label>
                      <Input 
                        id="email-signup" 
                        type="email" 
                        required 
                        placeholder="nama@email.com" 
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="rounded-xl px-4 py-6 bg-white border-slate-200 text-slate-900 placeholder:text-slate-400 placeholder:font-normal focus-visible:ring-orange-500/50 focus-visible:border-orange-500 transition-all shadow-sm"
                      />
                    </div>
                    <div className="space-y-2.5">
                      <Label htmlFor="password-signup" className="text-sm font-bold text-slate-700">Password</Label>
                      <Input 
                        id="password-signup" 
                        type="password" 
                        required 
                        placeholder="Minimal 6 karakter"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="rounded-xl px-4 py-6 bg-white border-slate-200 text-slate-900 placeholder:text-slate-400 placeholder:font-normal focus-visible:ring-orange-500/50 focus-visible:border-orange-500 transition-all shadow-sm"
                      />
                    </div>
                    <Button type="submit" disabled={isLoading} className="w-full rounded-xl h-12 font-extrabold bg-orange-600 hover:bg-orange-700 text-white shadow-lg shadow-orange-600/20 border-0 transition-all">
                      {isLoading ? 'Memproses...' : 'Daftar Akun Baru'}
                    </Button>
                    {error && <p className="text-sm font-semibold text-red-500 mt-2 bg-red-50 p-3 rounded-lg border border-red-100">{error}</p>}
                  </form>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}
