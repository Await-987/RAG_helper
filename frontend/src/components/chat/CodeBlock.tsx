import { useState, useCallback } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
  language?: string;
  code: string;
}

export function CodeBlock({ language, code }: CodeBlockProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [code]);

  return (
    <div className="relative group rounded-2xl overflow-hidden my-3 border border-white/[0.06]">
      <div className="flex items-center justify-between px-4 py-2 bg-[#282c34] text-gray-400 text-xs border-b border-white/[0.04]">
        <span className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-emerald-500/60" />
          {language || 'code'}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-gray-200 transition-colors px-2 py-0.5 rounded hover:bg-white/5"
        >
          {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <SyntaxHighlighter
        language={language || 'text'}
        style={oneDark}
        showLineNumbers
        lineNumberStyle={{ color: '#555', minWidth: '2.5em', paddingRight: '1em' }}
        customStyle={{
          margin: 0,
          borderRadius: 0,
          fontSize: '0.85rem',
          background: '#1a1a2e',
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}
