import { Image as ImageIcon, ExternalLink } from 'lucide-react';
import { fileApi } from '@/api';
import { normalizeChatAssets } from '@/types';
import type { ChatAsset } from '@/types';
import { AuthenticatedImage } from './AuthenticatedImage';
import { withAccessToken } from './utils';

interface AssetGalleryProps {
  assets: ChatAsset[];
}

export function AssetGallery({ assets }: AssetGalleryProps) {
  const normalizedAssets = normalizeChatAssets(assets);
  if (normalizedAssets.length === 0) return null;

  return (
    <div className="mt-4 pt-3 border-t border-zinc-800/50">
      <div className="flex items-center gap-2 mb-3">
        <ImageIcon size={14} className="text-zinc-500" />
        <span className="text-xs font-medium text-zinc-500">表格图片</span>
      </div>
      <div className="space-y-4">
        {normalizedAssets.map((asset, index) => (
          <div key={`${asset.asset_tag}-${index}`} className="rounded-xl border border-white/[0.06] bg-zinc-900/40 p-3 transition-colors hover:border-white/[0.1]">
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-xs text-zinc-400 truncate">{asset.label}</span>
              <a
                href={withAccessToken(asset.content_url || fileApi.getContentUrl(asset.asset_tag))}
                target="_blank"
                rel="noopener noreferrer"
                className="source-card"
              >
                <ExternalLink size={10} />
                打开原图
              </a>
            </div>
            <AuthenticatedImage src={asset.content_url || asset.asset_tag} alt={asset.label} />
          </div>
        ))}
      </div>
    </div>
  );
}
