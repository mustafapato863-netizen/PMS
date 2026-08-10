import type { ReactNode } from 'react';
import { ClipboardCheck, Database, SlidersHorizontal, Users } from 'lucide-react';
import type { SettingsSection } from './types';

interface SettingsLayoutProps {
  activeSection: SettingsSection;
  onSectionChange: (section: SettingsSection) => void;
  children: ReactNode;
}

const navigation = [
  { id: 'upload' as const, label: 'Data Management', description: 'Employee and management uploads', icon: Database },
  { id: 'corrective_actions' as const, label: 'Corrective Actions', description: 'Transfer action history safely', icon: ClipboardCheck },
  { id: 'kpis' as const, label: 'KPI Configuration', description: 'Weights and targets by team', icon: SlidersHorizontal },
  { id: 'users' as const, label: 'User Management', description: 'Accounts, roles and access', icon: Users },
];

export function SettingsLayout({ activeSection, onSectionChange, children }: SettingsLayoutProps) {
  return (
    <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="glass-panel h-fit rounded-3xl border border-[var(--border-light)] p-3 shadow-sm xl:sticky xl:top-24">
        <div className="px-3 pb-3 pt-2">
          <p className="text-[10px] font-black uppercase tracking-[0.18em] text-[var(--text-muted)]">Administration</p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">Choose a workspace to configure.</p>
        </div>
        <nav aria-label="Settings sections" className="space-y-1.5">
          {navigation.map(({ id, label, description, icon: Icon }) => {
            const selected = id === activeSection;
            return (
              <button
                key={id}
                type="button"
                aria-current={selected ? 'page' : undefined}
                onClick={() => onSectionChange(id)}
                className={`flex w-full items-start gap-3 rounded-2xl border px-3 py-3 text-left transition-colors ${
                  selected
                    ? 'border-blue-500/25 bg-blue-500/10 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-[var(--text-secondary)] hover:border-[var(--border-light)] hover:bg-[var(--bg-sunken)]'
                }`}
              >
                <Icon size={18} className="mt-0.5 shrink-0" />
                <span>
                  <span className="block text-xs font-extrabold">{label}</span>
                  <span className="mt-0.5 block text-[10px] leading-4 text-[var(--text-muted)]">{description}</span>
                </span>
              </button>
            );
          })}
        </nav>
      </aside>
      <section className="min-w-0">{children}</section>
    </div>
  );
}
