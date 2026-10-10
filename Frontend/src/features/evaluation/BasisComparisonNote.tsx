import { dedupeBasisMessages } from './scoringBasisComparison';

export default function BasisComparisonNote({ messages }: { messages: Array<string | null | undefined> }) {
  const unique = dedupeBasisMessages(messages);
  if (!unique.length) return null;
  return (
    <p data-testid="basis-comparison-note" role="note" className="min-w-0 whitespace-normal break-words text-[11px] leading-4 text-[var(--text-secondary)]">
      {unique.join(' ')}
    </p>
  );
}
