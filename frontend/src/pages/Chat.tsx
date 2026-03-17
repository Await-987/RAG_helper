import { startTransition, useEffect, useRef, useState } from 'react';
import { useChatStore, createMessage } from '@/stores';
import { chatApi } from '@/api';
import { Send, Loader2, Trash2, MessageSquare } from 'lucide-react';
import { MessageItem } from '@/components/Chat';
import { StreamingMessage } from '@/components/Chat';
import type { ChatMessage, ChatSessionSummary } from '@/types';
import { getAccessToken } from '@/utils/authToken';

function normalizeMessage(message: ChatMessage | {
  role: 'user' | 'assistant';
  content: string;
  blocks?: ChatMessage['blocks'] | null;
  reasoning?: string | null;
  reasoning_blocks?: ChatMessage['reasoningBlocks'] | null;
  timestamp: string;
}): ChatMessage {
  if ('id' in message) {
    return message;
  }

  return {
    id: `${message.role}-${message.timestamp}-${message.content.slice(0, 12)}`,
    role: message.role,
    content: message.content,
    blocks: message.blocks || undefined,
    reasoning: message.reasoning || undefined,
    reasoningBlocks: message.reasoning_blocks || undefined,
    timestamp: new Date(message.timestamp),
  };
}

export function ChatPage() {
  const {
    messages,
    sessionId,
    isLoading,
    streamingContent,
    streamingReasoning,
    addMessage,
    updateStreamingContent,
    updateStreamingReasoning,
    clearStreaming,
    setSessionId,
    setLoading,
    clearMessages,
    setMessages,
  } = useChatStore();

  const [input, setInput] = useState('');
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [isSessionsLoading, setIsSessionsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const streamingContentRef = useRef('');
  const streamingReasoningRef = useRef('');
  const streamingFlushHandleRef = useRef<number | null>(null);
  const streamingDoneRef = useRef(false);
  const wasStreamingRef = useRef(false);

  const scheduleStreamingFlush = () => {
    if (streamingFlushHandleRef.current !== null) {
      return;
    }

    streamingFlushHandleRef.current = window.setTimeout(() => {
      streamingFlushHandleRef.current = null;
      const nextContent = streamingContentRef.current;
      const nextReasoning = streamingReasoningRef.current;

      startTransition(() => {
        updateStreamingContent(nextContent);
        updateStreamingReasoning(nextReasoning);
      });
    }, 33);
  };

  const flushStreamingState = () => {
    if (streamingFlushHandleRef.current !== null) {
      window.clearTimeout(streamingFlushHandleRef.current);
      streamingFlushHandleRef.current = null;
    }

    updateStreamingContent(streamingContentRef.current);
    updateStreamingReasoning(streamingReasoningRef.current);
  };

  const resetStreamingBuffers = () => {
    streamingContentRef.current = '';
    streamingReasoningRef.current = '';
    if (streamingFlushHandleRef.current !== null) {
      window.clearTimeout(streamingFlushHandleRef.current);
      streamingFlushHandleRef.current = null;
    }
  };

  const loadSessions = async (preferredSessionId?: string | null) => {
    setIsSessionsLoading(true);
    try {
      const data = await chatApi.listSessions();
      setSessions(data.sessions);

      const targetSessionId = preferredSessionId ?? sessionId;
      if (!targetSessionId) {
        return;
      }

      const hasTarget = data.sessions.some((item) => item.session_id === targetSessionId);
      if (!hasTarget) {
        if (targetSessionId === sessionId) {
          clearMessages();
        }
      }
    } catch (error) {
      console.error('Failed to load sessions:', error);
    } finally {
      setIsSessionsLoading(false);
    }
  };

  const openSession = async (targetSessionId: string) => {
    if (isLoading || targetSessionId === sessionId) {
      return;
    }

    try {
      setLoading(true);
      clearStreaming();
      const detail = await chatApi.getSessionDetail(targetSessionId);
      setSessionId(detail.session_id);
      setMessages(detail.messages.map(normalizeMessage));
    } catch (error) {
      console.error('Failed to load session detail:', error);
    } finally {
      setLoading(false);
    }
  };

  // Auto scroll to bottom
  useEffect(() => {
    const isStreaming = Boolean(streamingContent || streamingReasoning || isLoading);
    const behavior: ScrollBehavior = isStreaming || wasStreamingRef.current ? 'auto' : 'smooth';
    messagesEndRef.current?.scrollIntoView({ behavior, block: 'end' });
    wasStreamingRef.current = isStreaming;
  }, [messages, streamingContent, streamingReasoning, isLoading]);

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => () => {
    if (streamingFlushHandleRef.current !== null) {
      window.clearTimeout(streamingFlushHandleRef.current);
    }
  }, []);

  // Listen for new chat event
  useEffect(() => {
    const handleNewChat = () => {
      clearMessages();
      setInput('');
    };

    window.addEventListener('new-chat', handleNewChat);
    return () => window.removeEventListener('new-chat', handleNewChat);
  }, [clearMessages]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();

    const message = input.trim();
    if (!message || isLoading) return;

    // Add user message
    const userMessage = createMessage('user', message);
    addMessage(userMessage);
    setInput('');
    setLoading(true);
    clearStreaming();
    streamingDoneRef.current = false;
    resetStreamingBuffers();

    try {
      const token = getAccessToken() || undefined;

      // Create assistant message placeholder
      // Stream chat response
      for await (const event of chatApi.streamChat(message, sessionId || undefined, token)) {
        switch (event.type) {
          case 'session':
            if (event.session_id) {
              setSessionId(event.session_id);
            }
            break;

          case 'reasoning':
            if (event.content) {
              streamingReasoningRef.current += event.content;
              scheduleStreamingFlush();
            }
            break;

          case 'content':
            if (event.content) {
              streamingContentRef.current += event.content;
              scheduleStreamingFlush();
            }
            break;

          case 'done':
            // Final message
            if (event.reasoning) {
              streamingReasoningRef.current = event.reasoning;
            }
            if (event.content) {
              streamingContentRef.current = event.content;
            }
            flushStreamingState();
            const assistantMessage = createMessage(
              'assistant',
              streamingContentRef.current,
              streamingReasoningRef.current || undefined,
              event.blocks,
              event.reasoning_blocks,
            );
            addMessage(assistantMessage);
            if (event.session_id) {
              setSessionId(event.session_id);
            }
            clearStreaming();
            setLoading(false);
            loadSessions(event.session_id || sessionId);
            streamingDoneRef.current = true;
            resetStreamingBuffers();
            break;

          case 'error':
            const errorMessage = createMessage(
              'assistant',
              `错误: ${event.message || '未知错误'}`
            );
            addMessage(errorMessage);
            clearStreaming();
            setLoading(false);
            loadSessions(sessionId);
            streamingDoneRef.current = true;
            resetStreamingBuffers();
            break;
        }
      }

      if (!streamingDoneRef.current) {
        flushStreamingState();
        const finalContent = streamingContentRef.current.trim() || '未收到完整响应，请重试。';
        addMessage(createMessage('assistant', finalContent, streamingReasoningRef.current || undefined));
        clearStreaming();
        setLoading(false);
        loadSessions(sessionId);
        resetStreamingBuffers();
      }
    } catch (error: any) {
      const errorMessage = createMessage(
        'assistant',
        `发送消息失败: ${error.message || '未知错误'}`
      );
      addMessage(errorMessage);
      clearStreaming();
      setLoading(false);
      resetStreamingBuffers();
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleNewChat = async () => {
    clearMessages();
    clearStreaming();
    setLoading(false);
    setInput('');
    inputRef.current?.focus();
  };

  const handleDeleteSession = async (targetSessionId: string) => {
    try {
      await chatApi.clearSession(targetSessionId);
      if (targetSessionId === sessionId) {
        clearMessages();
      }
      await loadSessions(targetSessionId === sessionId ? null : sessionId);
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  return (
    <div className="flex h-full min-h-0">
      <div className="hidden lg:flex w-80 border-r border-dark-border bg-dark-card flex-col">
        <div className="flex-1 overflow-y-auto custom-scrollbar p-3 space-y-2">
          {isSessionsLoading && (
            <div className="text-sm text-gray-500 px-2 py-3">正在加载历史对话...</div>
          )}

          {!isSessionsLoading && sessions.length === 0 && (
            <div className="text-sm text-gray-500 px-2 py-3">暂无历史对话</div>
          )}

          {sessions.map((item) => (
            <div
              key={item.session_id}
              className={`group rounded-xl border transition-colors ${
                item.session_id === sessionId
                  ? 'border-primary-600 bg-primary-900/20'
                  : 'border-dark-border bg-dark-bg hover:bg-dark-hover'
              }`}
            >
              <button
                onClick={() => openSession(item.session_id)}
                className="w-full text-left px-3 py-3"
              >
                <div className="flex items-start gap-3">
                  <MessageSquare size={18} className="mt-0.5 text-gray-400" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-gray-100">
                      {item.title}
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {new Date(item.updated_at).toLocaleString()}
                    </div>
                    <div className="mt-1 text-xs text-gray-500">
                      {item.message_count} 条消息
                    </div>
                  </div>
                </div>
              </button>
              <div className="px-3 pb-3">
                <button
                  onClick={() => handleDeleteSession(item.session_id)}
                  className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1"
                >
                  <Trash2 size={14} />
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 flex h-full min-h-0 flex-col">
        <div className="flex items-center justify-between p-4 border-b border-dark-border bg-dark-card">
          <div>
            <h1 className="text-xl font-bold text-white">智能设计助手</h1>
            <p className="text-xs text-gray-500 mt-1">
              {sessionId ? `当前会话：${sessionId}` : '未选择历史会话'}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {sessionId && (
              <button
                onClick={() => handleDeleteSession(sessionId)}
                className="btn btn-secondary flex items-center gap-2"
                title="删除当前会话"
              >
                <Trash2 size={18} />
                <span className="hidden sm:inline">删除会话</span>
              </button>
            )}
          </div>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4 custom-scrollbar">
          {messages.length === 0 && !isLoading && (
            <div className="flex flex-col items-center justify-center h-full text-gray-400">
              <div className="w-20 h-20 rounded-full bg-dark-hover flex items-center justify-center text-4xl mb-4">
                💬
              </div>
              <p className="text-lg font-medium">开始新对话</p>
              <p className="text-sm mt-2">输入您的问题，我将基于知识库为您解答</p>
            </div>
          )}

          {messages.map((msg) => (
            <MessageItem key={msg.id} message={msg} />
          ))}

          {(streamingContent || streamingReasoning || isLoading) && (
            <StreamingMessage
              content={streamingContent}
              reasoning={streamingReasoning}
              isLoading={isLoading}
            />
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="p-4 border-t border-dark-border bg-dark-card">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="输入您的问题... (Enter 发送, Shift+Enter 换行)"
                className="input-field resize-none pr-12 min-h-[52px] max-h-[200px]"
                rows={1}
                disabled={isLoading}
                style={{
                  height: 'auto',
                  minHeight: '52px',
                }}
              />
            </div>
            <button
              type="submit"
              disabled={!input.trim() || isLoading}
              className="btn btn-primary h-[52px] px-6 flex items-center justify-center"
            >
              {isLoading ? (
                <Loader2 size={20} className="animate-spin" />
              ) : (
                <Send size={20} />
              )}
            </button>
          </form>
          <p className="text-xs text-gray-500 mt-2 text-center">
            基于知识库检索的回答，所有信息可溯源
          </p>
        </div>
      </div>
    </div>
  );
}
