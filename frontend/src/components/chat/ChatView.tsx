import { useRef, useEffect, useCallback, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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
import { Skeleton } from '@/components/ui/skeleton';
import { Sparkles, ArrowDown } from 'lucide-react';

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
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  const checkIfNearBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return true;
    return el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }, []);

  useEffect(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const handleScroll = () => {
      const nearBottom = checkIfNearBottom();
      isNearBottomRef.current = nearBottom;
      setShowScrollBottom(!nearBottom);
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

  const scrollToBottom = useCallback(() => {
    const el = scrollContainerRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
    }
  }, []);

  const showWelcome = messages.length === 0 && !isLoading && !currentSessionId;
  const isActivelyStreaming = isLoading && (!!streamingContent || !!streamingReasoning);

  if (showWelcome) {
    return <WelcomeScreen onSend={sendMessage} />;
  }

  return (
    <div className="flex flex-col h-full relative">
      {/* Messages */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto custom-scrollbar">
        <AnimatePresence initial={false}>
          {messages.map((msg, idx) => (
            <MessageItem
              key={msg.id}
              message={msg}
              isLast={idx === messages.length - 1}
            />
          ))}
        </AnimatePresence>

        {/* Streaming message */}
        {isActivelyStreaming && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
            className="px-4 py-6"
          >
            <div className="max-w-3xl mx-auto flex gap-4">
              <div className="shrink-0">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center shadow-sm shadow-primary-600/20">
                  <Sparkles size={16} className="text-white" />
                </div>
              </div>
              <div className="flex-1 min-w-0">
                {streamingReasoning && (
                  <ReasoningBlock content={streamingReasoning} />
                )}
                {streamingContent && (
                  <div className="markdown-content">
                    <MessageContent content={streamingContent} />
                  </div>
                )}
              </div>
            </div>
          </motion.div>
        )}

        {/* Loading indicator - skeleton */}
        {isLoading && !streamingContent && !streamingReasoning && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="px-4 py-6"
          >
            <div className="max-w-3xl mx-auto flex gap-4">
              <div className="shrink-0">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary-500 to-primary-600 flex items-center justify-center shadow-sm shadow-primary-600/20">
                  <Sparkles size={16} className="text-white" />
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium mb-2 text-zinc-300">知识库助手</div>
                <div className="flex items-center gap-3">
                  <div className="flex gap-1.5">
                    <Skeleton className="h-2 w-16 rounded" />
                    <Skeleton className="h-2 w-24 rounded" />
                    <Skeleton className="h-2 w-12 rounded" />
                  </div>
                  <span className="text-zinc-400 text-sm">思考中...</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        <div className="h-32" />
      </div>

      {/* Scroll to bottom button */}
      <AnimatePresence>
        {showScrollBottom && (
          <motion.button
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            onClick={scrollToBottom}
            className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 w-9 h-9 rounded-full flex items-center justify-center bg-dark-tertiary border border-white/10 shadow-lg shadow-black/30 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-600 transition-colors"
          >
            <ArrowDown size={16} />
          </motion.button>
        )}
      </AnimatePresence>

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