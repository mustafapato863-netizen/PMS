import { Award, UsersRound } from 'lucide-react';

export type RosterView = 'all' | 'top_bottom';

export default function RosterViewTiles({ value, onChange, label = 'Employee roster view' }: {
  value: RosterView;
  onChange: (value: RosterView) => void;
  label?: string;
}) {
  return (
    <div role="group" aria-label={label} className="grid w-full grid-cols-2 gap-2 sm:w-auto">
      {([
        { value: 'all', label: 'All Employees', description: 'Full employee roster', icon: UsersRound },
        { value: 'top_bottom', label: 'Top / Bottom', description: 'Highest & lowest scores', icon: Award },
      ] as const).map((option) => {
        const selected = value === option.value;
        const Icon = option.icon;
        return (
          <button key={option.value} type="button" aria-label={option.label} aria-pressed={selected}
            onClick={() => onChange(option.value)}
            className={`roster-view-tile flex min-w-0 cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] motion-reduce:transition-none ${selected
              ? 'border-blue-500 bg-blue-500/10 text-blue-700 dark:text-blue-300'
              : 'border-[var(--border-medium)] bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:border-blue-400 hover:bg-blue-500/5'}`}>
            <Icon size={18} aria-hidden="true" className="shrink-0" />
            <span className="min-w-0">
              <span className="block text-xs font-bold sm:text-sm">{option.label}</span>
              <span className="mt-0.5 hidden text-[11px] text-[var(--text-secondary)] sm:block">{option.description}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
