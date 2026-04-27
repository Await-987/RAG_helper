import { useState, useCallback, memo } from 'react';
import { Copy, Check, User, Sparkles } from 'lucide-react';
import type { ChatMessage } from '@/types';
import { MessageContent } from './MessageContent';
import { ReasoningBlock } from './ReasoningBlock';
import { AssetGallery } from './AssetGallery';

interface MessageItemProps {
  message: ChatMessage;
  isLast?: boolean;
}

export const MessageItem = memo(function MessageItem({ message, isLast }: MessageItemProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [message.content]);

  return (
    <div className="px-4 py-6 group">
      <div className="max-w-3xl mx-auto flex gap-4">
        {/* Avatar */}
        <div className="shrink-0 select-none">
          {isUser ? (
            <div className="w-8 h-8 rounded-lg bg-zinc-600 flex items-center justify-center">
              <User size={16} className="text-zinc-300" />
            </div>
          ) : (
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center shadow-sm shadow-primary-600/20">
              <Sparkles size={16} className="text-white" />
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          {/* Name label */}
          <div className="text-sm font-medium mb-1.5 text-zinc-300">
            {isUser ? '你' : '知识库助手'}
          </div>

          {/* Reasoning */}
          {message.reasoning && !isUser && (
            <ReasoningBlock content={message.reasoning} />
          )}

          {/* Main content */}
          <div className="markdown-content">
            <MessageContent content={message.content} blocks={message.blocks} />
          </div>

          {/* Assets */}
          {message.assets && message.assets.length > 0 && !isUser && (
            <AssetGallery assets={message.assets} />
          )}

          {/* Actions - appear on message hover */}
          {!isUser && (
            <div className="flex items-center gap-2 mt-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
              <button
                onClick={handleCopy}
                className="text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1.5 text-xs px-2 py-1 rounded-lg hover:bg-zinc-800/50"
              >
                {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                {copied ? '已复制' : '复制'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
