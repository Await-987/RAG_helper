import { create } from 'zustand';
import type { ChatContentBlock, ChatMessage, ChatState } from '@/types';

interface ChatStore extends ChatState {
  addMessage: (message: ChatMessage) => void;
  setMessages: (messages: ChatMessage[]) => void;
  updateStreamingContent: (content: string) => void;
  updateStreamingReasoning: (reasoning: string) => void;
  clearStreaming: () => void;
  setSessionId: (sessionId: string | null) => void;
  setLoading: (loading: boolean) => void;
  clearMessages: () => void;
}

const generateId = () => Math.random().toString(36).substring(2, 9);

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  sessionId: null,
  isLoading: false,
  streamingContent: '',
  streamingReasoning: '',

  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
      streamingContent: '',
      streamingReasoning: '',
    })),

  setMessages: (messages) =>
    set({
      messages,
      streamingContent: '',
      streamingReasoning: '',
    }),

  updateStreamingContent: (content) =>
    set({ streamingContent: content }),

  updateStreamingReasoning: (reasoning) =>
    set({ streamingReasoning: reasoning }),

  clearStreaming: () =>
    set({ streamingContent: '', streamingReasoning: '' }),

  setSessionId: (sessionId) =>
    set({ sessionId }),

  setLoading: (loading) =>
    set({ isLoading: loading }),

  clearMessages: () =>
    set({
      messages: [],
      sessionId: null,
      streamingContent: '',
      streamingReasoning: '',
    }),
}));

// Helper to create a new message
export const createMessage = (
  role: 'user' | 'assistant',
  content: string,
  reasoning?: string,
  blocks?: ChatContentBlock[],
  reasoningBlocks?: ChatContentBlock[],
): ChatMessage => ({
  id: generateId(),
  role,
  content,
  blocks,
  reasoning,
  reasoningBlocks,
  timestamp: new Date(),
});
