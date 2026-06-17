import type {
  ChatRequest,
  ChatSessionDetailResponse,
  ChatSessionListResponse,
  SSEEvent,
} from '@/types';
import { getAccessToken } from '@/utils/authToken';

const API_BASE_URL = '/api/v1';

function parseSSEEvent(rawEvent: string): SSEEvent | null {
  const lines = rawEvent
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line.length > 0 && !line.startsWith(':'));

  if (lines.length === 0) {
    return null;
  }

  let sseEventName: string | null = null;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith('event:')) {
      sseEventName = line.slice(6).trim();
      continue;
    }

    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!sseEventName || dataLines.length === 0) {
    return null;
  }

  try {
    const data = JSON.parse(dataLines.join('\n'));

    // New format: all business events use "event: message" with internal "type" field
    if (sseEventName === 'message') {
      const eventType = data.type as SSEEvent['type'];
      if (!eventType) return null;
      return { type: eventType, ...data } as SSEEvent;
    }

    // Error events use "event: error"
    if (sseEventName === 'error') {
      return { type: 'error', message: data.message || data.error || 'Unknown error' } as SSEEvent;
    }

    // Fallback for legacy format (shouldn't happen with new backend)
    return { type: sseEventName as SSEEvent['type'], ...data } as SSEEvent;
  } catch (error) {
    console.error('Failed to parse SSE event payload:', error, rawEvent);
    return null;
  }
}

export const chatApi = {
  /**
   * Stream chat response via SSE
   */
  streamChat: async function* (
    message: string,
    sessionId?: string,
    token?: string
  ): AsyncGenerator<SSEEvent> {
    const body: ChatRequest = { message, session_id: sessionId };

    const response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: {
        Accept: 'text/event-stream',
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      let detail = `HTTP error! status: ${response.status}`;

      try {
        const errorData = await response.json();
        if (errorData?.detail) {
          detail = typeof errorData.detail === 'string'
            ? errorData.detail
            : JSON.stringify(errorData.detail);
        }
      } catch {
        // Ignore JSON parse errors and fall back to the status code message.
      }

      throw new Error(detail);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No reader available');
    }

    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop() || '';

      for (const rawEvent of events) {
        const parsedEvent = parseSSEEvent(rawEvent);
        if (parsedEvent) {
          yield parsedEvent;
        }
      }
    }

    const trailingEvent = parseSSEEvent(buffer);
    if (trailingEvent) {
      yield trailingEvent;
    }
  },

  clearSession: async (sessionId: string): Promise<void> => {
    const token = getAccessToken();
    const response = await fetch(`${API_BASE_URL}/chat/session/${sessionId}`, {
      method: 'DELETE',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

    if (!response.ok) {
      if (response.status === 404) {
        return;
      }
      throw new Error(`HTTP error! status: ${response.status}`);
    }
  },

  listSessions: async (): Promise<ChatSessionListResponse> => {
    const token = getAccessToken();
    const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  },

  getSessionDetail: async (sessionId: string): Promise<ChatSessionDetailResponse> => {
    const token = getAccessToken();
    const response = await fetch(`${API_BASE_URL}/chat/session/${sessionId}`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    return response.json();
  },
};
