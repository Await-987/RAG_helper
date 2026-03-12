import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useAuthStore } from '@/stores';

// Layout
import { MainLayout } from '@/components/Layout/MainLayout';

// Pages
import { LoginPage } from '@/pages/Login';
import { ChatPage } from '@/pages/Chat';
import { FileManagerPage } from '@/pages/FileManager';
import { UserManagementPage } from '@/pages/UserManagement';
import { ChangePasswordPage } from '@/pages/ChangePassword';

// Protected Route
function ProtectedRoute({
  children,
  adminOnly = false,
}: {
  children: React.ReactNode;
  adminOnly?: boolean;
}) {
  const { isAuthenticated, user, isLoading } = useAuthStore();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const checkAuth = async () => {
      const timeoutMs = 8000;

      try {
        await Promise.race([
          useAuthStore.getState().checkAuth(),
          new Promise((_, reject) => {
            window.setTimeout(() => reject(new Error('auth check timeout')), timeoutMs);
          }),
        ]);
      } catch (error) {
        console.error('Auth check failed:', error);
      } finally {
        if (!cancelled) {
          setChecking(false);
          useAuthStore.setState({ isLoading: false });
        }
      }
    };

    checkAuth();

    return () => {
      cancelled = true;
    };
  }, []);

  if (checking || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-dark-bg">
        <div className="text-gray-400">加载中...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (adminOnly && user?.role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return <MainLayout>{children}</MainLayout>;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected routes */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <ChatPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/files"
          element={
            <ProtectedRoute>
              <FileManagerPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/users"
          element={
            <ProtectedRoute adminOnly>
              <UserManagementPage />
            </ProtectedRoute>
          }
        />
        <Route
          path="/change-password"
          element={
            <ProtectedRoute>
              <ChangePasswordPage />
            </ProtectedRoute>
          }
        />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
