import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useAuthStore } from '@/stores/authStore';
import { AppLayout } from '@/components/layout/AppLayout';
import { ChatPage } from '@/pages/ChatPage';
import { LoginPage } from '@/pages/LoginPage';
import { FileManagerPage } from '@/pages/FileManagerPage';
import { UserManagementPage } from '@/pages/UserManagementPage';
import { ChangePasswordPage } from '@/pages/ChangePasswordPage';
import { ErrorBoundary } from '@/components/ErrorBoundary';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const doCheck = async () => {
      try {
        await Promise.race([
          useAuthStore.getState().checkAuth(),
          new Promise((_, reject) =>
            window.setTimeout(() => reject(new Error('timeout')), 8000)
          ),
        ]);
      } catch {
        // ignore
      } finally {
        if (!cancelled) {
          setChecking(false);
          useAuthStore.setState({ isLoading: false });
        }
      }
    };

    doCheck();
    return () => { cancelled = true; };
  }, []);

  if (checking || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-dark-bg">
        <div className="text-gray-400">加载中...</div>
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return <>{children}</>;
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <ProtectedRoute>
                <AppLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/" element={<ChatPage />} />
            <Route path="/files" element={<FileManagerPage />} />
            <Route path="/users" element={<UserManagementPage />} />
            <Route path="/change-password" element={<ChangePasswordPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
