import { useMemo, useState, type ReactNode } from 'react';
import { ChevronDown, FileBarChart, LayoutGrid } from 'lucide-react';
import { canonicalTeamName } from '../../types';
import { executiveFunctionForTeam, functionSlug, isTeamInFunctions, teamPath } from '../../features/executive/functions';
import type { ExecutiveFunction } from '../../features/executive/types';
import { getTeamIcon, isHiddenTeam } from './sidebarTeamItems';

type NavItem = { id?: string; name: string; path: string; icon: ReactNode };

/**
 * Function Viewer sidebar (Figma 48:3): Function Summary, then "My functions"
 * (each allowed function → its Function Summary, expandable to its teams'
 * read-only dashboards), then Library → Reports. No employee tree, Shared
 * Functions, Insights, Planning or Corrective Actions.
 */
export default function FunctionViewerNav({ allowed, catalogTeams, renderLink, isCollapsed }: {
  allowed: ExecutiveFunction[];
  /** Team names from the performance catalog (backend-scoped). */
  catalogTeams: string[];
  renderLink: (item: NavItem, nested?: boolean) => ReactNode;
  isCollapsed: boolean;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>(() => Object.fromEntries(allowed.map((fn, index) => [fn, index === 0])));
  const teamsByFunction = useMemo(() => {
    const map = new Map<ExecutiveFunction, string[]>();
    const seen = new Set<string>();
    catalogTeams.forEach((raw) => {
      const team = canonicalTeamName(raw) || raw;
      const key = team.toLowerCase();
      if (!team || seen.has(key) || isHiddenTeam(team)) return;
      const primary = executiveFunctionForTeam(team);
      const fn = primary && allowed.includes(primary) ? primary : allowed.find((fn) => isTeamInFunctions(team, [fn]));
      if (!fn || !allowed.includes(fn)) return;
      seen.add(key);
      map.set(fn, [...(map.get(fn) ?? []), team]);
    });
    map.forEach((teams) => teams.sort((left, right) => left.localeCompare(right)));
    return map;
  }, [allowed, catalogTeams]);

  const section = (label: string) => (
    <div className={`px-3 pb-1 pt-3 ${isCollapsed ? 'xl:hidden' : ''}`}>
      <p className="text-label text-[0.625rem] text-[var(--text-faint)]">{label}</p>
    </div>
  );

  return (
    <div data-testid="function-viewer-nav">
      {renderLink({ name: 'Function Summary', path: '/function-summary', icon: <LayoutGrid size={18} /> })}
      {section('MY FUNCTIONS')}
      {allowed.map((fn) => {
        const teams = teamsByFunction.get(fn) ?? [];
        const isOpen = open[fn] ?? false;
        return (
          <div key={fn} className="sidebar-nav-group">
            <div className="flex items-center gap-1">
              <div className="min-w-0 flex-1">{renderLink({ id: `fn-${fn}`, name: fn, path: `/function-summary/${functionSlug(fn)}`, icon: getTeamIcon(fn === 'Call Center' ? 'call center' : fn) })}</div>
              {teams.length > 0 && (
                <button
                  type="button"
                  aria-expanded={isOpen}
                  aria-label={`${isOpen ? 'Hide' : 'Show'} ${fn} teams`}
                  onClick={() => setOpen((state) => ({ ...state, [fn]: !isOpen }))}
                  className={`flex min-h-9 min-w-9 items-center justify-center rounded-lg text-[var(--text-faint)] hover:bg-[var(--sidebar-hover-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sgh-cyan-primary)] ${isCollapsed ? 'xl:hidden' : ''}`}
                >
                  <ChevronDown size={14} className={`transition-transform ${isOpen ? '' : '-rotate-90'}`} />
                </button>
              )}
            </div>
            {isOpen && teams.length > 0 && (
              <div className={`space-y-0.5 ${isCollapsed ? 'xl:hidden' : ''}`} role="group" aria-label={`${fn} teams`}>
                {teams.map((team) => renderLink({ id: `fn-${fn}-${team}`, name: team, path: teamPath(team), icon: <span className="block h-1.5 w-1.5 rounded-full bg-current" /> }, true))}
              </div>
            )}
          </div>
        );
      })}
      {section('LIBRARY')}
      {renderLink({ name: 'Reports', path: '/reports', icon: <FileBarChart size={18} /> })}
    </div>
  );
}
