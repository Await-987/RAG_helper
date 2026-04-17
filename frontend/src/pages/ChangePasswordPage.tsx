import { useState, useCallback, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { userApi } from '@/api/users';
import { Loader2, CheckCircle } from 'lucide-react';
import type { AxiosError } from 'axios';

export function ChangePasswordPage() {
  const navigate = useNavigate();
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setError('');
      if (newPassword !== confirmPassword) {
        setError('两次输入的密码不一致');
        return;
      }
      setLoading(true);
      try {
        await userApi.changePassword({
          old_password: oldPassword,
          new_password: newPassword,
        });
        setSuccess(true);
      } catch (err: unknown) {
        const axiosErr = err as AxiosError<{ detail: string }>;
        setError(axiosErr?.response?.data?.detail || '修改密码失败');
      } finally {
        setLoading(false);
      }
    },
    [oldPassword, newPassword, confirmPassword]
  );

  if (success) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-emerald-500/10 flex items-center justify-center">
            <CheckCircle size={24} className="text-emerald-400" />
          </div>
          <h2 className="text-lg font-medium text-white mb-2">密码已更新</h2>
          <button onClick={() => navigate('/')} className="btn btn-primary mt-4">
            返回
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <h1 className="text-xl font-medium text-white mb-6 text-center">修改密码</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="px-4 py-3 rounded-xl text-sm text-red-400 bg-red-500/10">
              {error}
            </div>
          )}
          <input
            type="password"
            placeholder="当前密码"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            required
            className="input-field"
          />
          <input
            type="password"
            placeholder="新密码"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            className="input-field"
          />
          <input
            type="password"
            placeholder="确认新密码"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            className="input-field"
          />
          <button type="submit" disabled={loading} className="btn btn-primary w-full flex items-center justify-center gap-2">
            {loading && <Loader2 size={14} className="animate-spin" />}
            更新密码
          </button>
        </form>
      </div>
    </div>
  );
}