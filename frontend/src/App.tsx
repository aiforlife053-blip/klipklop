import { lazy, Suspense, useEffect, useState, type ReactNode } from 'react';
import { createBrowserRouter, RouterProvider, Navigate, useLocation } from 'react-router-dom';
import Login from './pages/Login';
import DashboardLayout from './components/layout/DashboardLayout';
import Dashboard from './pages/Dashboard';

const Console = lazy(() => import('./pages/Console'));
const Settings = lazy(() => import('./pages/Settings'));
const Preview = lazy(() => import('./pages/Preview'));

const deferred = (page: React.ReactNode) => <Suspense fallback={<div className="p-8 text-sm text-muted" role="status">Memuat halaman...</div>}>{page}</Suspense>;

function AuthGate({ children, publicOnly = false }: { children: ReactNode; publicOnly?: boolean }) {
  const location = useLocation();
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetch('/api/status', { credentials: 'same-origin', signal: controller.signal })
      .then((response) => setAuthenticated(response.ok))
      .catch((error) => {
        if (!(error instanceof DOMException && error.name === 'AbortError')) setAuthenticated(false);
      });
    return () => controller.abort();
  }, []);

  if (authenticated === null) return <main className="flex min-h-dvh items-center justify-center bg-background text-sm text-muted" role="status">Memeriksa sesi...</main>;
  if (publicOnly && authenticated) return <Navigate to="/" replace />;
  if (!publicOnly && !authenticated) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  return children;
}

function NotFound() {
  return <main className="flex min-h-dvh items-center justify-center bg-background px-6 text-foreground">
    <div className="max-w-md text-center">
      <p className="text-sm font-bold text-primary">404</p>
      <h1 className="mt-2 font-display text-3xl font-bold">Halaman tidak ditemukan</h1>
      <p className="mt-3 text-sm leading-relaxed text-muted">Alamat ini tidak tersedia atau sudah dipindahkan.</p>
      <a href="/" className="mt-6 inline-flex rounded-xl bg-primary px-5 py-3 text-sm font-bold text-primary-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background">Kembali ke Dashboard</a>
    </div>
  </main>;
}

const router = createBrowserRouter([
  { path: '/login', element: <AuthGate publicOnly><Login /></AuthGate> },
  {
    element: <AuthGate><DashboardLayout /></AuthGate>,
    children: [
      { path: '/', element: <Dashboard /> },
      { path: '/gallery', element: <Navigate to="/preview" replace /> },
      { path: '/console', element: deferred(<Console />) },
      { path: '/settings', element: deferred(<Settings />) },
      { path: '/preview', element: deferred(<Preview />) },
    ],
  },
  { path: '*', element: <NotFound /> },
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
