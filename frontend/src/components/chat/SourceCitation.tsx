import { FileText } from 'lucide-react';

interface SourceCitationProps {
  sources: string[];
}

export function SourceCitation({ sources }: SourceCitationProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-4 pt-3 border-t border-zinc-800">
      <div className="flex items-center gap-2 mb-2">
        <FileText size={14} className="text-zinc-500" />
        <span className="text-xs font-medium text-zinc-400">参考来源</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {sources.map((source, i) => (
          <span
            key={i}
            className="inline-flex items-center px-2 py-0.5 rounded-lg text-xs text-primary-400 bg-primary-500/10"
          >
            {source}
          </span>
        ))}
      </div>
    </div>
  );
}