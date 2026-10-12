import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ClipboardCheck, Database, LayoutDashboard, SlidersHorizontal, Users, type LucideIcon } from 'lucide-react';
import { settingsPathFor, type SettingsPage, type SettingsRoutePage } from './shell/settingsNavigation';

interface SettingsLayoutProps {
  activePage: SettingsPage;
  children: ReactNode;
}

interface NavItem {
  page: SettingsRoutePage;
  label: string;
  icon: LucideIcon;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const OVERVIEW_ITEM: NavItem = { page: 'overview', label: 'Overview', icon: LayoutDashboard };

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Data',
    items: [
      { page: 'upload', label: 'Data uploads', icon: Database },
      { page: 'corrective_actions', label: 'Corrective action backup', icon: ClipboardCheck },
    ],
  },
  { label: 'Evaluation', items: [{ page: 'kpis', label: 'Evaluation settings', icon: SlidersHorizontal }] },
  { label: 'Access', items: [{ page: 'users', label: 'Users', icon: Users }] },
  { label: 'System', items: [{ page: 'system_errors', label: 'System errors', icon: Activity }] },
];

function matches(query: string) {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(query).matches;
}

export function SettingsLayout({ activePage, children }: SettingsLayoutProps) {
  const railRef = useRef<HTMLElement | null>(null);
  const activeRef = useRef<HTMLAnchorElement | null>(null);

  useEffect(() => {
    // Below xl the rail is one horizontal row. Scroll that row only, so the page itself does not move.
    const rail = railRef.current;
    const item = activeRef.current;
    if (!rail || !item || matches('(min-width: 80rem)')) return;
    const offset = item.getBoundingClientRect().left - rail.getBoundingClientRect().left;
    const reduced = matches('(prefers-reduced-motion: reduce)');
    rail.scrollTo?.({
      left: rail.scrollLeft + offset - (rail.clientWidth - item.offsetWidth) / 2,
      behavior: reduced ? 'auto' : 'smooth',
    });
  }, [activePage]);

  const renderItem = ({ page, label, icon: Icon }: NavItem) => {
    const active = page === activePage;
    return (
      <Link
        to={settingsPathFor(page)}
        aria-current={active ? 'page' : undefined}
        ref={active ? activeRef : undefined}
        className={`inline-flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl border px-3 text-sm font-bold transition-colors duration-200 motion-reduce:transition-none xl:min-h-10 xl:w-full xl:whitespace-normal ${
          active
            ? 'border-blue-500/25 bg-blue-500/10 text-blue-600 dark:text-blue-400'
            : 'border-transparent text-[var(--text-secondary)] hover:border-[var(--border-light)] hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]'
        } focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)]`}
      >
        <Icon size={18} aria-hidden="true" className="shrink-0" />
        {label}
      </Link>
    );
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[248px_minmax(0,1fr)]">
      <aside className="glass-panel h-fit min-w-0 rounded-2xl border border-[var(--border-light)] p-2 shadow-sm xl:sticky xl:top-24">
        <nav aria-label="Settings sections" ref={railRef} className="-mx-1 overflow-x-auto px-1 pb-1 xl:mx-0 xl:overflow-visible xl:p-0">
          <ul className="flex w-max items-stretch gap-1 xl:w-auto xl:flex-col xl:gap-4">
            <li className="flex">{renderItem(OVERVIEW_ITEM)}</li>
            {NAV_GROUPS.map((group, index) => (
              <li
                key={group.label}
                className={`flex items-stretch gap-1 xl:block ${index > 0 ? 'ml-1 border-l border-[var(--border-light)] pl-2 xl:ml-0 xl:border-l-0 xl:pl-0' : ''}`}
              >
                <p className="sr-only xl:not-sr-only xl:px-3 xl:pt-1 text-xs font-black uppercase tracking-[0.12em] text-[var(--text-muted)]">{group.label}</p>
                <ul className="flex items-stretch gap-1 xl:mt-1 xl:flex-col">
                  {group.items.map((item) => <li key={item.page} className="flex">{renderItem(item)}</li>)}
                </ul>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <section className="min-w-0">{children}</section>
    </div>
  );
}
