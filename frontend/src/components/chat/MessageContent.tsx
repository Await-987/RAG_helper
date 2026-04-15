import React, { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import 'katex/dist/katex.min.css';
import type { ChatContentBlock } from '@/types';
import { CodeBlock } from './CodeBlock';
import { AuthenticatedImage } from './AuthenticatedImage';

interface MessageContentProps {
  content: string;
  blocks?: ChatContentBlock[];
}

export const MessageContent = memo(function MessageContent({ content, blocks }: MessageContentProps) {
  // If blocks are available, render them individually for better formatting
  if (blocks && blocks.length > 0) {
    return (
      <div className="markdown-content">
        {blocks.map((block, i) => (
          <ContentBlockRenderer key={i} block={block} />
        ))}
      </div>
    );
  }

  // Fallback: render raw content as markdown
  return (
    <div className="markdown-content">
      <MarkdownRenderer content={content} />
    </div>
  );
});

function ContentBlockRenderer({ block }: { block: ChatContentBlock }) {
  switch (block.type) {
    case 'code': {
      const match = block.content.match(/^```(\w*)\n([\s\S]*?)\n?```$/);
      if (match) {
        return <CodeBlock language={match[1] || undefined} code={match[2]} />;
      }
      return <MarkdownRenderer content={block.content} />;
    }
    case 'math':
      return <MarkdownRenderer content={`$$\n${block.content}\n$$`} />;
    case 'table':
      return (
        <div className="chat-block-shell">
          <MarkdownRenderer content={block.content} />
        </div>
      );
    case 'markdown':
    default:
      return <MarkdownRenderer content={block.content} />;
  }
}

const MarkdownRenderer = memo(function MarkdownRenderer({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex, rehypeRaw]}
      components={{
        pre: ({ children }) => <>{children}</>,
        code: ({ className, children, ...props }) => {
          const match = /language-(\w+)/.exec(className || '');
          const codeString = String(children).replace(/\n$/, '');
          if (match) {
            return <CodeBlock language={match[1]} code={codeString} />;
          }
          return (
            <code className={className} {...props}>
              {children}
            </code>
          );
        },
        img: ({ src, alt }) => {
          if (!src) return null;
          return <AuthenticatedImage src={src} alt={alt || ''} />;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
});
