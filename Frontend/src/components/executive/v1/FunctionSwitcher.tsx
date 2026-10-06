import type { ExecutiveFunction } from '../../../features/executive/types';

/** Function Summary header switcher (Figma 48:3): segmented over the viewer's functions. */
/** `assigned`: Function Viewer (functions come from its assignment; the first is its primary). */
export default function FunctionSwitcher({ functions, value, onChange, assigned = false }: { functions: ExecutiveFunction[]; value: ExecutiveFunction; onChange: (fn: ExecutiveFunction) => void; assigned?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-[4px]">
      <div className="flex items-center gap-[6px]">
        <span className="text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]">Function</span>
        {assigned && value === functions[0] && <span className="rounded-full bg-[var(--insights-accent-tag)] px-[6px] py-px text-[9px] font-semibold text-[var(--insights-accent-text)]">Primary</span>}
        <span className="text-[9px] font-semibold text-[var(--text-muted)]">{functions.length} {assigned ? 'assigned' : 'available'}</span>
      </div>
      <div role="radiogroup" aria-label="Function" className="flex h-[34px] items-center gap-[2px] rounded-[8px] border-[1.5px] border-[var(--insights-accent)] bg-[var(--bg-surface)] p-[2px]">
        {functions.map((fn) => {
          const active = fn === value;
          return (
            <button
              key={fn}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(fn)}
              className={`h-full whitespace-nowrap rounded-[6px] px-[10px] text-[12px] font-semibold transition-colors ${active ? 'bg-[var(--insights-accent)] text-white' : 'text-[var(--text-secondary)] hover:bg-[var(--insights-accent-soft)]'}`}
            >
              {fn}
            </button>
          );
        })}
      </div>
    </div>
  );
}
