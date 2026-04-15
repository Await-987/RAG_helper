import { useState, useCallback } from 'react';
import { Copy, Check, RotateCcw, Bot, User } from 'lucide-react';
import type { ChatMessage } from '@/types';
import { MessageContent } from './MessageContent';
import { ReasoningBlock } from './ReasoningBlock';
import { SourceCitation } from './SourceCitation';

interface MessageItemProps {
  message: ChatMessage;
  isStreaming?: boolean;
  onRegenerate?: (message: string) => void;
}

export function MessageItem({ message, isStreaming, onRegenerate }: MessageItemProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [message.content]);

  const handleRegenerate = useCallback(() => {
    if (onRegenerate) onRegenerate(message.content);
  }, [onRegenerate, message.content]);

  return (
    <div className={`group px-4 py-4 ${isUser ? '' : 'bg-[#1a1a1a]'}`}>
      <div className="max-w-3xl mx-auto flex gap-4">
        {/* Avatar */}
        <div className="shrink-0 mt-0.5">
          {isUser ? (
            <div className="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center">
              <User size={16} className="text-gray-300" />
            </div>
          ) : (
            <div className="w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center">
              <Bot size={16} className="text-white" />
            </div>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="text-xs text-gray-500 mb-1">
            {isUser ? '你' : 'AI 助手'}
          </div>

          {/* Reasoning */}
          {message.reasoning && !isUser && (
            <ReasoningBlock content={message.reasoning} defaultOpen={isStreaming} />
          )}

          {/* Main content */}
          <MessageContent content={message.content} blocks={message.blocks} />

          {/* Sources */}
          {message.sources && !isUser && (
            <SourceCitation sources={message.sources} />
          )}

          {/* Actions */}
          <div className="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              onClick={handleCopy}
              className="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-dark-hover transition-colors"
              title="复制"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
            {!isUser && onRegenerate && (
              <button
                onClick={handleRegenerate}
                className="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-dark-hover transition-colors"
                title="重新生成"
              >
                <RotateCcw size={14} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
