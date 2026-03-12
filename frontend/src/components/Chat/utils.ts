import { fileApi } from '@/api';

function safeDecodeURIComponent(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export function resolveKnowledgeBaseAssetUrl(src?: string): string {
  if (!src) {
    return '';
  }

  if (/^(https?:)?\/\//.test(src) || src.startsWith('data:') || src.startsWith('blob:')) {
    return src;
  }

  const normalizedPath = safeDecodeURIComponent(src)
    .replace(/^\.?\//, '')
    .replace(/^data\/stored_files\//, '');

  return fileApi.getContentUrl(normalizedPath);
}
