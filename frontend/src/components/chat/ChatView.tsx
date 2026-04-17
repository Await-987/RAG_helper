import { useRef, useEffect, useCallback } from 'react';
import {
  useChatStore,
  useCurrentMessages,
  useCurrentIsLoading,
  useCurrentStreamingContent,
  useCurrentStreamingReasoning,
  useCurrentSessionId,
} from '@/stores/chatStore';
import { MessageItem } from './MessageItem';
import { WelcomeScreen } from './WelcomeScreen';
import { ReasoningBlock } from './ReasoningBlock';
import { MessageContent } from './MessageContent';
import { ChatInput } from './ChatInput';
import { Sparkles } from 'lucide-react';

export function ChatView() {
  const currentSessionId = useCurrentSessionId();
  const sendMessage = useChatStore((s) => s.sendMessage);
  const stopStreaming = useChatStore((s) => s.stopStreaming);

  // Use independent session state hooks
  const messages = useCurrentMessages();
  const isLoading = useCurrentIsLoading();
  const streamingContent = useCurrentStreamingContent();
  const streamingReasoning = useCurrentStreamingReasoning();

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);

  const checkIfNearBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  }, []);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      isNearBottomRef.current = checkIfNearBottom();
    };
    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => el.removeEventListener('scroll', handleScroll);
  }, [checkIfNearBottom]);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    if (!isNearBottomRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, streamingContent, streamingReasoning, isLoading]);

  const showWelcome = messages.length === 0 && !isLoading && !currentSessionId;
  const isActivelyStreaming = isLoading && (!!streamingContent || !!streamingReasoning);

  if (showWelcome) {
    return <WelcomeScreen onSend={sendMessage} />;
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto custom-scrollbar">
        {messages.map((msg, idx) => (
          <MessageItem
            key={msg.id}
            message={msg}
            isLast={idx === messages.length - 1}
          />
        ))}

        {/* Streaming message */}
        {isActivelyStreaming && (
          <div className="px-4 py-6">
            <div className="max-w-3xl mx-auto flex gap-4">
              <div className="shrink-0">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center">
                  <Sparkles size={16} className="text-white" />
                </div>
              </div>
              <div className="flex-1 min-w-0">
                {streamingReasoning && (
                  <ReasoningBlock content={streamingReasoning} defaultOpen={true} />
                )}
                {streamingContent && (
                  <div className="markdown-content">
                    <MessageContent content={streamingContent} />
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Loading indicator */}
        {isLoading && !streamingContent && !streamingReasoning && (
          <div className="px-4 py-6">
            <div className="max-w-3xl mx-auto flex gap-4">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center">
                <Sparkles size={16} className="text-white animate-pulse" />
              </div>
              <div className="flex items-center gap-3 text-zinc-400 text-sm">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-1.5 h-1.5 bg-zinc-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span>思考中...</span>
              </div>
            </div>
          </div>
        )}

        <div className="h-32" />
      </div>

      {/* Bottom input */}
      <div className="px-4 pb-4">
        <div className="max-w-3xl mx-auto">
          <ChatInput
            onSend={sendMessage}
            onStop={stopStreaming}
            isLoading={isLoading}
          />
        </div>
      </div>
    </div>
  );
}