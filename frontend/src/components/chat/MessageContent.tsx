import React, { memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import 'katex/dist/katex.min.css';
import { CodeBlock } from './CodeBlock';
import { AuthenticatedImage } from './AuthenticatedImage';
import { getAccessToken } from '@/utils/authToken';
import { FileText } from 'lucide-react';

interface MessageContentProps {
  content: string;
  blocks?: unknown[];
}

// 解析 sources 区块
const SOURCE_REFS_REGEX = /<!-- SOURCE_REFS_START -->\s*([\s\S]*?)\s*<!-- SOURCE_REFS_END -->/;

function extractSourcesBlock(content: string): { mainContent: string; sourcesContent: string | null } {
  const match = content.match(SOURCE_REFS_REGEX);
  if (match) {
    const mainContent = content.replace(SOURCE_REFS_REGEX, '').trim();
    return { mainContent, sourcesContent: match[1] };
  }
  return { mainContent: content, sourcesContent: null };
}

export const MessageContent = memo(function MessageContent({ content }: MessageContentProps) {
  // 解析 sources 区块
  const { mainContent, sourcesContent } = extractSourcesBlock(content);
  const hasVisibleContent = mainContent.trim().length > 0;

  // 用 MarkdownRenderer 渲染内容（包含图片），SourcesBlock 渲染超链接
  return (
    <div className="markdown-content">
      {hasVisibleContent ? (
        <MarkdownRenderer content={mainContent} />
      ) : sourcesContent ? (
        <p className="text-zinc-300">已找到相关文档来源，见下方参考来源。</p>
      ) : null}
      {sourcesContent && <SourcesBlock content={sourcesContent} />}
    </div>
  );
});

// 渲染 sources 区块
function SourcesBlock({ content }: { content: string }) {
  const token = getAccessToken();

  // 按行解析，支持多种 markdown 链接格式
  const lines = content.split('\n').filter(line => line.trim());
  const sources: { label: string; url: string }[] = [];
  const seenUrls = new Set<string>();
  const pushSource = (label: string, url: string) => {
    if (!url || seenUrls.has(url)) return;
    sources.push({ label, url });
    seenUrls.add(url);
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const linkMatches = [...trimmed.matchAll(/\[([^\]]+)\]\(([^)]+)\)/g)];
    if (linkMatches.length > 0) {
      for (const match of linkMatches) {
        pushSource(match[1], match[2]);
      }
      continue;
    }

    // 模式1: - [label](url)
    const match1 = trimmed.match(/^-\s*\[([^\]]+)\]\(([^)]+)\)$/);
    if (match1) {
      pushSource(match1[1], match1[2]);
      continue;
    }

    // 模式2: [label](url) (没有 - 前缀)
    const match2 = trimmed.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (match2) {
      pushSource(match2[1], match2[2]);
      continue;
    }

    // 模式3: 行内包含 markdown 链接
    const match3 = trimmed.match(/\[([^\]]+)\]\(([^)]+)\)/);
    if (match3) {
      pushSource(match3[1], match3[2]);
      continue;
    }

    // 模式4: 纯 API URL
    if (trimmed.includes('/api/v1/files/content')) {
      const urlMatch = trimmed.match(/(\/api\/v1\/files\/content\?[^\s]+)/);
      if (urlMatch) {
        const fileName = decodeURIComponent(urlMatch[1].split('file_tag=').pop() || '').split('/').pop() || '来源文件';
        pushSource(fileName, urlMatch[1]);
      }
    }
  }

  if (sources.length === 0) return null;

  return (
    <div className="mt-4 pt-3 border-t border-zinc-800/50">
      <div className="text-xs font-medium text-zinc-500 mb-2 flex items-center gap-1.5">
        <FileText size={12} />
        参考来源
      </div>
      <div className="flex flex-wrap gap-2">
        {sources.map((source, i) => {
          let url = source.url;
          if (token) {
            const separator = url.includes('?') ? '&' : '?';
            url = `${url}${separator}token=${encodeURIComponent(token)}`;
          }
          return (
            <a
              key={i}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="source-card"
            >
              <span className="text-[10px] text-primary-500/60 font-medium">[{i + 1}]</span>
              {source.label}
            </a>
          );
        })}
      </div>
    </div>
  );
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
