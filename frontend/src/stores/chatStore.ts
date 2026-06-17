import { create } from 'zustand';
import { normalizeChatAssets, normalizeChatSources, normalizeRetrievalTraces } from '@/types';
import type {
  ChatAsset,
  ChatContentBlock,
  ChatMessage,
  ChatSessionSummary,
  ChatSource,
  RetrievalTrace,
} from '@/types';
import { chatApi } from '@/api/chat';
import { getAccessToken } from '@/utils/authToken';

// Each session has its own independent state
interface SessionState {
  messages: ChatMessage[];
  isLoading: boolean;
  streamingContent: string;
  streamingReasoning: string;
  streamingSources: ChatSource[];
  streamingAssets: ChatAsset[];
  abortController: AbortController | null;
}

interface ChatStore {
  // All session states keyed by session_id (empty string key for new chat)
  sessionStates: Record<string, SessionState>;
  // Currently displayed session (empty string means new chat)
  currentSessionId: string;

  // Sessions list
  sessions: ChatSessionSummary[];
  sessionsLoading: boolean;

  // Actions
  sendMessage: (message: string) => Promise<void>;
  stopStreaming: (sessionId?: string) => void;
  loadSession: (sessionId: string) => Promise<void>;
  loadSessions: () => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  setCurrentSessionId: (id: string | null) => void;
  createNewChat: () => void;
}

const generateId = () => Math.random().toString(36).substring(2, 9);

const NULL_SESSION_KEY = ''; // Empty string represents new/null session

function createMessage(
  role: 'user' | 'assistant',
  content: string,
  reasoning?: string,
  blocks?: ChatContentBlock[],
  reasoningBlocks?: ChatContentBlock[],
  sources?: ChatSource[],
  assets?: ChatAsset[],
  retrievalTraces?: RetrievalTrace[],
): ChatMessage {
  return {
    id: generateId(),
    role,
    content,
    blocks,
    reasoning,
    reasoningBlocks,
    sources,
    assets,
    retrievalTraces,
    timestamp: new Date(),
  };
}

function toSessionKey(sessionId: string | null): string {
  return sessionId ?? NULL_SESSION_KEY;
}

function mergeStreamText(current: string, incoming: string): string {
  if (!incoming) return current;
  if (!current) return incoming;
  if (incoming.startsWith(current)) return incoming;
  if (current.startsWith(incoming)) return current;
  if (current.endsWith(incoming)) return current;
  if (looksLikeCumulativeRestart(current, incoming)) return incoming;
  return current + incoming;
}

function normalizeStreamPrefix(text: string, maxChars = 120): string {
  return text
    .replace(/<!-- SOURCE_REFS_START -->[\s\S]*?<!-- SOURCE_REFS_END -->/g, '')
    .replace(/\s+/g, '')
    .slice(0, maxChars);
}

function looksLikeCumulativeRestart(current: string, incoming: string): boolean {
  const currentPrefix = normalizeStreamPrefix(current);
  const incomingPrefix = normalizeStreamPrefix(incoming);
  if (currentPrefix.length < 24 || incomingPrefix.length < 24) return false;

  const prefixLength = Math.min(currentPrefix.length, incomingPrefix.length, 80);
  const currentSample = currentPrefix.slice(0, prefixLength);
  const incomingSample = incomingPrefix.slice(0, prefixLength);

  let commonPrefixLength = 0;
  for (let i = 0; i < prefixLength; i += 1) {
    if (currentSample[i] !== incomingSample[i]) break;
    commonPrefixLength += 1;
  }
  if (commonPrefixLength >= 16) return true;

  let samePositionMatches = 0;
  for (let i = 0; i < prefixLength; i += 1) {
    if (currentSample[i] === incomingSample[i]) samePositionMatches += 1;
  }
  return samePositionMatches / prefixLength >= 0.88;
}

function getEmptySessionState(): SessionState {
  return {
    messages: [],
    isLoading: false,
    streamingContent: '',
    streamingReasoning: '',
    streamingSources: [],
    streamingAssets: [],
    abortController: null,
  };
}

function ensureSessionState(states: Record<string, SessionState>, key: string): Record<string, SessionState> {
  if (states[key]) return states;
  return { ...states, [key]: getEmptySessionState() };
}

export const useChatStore = create<ChatStore>((set, get) => ({
  sessionStates: { [NULL_SESSION_KEY]: getEmptySessionState() },
  currentSessionId: NULL_SESSION_KEY,
  sessions: [],
  sessionsLoading: false,

  sendMessage: async (message: string) => {
    const token = getAccessToken() || undefined;
    const currentKey = get().currentSessionId;

    // Ensure session state exists
    set((s) => ({
      sessionStates: ensureSessionState(s.sessionStates, currentKey),
    }));

    // Add user message to THIS session only
    const userMsg = createMessage('user', message);
    set((s) => ({
      sessionStates: {
        ...s.sessionStates,
        [currentKey]: {
          ...s.sessionStates[currentKey],
          messages: [...s.sessionStates[currentKey].messages, userMsg],
          isLoading: true,
          streamingContent: '',
          streamingReasoning: '',
          streamingSources: [],
          streamingAssets: [],
        },
      },
    }));

    const controller = new AbortController();
    set((s) => ({
      sessionStates: {
        ...s.sessionStates,
        [currentKey]: {
          ...s.sessionStates[currentKey],
          abortController: controller,
        },
      },
    }));

    // The actual sessionId for API (empty string means null/new)
    const apiSessionId = currentKey === NULL_SESSION_KEY ? undefined : currentKey;
    let streamingKey = currentKey;

    try {
      let fullContent = '';
      let fullReasoning: string | undefined;
      let finalSources: ChatSource[] = [];
      let finalAssets: ChatAsset[] = [];
      let finalBlocks: ChatContentBlock[] | undefined;
      let finalReasoningBlocks: ChatContentBlock[] | undefined;
      let finalRetrievalTraces: RetrievalTrace[] = [];

      // Helper to update the session we're streaming for
      const updateStreamingSession = (updates: Partial<SessionState>) => {
        set((s) => ({
          sessionStates: {
            ...s.sessionStates,
            [streamingKey]: {
              ...s.sessionStates[streamingKey],
              ...updates,
            },
          },
        }));
      };

      for await (const event of chatApi.streamChat(message, apiSessionId, token)) {
        if (controller.signal.aborted) break;

        switch (event.type) {
          case 'session':
            // Server returned a new session ID (for new chats)
            if (event.session_id && streamingKey === NULL_SESSION_KEY) {
              const newKey = event.session_id;
              // Move state from empty key to new session key
              set((s) => {
                const oldState = s.sessionStates[NULL_SESSION_KEY];
                const states = { ...s.sessionStates };
                states[newKey] = oldState;
                states[NULL_SESSION_KEY] = getEmptySessionState();
                return {
                  currentSessionId: newKey,
                  sessionStates: states,
                };
              });
              streamingKey = newKey;
            }
            break;

          case 'reasoning':
            if (event.content) {
              fullReasoning = mergeStreamText(fullReasoning ?? '', event.content);
              updateStreamingSession({ streamingReasoning: fullReasoning });
            }
            break;

          case 'content':
            if (event.content) {
              fullContent = mergeStreamText(fullContent, event.content);
              updateStreamingSession({ streamingContent: fullContent });
            }
            break;

          case 'done':
            {
              if (event.content) {
                fullContent = event.content;
              }
              // 从 done 事件中提取 sources block
              let sourcesBlock = '';
              if (event.content) {
                const match = event.content.match(/<!-- SOURCE_REFS_START -->[\s\S]*<!-- SOURCE_REFS_END -->/);
                if (match) {
                  sourcesBlock = match[0];
                }
              }
              // 确保 sources block 被追加到流式内容末尾
              // 检查完整标记（不只是开头），避免流式中偶然出现的部分文本
              const hasCompleteSourcesBlock =
                fullContent.includes('<!-- SOURCE_REFS_START -->') &&
                fullContent.includes('<!-- SOURCE_REFS_END -->');
              if (sourcesBlock && !hasCompleteSourcesBlock) {
                // 先移除可能存在的不完整片段
                const cleaned = fullContent
                  .replace(/<!-- SOURCE_REFS_START -->[\s\S]*$/, '')
                  .trim();
                fullContent = cleaned + '\n\n' + sourcesBlock;
              }
              fullReasoning = event.reasoning ?? fullReasoning;
              finalBlocks = event.blocks;
              finalReasoningBlocks = event.reasoning_blocks;
              finalSources = normalizeChatSources(event.sources);
              finalAssets = normalizeChatAssets(event.assets);
              finalRetrievalTraces = normalizeRetrievalTraces(event.retrieval_traces);
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
        fullReasoning,
        finalBlocks,
        finalReasoningBlocks,
        finalSources,
        finalAssets,
        finalRetrievalTraces,
      );

      console.log('[DEBUG] Adding assistant message:', {
        streamingKey,
        currentSessionId: get().currentSessionId,
        msgId: assistantMsg.id,
        msgContent: assistantMsg.content.substring(0, 50),
        msgContentLength: assistantMsg.content.length,
        existingMessages: get().sessionStates[streamingKey]?.messages?.length,
      });

      set((s) => {
        const existingMsgs = s.sessionStates[streamingKey]?.messages ?? [];
        console.log('[DEBUG] set state - existing messages:', existingMsgs.length);
        return {
          sessionStates: {
            ...s.sessionStates,
            [streamingKey]: {
              ...s.sessionStates[streamingKey],
              messages: [...existingMsgs, assistantMsg],
              isLoading: false,
              streamingContent: '',
              streamingReasoning: '',
              streamingSources: finalSources,
              streamingAssets: finalAssets,
              abortController: null,
            },
          },
        };
      });

      console.log('[DEBUG] After set, messages count:', get().sessionStates[streamingKey]?.messages?.length);

      // Refresh sessions list
      get().loadSessions();
    } catch (error) {
      console.error('Chat error:', error);
      set((s) => ({
        sessionStates: {
          ...s.sessionStates,
          [streamingKey]: {
            ...s.sessionStates[streamingKey],
            isLoading: false,
            abortController: null,
          },
        },
      }));
    }
  },

  stopStreaming: (sessionId?: string) => {
    const targetKey = sessionId ?? get().currentSessionId;
    const sessionState = get().sessionStates[targetKey];

    if (sessionState?.abortController) {
      sessionState.abortController.abort();
      set((s) => ({
        sessionStates: {
          ...s.sessionStates,
          [targetKey]: {
            ...s.sessionStates[targetKey],
            isLoading: false,
            abortController: null,
            streamingContent: '',
            streamingReasoning: '',
            streamingSources: [],
            streamingAssets: [],
          },
        },
      }));
    }
  },

  loadSession: async (sessionId: string) => {
    try {
      const detail = await chatApi.getSessionDetail(sessionId);
        const loadedMessages: ChatMessage[] = detail.messages.map((msg, i) => ({
          id: `${sessionId}-${i}`,
          role: msg.role,
          content: msg.content,
          blocks: msg.blocks ?? undefined,
          reasoning: msg.reasoning ?? undefined,
          reasoningBlocks: msg.reasoning_blocks ?? undefined,
          sources: normalizeChatSources(msg.sources),
          assets: normalizeChatAssets(msg.assets),
          retrievalTraces: normalizeRetrievalTraces(msg.retrieval_traces),
          timestamp: new Date(msg.timestamp),
        }));

      set((s) => ({
        currentSessionId: sessionId,
        sessionStates: {
          ...s.sessionStates,
          [sessionId]: {
            messages: loadedMessages,
            isLoading: false,
            streamingContent: '',
            streamingReasoning: '',
            streamingSources: [],
            streamingAssets: [],
            abortController: null,
          },
        },
      }));
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
      set((s) => {
        const newStates = { ...s.sessionStates };
        delete newStates[sessionId];
        return {
          sessions: s.sessions.filter((sess) => sess.session_id !== sessionId),
          sessionStates: newStates,
          currentSessionId: s.currentSessionId === sessionId ? NULL_SESSION_KEY : s.currentSessionId,
        };
      });
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  },

  setCurrentSessionId: (id) => {
    const key = toSessionKey(id);
    set((s) => ({
      currentSessionId: key,
      sessionStates: ensureSessionState(s.sessionStates, key),
    }));
  },

  createNewChat: () => {
    set((s) => ({
      currentSessionId: NULL_SESSION_KEY,
      sessionStates: ensureSessionState(s.sessionStates, NULL_SESSION_KEY),
    }));
  },
}));

// Convenience hooks
export function useCurrentMessages() {
  return useChatStore((s) => s.sessionStates[s.currentSessionId]?.messages ?? []);
}

export function useCurrentIsLoading() {
  return useChatStore((s) => s.sessionStates[s.currentSessionId]?.isLoading ?? false);
}

export function useCurrentStreamingContent() {
  return useChatStore((s) => s.sessionStates[s.currentSessionId]?.streamingContent ?? '');
}

export function useCurrentStreamingReasoning() {
  return useChatStore((s) => s.sessionStates[s.currentSessionId]?.streamingReasoning ?? '');
}

export function useCurrentStreamingSources() {
  return useChatStore((s) => s.sessionStates[s.currentSessionId]?.streamingSources ?? []);
}

export function useCurrentSessionId() {
  return useChatStore((s) => s.currentSessionId === NULL_SESSION_KEY ? null : s.currentSessionId);
}
