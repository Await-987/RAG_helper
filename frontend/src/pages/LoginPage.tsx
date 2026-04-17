import { useState, useCallback, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { Zap, Loader2 } from 'lucide-react';
import type { AxiosError } from 'axios';

export function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuthStore();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setError('');
      setLoading(true);
      try {
        await login({ username, password });
        navigate('/');
      } catch (err: unknown) {
        const axiosErr = err as AxiosError<{ detail: string }>;
        setError(axiosErr?.response?.data?.detail || (err as Error).message || '登录失败');
      } finally {
        setLoading(false);
      }
    },
    [username, password, login, navigate]
  );

  return (
    <div className="min-h-screen flex items-center justify-center bg-dark-bg p-4">
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 mb-4 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600">
            <Zap size={24} className="text-white" />
          </div>
          <h1 className="text-xl font-semibold text-white mb-1">知识库助手</h1>
          <p className="text-zinc-500 text-sm">登录以继续</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="px-4 py-3 rounded-xl text-sm text-red-400 bg-red-500/10">
              {error}
            </div>
          )}

          <input
            type="text"
            placeholder="用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            className="input-field"
            disabled={loading}
          />
          <input
            type="password"
            placeholder="密码"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="input-field"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary w-full flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 size={16} className="animate-spin" /> : null}
            {loading ? '登录中...' : '登录'}
          </button>
        </form>
      </div>
    </div>
  );
}