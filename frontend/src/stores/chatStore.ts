import { create } from 'zustand';
import type { ChatContentBlock, ChatMessage, ChatSessionSummary, SSEEvent } from '@/types';
import { chatApi } from '@/api/chat';
import { getAccessToken } from '@/utils/authToken';

interface ChatStore {
  // Messages
  messages: ChatMessage[];
  currentSessionId: string | null;
  isLoading: boolean;
  streamingContent: string;
  streamingReasoning: string;
  streamingSources: string[];
  abortController: AbortController | null;

  // Sessions
  sessions: ChatSessionSummary[];
  sessionsLoading: boolean;

  // Actions
  sendMessage: (message: string) => Promise<void>;
  stopStreaming: () => void;
  loadSession: (sessionId: string) => Promise<void>;
  loadSessions: () => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  setCurrentSessionId: (id: string | null) => void;
  createNewChat: () => void;
}

const generateId = () => Math.random().toString(36).substring(2, 9);

function createMessage(
  role: 'user' | 'assistant',
  content: string,
  reasoning?: string,
  blocks?: ChatContentBlock[],
  reasoningBlocks?: ChatContentBlock[],
  sources?: string[],
): ChatMessage {
  return {
    id: generateId(),
    role,
    content,
    blocks,
    reasoning,
    reasoningBlocks,
    sources,
    timestamp: new Date(),
  };
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  currentSessionId: null,
  isLoading: false,
  streamingContent: '',
  streamingReasoning: '',
  streamingSources: [],
  abortController: null,
  sessions: [],
  sessionsLoading: false,

  sendMessage: async (message: string) => {
    const token = getAccessToken() || undefined;
    const state = get();

    // Add user message
    const userMsg = createMessage('user', message);
    set((s) => ({
      messages: [...s.messages, userMsg],
      isLoading: true,
      streamingContent: '',
      streamingReasoning: '',
      streamingSources: [],
    }));

    const controller = new AbortController();
    set({ abortController: controller });

    try {
      let fullContent = '';
      let fullReasoning = '';
      let finalSources: string[] = [];
      let finalBlocks: ChatContentBlock[] | undefined;
      let finalReasoningBlocks: ChatContentBlock[] | undefined;

      // Throttle streaming updates to avoid React infinite re-render
      let lastUpdateTime = 0;
      const UPDATE_INTERVAL = 100; // ms
      let pendingContent = '';
      let pendingReasoning = '';

      const flushUpdates = (force = false) => {
        const now = Date.now();
        if (!force && now - lastUpdateTime < UPDATE_INTERVAL) return;
        lastUpdateTime = now;
        const updates: Partial<ChatStore> = {};
        if (pendingReasoning) { updates.streamingReasoning = pendingReasoning; pendingReasoning = ''; }
        if (pendingContent) { updates.streamingContent = pendingContent; pendingContent = ''; }
        if (Object.keys(updates).length > 0) set(updates);
      };

      for await (const event of chatApi.streamChat(
        message,
        state.currentSessionId || undefined,
        token
      )) {
        if (controller.signal.aborted) break;

        switch (event.type) {
          case 'session':
            set({ currentSessionId: event.session_id || null });
            break;

          case 'reasoning':
            if (event.content) {
              fullReasoning += event.content;
              pendingReasoning = fullReasoning;
              flushUpdates();
            }
            break;

          case 'content':
            if (event.content) {
              fullContent += event.content;
              pendingContent = fullContent;
              flushUpdates();
            }
            break;

          case 'done':
            // Force flush any pending streaming content before finalizing
            flushUpdates(true);
            fullContent = event.content || fullContent;
            fullReasoning = event.reasoning || fullReasoning;
            finalBlocks = event.blocks;
            finalReasoningBlocks = event.reasoning_blocks;
            finalSources = event.sources || [];
            if (event.session_id) {
              set({ currentSessionId: event.session_id });
            }
            break;

          case 'error':
            console.error('SSE error:', event.message);
            break;
        }
      }

      // Add assistant message
      const assistantMsg = createMessage(
        'assistant',
        fullContent,
        fullReasoning || undefined,
        finalBlocks,
        finalReasoningBlocks,
        finalSources,
      );

      set((s) => ({
        messages: [...s.messages, assistantMsg],
        isLoading: false,
        streamingContent: '',
        streamingReasoning: '',
        streamingSources: finalSources,
        abortController: null,
      }));

      // Refresh sessions list after sending (outside the streaming loop)
      get().loadSessions();
    } catch (error) {
      console.error('Chat error:', error);
      set({ isLoading: false, abortController: null });
      throw error;
    }
  },

  stopStreaming: () => {
    const { abortController } = get();
    if (abortController) {
      abortController.abort();
      set({ isLoading: false, abortController: null });
    }
  },

  loadSession: async (sessionId: string) => {
    try {
      const detail = await chatApi.getSessionDetail(sessionId);
      const loadedMessages: ChatMessage[] = detail.messages.map((msg, i) => ({
        id: `${sessionId}-${i}`,
        role: msg.role,
        content: msg.content,
        blocks: msg.blocks || undefined,
        reasoning: msg.reasoning || undefined,
        reasoningBlocks: msg.reasoning_blocks || undefined,
        timestamp: new Date(msg.timestamp),
      }));
      set({
        currentSessionId: sessionId,
        messages: loadedMessages,
        streamingContent: '',
        streamingReasoning: '',
        streamingSources: [],
      });
    } catch (error) {
      console.error('Failed to load session:', error);
    }
  },

  loadSessions: async () => {
    set({ sessionsLoading: true });
    try {
      const response = await chatApi.listSessions();
      set({ sessions: response.sessions, sessionsLoading: false });
    } catch (error) {
      console.error('Failed to load sessions:', error);
      set({ sessionsLoading: false });
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      await chatApi.clearSession(sessionId);
      set((s) => ({
        sessions: s.sessions.filter((sess) => sess.session_id !== sessionId),
        currentSessionId: s.currentSessionId === sessionId ? null : s.currentSessionId,
        messages: s.currentSessionId === sessionId ? [] : s.messages,
      }));
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  },

  setCurrentSessionId: (id) => {
    set({ currentSessionId: id });
    if (id === null) {
      set({ messages: [], streamingContent: '', streamingReasoning: '', streamingSources: [] });
    }
  },

  createNewChat: () => {
    set({
      currentSessionId: null,
      messages: [],
      streamingContent: '',
      streamingReasoning: '',
      streamingSources: [],
    });
  },
}));
