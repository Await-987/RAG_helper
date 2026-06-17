import { useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Send, FileText, Calculator, HelpCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface WelcomeScreenProps {
  onSend: (message: string) => void;
}

const SUGGESTION_CATEGORIES = [
  {
    icon: FileText,
    title: '文档查询',
    color: 'text-blue-400',
    bg: 'bg-blue-500/10',
    border: 'border-blue-500/10',
    suggestions: ['变压器短路阻抗标准值是多少？', '电力线路保护配置有哪些要求？'],
  },
  {
    icon: Calculator,
    title: '数据分析',
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/10',
    suggestions: ['绝缘配合的基本原则是什么？', '计算导线载流量的方法'],
  },
  {
    icon: HelpCircle,
    title: '概念解释',
    color: 'text-purple-400',
    bg: 'bg-purple-500/10',
    border: 'border-purple-500/10',
    suggestions: ['什么是短路电流？', '解释无功补偿的作用'],
  },
];

export function WelcomeScreen({ onSend }: WelcomeScreenProps) {
  const [input, setInput] = useState('');

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim();
    if (trimmed) onSend(trimmed);
  }, [input, onSend]);

  return (
    <div className="flex flex-col h-full">
      {/* Main content area */}
      <div className="flex-1 flex flex-col items-center justify-center px-4 pt-8 pb-4">
        {/* Brand and greeting */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="text-center mb-10"
        >
          <div className="inline-flex items-center gap-2 mb-4 px-3 py-1.5 rounded-full bg-primary-500/10 border border-primary-500/15">
            <span className="text-xs font-medium text-primary-400">RAG Knowledge Base</span>
          </div>
          <h1 className="text-3xl font-semibold text-white mb-2">
            今天需要什么帮助？
          </h1>
          <p className="text-zinc-400">
            基于知识库文档的智能问答，支持 PDF、表格、公式
          </p>
        </motion.div>

        {/* Suggestion cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-2xl w-full mb-8">
          {SUGGESTION_CATEGORIES.map((category, i) => (
            <motion.div
              key={category.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: i * 0.1 }}
              whileHover={{ y: -4, transition: { duration: 0.15 } }}
              className={`suggestion-card ${category.border} group-hover:border-blue-500/25`}
            >
              <div className={`inline-flex items-center gap-2 mb-3 ${category.color}`}>
                <div className={`p-1.5 rounded-lg ${category.bg}`}>
                  <category.icon size={16} />
                </div>
                <span className="font-medium">{category.title}</span>
              </div>
              <div className="space-y-2">
                {category.suggestions.map((text) => (
                  <button
                    key={text}
                    onClick={() => onSend(text)}
                    className="block w-full text-left text-sm text-zinc-400 hover:text-zinc-200 transition-colors py-1 px-2 -mx-2 rounded-lg hover:bg-white/[0.03]"
                  >
                    {text}
                  </button>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Bottom input area */}
      <div className="px-4 pb-4">
        <div className="max-w-2xl mx-auto">
          <div className="input-chat flex items-center gap-2 pr-3">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder="向知识库提问..."
              className="flex-1 bg-transparent outline-none resize-none text-base text-zinc-100 placeholder-zinc-500"
              rows={1}
              style={{ maxHeight: '200px', overflowY: 'hidden' }}
              autoFocus
            />
            <Button
              size="icon"
              onClick={handleSubmit}
              disabled={!input.trim()}
              className="shrink-0"
            >
              <Send size={18} className="text-white" />
            </Button>
          </div>
          <p className="text-center text-xs text-zinc-500 mt-2">
            智能知识库助手可能出错，请核实重要信息
          </p>
        </div>
      </div>
    </div>
  );
}