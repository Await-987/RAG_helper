import { useEffect, useState } from 'react';
import { resolveKnowledgeBaseAssetUrl } from './utils';
import { getAccessToken } from '@/utils/authToken';

interface AuthenticatedImageProps {
  src?: string;
  alt?: string;
  className?: string;
  onClick?: (resolvedSrc: string) => void;
}

export function AuthenticatedImage({
  src,
  alt = '',
  className,
  onClick,
}: AuthenticatedImageProps) {
  const [resolvedSrc, setResolvedSrc] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');
  const [isDecoded, setIsDecoded] = useState(false);
  const [originalSrc] = useState(src || '');

  useEffect(() => {
    const normalizedSrc = resolveKnowledgeBaseAssetUrl(src);
    setIsDecoded(false);

    if (!normalizedSrc) {
      setResolvedSrc('');
      setStatus('error');
      return;
    }

    if (
      /^(https?:)?\/\//.test(normalizedSrc) ||
      normalizedSrc.startsWith('data:') ||
      normalizedSrc.startsWith('blob:')
    ) {
      setResolvedSrc(normalizedSrc);
      setStatus('loading');
      return;
    }

    let revokedUrl = '';
    let cancelled = false;
    setStatus('loading');

    const loadImage = async () => {
      try {
        const token = getAccessToken();
        const response = await fetch(normalizedSrc, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });

        if (!response.ok) {
          throw new Error(`Image request failed: ${response.status}`);
        }

        const blob = await response.blob();
        revokedUrl = URL.createObjectURL(blob);
        if (!cancelled) {
          setResolvedSrc(revokedUrl);
          setStatus('loading');
        }
      } catch (error) {
        console.error('Failed to load knowledge base image:', error, 'src:', src);
        if (!cancelled) {
          setResolvedSrc('');
          setStatus('error');
        }
      }
    };

    loadImage();

    return () => {
      cancelled = true;
      if (revokedUrl) {
        URL.revokeObjectURL(revokedUrl);
      }
    };
  }, [src]);

  return (
    <div className="kb-image-shell my-3">
      {status === 'error' ? (
        <div className="kb-image-fallback text-xs text-zinc-500 p-2 bg-zinc-800/50 rounded">
          <span className="block mb-1">图片加载失败</span>
          {alt && <span className="block text-zinc-400">{alt}</span>}
          {originalSrc && (
            <span className="block text-zinc-600 truncate" title={originalSrc}>
              {originalSrc.slice(0, 80)}{originalSrc.length > 80 ? '...' : ''}
            </span>
          )}
        </div>
      ) : (
        <>
          {!isDecoded && status === 'loading' && (
            <div className="kb-image-placeholder flex items-center justify-center h-24 bg-zinc-800/30 rounded" aria-hidden="true">
              <span className="text-xs text-zinc-500">{alt || '加载中...'}</span>
            </div>
          )}
          {resolvedSrc && (
            <img
              src={resolvedSrc}
              alt={alt}
              className={`${className ?? ''} kb-image ${isDecoded ? 'kb-image-visible' : 'kb-image-hidden'}`.trim()}
              onLoad={() => {
                setIsDecoded(true);
                setStatus('loaded');
              }}
              onError={() => {
                setIsDecoded(false);
                setResolvedSrc('');
                setStatus('error');
              }}
              onClick={() => onClick?.(resolvedSrc)}
            />
          )}
        </>
      )}
    </div>
  );
}
