import { useState, useCallback, memo } from 'react';
import { Copy, Check, User, Sparkles, HelpCircle } from 'lucide-react';
import type { ChatMessage } from '@/types';
import { MessageContent } from './MessageContent';
import { ReasoningBlock } from './ReasoningBlock';
import { AssetGallery } from './AssetGallery';
import { RetrievalTracePanel } from './RetrievalTracePanel';

interface MessageItemProps {
  message: ChatMessage;
  isLast?: boolean;
}

export const MessageItem = memo(function MessageItem({ message, isLast }: MessageItemProps) {
  const [copied, setCopied] = useState(false);
  const [tracesOpen, setTracesOpen] = useState(false);
  const isUser = message.role === 'user';
  const hasTraces = !isUser && !!message.retrievalTraces && message.retrievalTraces.length > 0;

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [message.content]);

  return (
    <div className={`px-4 py-6 ${isUser ? '' : ''}`}>
      <div className="max-w-3xl mx-auto flex gap-4">
        {/* Avatar */}
        <div className="shrink-0 select-none">
          {isUser ? (
            <div className="w-8 h-8 rounded-lg bg-zinc-600 flex items-center justify-center">
              <User size={16} className="text-zinc-300" />
            </div>
          ) : (
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center">
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

          {/* Main content - sources 现在在正文中渲染 */}
          <div className="markdown-content">
            <MessageContent content={message.content} blocks={message.blocks} />
          </div>

          {/* Assets - 表格图片等 */}
          {message.assets && message.assets.length > 0 && !isUser && (
            <AssetGallery assets={message.assets} />
          )}

          {/* Retrieval trace panel (toggle) */}
          {tracesOpen && !isUser && (
            <RetrievalTracePanel traces={message.retrievalTraces ?? []} />
          )}

          {/* Actions - appear on hover */}
          {!isUser && (
            <div className="flex items-center gap-3 mt-3 opacity-0 hover:opacity-100 focus-within:opacity-100 transition-opacity">
              <button
                onClick={handleCopy}
                className="text-zinc-500 hover:text-zinc-300 transition-colors flex items-center gap-1.5 text-xs"
              >
                {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
                {copied ? '已复制' : '复制'}
              </button>
              <button
                onClick={() => setTracesOpen((v) => !v)}
                title={hasTraces ? '查看本轮检索的 query、意图和文本块（问题溯源）' : '本轮未触发知识库检索'}
                className={`transition-colors flex items-center gap-1.5 text-xs ${
                  tracesOpen
                    ? 'text-primary-400 hover:text-primary-300'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                <HelpCircle size={14} />
                {tracesOpen ? '收起溯源' : '问题溯源'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
});
