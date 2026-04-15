import { useState, useCallback } from 'react';
import { Send, Zap } from 'lucide-react';

interface WelcomeScreenProps {
  onSend: (message: string) => void;
}

const SUGGESTIONS = [
  '变压器短路阻抗标准值是多少？',
  '电力线路保护配置有哪些要求？',
  '绝缘配合的基本原则是什么？',
];

export function WelcomeScreen({ onSend }: WelcomeScreenProps) {
  const [input, setInput] = useState('');

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (trimmed) onSend(trimmed);
  }, [input, onSend]);

  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="max-w-2xl w-full text-center">
        <div className="mb-6">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-primary-600/20 flex items-center justify-center">
            <Zap size={32} className="text-primary-400" />
          </div>
          <h1 className="text-2xl font-bold text-white mb-2">智能知识库助手</h1>
          <p className="text-gray-400">
            基于文档的专业问答系统，支持 PDF 解析、表格提取、公式识别
          </p>
        </div>

        <div className="relative mb-8">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            placeholder="输入您的问题..."
            className="w-full bg-dark-card border border-dark-border rounded-2xl px-5 py-4 pr-14 text-base text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
          />
          <button
            onClick={handleSubmit}
            disabled={!input.trim()}
            className="absolute right-3 top-1/2 -translate-y-1/2 p-2 rounded-xl bg-primary-600 hover:bg-primary-700 disabled:bg-gray-700 disabled:text-gray-500 text-white transition-colors"
          >
            <Send size={20} />
          </button>
        </div>

        <div>
          <p className="text-sm text-gray-500 mb-3">试试问：</p>
          <div className="flex flex-wrap justify-center gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => onSend(suggestion)}
                className="px-4 py-2 rounded-lg bg-dark-card border border-dark-border text-sm text-gray-300 hover:bg-dark-hover hover:text-gray-100 transition-colors"
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
