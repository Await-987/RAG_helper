import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { useChatStore } from '@/stores/chatStore';
import { chatApi } from '@/api/chat';
import {
  Plus,
  MessageSquare,
  FileText,
  Users,
  Search,
  Trash2,
  LogOut,
  Key,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const { sessions, loadSessions, loadSession, currentSessionId, setCurrentSessionId, deleteSession } = useChatStore();
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
    <div className="w-72 h-full flex flex-col bg-[#171717] border-r border-dark-border">
      {/* New chat button */}
      <div className="p-3">
        <button
          onClick={handleNewChat}
          className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg border border-dark-border hover:bg-dark-hover transition-colors text-sm"
        >
          <Plus size={16} />
          新建对话
        </button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
          <input
            type="text"
            placeholder="搜索对话..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-dark-bg border border-dark-border rounded-lg pl-9 pr-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          />
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-2">
        {filteredSessions.length === 0 ? (
          <div className="text-center text-gray-500 text-sm py-8">暂无对话</div>
        ) : (
          filteredSessions.map((session) => (
            <div
              key={session.session_id}
              onClick={() => handleSelectSession(session.session_id)}
              className={`
                group flex items-center gap-2 px-3 py-2.5 rounded-lg cursor-pointer text-sm mb-0.5
                transition-colors
                ${currentSessionId === session.session_id
                  ? 'bg-dark-hover text-gray-100'
                  : 'text-gray-400 hover:text-gray-100 hover:bg-dark-hover'}
              `}
            >
              <MessageSquare size={14} className="shrink-0" />
              <span className="flex-1 truncate">{session.title}</span>
              <button
                onClick={(e) => handleDeleteSession(e, session.session_id)}
                className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-all"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* Navigation */}
      <div className="border-t border-dark-border px-2 py-2">
        <nav className="space-y-0.5">
          <button
            onClick={() => navigate('/files')}
            className={`sidebar-item w-full text-sm ${location.pathname === '/files' ? 'sidebar-item-active' : ''}`}
          >
            <FileText size={16} />
            文件管理
          </button>
          {isAdmin && (
            <button
              onClick={() => navigate('/users')}
              className={`sidebar-item w-full text-sm ${location.pathname === '/users' ? 'sidebar-item-active' : ''}`}
            >
              <Users size={16} />
              用户管理
            </button>
          )}
        </nav>
      </div>

      {/* User section */}
      <div className="border-t border-dark-border p-3">
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-dark-hover transition-colors text-sm text-gray-300"
          >
            <div className="w-7 h-7 rounded-full bg-primary-600 flex items-center justify-center text-xs font-medium">
              {user?.username?.charAt(0).toUpperCase()}
            </div>
            <span className="flex-1 text-left truncate">{user?.username}</span>
            <ChevronDown size={14} className="text-gray-500" />
          </button>

          {showUserMenu && (
            <div className="absolute bottom-full left-0 w-full mb-1 bg-dark-card border border-dark-border rounded-lg shadow-lg overflow-hidden z-50">
              <button
                onClick={() => {
                  navigate('/change-password');
                  setShowUserMenu(false);
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-300 hover:bg-dark-hover"
              >
                <Key size={14} />
                修改密码
              </button>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-400 hover:bg-dark-hover"
              >
                <LogOut size={14} />
                退出登录
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
