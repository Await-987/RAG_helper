import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Command } from 'cmdk';
import {
  MessageSquare,
  FolderOpen,
  Users,
  Plus,
  Search,
} from 'lucide-react';
import { useChatStore } from '@/stores/chatStore';
import type { ChatSessionSummary } from '@/types';

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const sessions = useChatStore((s) => s.sessions);
  const createNewChat = useChatStore((s) => s.createNewChat);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    document.addEventListener('keydown', down);
    return () => document.removeEventListener('keydown', down);
  }, []);

  const runAction = (action: () => void) => {
    setOpen(false);
    action();
  };

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command Palette"
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[20vh]"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => setOpen(false)}
      />

      {/* Dialog */}
      <div className="relative z-50 w-full max-w-lg rounded-2xl border border-white/[0.08] bg-[#2f2f2f] shadow-2xl overflow-hidden">
        <div className="flex items-center border-b border-white/[0.06] px-4">
          <Search className="mr-2 h-4 w-4 shrink-0 text-zinc-500" />
          <Command.Input
            placeholder="搜索会话、文件或操作..."
            className="flex h-12 w-full bg-transparent py-3 text-sm text-zinc-100 outline-none placeholder:text-zinc-500"
          />
        </div>

        <Command.List className="max-h-80 overflow-y-auto p-2 custom-scrollbar">
          <Command.Empty className="py-6 text-center text-sm text-zinc-500">
            未找到匹配项
          </Command.Empty>

          <Command.Group heading="快捷操作" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-zinc-500">
            <Command.Item
              onSelect={() => runAction(() => { createNewChat(); navigate('/'); })}
              className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-300 transition-colors data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
            >
              <Plus className="h-4 w-4" />
              新建对话
            </Command.Item>
            <Command.Item
              onSelect={() => runAction(() => navigate('/files'))}
              className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-300 transition-colors data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
            >
              <FolderOpen className="h-4 w-4" />
              文件管理
            </Command.Item>
            <Command.Item
              onSelect={() => runAction(() => navigate('/users'))}
              className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-300 transition-colors data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
            >
              <Users className="h-4 w-4" />
              用户管理
            </Command.Item>
          </Command.Group>

          {sessions.length > 0 && (
            <Command.Group heading="最近会话" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-zinc-500">
              {sessions.slice(0, 8).map((session: ChatSessionSummary) => (
                <Command.Item
                  key={session.session_id}
                  value={session.title || session.session_id}
                  onSelect={() => runAction(() => {
                    useChatStore.getState().setCurrentSessionId(session.session_id);
                    navigate('/');
                  })}
                  className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-300 transition-colors data-[selected=true]:bg-zinc-800 data-[selected=true]:text-zinc-100"
                >
                  <MessageSquare className="h-4 w-4 shrink-0" />
                  <span className="truncate">{session.title || '新对话'}</span>
                </Command.Item>
              ))}
            </Command.Group>
          )}
        </Command.List>

        <div className="border-t border-white/[0.06] px-4 py-2">
          <p className="text-xs text-zinc-600">
            <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">↑↓</kbd> 导航{' '}
            <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">↵</kbd> 选择{' '}
            <kbd className="rounded bg-zinc-800 px-1.5 py-0.5 text-zinc-400">esc</kbd> 关闭
          </p>
        </div>
      </div>
    </Command.Dialog>
  );
}