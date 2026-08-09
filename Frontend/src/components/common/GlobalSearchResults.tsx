import {
  Briefcase,
  FileSpreadsheet,
  LayoutGrid,
  Search,
  Settings,
  Shield,
  Target,
  UserRound,
  Users,
} from 'lucide-react';

import type { SearchGroupId, SearchIconKey, SearchResultItem } from '../../lib/searchNavigation';

const GROUP_LABELS: Record<SearchGroupId, string> = {
  navigation: 'Navigate',
  employees: 'Employees',
  teams: 'Teams',
  actions: 'Actions',
};

const ICONS: Record<SearchIconKey, typeof Search> = {
  search: Search,
  layout: LayoutGrid,
  team: Users,
  employee: UserRound,
  settings: Settings,
  planning: Target,
  upload: FileSpreadsheet,
  shield: Shield,
  chart: Target,
  briefcase: Briefcase,
};

export default function GlobalSearchResults({
  groupedResults,
  activeIndex,
  onSelect,
  onHover,
  loading,
  error,
  query,
}: {
  groupedResults: Array<{ group: SearchGroupId; items: SearchResultItem[] }>;
  activeIndex: number;
  onSelect: (item: SearchResultItem) => void;
  onHover: (index: number) => void;
  loading: boolean;
  error: string | null;
  query: string;
}) {
  if (error) {
    return (
      <div className="px-4 py-6 text-sm text-rose-600 dark:text-rose-300">
        {error}
      </div>
    );
  }

  if (loading && groupedResults.length === 0) {
    return (
      <div className="px-4 py-6 text-sm text-[var(--text-muted)]">
        Searching…
      </div>
    );
  }

  if (!groupedResults.length) {
    return (
      <div className="px-4 py-7 text-center">
        <p className="text-sm font-semibold text-[var(--text-primary)]">No matching results</p>
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          {query ? 'Try a different employee, team, page, or action.' : 'Start typing to search the PMS system.'}
        </p>
      </div>
    );
  }

  return (
    <div className="max-h-[min(60vh,34rem)] overflow-y-auto p-2">
      {groupedResults.map((group, groupIndex) => (
        <section key={group.group} className="mb-2 last:mb-0">
          <div className="px-3 py-2 text-[10px] font-extrabold uppercase tracking-[0.18em] text-[var(--text-muted)]">
            {GROUP_LABELS[group.group]}
          </div>
          <div className="space-y-1">
            {group.items.map((item, itemIndex) => {
              const flatIndex = groupedResults
                .slice(0, groupIndex)
                .reduce((count, previousGroup) => count + previousGroup.items.length, itemIndex);
              const Icon = ICONS[item.icon];
              const active = flatIndex === activeIndex;
              return (
                <button
                  key={item.id}
                  type="button"
                  onMouseEnter={() => onHover(flatIndex)}
                  onClick={() => onSelect(item)}
                  className={`flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left transition-all ${
                    active
                      ? 'bg-blue-600 text-white shadow-[0_10px_24px_rgba(37,99,235,0.28)]'
                      : 'bg-transparent text-[var(--text-primary)] hover:bg-[var(--bg-sunken)]/80'
                  }`}
                >
                  <span
                    className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border ${
                      active
                        ? 'border-white/20 bg-white/10'
                        : 'border-[var(--border-light)] bg-[var(--bg-sunken)] text-blue-600 dark:text-blue-300'
                    }`}
                  >
                    <Icon size={16} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={`block truncate text-sm font-bold ${active ? 'text-white' : 'text-[var(--text-primary)]'}`}>
                      {item.label}
                    </span>
                    <span className={`mt-0.5 block truncate text-xs ${active ? 'text-blue-100' : 'text-[var(--text-muted)]'}`}>
                      {item.subtitle}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
