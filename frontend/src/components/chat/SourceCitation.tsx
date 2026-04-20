import { FileText, ExternalLink } from 'lucide-react';
import { normalizeChatSources } from '@/types';
import type { ChatSource } from '@/types';
import { fileApi } from '@/api';
import { withAccessToken } from './utils';

interface SourceCitationProps {
  sources: ChatSource[];
}

function buildContentUrl(fileTag: string): string {
  return fileApi.getContentUrl(fileTag);
}

export function SourceCitation({ sources }: SourceCitationProps) {
  const normalizedSources = normalizeChatSources(sources);
  if (normalizedSources.length === 0) return null;

  return (
    <div className="mt-4 pt-3 border-t border-zinc-800">
      <div className="flex items-center gap-2 mb-2">
        <FileText size={14} className="text-zinc-500" />
        <span className="text-xs font-medium text-zinc-400">参考来源</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {normalizedSources.map((source, i) => (
          <a
            key={i}
            href={withAccessToken(source.content_url || buildContentUrl(source.file_tag))}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-xs text-primary-400 bg-primary-500/10 hover:bg-primary-500/20 hover:text-primary-300 transition-colors cursor-pointer"
          >
            <ExternalLink size={10} />
            {source.label}
          </a>
        ))}
      </div>
    </div>
  );
}
