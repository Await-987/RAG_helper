import { useState, useEffect, useCallback, FormEvent } from 'react';
import { userApi } from '@/api/users';
import type { UserInfo, UserCreate } from '@/types/user';
import { Plus, Trash2, Shield, Loader2, Key } from 'lucide-react';

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
      if (!confirm(`确定删除用户 ${username}？`)) return;
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
    const newPassword = prompt(`为用户 ${username} 设置新密码：`);
    if (!newPassword) return;
    try {
      await userApi.resetPassword({ username, new_password: newPassword });
      alert('密码已重置');
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
    <div className="h-full overflow-y-auto custom-scrollbar p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-bold text-white">用户管理</h1>
          <button onClick={() => setShowCreate(true)} className="btn btn-primary flex items-center gap-2">
            <Plus size={14} />
            添加用户
          </button>
        </div>

        {loading ? (
          <div className="text-center py-12 text-gray-400">加载中...</div>
        ) : (
          <div className="bg-dark-card border border-dark-border rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-dark-border">
                  <th className="text-left px-4 py-3 text-sm text-gray-400 font-medium">用户名</th>
                  <th className="text-left px-4 py-3 text-sm text-gray-400 font-medium">角色</th>
                  <th className="text-right px-4 py-3 text-sm text-gray-400 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.username} className="border-b border-dark-border last:border-0 hover:bg-dark-hover">
                    <td className="px-4 py-3 text-sm">{u.username}</td>
                    <td className="px-4 py-3">
                      <span className={`px-2 py-0.5 rounded-md text-xs ${
                        u.role === 'admin'
                          ? 'bg-primary-600/20 text-primary-400 border border-primary-600/30'
                          : 'bg-gray-600/20 text-gray-400 border border-gray-600/30'
                      }`}>
                        {u.role}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => handleToggleRole(u)} className="p-1.5 rounded-md text-gray-500 hover:text-primary-400 hover:bg-dark-hover" title="切换角色">
                          <Shield size={14} />
                        </button>
                        <button onClick={() => handleResetPassword(u.username)} className="p-1.5 rounded-md text-gray-500 hover:text-yellow-400 hover:bg-dark-hover" title="重置密码">
                          <Key size={14} />
                        </button>
                        <button onClick={() => handleDelete(u.username)} className="p-1.5 rounded-md text-gray-500 hover:text-red-400 hover:bg-dark-hover" title="删除">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Create user modal */}
        {showCreate && (
          <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4" onClick={() => setShowCreate(false)}>
            <div className="bg-dark-card border border-dark-border rounded-xl p-6 w-full max-w-sm" onClick={(e) => e.stopPropagation()}>
              <h2 className="text-lg font-bold text-white mb-4">添加用户</h2>
              <form onSubmit={handleCreate} className="space-y-4">
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
                  <option value="user">普通用户</option>
                  <option value="admin">管理员</option>
                </select>
                <div className="flex gap-3">
                  <button type="button" onClick={() => setShowCreate(false)} className="btn btn-secondary flex-1">
                    取消
                  </button>
                  <button type="submit" disabled={creating} className="btn btn-primary flex-1 flex items-center justify-center gap-2">
                    {creating && <Loader2 size={14} className="animate-spin" />}
                    创建
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
