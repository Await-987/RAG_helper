export interface ChatContentBlock {
  type: 'markdown' | 'math' | 'table' | 'code';
  content: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  blocks?: ChatContentBlock[];
  reasoning?: string;
  reasoningBlocks?: ChatContentBlock[];
  sources?: string[];
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
  sources?: string[];
}

export interface ChatState {
  messages: ChatMessage[];
  sessionId: string | null;
  isLoading: boolean;
  streamingContent: string;
  streamingReasoning: string;
}
