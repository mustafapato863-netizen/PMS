import { Sparkles, Square } from 'lucide-react';

interface AiThinkingProgressCardProps {
  onStop?: () => void;
  compact?: boolean;
}

export default function AiThinkingProgressCard({ onStop, compact = false }: AiThinkingProgressCardProps) {
  return (
    <div className="flex min-h-10 flex-wrap items-center gap-3 py-2 text-sm text-slate-600 dark:text-slate-300">
      <span role="status" aria-label="Analyzing workspace data" className="inline-flex items-center gap-2.5">
        <Sparkles size={compact ? 14 : 17} className="text-blue-600 dark:text-blue-400" aria-hidden="true" />
        <span>Thinking</span>
        <span className="flex gap-1" aria-hidden="true">
          {[0, 140, 280].map((delay) => (
            <span key={delay} style={{ animationDelay: `${delay}ms` }}
              className="size-1 rounded-full bg-current motion-safe:animate-pulse" />
          ))}
        </span>
      </span>
      {onStop && (
        <button type="button" onClick={onStop} aria-label="Stop generating response"
          className="inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-xs font-medium hover:bg-slate-100 dark:hover:bg-slate-800">
          <Square size={10} aria-hidden="true" />
          Stop
        </button>
      )}
    </div>
  );
}
