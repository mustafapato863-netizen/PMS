import { useRef } from 'react';
import { ArrowRight, LayoutGrid, Send, X } from 'lucide-react';
import type { AiStarterPrompt } from '../../../features/ai/types';

interface AiComposerDockProps {
  promptInput: string;
  onChangePromptInput: (value: string) => void;
  onSubmitPrompt: (prompt: string) => void;
  isSending: boolean;
  hasTurns: boolean;
  showPromptLibrary: boolean;
  onTogglePromptLibrary: () => void;
  starterPrompts: AiStarterPrompt[];
}

export default function AiComposerDock({
  promptInput,
  onChangePromptInput,
  onSubmitPrompt,
  isSending,
  hasTurns,
  showPromptLibrary,
  onTogglePromptLibrary,
  starterPrompts,
}: AiComposerDockProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleTextareaChange = (value: string) => {
    onChangePromptInput(value);
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
    }
  };

  const resetHeightAndSubmit = () => {
    if (!promptInput.trim() || isSending) return;
    const text = promptInput;
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    onSubmitPrompt(text);
  };

  return (
    <div className="relative z-20 mx-auto w-full max-w-[49rem] px-4 pb-3 pt-2 sm:px-6">
      {/* On-demand Guided Prompts Popover (replaces the permanent duplicate gray follow-up tray) */}
      {hasTurns && showPromptLibrary && (
        <div
          data-testid="ai-midchat-scenarios-panel"
          className="mb-2.5 rounded-2xl border border-slate-200 bg-slate-50/90 p-3 shadow-xs"
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="text-xs font-bold text-slate-700">Guided Prompt Templates</span>
            <button
              type="button"
              aria-label="Close guided prompts"
              onClick={onTogglePromptLibrary}
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-200/60 hover:text-slate-700"
            >
              <X size={13} />
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {starterPrompts.map((item) => (
              <button
                key={item.id}
                type="button"
                disabled={isSending}
                onClick={() => {
                  onTogglePromptLibrary();
                  onSubmitPrompt(item.prompt);
                }}
                className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-left text-xs font-semibold text-slate-700 transition-colors hover:border-blue-400 hover:bg-blue-50/60 hover:text-blue-700 disabled:opacity-50"
              >
                <span>{item.label}</span>
                <ArrowRight size={12} className="shrink-0 text-blue-600" />
              </button>
            ))}
          </div>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          resetHeightAndSubmit();
        }}
        className="flex items-end gap-2 rounded-2xl border border-slate-200/90 bg-white px-3 py-2 shadow-xs transition-all focus-within:border-blue-500 focus-within:ring-3 focus-within:ring-blue-500/10"
      >
        {hasTurns && (
          <button
            type="button"
            data-testid="ai-midchat-scenarios-toggle"
            aria-expanded={showPromptLibrary}
            title="Browse guided prompt templates"
            onClick={onTogglePromptLibrary}
            className={`mb-0.5 inline-flex h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-xl border px-2.5 text-xs font-semibold transition-colors ${
              showPromptLibrary
                ? 'border-blue-300 bg-blue-50 text-blue-700'
                : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-blue-300 hover:text-blue-600'
            }`}
          >
            <LayoutGrid size={13} />
            <span className="hidden sm:inline">Prompts</span>
          </button>
        )}

        <textarea
          ref={textareaRef}
          rows={1}
          dir="auto"
          value={promptInput}
          onChange={(e) => handleTextareaChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              resetHeightAndSubmit();
            }
          }}
          disabled={isSending}
          placeholder="Ask a question about PMS…"
          aria-label="Ask PMS AI a question"
          className="max-h-[132px] min-h-[36px] min-w-0 flex-1 resize-none bg-transparent py-1.5 text-sm font-medium leading-snug text-slate-900 placeholder:text-slate-400 focus:outline-none disabled:opacity-60"
        />

        <button
          type="submit"
          disabled={isSending || !promptInput.trim()}
          aria-label="Send prompt"
          className="mb-0.5 flex h-9 w-10 shrink-0 cursor-pointer items-center justify-center rounded-xl bg-blue-600 text-white shadow-xs transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Send size={15} />
        </button>
      </form>

    </div>
  );
}
