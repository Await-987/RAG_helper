import { useState } from 'react';
import { ChevronDown, Lightbulb } from 'lucide-react';

interface ReasoningBlockProps {
  content: string;
  defaultOpen?: boolean;
}

export function ReasoningBlock({ content, defaultOpen = false }: ReasoningBlockProps) {
  const [open, setOpen] = useState(defaultOpen);

  if (!content) return null;

  return (
    <div className="mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50 transition-colors"
      >
        <Lightbulb size={14} />
        <span>思考过程</span>
        <ChevronDown
          size={14}
          className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
        />
      </button>
      <div className={`collapse-wrapper ${open ? 'open' : ''}`}>
        <div className="collapse-inner">
          <div className="mt-2 p-3 rounded-xl text-sm text-zinc-400 leading-relaxed max-h-[50vh] overflow-y-auto custom-scrollbar border border-white/[0.04]"
            style={{ background: 'rgba(255,255,255,0.03)' }}
          >
            {content}
          </div>
        </div>
      </div>
    </div>
  );
}
