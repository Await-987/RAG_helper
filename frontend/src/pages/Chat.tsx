import { useEffect, useRef, useState } from 'react';
import { useChatStore, createMessage } from '@/stores';
import { chatApi } from '@/api';
import { Send, Loader2, Trash2 } from 'lucide-react';
import { MessageItem } from '@/components/Chat';
import { StreamingMessage } from '@/components/Chat';

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
  } = useChatStore();

  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent, streamingReasoning]);

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

    try {
      const token = localStorage.getItem('access_token') || undefined;

      // Create assistant message placeholder
      let assistantContent = '';
      let assistantReasoning = '';
      let completed = false;

      // Stream chat response
      for await (const event of chatApi.streamChat(message, sessionId || undefined, token)) {
        switch (event.type) {
          case 'session':
            if (event.session_id) {
              setSessionId(event.session_id);
            }
            break;

          case 'reasoning':
            if (event.full) {
              assistantReasoning = event.full;
            } else if (event.content) {
              assistantReasoning += event.content;
            }
            updateStreamingReasoning(assistantReasoning);
            break;

          case 'content':
            if (event.full) {
              assistantContent = event.full;
            } else if (event.content) {
              assistantContent += event.content;
            }
            updateStreamingContent(assistantContent);
            break;

          case 'done':
            // Final message
            const assistantMessage = createMessage(
              'assistant',
              event.content || assistantContent,
              event.reasoning || assistantReasoning
            );
            addMessage(assistantMessage);
            clearStreaming();
            setLoading(false);
            completed = true;
            break;

          case 'error':
            const errorMessage = createMessage(
              'assistant',
              `错误: ${event.message || '未知错误'}`
            );
            addMessage(errorMessage);
            clearStreaming();
            setLoading(false);
            completed = true;
            break;
        }
      }

      if (!completed) {
        const finalContent = assistantContent.trim() || '未收到完整响应，请重试。';
        addMessage(createMessage('assistant', finalContent, assistantReasoning || undefined));
        clearStreaming();
        setLoading(false);
      }
    } catch (error: any) {
      const errorMessage = createMessage(
        'assistant',
        `发送消息失败: ${error.message || '未知错误'}`
      );
      addMessage(errorMessage);
      clearStreaming();
      setLoading(false);
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
    if (sessionId) {
      try {
        await chatApi.clearSession(sessionId);
      } catch (error) {
        console.error('Failed to clear session:', error);
      }
    }
    clearMessages();
    clearStreaming();
    setLoading(false);
    setInput('');
    inputRef.current?.focus();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-dark-border bg-dark-card">
        <h1 className="text-xl font-bold text-white">智能设计助手</h1>
        <button
          onClick={handleNewChat}
          className="btn btn-secondary flex items-center gap-2"
          title="开始新对话"
        >
          <Trash2 size={18} />
          <span className="hidden sm:inline">清空对话</span>
        </button>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
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

        {/* Streaming message */}
        {(streamingContent || streamingReasoning || isLoading) && (
          <StreamingMessage
            content={streamingContent}
            reasoning={streamingReasoning}
            isLoading={isLoading && !streamingContent && !streamingReasoning}
          />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
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
  );
}
