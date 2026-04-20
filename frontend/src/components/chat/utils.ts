import { fileApi } from '@/api';
import { getAccessToken } from '@/utils/authToken';

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
  if (!src) return '';

  const safeSrc = src.trim().replace(/^<|>$/g, '');

  // 已经是完整 URL 或 API 路径
  if (/^(https?:)?\/\//.test(safeSrc) || safeSrc.startsWith('data:') || safeSrc.startsWith('blob:')) {
    return safeSrc;
  }
  if (safeSrc.startsWith('/api/')) {
    return safeSrc;
  }

  // 解码并规范化路径
  let normalizedPath = safeDecodeURIComponent(safeSrc)
    .replace(/^\.?\//, '')
    .replace(/^\/+/, '');

  // 统一移除前缀，目标是得到 mineru_output/xxx.jpg 或 xxx.pdf 格式
  for (const prefix of ['data/stored_files/', 'stored_files/', 'data/']) {
    if (normalizedPath.startsWith(prefix)) {
      normalizedPath = normalizedPath.slice(prefix.length);
      break;
    }
  }

  return fileApi.getContentUrl(normalizedPath);
}

export function withAccessToken(url?: string): string {
  const normalized = (url ?? '').trim();
  if (!normalized) {
    return '';
  }

  const token = getAccessToken();
  if (!token) {
    return normalized;
  }

  const separator = normalized.includes('?') ? '&' : '?';
  return `${normalized}${separator}token=${encodeURIComponent(token)}`;
}
