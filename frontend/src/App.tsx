import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { Toaster } from 'sonner';
import { useAuthStore } from '@/stores/authStore';
import { AppLayout } from '@/components/layout/AppLayout';
import { ChatPage } from '@/pages/ChatPage';
import { LoginPage } from '@/pages/LoginPage';
import { FileManagerPage } from '@/pages/FileManagerPage';
import { UserManagementPage } from '@/pages/UserManagementPage';
import { ChangePasswordPage } from '@/pages/ChangePasswordPage';
import { KnowledgeGraphPage } from '@/pages/KnowledgeGraphPage';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { CommandPalette } from '@/components/CommandPalette';
import { TooltipProvider } from '@/components/ui/tooltip';

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
      <TooltipProvider delayDuration={300}>
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
              <Route path="/knowledge-graph" element={<KnowledgeGraphPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <CommandPalette />
        </BrowserRouter>
        <Toaster
          theme="dark"
          position="top-right"
          toastOptions={{
            style: {
              background: '#2f2f2f',
              border: '1px solid rgba(255,255,255,0.08)',
              color: '#e4e4e7',
            },
          }}
        />
      </TooltipProvider>
    </ErrorBoundary>
  );
}