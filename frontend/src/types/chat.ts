export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  reasoning?: string;
  timestamp: Date;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface SSEEvent {
  type: 'session' | 'reasoning' | 'content' | 'done' | 'error';
  content?: string;
  full?: string;
  reasoning?: string;
  session_id?: string;
  message?: string;
}

export interface ChatState {
  messages: ChatMessage[];
  sessionId: string | null;
  isLoading: boolean;
  streamingContent: string;
  streamingReasoning: string;
}
