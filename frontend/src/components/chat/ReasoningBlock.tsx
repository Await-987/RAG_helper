import { useState } from 'react';
import { ChevronRight, Brain } from 'lucide-react';

interface ReasoningBlockProps {
  content: string;
  defaultOpen?: boolean;
}

export function ReasoningBlock({ content, defaultOpen = false }: ReasoningBlockProps) {
  const [open, setOpen] = useState(defaultOpen);

  if (!content) return null;

  return (
    <div className="mb-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200 transition-colors"
      >
        <Brain size={14} />
        <span>思考过程</span>
        <ChevronRight
          size={14}
          className={`transition-transform duration-200 ${open ? 'rotate-90' : ''}`}
        />
      </button>
      {open && (
        <div className="mt-2 pl-3 border-l-2 border-primary-500/50 text-sm text-gray-400 whitespace-pre-wrap max-h-[60vh] overflow-y-auto custom-scrollbar">
          {content}
        </div>
      )}
    </div>
  );
}
