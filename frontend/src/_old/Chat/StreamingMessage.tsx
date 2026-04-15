import { Bot, Loader2 } from 'lucide-react';
import { ChatContent } from './ChatContent';

interface StreamingMessageProps {
  content: string;
  reasoning: string;
  isLoading: boolean;
}

export function StreamingMessage({ content, reasoning, isLoading }: StreamingMessageProps) {
  const showLoading = isLoading && !content && !reasoning;
  const hasReasoning = reasoning && reasoning.length > 0;
  const hasUnclosedTable = /<table\b/i.test(content) && !/<\/table>/i.test(content);
  const reasoningPreview = reasoning
    .replace(/!\[[^\]]*]\([^)]+\)/g, '')
    .replace(/<img\b[^>]*>/gi, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  const streamingPreview = content
    .replace(/!\[[^\]]*]\([^)]+\)/g, '')
    .replace(/<img\b[^>]*>/gi, '')
    .replace(/<table[\s\S]*?<\/table>/gi, '\n\n[表格内容生成中]\n\n')
    .replace(/<\/?(table|thead|tbody|tr|th|td)[^>]*>/gi, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  const streamingText = hasUnclosedTable
    ? `${streamingPreview}\n\n[表格内容生成中]`.trim()
    : streamingPreview;

  return (
    <div className="flex gap-3">
      {/* Avatar */}
      <div className="w-8 h-8 rounded-full bg-dark-hover flex items-center justify-center flex-shrink-0">
        <Bot size={18} className="text-primary-400" />
      </div>

      {/* Content */}
      <div className="flex-1 max-w-[85%]">
        <div className="message-bubble message-bubble-assistant">
          {/* Loading state */}
          {showLoading && (
            <div className="flex items-center gap-2 text-gray-400">
              <Loader2 size={16} className="animate-spin" />
              <span>思考中...</span>
            </div>
          )}

          {/* Reasoning (streaming) */}
          {hasReasoning && (
            <div className="reasoning-block mb-3">
              <div className="flex items-center gap-2 mb-2 text-sm text-gray-400">
                <Loader2 size={14} className="animate-spin" />
                <span>思考过程</span>
              </div>
              {isLoading ? (
                <div className="markdown-content whitespace-pre-wrap">{reasoningPreview}</div>
              ) : (
                <ChatContent content={reasoning} suppressImages />
              )}
            </div>
          )}

          {/* Content (streaming) */}
          {content && (
            <div>
              {isLoading ? (
                <div className="markdown-content whitespace-pre-wrap">{streamingText}</div>
              ) : (
                <ChatContent content={content} suppressImages />
              )}
              {!content.endsWith('.') && !content.endsWith('。') && !content.endsWith('\n') && (
                <span className="inline-block w-2 h-4 bg-primary-400 animate-pulse ml-0.5" />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
