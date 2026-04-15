import { memo, useState } from 'react';
import type { ChatMessage } from '@/types';
import { User, Bot, ChevronDown, ChevronUp, Copy, Check, Image as ImageIcon } from 'lucide-react';
import clsx from 'clsx';
import { AuthenticatedImage } from './AuthenticatedImage';
import { ChatContent } from './ChatContent';
import { extractImageReferences, stripImageReferences } from './markdown';

interface MessageItemProps {
  message: ChatMessage;
}

export const MessageItem = memo(function MessageItem({ message }: MessageItemProps) {
  const [showReasoning, setShowReasoning] = useState(false);
  const [showAttachments, setShowAttachments] = useState(false);
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';
  const hasReasoning = message.reasoning && message.reasoning.length > 0;
  const imageReferences = extractImageReferences(message.content);
  const hasAttachments = imageReferences.length > 0;
  const contentWithoutImages = stripImageReferences(message.content);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      console.error('Failed to copy:', error);
    }
  };

  return (
    <div
      className={clsx(
        'flex gap-3',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* Avatar */}
      <div
        className={clsx(
          'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
          isUser ? 'bg-primary-600' : 'bg-dark-hover'
        )}
      >
        {isUser ? (
          <User size={18} className="text-white" />
        ) : (
          <Bot size={18} className="text-primary-400" />
        )}
      </div>

      {/* Message content */}
      <div
        className={clsx(
          'flex-1 max-w-[85%]',
          isUser ? 'text-right' : 'text-left'
        )}
      >
        <div
          className={clsx(
            'message-bubble inline-block text-left',
            isUser ? 'message-bubble-user' : 'message-bubble-assistant'
          )}
        >
          {/* Reasoning block (collapsible) */}
          {hasReasoning && (
            <div className="mb-3">
              <button
                onClick={() => setShowReasoning(!showReasoning)}
                className="flex items-center gap-1 text-sm text-gray-400 hover:text-gray-300 transition-colors"
              >
                {showReasoning ? (
                  <ChevronUp size={16} />
                ) : (
                  <ChevronDown size={16} />
                )}
                <span>思考过程</span>
              </button>
              {showReasoning && (
                <div className="reasoning-block mt-2">
                  <ChatContent
                    content={message.reasoning || ''}
                    blocks={message.reasoningBlocks}
                    suppressImages
                  />
                </div>
              )}
            </div>
          )}

          {/* Main content */}
          <ChatContent content={contentWithoutImages} blocks={message.blocks} suppressImages />

          {!isUser && hasAttachments && (
            <div className="mt-3 rounded-xl border border-dark-border bg-dark-hover/40">
              <button
                onClick={() => setShowAttachments(!showAttachments)}
                className="flex w-full items-center justify-between px-3 py-2 text-sm text-gray-300"
              >
                <span className="flex items-center gap-2">
                  <ImageIcon size={15} />
                  附件图片 ({imageReferences.length})
                </span>
                {showAttachments ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </button>
              {showAttachments && (
                <div className="border-t border-dark-border px-3 py-3">
                  {imageReferences.map((image) => (
                    <AuthenticatedImage
                      key={image.src}
                      src={image.src}
                      alt={image.alt}
                      className="max-w-full rounded-lg cursor-pointer hover:opacity-90"
                      onClick={(resolvedSrc) => {
                        if (resolvedSrc) window.open(resolvedSrc, '_blank');
                      }}
                    />
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Copy button for assistant messages */}
          {!isUser && (
            <button
              onClick={handleCopy}
              className="mt-2 p-1.5 rounded text-gray-500 hover:text-gray-300 hover:bg-dark-hover transition-colors"
              title="复制内容"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          )}
        </div>

        {/* Timestamp */}
        <p
          className={clsx(
            'text-xs text-gray-500 mt-1',
            isUser ? 'text-right' : 'text-left'
          )}
        >
          {new Date(message.timestamp).toLocaleTimeString('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </p>
      </div>
    </div>
  );
});
