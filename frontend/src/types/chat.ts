export interface ChatContentBlock {
  type: 'markdown' | 'math' | 'table' | 'code';
  content: string;
}

export interface ChatSource {
  label: string;
  file_tag: string;
  content_url?: string;
}

export interface ChatAsset {
  asset_tag: string;
  label: string;
  kind: string;
  source_file_tag?: string;
  content_url?: string;
}

export function normalizeChatSources(input: unknown): ChatSource[] {
  if (!Array.isArray(input)) {
    return [];
  }

  const normalized: ChatSource[] = [];
  const seen = new Set<string>();

  for (const item of input) {
    let fileTag = '';
    let label = '';
    let contentUrl = '';

    if (typeof item === 'string') {
      fileTag = item.trim();
      label = fileTag.split('/').pop() || fileTag;
    } else if (item && typeof item === 'object') {
      const record = item as Record<string, unknown>;
      fileTag = String(record.file_tag ?? '').trim();
      label = String(record.label ?? '').trim();
      contentUrl = String(record.content_url ?? '').trim();
      if (!label && fileTag) {
        label = fileTag.split('/').pop() || fileTag;
      }
    }

    if (!fileTag || seen.has(fileTag)) {
      continue;
    }

    normalized.push({
      file_tag: fileTag,
      label: label || fileTag,
      content_url: contentUrl || undefined,
    });
    seen.add(fileTag);
  }

  return normalized;
}

export interface RetrievalChunkRef {
  file_tag: string;
  label: string;
  score: number;
  preview: string;
}

export interface RetrievalTrace {
  query: string;
  intent_description: string;
  chunks: RetrievalChunkRef[];
}

export function normalizeRetrievalTraces(input: unknown): RetrievalTrace[] {
  if (!Array.isArray(input)) {
    return [];
  }

  const normalized: RetrievalTrace[] = [];
  for (const item of input) {
    if (!item || typeof item !== 'object') {
      continue;
    }
    const record = item as Record<string, unknown>;
    const query = String(record.query ?? '').trim();
    const intentDescription = String(record.intent_description ?? '').trim();
    const rawChunks = Array.isArray(record.chunks) ? record.chunks : [];

    const chunks: RetrievalChunkRef[] = [];
    for (const chunkItem of rawChunks) {
      if (!chunkItem || typeof chunkItem !== 'object') {
        continue;
      }
      const chunkRecord = chunkItem as Record<string, unknown>;
      const fileTag = String(chunkRecord.file_tag ?? '').trim();
      const preview = String(chunkRecord.preview ?? '').trim();
      if (!fileTag && !preview) {
        continue;
      }
      const label = String(chunkRecord.label ?? '').trim()
        || (fileTag ? fileTag.split('/').pop() || fileTag : '未知来源');
      const rawScore = Number(chunkRecord.score ?? 0);
      const score = Number.isFinite(rawScore) ? rawScore : 0;
      chunks.push({
        file_tag: fileTag,
        label,
        score,
        preview,
      });
    }

    if (!query && !intentDescription && chunks.length === 0) {
      continue;
    }

    normalized.push({
      query,
      intent_description: intentDescription,
      chunks,
    });
  }
  return normalized;
}

export function normalizeChatAssets(input: unknown): ChatAsset[] {
  if (!Array.isArray(input)) {
    return [];
  }

  const normalized: ChatAsset[] = [];
  const seen = new Set<string>();

  for (const item of input) {
    let assetTag = '';
    let label = '';
    let kind = 'table_image';
    let sourceFileTag = '';
    let contentUrl = '';

    if (typeof item === 'string') {
      assetTag = item.trim();
      label = assetTag.split('/').pop() || assetTag;
    } else if (item && typeof item === 'object') {
      const record = item as Record<string, unknown>;
      assetTag = String(record.asset_tag ?? '').trim();
      label = String(record.label ?? '').trim();
      kind = String(record.kind ?? 'table_image').trim() || 'table_image';
      sourceFileTag = String(record.source_file_tag ?? '').trim();
      contentUrl = String(record.content_url ?? '').trim();
      if (!label && assetTag) {
        label = assetTag.split('/').pop() || assetTag;
      }
    }

    if (!assetTag || seen.has(assetTag)) {
      continue;
    }

    normalized.push({
      asset_tag: assetTag,
      label: label || assetTag,
      kind,
      source_file_tag: sourceFileTag || undefined,
      content_url: contentUrl || undefined,
    });
    seen.add(assetTag);
  }

  return normalized;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  blocks?: ChatContentBlock[];
  reasoning?: string;
  reasoningBlocks?: ChatContentBlock[];
  sources?: ChatSource[];
  assets?: ChatAsset[];
  retrievalTraces?: RetrievalTrace[];
  timestamp: Date;
}

export interface ChatSessionSummary {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_activity: string;
}

export interface ChatSessionListResponse {
  sessions: ChatSessionSummary[];
}

export interface ChatSessionDetailResponse {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    blocks?: ChatContentBlock[] | null;
    reasoning?: string | null;
    reasoning_blocks?: ChatContentBlock[] | null;
    sources?: ChatSource[] | null;
    assets?: ChatAsset[] | null;
    retrieval_traces?: RetrievalTrace[] | null;
    timestamp: string;
  }>;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface SSEEvent {
  type: 'session' | 'reasoning' | 'content' | 'done' | 'error';
  content?: string;
  blocks?: ChatContentBlock[];
  full?: string;
  reasoning?: string;
  reasoning_blocks?: ChatContentBlock[];
  session_id?: string;
  message?: string;
  sources?: ChatSource[];
  assets?: ChatAsset[];
  retrieval_traces?: RetrievalTrace[];
}

export interface ChatState {
  messages: ChatMessage[];
  sessionId: string | null;
  isLoading: boolean;
  streamingContent: string;
  streamingReasoning: string;
}
