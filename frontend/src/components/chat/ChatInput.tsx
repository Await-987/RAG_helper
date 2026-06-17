import { useState, useRef, useCallback, type KeyboardEvent } from 'react';
import { Send, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ChatInputProps {
  onSend: (message: string) => void;
  onStop: () => void;
  isLoading: boolean;
  disabled?: boolean;
}

export function ChatInput({ onSend, onStop, isLoading, disabled }: ChatInputProps) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isLoading || disabled) return;
    onSend(trimmed);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [input, isLoading, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend]
  );

  const handleInput = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      const scrollH = textarea.scrollHeight;
      textarea.style.height = Math.min(scrollH, 200) + 'px';
      textarea.style.overflowY = scrollH > 200 ? 'auto' : 'hidden';
    }
  }, []);

  return (
    <div className="input-chat flex items-end gap-2 pr-3">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        placeholder="发送消息..."
        disabled={disabled}
        rows={1}
        className="flex-1 bg-transparent outline-none resize-none text-base text-zinc-100 placeholder-zinc-500"
        style={{ maxHeight: '200px', overflowY: 'hidden' }}
      />
      {isLoading ? (
        <Button
          variant="secondary"
          size="icon"
          onClick={onStop}
          className="shrink-0 mb-0.5"
        >
          <Square size={18} className="text-white" />
        </Button>
      ) : (
        <Button
          size="icon"
          onClick={handleSend}
          disabled={!input.trim() || disabled}
          className="shrink-0 mb-0.5"
        >
          <Send size={18} className="text-white" />
        </Button>
      )}
    </div>
  );
}