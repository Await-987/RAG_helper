import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore, useCurrentSessionId } from '@/stores/chatStore';
import {
  Plus,
  MessageSquare,
  FileText,
  Users,
  Search,
  Trash2,
  LogOut,
  Key,
  ChevronRight,
  Loader2,
} from 'lucide-react';

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const currentSessionId = useCurrentSessionId();
  const { sessions, loadSessions, loadSession, setCurrentSessionId, deleteSession, sessionsLoading } = useChatStore();
  const [searchQuery, setSearchQuery] = useState('');
  const [showUserMenu, setShowUserMenu] = useState(false);
  const isAdmin = user?.role === 'admin';

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const filteredSessions = searchQuery
    ? sessions.filter((s) => s.title.toLowerCase().includes(searchQuery.toLowerCase()))
    : sessions;

  const handleNewChat = useCallback(() => {
    setCurrentSessionId(null);
    navigate('/');
  }, [navigate, setCurrentSessionId]);

  const handleSelectSession = useCallback(
    async (sessionId: string) => {
      await loadSession(sessionId);
      navigate('/');
    },
    [navigate, loadSession]
  );

  const handleDeleteSession = useCallback(
    async (e: React.MouseEvent, sessionId: string) => {
      e.stopPropagation();
      await deleteSession(sessionId);
    },
    [deleteSession]
  );

  const handleLogout = useCallback(() => {
    logout();
    navigate('/login');
  }, [logout, navigate]);

  return (
    <div className="w-60 h-full flex flex-col sidebar-container">
      {/* New chat */}
      <div className="p-3">
        <button
          onClick={handleNewChat}
          className="sidebar-item w-full justify-center gap-2 rounded-xl border border-zinc-700 text-sm"
        >
          <Plus size={16} />
          新对话
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            type="text"
            placeholder="搜索..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm rounded-xl bg-zinc-800/50 border-none outline-none text-zinc-300 placeholder-zinc-500 focus:bg-zinc-800"
          />
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-2">
        {sessionsLoading ? (
          <div className="flex items-center justify-center py-6">
            <Loader2 size={16} className="animate-spin text-zinc-500" />
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="text-center text-zinc-500 text-sm py-6">暂无对话</div>
        ) : (
          filteredSessions.map((session) => (
            <div
              key={session.session_id}
              onClick={() => handleSelectSession(session.session_id)}
              className={`group flex items-center gap-2 px-2 py-2 rounded-xl cursor-pointer mb-1 ${
                currentSessionId === session.session_id
                  ? 'sidebar-item-active'
                  : 'sidebar-item'
              }`}
            >
              <MessageSquare size={14} className="text-zinc-500 shrink-0" />
              <span className="flex-1 truncate text-sm text-zinc-300">{session.title}</span>
              <button
                onClick={(e) => handleDeleteSession(e, session.session_id)}
                className="opacity-0 group-hover:opacity-100 p-1 text-zinc-500 hover:text-red-400 transition-all"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Navigation */}
      <div className="px-2 py-2 space-y-1">
        <button
          onClick={() => navigate('/files')}
          className={`sidebar-item w-full text-sm ${location.pathname === '/files' ? 'sidebar-item-active' : ''}`}
        >
          <FileText size={16} className="text-zinc-500" />
          文件管理
        </button>
        {isAdmin && (
          <button
            onClick={() => navigate('/users')}
            className={`sidebar-item w-full text-sm ${location.pathname === '/users' ? 'sidebar-item-active' : ''}`}
          >
            <Users size={16} className="text-zinc-500" />
            用户管理
          </button>
        )}
      </div>

      {/* User */}
      <div className="p-3">
        <button
          onClick={() => setShowUserMenu(!showUserMenu)}
          className="w-full flex items-center gap-2 px-2 py-2 rounded-xl text-sm text-zinc-300 hover:bg-zinc-800/50 transition-colors"
        >
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center text-xs font-medium text-white">
            {user?.username?.charAt(0).toUpperCase()}
          </div>
          <span className="flex-1 truncate">{user?.username}</span>
          <ChevronRight size={14} className={`text-zinc-500 transition-transform ${showUserMenu ? 'rotate-90' : ''}`} />
        </button>

        {showUserMenu && (
          <div className="mt-1 rounded-xl bg-zinc-800/80 overflow-hidden">
            <button
              onClick={() => { navigate('/change-password'); setShowUserMenu(false); }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-zinc-400 hover:text-zinc-200 hover:bg-zinc-700/50 transition-colors"
            >
              <Key size={14} />
              修改密码
            </button>
            <button
              onClick={handleLogout}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-zinc-700/50 transition-colors"
            >
              <LogOut size={14} />
              退出
            </button>
          </div>
        )}
      </div>
    </div>
  );
}