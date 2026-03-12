import type { ComponentPropsWithoutRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import { Bot, Loader2 } from 'lucide-react';
import { AuthenticatedImage } from './AuthenticatedImage';
import { normalizeChatMarkdown } from './markdown';

import 'katex/dist/katex.min.css';

type TableProps = ComponentPropsWithoutRef<'table'>;
type TableSectionProps = ComponentPropsWithoutRef<'thead'>;
type TableBodyProps = ComponentPropsWithoutRef<'tbody'>;
type TableRowProps = ComponentPropsWithoutRef<'tr'>;
type TableCellProps = ComponentPropsWithoutRef<'th'>;
type TableDataCellProps = ComponentPropsWithoutRef<'td'>;

interface StreamingMessageProps {
  content: string;
  reasoning: string;
  isLoading: boolean;
}

export function StreamingMessage({ content, reasoning, isLoading }: StreamingMessageProps) {
  const showLoading = isLoading && !content && !reasoning;
  const hasReasoning = reasoning && reasoning.length > 0;
  const markdownContent = normalizeChatMarkdown(content);
  const hasUnclosedTable = /<table\b/i.test(content) && !/<\/table>/i.test(content);
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
              <div className="whitespace-pre-wrap text-sm">{reasoning}</div>
            </div>
          )}

          {/* Content (streaming) */}
          {content && (
            <div className="markdown-content">
              {isLoading ? (
                <div className="whitespace-pre-wrap">{streamingText}</div>
              ) : (
                <ReactMarkdown
                  remarkPlugins={[remarkMath, remarkGfm]}
                  rehypePlugins={[rehypeKatex, rehypeRaw]}
                  components={{
                    img: () => null,
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
                    pre: ({ children }) => (
                      <pre className="bg-dark-bg p-3 rounded-lg overflow-x-auto my-3 text-sm">
                        {children}
                      </pre>
                    ),
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
