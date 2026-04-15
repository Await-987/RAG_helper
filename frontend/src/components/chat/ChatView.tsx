import { useRef, useEffect, useCallback, useState } from 'react';
import { useChatStore } from '@/stores/chatStore';
import { ChatInput } from './ChatInput';
import { MessageItem } from './MessageItem';
import { WelcomeScreen } from './WelcomeScreen';
import { ReasoningBlock } from './ReasoningBlock';
import { MessageContent } from './MessageContent';

export function ChatView() {
  const {
    messages,
    isLoading,
    streamingContent,
    streamingReasoning,
    currentSessionId,
    sendMessage,
    stopStreaming,
  } = useChatStore();

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);
  const lastScrollHeightRef = useRef(0);
  const [displayContent, setDisplayContent] = useState('');
  const [displayReasoning, setDisplayReasoning] = useState('');
  const contentTimerRef = useRef<ReturnType<typeof requestAnimationFrame> | null>(null);

  // Throttle streaming content display to ~200ms via rAF to reduce re-renders
  useEffect(() => {
    if (contentTimerRef.current) cancelAnimationFrame(contentTimerRef.current);
    contentTimerRef.current = requestAnimationFrame(() => {
      setDisplayContent(streamingContent);
      setDisplayReasoning(streamingReasoning);
    });
    return () => {
      if (contentTimerRef.current) cancelAnimationFrame(contentTimerRef.current);
    };
  }, [streamingContent, streamingReasoning]);

  // When not streaming, sync immediately
  useEffect(() => {
    if (!isLoading) {
      setDisplayContent(streamingContent);
      setDisplayReasoning(streamingReasoning);
    }
  }, [isLoading, streamingContent, streamingReasoning]);

  // Track if user is near the bottom before updates
  const checkIfNearBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return true;
    const threshold = 120;
    return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
  }, []);

  // Monitor scroll position
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      isNearBottomRef.current = checkIfNearBottom();
    };
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, [checkIfNearBottom]);

  // Auto-scroll: use direct scrollTop manipulation instead of scrollIntoView to avoid jitter
  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    if (!isNearBottomRef.current) return;

    if (isLoading) {
      // During streaming: pin to bottom directly, no layout thrashing
      el.scrollTop = el.scrollHeight;
    } else {
      // After new message: smooth scroll
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, [messages, displayContent, displayReasoning, isLoading]);

  const showWelcome = messages.length === 0 && !isLoading && !currentSessionId;
  const isActivelyStreaming = isLoading && (!!displayContent || !!displayReasoning);

  if (showWelcome) {
    return <WelcomeScreen onSend={sendMessage} />;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages - overflow anchor keeps scroll stable */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto custom-scrollbar"
        style={{ overflowAnchor: 'auto' }}
      >
        {messages.map((msg) => (
          <MessageItem key={msg.id} message={msg} />
        ))}

        {/* Streaming message - use overflow-anchor: none to prevent jump */}
        {isActivelyStreaming && (
          <div
            className="group px-4 py-4 bg-[#1a1a1a]"
            style={{ overflowAnchor: 'none' }}
          >
            <div className="max-w-3xl mx-auto flex gap-4">
              <div className="shrink-0 mt-0.5">
                <div className="w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center">
                  <span className="text-white text-xs font-bold">AI</span>
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-gray-500 mb-1">AI 助手</div>
                {displayReasoning && (
                  <ReasoningBlock content={displayReasoning} defaultOpen={true} />
                )}
                {displayContent && (
                  <div className="markdown-content">
                    <MessageContent content={displayContent} />
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Loading indicator */}
        {isLoading && !streamingContent && !streamingReasoning && (
          <div className="px-4 py-4 bg-[#1a1a1a]">
            <div className="max-w-3xl mx-auto flex gap-4">
              <div className="w-8 h-8 rounded-full bg-primary-600 flex items-center justify-center">
                <span className="text-white text-xs font-bold">AI</span>
              </div>
              <div className="flex-1">
                <div className="text-xs text-gray-500 mb-1">AI 助手</div>
                <div className="flex items-center gap-2 text-gray-400 text-sm">
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                  正在思考...
                </div>
              </div>
            </div>
          </div>
        )}

        <div />
      </div>

      {/* Input */}
      <ChatInput
        onSend={sendMessage}
        onStop={stopStreaming}
        isLoading={isLoading}
      />
    </div>
  );
}
