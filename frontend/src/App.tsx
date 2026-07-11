import { lazy, Suspense } from 'react';
import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import DashboardLayout from './components/layout/DashboardLayout';
import Dashboard from './pages/Dashboard';

const Gallery = lazy(() => import('./pages/Gallery'));
const Console = lazy(() => import('./pages/Console'));
const Settings = lazy(() => import('./pages/Settings'));
const Preview = lazy(() => import('./pages/Preview'));

const deferred = (page: React.ReactNode) => <Suspense fallback={<div className="p-8 text-sm text-muted" role="status">Memuat halaman...</div>}>{page}</Suspense>;

const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    element: <DashboardLayout />,
    children: [
      { path: '/', element: <Dashboard /> },
      { path: '/gallery', element: deferred(<Gallery />) },
      { path: '/console', element: deferred(<Console />) },
      { path: '/settings', element: deferred(<Settings />) },
      { path: '/preview', element: deferred(<Preview />) },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
