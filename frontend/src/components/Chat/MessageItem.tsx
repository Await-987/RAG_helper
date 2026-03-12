import { useState } from 'react';
import type { ComponentPropsWithoutRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import type { ChatMessage } from '@/types';
import { User, Bot, ChevronDown, ChevronUp, Copy, Check, Image as ImageIcon } from 'lucide-react';
import clsx from 'clsx';
import { AuthenticatedImage } from './AuthenticatedImage';
import { extractImageReferences, normalizeChatMarkdown, stripImageReferences } from './markdown';

import 'katex/dist/katex.min.css';

type TableProps = ComponentPropsWithoutRef<'table'>;
type TableSectionProps = ComponentPropsWithoutRef<'thead'>;
type TableBodyProps = ComponentPropsWithoutRef<'tbody'>;
type TableRowProps = ComponentPropsWithoutRef<'tr'>;
type TableCellProps = ComponentPropsWithoutRef<'th'>;
type TableDataCellProps = ComponentPropsWithoutRef<'td'>;

interface MessageItemProps {
  message: ChatMessage;
}

export function MessageItem({ message }: MessageItemProps) {
  const [showReasoning, setShowReasoning] = useState(false);
  const [showAttachments, setShowAttachments] = useState(false);
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';
  const hasReasoning = message.reasoning && message.reasoning.length > 0;
  const imageReferences = extractImageReferences(message.content);
  const hasAttachments = imageReferences.length > 0;
  const markdownContent = normalizeChatMarkdown(stripImageReferences(message.content));

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
                <div className="reasoning-block mt-2 whitespace-pre-wrap">
                  {message.reasoning}
                </div>
              )}
            </div>
          )}

          {/* Main content */}
          <div className="markdown-content">
            <ReactMarkdown
              remarkPlugins={[remarkMath, remarkGfm]}
              rehypePlugins={[rehypeKatex, rehypeRaw]}
              components={{
                // Table styling
                table: ({ children, ...props }: TableProps) => (
                  <div className="overflow-x-auto my-3">
                    <table {...props} className="min-w-full border-collapse text-sm">
                      {children}
                    </table>
                  </div>
                ),
                thead: ({ children, ...props }: TableSectionProps) => (
                  <thead {...props} className="bg-dark-hover text-gray-100">
                    {children}
                  </thead>
                ),
                tbody: ({ children, ...props }: TableBodyProps) => (
                  <tbody {...props} className="divide-y divide-dark-border">
                    {children}
                  </tbody>
                ),
                tr: ({ children, ...props }: TableRowProps) => (
                  <tr {...props} className="border-b border-dark-border align-top">
                    {children}
                  </tr>
                ),
                th: ({ children, ...props }: TableCellProps) => (
                  <th
                    {...props}
                    className="border border-dark-border px-3 py-2 text-left font-semibold whitespace-nowrap"
                  >
                    {children}
                  </th>
                ),
                td: ({ children, ...props }: TableDataCellProps) => (
                  <td
                    {...props}
                    className="border border-dark-border px-3 py-2 align-top whitespace-pre-wrap"
                  >
                    {children}
                  </td>
                ),
                // Code block styling
                pre: ({ children }) => (
                  <pre className="bg-dark-bg p-3 rounded-lg overflow-x-auto my-3 text-sm">
                    {children}
                  </pre>
                ),
                // Inline code styling
                code: ({ className, children }) => {
                  const isInline = !className;
                  return isInline ? (
                    <code className="bg-dark-hover px-1.5 py-0.5 rounded text-primary-400 text-sm">
                      {children}
                    </code>
                  ) : (
                    <code className={className}>{children}</code>
                  );
                },
              }}
            >
              {markdownContent}
            </ReactMarkdown>
          </div>

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
}
