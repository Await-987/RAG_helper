import { useState, useCallback, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { userApi } from '@/api/users';
import { Loader2, Key } from 'lucide-react';

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
      } catch (err: any) {
        setError(err?.response?.data?.detail || '修改密码失败');
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
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-green-600/20 flex items-center justify-center">
            <Key size={24} className="text-green-400" />
          </div>
          <h2 className="text-lg font-bold text-white mb-2">密码修改成功</h2>
          <button onClick={() => navigate('/')} className="btn btn-primary mt-4">
            返回首页
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <h1 className="text-xl font-bold text-white mb-6 text-center">修改密码</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="p-3 rounded-lg bg-red-600/10 border border-red-600/20 text-red-400 text-sm">
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
            修改密码
          </button>
        </form>
      </div>
    </div>
  );
}
