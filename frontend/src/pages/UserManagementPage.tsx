import { useState, useEffect, useCallback, type FormEvent } from 'react';
import { userApi } from '@/api/users';
import { toast } from 'sonner';
import type { UserInfo, UserCreate } from '@/types/user';
import { Plus, Trash2, Shield, Loader2, Key } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export function UserManagementPage() {
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<UserCreate>({ username: '', password: '', role: 'user' });
  const [creating, setCreating] = useState(false);

  // AlertDialog state
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [resetTarget, setResetTarget] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState('');

  const loadUsers = useCallback(async () => {
    setLoading(true);
    try {
      const list = await userApi.getUsers();
      setUsers(list);
    } catch (err) {
      toast.error('加载用户列表失败');
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
        toast.success(`用户 ${createForm.username} 创建成功`);
        await loadUsers();
      } catch (err) {
        toast.error('创建用户失败');
        console.error('Create user failed:', err);
      } finally {
        setCreating(false);
      }
    },
    [createForm, loadUsers]
  );

  const handleDelete = useCallback(
    async (username: string) => {
      try {
        await userApi.deleteUser(username);
        toast.success(`用户 ${username} 已删除`);
        await loadUsers();
      } catch (err) {
        toast.error('删除用户失败');
        console.error('Delete user failed:', err);
      }
      setDeleteTarget(null);
    },
    [loadUsers]
  );

  const handleResetPassword = useCallback(async () => {
    if (!resetTarget || !newPassword) return;
    try {
      await userApi.resetPassword({ username: resetTarget, new_password: newPassword });
      toast.success(`${resetTarget} 密码已重置`);
      setResetTarget(null);
      setNewPassword('');
    } catch (err) {
      toast.error('重置密码失败');
      console.error('Reset password failed:', err);
    }
  }, [resetTarget, newPassword]);

  const handleToggleRole = useCallback(
    async (user: UserInfo) => {
      const newRole = user.role === 'admin' ? 'user' : 'admin';
      try {
        await userApi.changeRole({ username: user.username, new_role: newRole as 'admin' | 'user' });
        toast.success(`${user.username} 角色已切换为 ${newRole}`);
        await loadUsers();
      } catch (err) {
        toast.error('切换角色失败');
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
          <Button onClick={() => setShowCreate(true)} size="sm">
            <Plus size={14} />
            添加
          </Button>
        </div>

        {/* User list */}
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3 px-4 py-3">
                <Skeleton className="h-8 w-8 rounded-lg" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-3 w-12" />
                </div>
                <Skeleton className="h-6 w-16 rounded-full" />
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-white/[0.06] bg-[#2f2f2f] divide-y divide-zinc-800/50">
            {users.map((u) => (
              <div key={u.username} className="flex items-center gap-3 px-4 py-3 hover:bg-zinc-800/30 transition-colors">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center text-xs font-medium text-white">
                  {u.username.charAt(0).toUpperCase()}
                </div>
                <div className="flex-1">
                  <div className="text-sm text-zinc-200">{u.username}</div>
                  <div className="text-xs text-zinc-500">{u.role === 'admin' ? '管理员' : '用户'}</div>
                </div>
                <Badge variant={u.role === 'admin' ? 'default' : 'secondary'}>
                  {u.role}
                </Badge>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <Key size={14} />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => handleToggleRole(u)}>
                      <Shield size={14} />
                      切换角色
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => { setResetTarget(u.username); setNewPassword(''); }}>
                      <Key size={14} />
                      重置密码
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      className="text-red-400 focus:text-red-300"
                      onClick={() => setDeleteTarget(u.username)}
                    >
                      <Trash2 size={14} />
                      删除用户
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ))}
          </div>
        )}

        {/* Create Dialog */}
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>添加用户</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-3">
              <Input
                type="text"
                placeholder="用户名"
                value={createForm.username}
                onChange={(e) => setCreateForm((f) => ({ ...f, username: e.target.value }))}
                required
              />
              <Input
                type="password"
                placeholder="密码"
                value={createForm.password}
                onChange={(e) => setCreateForm((f) => ({ ...f, password: e.target.value }))}
                required
              />
              <select
                value={createForm.role}
                onChange={(e) => setCreateForm((f) => ({ ...f, role: e.target.value as 'admin' | 'user' }))}
                className="flex h-11 w-full rounded-2xl px-4 py-3 text-sm text-zinc-100 bg-[#2f2f2f] border border-white/[0.06] focus:outline-none focus:ring-2 focus:ring-primary-500/30"
              >
                <option value="user">用户</option>
                <option value="admin">管理员</option>
              </select>
              <DialogFooter>
                <Button type="submit" disabled={creating} className="w-full">
                  {creating && <Loader2 size={14} className="animate-spin" />}
                  创建
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        {/* Delete AlertDialog */}
        <AlertDialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>确认删除</AlertDialogTitle>
              <AlertDialogDescription>
                删除用户 {deleteTarget}？此操作不可撤销。
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction
                className="bg-red-600 hover:bg-red-700"
                onClick={() => deleteTarget && handleDelete(deleteTarget)}
              >
                删除
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        {/* Reset Password Dialog */}
        <Dialog open={!!resetTarget} onOpenChange={(v) => !v && setResetTarget(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>重置密码</DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <p className="text-sm text-zinc-400">为用户 {resetTarget} 设置新密码</p>
              <Input
                type="password"
                placeholder="新密码"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
              <DialogFooter>
                <Button variant="outline" onClick={() => setResetTarget(null)}>取消</Button>
                <Button onClick={handleResetPassword} disabled={!newPassword}>
                  重置
                </Button>
              </DialogFooter>
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}