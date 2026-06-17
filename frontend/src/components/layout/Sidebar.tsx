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
  Network,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

const APP_NAME = '基于大模型的电网工程系统设计智能助手';

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const currentSessionId = useCurrentSessionId();
  const { sessions, loadSessions, loadSession, setCurrentSessionId, deleteSession, sessionsLoading } = useChatStore();
  const [searchQuery, setSearchQuery] = useState('');
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
      {/* Brand area */}
      <div className="px-3 pt-5 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center shadow-lg shadow-blue-600/20">
            <MessageSquare size={18} className="text-white" />
          </div>
          <div className="min-w-0">
            <h1 className="max-w-40 text-xs font-semibold leading-snug text-zinc-100">
              {APP_NAME}
            </h1>
            <p className="text-[11px] text-zinc-500">知识库检索问答</p>
          </div>
        </div>
      </div>

      {/* New chat */}
      <div className="px-3 pb-2">
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-center gap-2"
          onClick={handleNewChat}
        >
          <Plus size={16} />
          新对话
        </Button>
      </div>

      {/* Search */}
      <div className="px-3 pb-2">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <Input
            type="text"
            placeholder="搜索..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-9 text-sm rounded-xl"
          />
        </div>
      </div>

      {/* Divider */}
      <div className="mx-3 border-t border-white/[0.04]" />

      {/* Session list */}
      <div className="flex-1 overflow-y-auto custom-scrollbar px-2 pt-2">
        {sessionsLoading ? (
          <div className="space-y-2 px-1">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="flex items-center gap-2 px-2 py-2">
                <Skeleton className="h-3.5 w-3.5 rounded" />
                <Skeleton className="h-4 flex-1" />
              </div>
            ))}
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="text-center text-zinc-500 text-sm py-6">暂无对话</div>
        ) : (
          filteredSessions.map((session) => (
            <div
              key={session.session_id}
              onClick={() => handleSelectSession(session.session_id)}
              className={`group flex items-center gap-2 px-2 py-2 rounded-xl cursor-pointer mb-1 transition-all duration-150 ${
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

      {/* Divider */}
      <div className="mx-3 border-t border-white/[0.04]" />

      {/* Navigation */}
      <div className="px-2 py-2 space-y-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => navigate('/files')}
              className={`sidebar-item w-full text-sm ${location.pathname === '/files' ? 'sidebar-item-active' : ''}`}
            >
              <FileText size={16} className="text-zinc-500" />
              文件管理
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">管理知识库文件</TooltipContent>
        </Tooltip>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => navigate('/knowledge-graph')}
              className={`sidebar-item w-full text-sm ${location.pathname === '/knowledge-graph' ? 'sidebar-item-active' : ''}`}
            >
              <Network size={16} className="text-zinc-500" />
              知识图谱
            </button>
          </TooltipTrigger>
          <TooltipContent side="right">知识图谱可视化</TooltipContent>
        </Tooltip>
        {isAdmin && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                onClick={() => navigate('/users')}
                className={`sidebar-item w-full text-sm ${location.pathname === '/users' ? 'sidebar-item-active' : ''}`}
              >
                <Users size={16} className="text-zinc-500" />
                用户管理
              </button>
            </TooltipTrigger>
            <TooltipContent side="right">管理系统用户</TooltipContent>
          </Tooltip>
        )}
      </div>

      {/* Divider */}
      <div className="mx-3 border-t border-white/[0.04]" />

      {/* User */}
      <div className="p-3">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="w-full flex items-center gap-2 px-2 py-2 rounded-xl text-sm text-zinc-300 hover:bg-zinc-800/50 transition-colors">
              <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center text-xs font-medium text-white shadow-sm shadow-primary-600/20">
                {user?.username?.charAt(0).toUpperCase()}
              </div>
              <span className="flex-1 truncate">{user?.username}</span>
              <ChevronRight size={14} className="text-zinc-500" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-48">
            <DropdownMenuItem onClick={() => navigate('/change-password')}>
              <Key size={14} />
              修改密码
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-red-400 focus:text-red-300" onClick={handleLogout}>
              <LogOut size={14} />
              退出登录
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
