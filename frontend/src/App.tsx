import { createBrowserRouter, RouterProvider, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import DashboardLayout from './components/layout/DashboardLayout';
import Dashboard from './pages/Dashboard';
import Gallery from './pages/Gallery';
import Console from './pages/Console';
import Settings from './pages/Settings';
import Preview from './pages/Preview';

const router = createBrowserRouter([
  { path: '/login', element: <Login /> },
  {
    element: <DashboardLayout />,
    children: [
      { path: '/', element: <Dashboard /> },
      { path: '/gallery', element: <Gallery /> },
      { path: '/console', element: <Console /> },
      { path: '/settings', element: <Settings /> },
      { path: '/preview', element: <Preview /> },
    ],
  },
  { path: '*', element: <Navigate to="/" replace /> },
]);

function App() {
  return <RouterProvider router={router} />;
}

export default App;
