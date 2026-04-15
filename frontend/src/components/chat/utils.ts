import { fileApi } from '@/api';

function safeDecodeURIComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function isValidKnowledgeBaseAssetPath(src?: string): boolean {
  if (!src) {
    return false;
  }

  const normalized = safeDecodeURIComponent(src).trim();
  if (!normalized) {
    return false;
  }

  return !normalized.includes('...') && !normalized.includes('…');
}

export function resolveKnowledgeBaseAssetUrl(src?: string): string {
  if (!isValidKnowledgeBaseAssetPath(src)) {
    return '';
  }

  const safeSrc = (src ?? '').trim();

  if (/^(https?:)?\/\//.test(safeSrc) || safeSrc.startsWith('data:') || safeSrc.startsWith('blob:')) {
    return safeSrc;
  }

  const normalizedPath = safeDecodeURIComponent(safeSrc)
    .replace(/^\.?\//, '')
    .replace(/^data\/stored_files\//, '');

  return fileApi.getContentUrl(normalizedPath);
}
