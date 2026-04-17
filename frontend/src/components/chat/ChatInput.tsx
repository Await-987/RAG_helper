import { useState, useRef, useCallback, type KeyboardEvent } from 'react';
import { Send, Square } from 'lucide-react';

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
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }
  }, []);

  return (
    <div className="relative">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        placeholder="发送消息..."
        disabled={disabled}
        rows={1}
        className="input-chat pr-12 resize-none"
        style={{ minHeight: '52px', maxHeight: '200px' }}
      />
      {isLoading ? (
        <button
          onClick={onStop}
          className="absolute right-3 bottom-3 w-9 h-9 rounded-xl bg-zinc-600 hover:bg-zinc-500 flex items-center justify-center transition-colors"
        >
          <Square size={18} className="text-white" />
        </button>
      ) : (
        <button
          onClick={handleSend}
          disabled={!input.trim() || disabled}
          className="absolute right-3 bottom-3 w-9 h-9 rounded-xl bg-primary-600 hover:bg-primary-700 disabled:bg-zinc-700 disabled:opacity-60 flex items-center justify-center transition-colors"
        >
          <Send size={18} className="text-white" />
        </button>
      )}
    </div>
  );
}