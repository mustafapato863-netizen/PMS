import { useEffect, useRef, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Activity, ClipboardCheck, Database, LayoutDashboard, SlidersHorizontal, Users, UsersRound, type LucideIcon } from 'lucide-react';
import { settingsPathFor, type SettingsPage, type SettingsRoutePage } from './shell/settingsNavigation';

/**
 * Width of the Administration area itself (not the window) at which the sections become a vertical rail.
 * The container query classes below carry the same number as a literal, because Tailwind reads class names statically.
 */
export const ADMIN_RAIL_MIN_WIDTH_PX = 900;

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
  { label: 'Access', items: [{ page: 'users', label: 'Users', icon: Users }, { page: 'teams', label: 'Teams', icon: UsersRound }] },
  { label: 'System', items: [{ page: 'system_errors', label: 'System errors', icon: Activity }] },
];

function matches(query: string) {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(query).matches;
}

export function SettingsLayout({ activePage, children }: SettingsLayoutProps) {
  const railRef = useRef<HTMLElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);
  const activeRef = useRef<HTMLAnchorElement | null>(null);

  useEffect(() => {
    // In row mode the list is one horizontal line. Scroll that line only, so the page itself does not move.
    // In rail mode the list is a column, and its computed direction is the layout's real mode, so no width is re-checked here.
    const rail = railRef.current;
    const list = listRef.current;
    const item = activeRef.current;
    if (!rail || !list || !item || getComputedStyle(list).flexDirection === 'column') return;
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
        className={`inline-flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl border px-3 text-sm font-bold transition-colors duration-200 motion-reduce:transition-none @min-[900px]/settings:min-h-10 @min-[900px]/settings:w-full @min-[900px]/settings:whitespace-normal ${
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

  // The Administration area is the size container, so its own width picks the layout. Opening or collapsing the app sidebar changes that width, and a viewport query would miss it.
  return (
    <div className="@container/settings">
      <div className="grid gap-4 @min-[900px]/settings:grid-cols-[208px_minmax(0,1fr)]">
        <aside className="glass-panel h-fit min-w-0 rounded-2xl border border-[var(--border-light)] p-2 shadow-sm @min-[900px]/settings:sticky @min-[900px]/settings:top-24 @min-[900px]/settings:max-h-[calc(100dvh-14rem)] @min-[900px]/settings:overflow-y-auto">
          {/* `relative` makes the rail the containing block of the sr-only group labels, so their overflow stays clipped by this scroller. */}
          <nav aria-label="Settings sections" ref={railRef} className="relative -mx-1 overflow-x-auto px-1 pb-1 @min-[900px]/settings:mx-0 @min-[900px]/settings:overflow-visible @min-[900px]/settings:p-0">
            <ul ref={listRef} className="flex w-max items-stretch gap-1 @min-[900px]/settings:w-auto @min-[900px]/settings:flex-col @min-[900px]/settings:gap-4">
              <li className="flex">{renderItem(OVERVIEW_ITEM)}</li>
              {NAV_GROUPS.map((group, index) => (
                <li
                  key={group.label}
                  className={`flex items-stretch gap-1 @min-[900px]/settings:block ${index > 0 ? 'ml-1 border-l border-[var(--border-light)] pl-2 @min-[900px]/settings:ml-0 @min-[900px]/settings:border-l-0 @min-[900px]/settings:pl-0' : ''}`}
                >
                  <p className="sr-only @min-[900px]/settings:not-sr-only @min-[900px]/settings:px-3 @min-[900px]/settings:pt-1 text-xs font-black uppercase tracking-[0.12em] text-[var(--text-muted)]">{group.label}</p>
                  <ul className="flex items-stretch gap-1 @min-[900px]/settings:mt-1 @min-[900px]/settings:flex-col">
                    {group.items.map((item) => <li key={item.page} className="flex">{renderItem(item)}</li>)}
                  </ul>
                </li>
              ))}
            </ul>
          </nav>
        </aside>
        <section className="min-w-0">{children}</section>
      </div>
    </div>
  );
}
