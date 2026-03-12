import { useState, useEffect } from 'react';
import { userApi } from '@/api';
import type { UserInfo, UserCreate } from '@/types';
import { useAuthStore } from '@/stores';
import {
  Users,
  UserPlus,
  Trash2,
  Key,
  Shield,
  User,
  Loader2,
  X,
} from 'lucide-react';
import clsx from 'clsx';

export function UserManagementPage() {
  const { user: currentUser } = useAuthStore();
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showResetModal, setShowResetModal] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null);

  // Form states
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'user'>('user');
  const [resetPassword, setResetPassword] = useState('');

  // Fetch users
  const fetchUsers = async () => {
    setLoading(true);
    try {
      const data = await userApi.getUsers();
      setUsers(data);
    } catch (error) {
      console.error('Failed to fetch users:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  // Create user
  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUsername || !newPassword) return;

    try {
      await userApi.createUser({
        username: newUsername,
        password: newPassword,
        role: newRole,
      });
      setShowCreateModal(false);
      setNewUsername('');
      setNewPassword('');
      setNewRole('user');
      await fetchUsers();
    } catch (error: any) {
      alert(error.response?.data?.detail || '创建用户失败');
    }
  };

  // Delete user
  const handleDeleteUser = async (username: string) => {
    try {
      await userApi.deleteUser(username);
      setShowDeleteConfirm(null);
      await fetchUsers();
    } catch (error: any) {
      alert(error.response?.data?.detail || '删除用户失败');
    }
  };

  // Reset password
  const handleResetPassword = async (username: string) => {
    if (!resetPassword) return;

    try {
      await userApi.resetPassword({
        username,
        new_password: resetPassword,
      });
      setShowResetModal(null);
      setResetPassword('');
    } catch (error: any) {
      alert(error.response?.data?.detail || '重置密码失败');
    }
  };

  // Change role
  const handleChangeRole = async (username: string, currentRole: string) => {
    const newRole = currentRole === 'admin' ? 'user' : 'admin';
    try {
      await userApi.changeRole({
        username,
        new_role: newRole as 'admin' | 'user',
      });
      await fetchUsers();
    } catch (error: any) {
      alert(error.response?.data?.detail || '修改角色失败');
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-dark-border bg-dark-card">
        <h1 className="text-xl font-bold text-white">用户管理</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn btn-primary flex items-center gap-2"
        >
          <UserPlus size={18} />
          <span>添加用户</span>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 size={24} className="animate-spin text-primary-400" />
          </div>
        ) : (
          <div className="space-y-3">
            {users.map((user) => (
              <div
                key={user.username}
                className="card flex flex-col sm:flex-row sm:items-center gap-4"
              >
                {/* User info */}
                <div className="flex items-center gap-3 flex-1">
                  <div
                    className={clsx(
                      'w-10 h-10 rounded-full flex items-center justify-center text-lg',
                      user.role === 'admin' ? 'bg-yellow-600' : 'bg-gray-600'
                    )}
                  >
                    {user.role === 'admin' ? '👑' : '👤'}
                  </div>
                  <div>
                    <p className="font-medium text-gray-100">{user.username}</p>
                    <p className="text-sm text-gray-400">
                      {user.role === 'admin' ? '管理员' : '普通用户'}
                    </p>
                  </div>
                </div>

                {/* Actions */}
                {user.username !== currentUser?.username && (
                  <div className="flex items-center gap-2">
                    {/* Change role */}
                    <button
                      onClick={() => handleChangeRole(user.username, user.role)}
                      className="btn btn-secondary flex items-center gap-2"
                      title={
                        user.role === 'admin'
                          ? '设为普通用户'
                          : '设为管理员'
                      }
                    >
                      <Shield size={16} />
                      <span className="hidden sm:inline">
                        {user.role === 'admin' ? '降为用户' : '升为管理员'}
                      </span>
                    </button>

                    {/* Reset password */}
                    <button
                      onClick={() => setShowResetModal(user.username)}
                      className="btn btn-secondary flex items-center gap-2"
                      title="重置密码"
                    >
                      <Key size={16} />
                      <span className="hidden sm:inline">重置密码</span>
                    </button>

                    {/* Delete */}
                    <button
                      onClick={() => setShowDeleteConfirm(user.username)}
                      className="btn btn-danger flex items-center gap-2"
                      title="删除用户"
                    >
                      <Trash2 size={16} />
                      <span className="hidden sm:inline">删除</span>
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create User Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="w-full max-w-md bg-dark-card rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white">添加用户</h3>
              <button
                onClick={() => setShowCreateModal(false)}
                className="p-2 text-gray-400 hover:text-white hover:bg-dark-hover rounded-lg"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleCreateUser} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  用户名
                </label>
                <input
                  type="text"
                  value={newUsername}
                  onChange={(e) => setNewUsername(e.target.value)}
                  className="input-field"
                  placeholder="请输入用户名"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  密码
                </label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="input-field"
                  placeholder="请输入密码"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  角色
                </label>
                <select
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value as 'admin' | 'user')}
                  className="input-field"
                >
                  <option value="user">普通用户</option>
                  <option value="admin">管理员</option>
                </select>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="btn btn-secondary flex-1"
                >
                  取消
                </button>
                <button type="submit" className="btn btn-primary flex-1">
                  创建
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Reset Password Modal */}
      {showResetModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="w-full max-w-md bg-dark-card rounded-xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-bold text-white">
                重置密码 - {showResetModal}
              </h3>
              <button
                onClick={() => setShowResetModal(null)}
                className="p-2 text-gray-400 hover:text-white hover:bg-dark-hover rounded-lg"
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  新密码
                </label>
                <input
                  type="password"
                  value={resetPassword}
                  onChange={(e) => setResetPassword(e.target.value)}
                  className="input-field"
                  placeholder="请输入新密码"
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => setShowResetModal(null)}
                  className="btn btn-secondary flex-1"
                >
                  取消
                </button>
                <button
                  onClick={() => handleResetPassword(showResetModal)}
                  className="btn btn-primary flex-1"
                  disabled={!resetPassword}
                >
                  确认
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirm Modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
          <div className="w-full max-w-md bg-dark-card rounded-xl p-6">
            <h3 className="text-lg font-bold text-white mb-4">确认删除</h3>
            <p className="text-gray-300 mb-6">
              确定要删除用户 <strong>{showDeleteConfirm}</strong> 吗？此操作无法撤销。
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowDeleteConfirm(null)}
                className="btn btn-secondary flex-1"
              >
                取消
              </button>
              <button
                onClick={() => handleDeleteUser(showDeleteConfirm)}
                className="btn btn-danger flex-1"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
