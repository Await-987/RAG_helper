import type { ComponentPropsWithoutRef, ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Components } from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import type { ChatContentBlock } from '@/types';
import { parseChatContentBlocks } from './markdown';

import 'katex/dist/katex.min.css';

type TableProps = ComponentPropsWithoutRef<'table'>;
type TableSectionProps = ComponentPropsWithoutRef<'thead'>;
type TableBodyProps = ComponentPropsWithoutRef<'tbody'>;
type TableRowProps = ComponentPropsWithoutRef<'tr'>;
type TableCellProps = ComponentPropsWithoutRef<'th'>;
type TableDataCellProps = ComponentPropsWithoutRef<'td'>;
type PreProps = ComponentPropsWithoutRef<'pre'>;
type ImageProps = ComponentPropsWithoutRef<'img'>;

interface ChatContentProps {
  content: string;
  blocks?: ChatContentBlock[];
  suppressImages?: boolean;
}

const markdownComponents = (suppressImages: boolean): Components => {
  const components: Components = {
  table: ({ children, ...props }: TableProps) => (
    <div className="chat-block-shell overflow-x-auto">
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
  pre: ({ children }: PreProps) => (
    <div className="chat-block-shell">
      <pre className="bg-dark-bg p-3 rounded-lg overflow-x-auto my-0 text-sm">
        {children}
      </pre>
    </div>
  ),
  code: ({ className, children }: { className?: string; children?: ReactNode }) => {
    const isInline = !className;
    return isInline ? (
      <code className="bg-dark-hover px-1.5 py-0.5 rounded text-primary-400 text-sm">
        {children}
      </code>
    ) : (
      <code className={className}>{children}</code>
    );
  },
  };

  if (suppressImages) {
    components.img = (_props: ImageProps) => null;
  }

  return components;
};

export function ChatContent({ content, blocks: providedBlocks, suppressImages = false }: ChatContentProps) {
  const blocks = (providedBlocks && providedBlocks.length > 0) ? providedBlocks : parseChatContentBlocks(content);
  const components = markdownComponents(suppressImages);

  return (
    <div className="markdown-content">
      {blocks.map((block, index) => {
        const key = `${block.type}-${index}`;

        if (block.type === 'math') {
          return (
            <div key={key} className="chat-block-shell">
              <ReactMarkdown
                remarkPlugins={[remarkMath, remarkGfm]}
                rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: 'ignore' }], rehypeRaw]}
                components={components}
              >
                {`$$\n${block.content}\n$$`}
              </ReactMarkdown>
            </div>
          );
        }

        if (block.type === 'table' || block.type === 'code') {
          return (
            <div key={key} className="chat-block-shell">
              <ReactMarkdown
                remarkPlugins={[remarkMath, remarkGfm]}
                rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: 'ignore' }], rehypeRaw]}
                components={components}
              >
                {block.content}
              </ReactMarkdown>
            </div>
          );
        }

        return (
          <ReactMarkdown
            key={key}
            remarkPlugins={[remarkMath, remarkGfm]}
            rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: 'ignore' }], rehypeRaw]}
            components={components}
          >
            {block.content}
          </ReactMarkdown>
        );
      })}
    </div>
  );
}
