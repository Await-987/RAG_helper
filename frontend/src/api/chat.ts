import type { ChatRequest, SSEEvent } from '@/types';

const API_BASE_URL = '/api/v1';

function parseSSEEvent(rawEvent: string): SSEEvent | null {
  const lines = rawEvent
    .split(/\r?\n/)
    .map((line) => line.trimEnd())
    .filter((line) => line.length > 0 && !line.startsWith(':'));

  if (lines.length === 0) {
    return null;
  }

  let eventType: SSEEvent['type'] | null = null;
  const dataLines: string[] = [];

  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventType = line.slice(6).trim() as SSEEvent['type'];
      continue;
    }

    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trim());
    }
  }

  if (!eventType || dataLines.length === 0) {
    return null;
  }

  try {
    const data = JSON.parse(dataLines.join('\n'));
    return { type: eventType, ...data } as SSEEvent;
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
    const token = localStorage.getItem('access_token');
    const response = await fetch(`${API_BASE_URL}/chat/session/${sessionId}`, {
      method: 'DELETE',
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
  },
};
