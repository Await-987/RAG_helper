import { FileText } from 'lucide-react';

interface SourceCitationProps {
  sources: string[];
}

export function SourceCitation({ sources }: SourceCitationProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-3 pt-3 border-t border-dark-border">
      <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1.5">
        <FileText size={12} />
        <span>来源</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {sources.map((source, i) => (
          <span
            key={i}
            className="inline-flex items-center px-2 py-0.5 rounded-md bg-primary-600/10 text-primary-400 text-xs border border-primary-600/20"
          >
            {source}
          </span>
        ))}
      </div>
    </div>
  );
}
