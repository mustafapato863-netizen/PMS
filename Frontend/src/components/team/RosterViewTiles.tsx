export type RosterView = 'all' | 'top_bottom';

/** Visible text is short; the accessible name keeps the full wording the tests and screen readers rely on. */
const OPTIONS = [
  { value: 'all', label: 'All', name: 'All Employees' },
  { value: 'top_bottom', label: 'Top / Bottom', name: 'Top / Bottom' },
] as const;

/** Compact segmented control for the roster: one row, no subtitles or icons. */
export default function RosterViewTiles({ value, onChange, label = 'Employee roster view' }: {
  value: RosterView;
  onChange: (value: RosterView) => void;
  label?: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg border border-[var(--border-medium)] bg-[var(--bg-sunken)] p-0.5">
      {OPTIONS.map((option) => {
        const selected = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            aria-label={option.name}
            aria-pressed={selected}
            onClick={() => onChange(option.value)}
            className={`h-[2.75rem] cursor-pointer whitespace-nowrap rounded-md px-3 text-xs font-semibold transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--bg-sunken)] motion-reduce:transition-none sm:h-8 ${selected
              ? 'bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-sm'
              : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
