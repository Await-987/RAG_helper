import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores';
import {
  MessageSquare,
  FileText,
  Users,
  Key,
  LogOut,
  Menu,
  X,
  Plus,
} from 'lucide-react';
import { useState } from 'react';
import clsx from 'clsx';

interface MainLayoutProps {
  children: ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  const { user, logout } = useAuthStore();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const isAdmin = user?.role === 'admin';

  const navItems = [
    { path: '/', label: '聊天', icon: MessageSquare },
    { path: '/files', label: '文件管理', icon: FileText },
  ];

  const adminItems = [
    { path: '/users', label: '用户管理', icon: Users },
  ];

  const handleLogout = () => {
    logout();
    window.location.href = '/login';
  };

  return (
    <div className="flex h-screen min-h-0 bg-dark-bg">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={clsx(
          'fixed lg:static inset-y-0 left-0 z-50 w-64 bg-dark-card border-r border-dark-border',
          'transform transition-transform duration-300 ease-in-out',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
        )}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="p-4 border-b border-dark-border">
            <h1 className="text-xl font-bold text-white">智能设计助手</h1>
          </div>

          {/* User info */}
          <div className="p-4 border-b border-dark-border">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-primary-600 flex items-center justify-center text-white">
                {user?.role === 'admin' ? '👑' : '👤'}
              </div>
              <div>
                <p className="font-medium text-gray-100">{user?.username}</p>
                <p className="text-xs text-gray-500">
                  {user?.role === 'admin' ? '管理员' : '普通用户'}
                </p>
              </div>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-4 space-y-2 overflow-y-auto custom-scrollbar">
            {/* New chat button */}
            <Link
              to="/"
              onClick={() => {
                // This will trigger a new chat in the chat page
                if (location.pathname === '/') {
                  window.dispatchEvent(new CustomEvent('new-chat'));
                }
              }}
              className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors"
            >
              <Plus size={20} />
              <span>新对话</span>
            </Link>

            <div className="mt-4">
              {navItems.map((item) => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={clsx(
                    'sidebar-item',
                    location.pathname === item.path && 'sidebar-item-active'
                  )}
                >
                  <item.icon size={20} />
                  <span>{item.label}</span>
                </Link>
              ))}
            </div>

            {isAdmin && (
              <div className="pt-4 border-t border-dark-border mt-4">
                <p className="px-3 py-2 text-xs text-gray-500 uppercase">管理员功能</p>
                {adminItems.map((item) => (
                  <Link
                    key={item.path}
                    to={item.path}
                    className={clsx(
                      'sidebar-item',
                      location.pathname === item.path && 'sidebar-item-active'
                    )}
                  >
                    <item.icon size={20} />
                    <span>{item.label}</span>
                  </Link>
                ))}
              </div>
            )}

            <div className="pt-4 border-t border-dark-border mt-4">
              <Link
                to="/change-password"
                className={clsx(
                  'sidebar-item',
                  location.pathname === '/change-password' && 'sidebar-item-active'
                )}
              >
                <Key size={20} />
                <span>修改密码</span>
              </Link>
            </div>
          </nav>

          {/* Logout */}
          <div className="p-4 border-t border-dark-border">
            <button
              onClick={handleLogout}
              className="sidebar-item w-full text-red-400 hover:text-red-300 hover:bg-red-900/20"
            >
              <LogOut size={20} />
              <span>退出登录</span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex min-h-0 flex-col overflow-hidden">
        {/* Mobile header */}
        <header className="lg:hidden flex items-center justify-between p-4 bg-dark-card border-b border-dark-border">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 text-gray-400 hover:text-gray-100"
          >
            <Menu size={24} />
          </button>
          <h1 className="font-bold text-white">智能设计助手</h1>
          <div className="w-10" />
        </header>

        {/* Page content */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {children}
        </div>
      </main>
    </div>
  );
}
