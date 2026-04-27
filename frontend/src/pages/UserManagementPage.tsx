import { useState, useEffect, useCallback, type FormEvent } from 'react';
import { userApi } from '@/api/users';
import type { UserInfo, UserCreate } from '@/types/user';
import { Plus, Trash2, Shield, Loader2, Key, X } from 'lucide-react';

export function UserManagementPage() {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<UserCreate>({ username: '', password: '', role: 'user' });
  const [creating, setCreating] = useState(false);

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const list = await userApi.getUsers();
      setUsers(list);
    } catch (err) {
      console.error('Failed to load users:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadUsers(); }, [loadUsers]);

  const handleCreate = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setCreating(true);
      try {
        await userApi.createUser(createForm);
        setShowCreate(false);
        setCreateForm({ username: '', password: '', role: 'user' });
        await loadUsers();
      } catch (err) {
        console.error('Create user failed:', err);
      } finally {
        setCreating(false);
      }
    },
    [createForm, loadUsers]
  );

  const handleDelete = useCallback(
    async (username: string) => {
      if (!confirm(`删除用户 ${username}？`)) return;
      try {
        await userApi.deleteUser(username);
        await loadUsers();
      } catch (err) {
        console.error('Delete user failed:', err);
      }
    },
    [loadUsers]
  );

  const handleResetPassword = useCallback(async (username: string) => {
    const newPassword = prompt(`新密码：`);
    if (!newPassword) return;
    try {
      await userApi.resetPassword({ username, new_password: newPassword });
      alert('已重置');
    } catch (err) {
      console.error('Reset password failed:', err);
    }
  }, []);

  const handleToggleRole = useCallback(
    async (user: UserInfo) => {
      const newRole = user.role === 'admin' ? 'user' : 'admin';
      try {
        await userApi.changeRole({ username: user.username, new_role: newRole as 'admin' | 'user' });
        await loadUsers();
      } catch (err) {
        console.error('Change role failed:', err);
      }
    },
    [loadUsers]
  );

  return (
    <div className="h-full overflow-y-auto custom-scrollbar p-4 lg:p-6">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-lg font-medium text-white">用户管理</h1>
          <button onClick={() => setShowCreate(true)} className="btn btn-primary flex items-center gap-2">
            <Plus size={14} />
            添加
          </button>
        </div>

        {/* User list */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={20} className="animate-spin text-zinc-500" />
          </div>
        ) : (
          <div className="card divide-y divide-zinc-800">
            {users.map((u) => (
              <div key={u.username} className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-800/30 transition-colors">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center text-xs font-medium text-white">
                  {u.username.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1">
                  <div className="text-sm text-zinc-200">{u.username}</div>
                  <div className="text-xs text-zinc-500">{u.role === 'admin' ? '管理员' : '用户'}</div>
                </div>
                <span className={`px-2 py-0.5 rounded-lg text-xs ${
                  u.role === 'admin' ? 'text-primary-400 bg-primary-500/10' : 'text-zinc-400 bg-zinc-800'
                }`}>
                  {u.role}
                </span>
                <div className="flex items-center gap-1">
                  <button onClick={() => handleToggleRole(u)} className="p-1.5 rounded-lg text-zinc-400 hover:text-primary-400 hover:bg-zinc-800/50">
                    <Shield size={14} />
                  </button>
                  <button onClick={() => handleResetPassword(u.username)} className="p-1.5 rounded-lg text-zinc-400 hover:text-amber-400 hover:bg-zinc-800/50">
                    <Key size={14} />
                  </button>
                  <button onClick={() => handleDelete(u.username)} className="p-1.5 rounded-lg text-zinc-400 hover:text-red-400 hover:bg-zinc-800/50">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Create modal */}
        {showCreate && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4 modal-overlay-enter" onClick={() => setShowCreate(false)}>
            <div className="card w-full max-w-sm modal-enter" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-base font-medium text-white">添加用户</h2>
                <button onClick={() => setShowCreate(false)} className="p-1 rounded-lg text-zinc-400 hover:text-white">
                  <X size={16} />
                </button>
              </div>
              <form onSubmit={handleCreate} className="space-y-3">
                <input
                  type="text"
                  placeholder="用户名"
                  value={createForm.username}
                  onChange={(e) => setCreateForm((f) => ({ ...f, username: e.target.value }))}
                  required
                  className="input-field"
                />
                <input
                  type="password"
                  placeholder="密码"
                  value={createForm.password}
                  onChange={(e) => setCreateForm((f) => ({ ...f, password: e.target.value }))}
                  required
                  className="input-field"
                />
                <select
                  value={createForm.role}
                  onChange={(e) => setCreateForm((f) => ({ ...f, role: e.target.value as 'admin' | 'user' }))}
                  className="input-field"
                >
                  <option value="user">用户</option>
                  <option value="admin">管理员</option>
                </select>
                <button type="submit" disabled={creating} className="btn btn-primary w-full flex items-center justify-center gap-2">
                  {creating && <Loader2 size={14} className="animate-spin" />}
                  创建
                </button>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}