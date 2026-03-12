import { useEffect, useState } from 'react';
import { resolveKnowledgeBaseAssetUrl } from './utils';

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
        const token = localStorage.getItem('access_token');
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
        console.error('Failed to load knowledge base image:', error);
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
      {!resolvedSrc && status === 'error' ? (
        <div className="kb-image-fallback">图片加载失败</div>
      ) : (
        <>
          {!isDecoded && (
            <div className="kb-image-placeholder" aria-hidden="true">
              <div className="kb-image-shimmer" />
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
