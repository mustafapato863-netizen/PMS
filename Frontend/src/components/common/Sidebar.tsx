import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CalendarCheck, ChevronDown, Eye, Gauge, LogOut, Settings, ShieldAlert, User, Users, UsersRound, X, Megaphone,
  FileBarChart,
  Lightbulb,
  Building2,
  Layers,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useUserRole } from '../../context/RoleContext';
import { useAuth } from '../../context/auth';
import { usePerformanceCatalog } from '../../hooks/api/usePerformanceCatalog';
import { apiFetch } from '../../lib/apiClient';
import { performanceSessionKey } from '../../lib/performanceSessionKey';
import { normalizeTeamName } from '../../hooks/api/useKpiWeights';
import { shouldShowMarketingNavigation } from '../../features/marketing/navigation';
import type { PerformanceLevel } from '../../types';
import { canonicalTeamName, isCallCenterTeam, CALL_CENTER_TEAM, isRcmTeam, RCM_TEAM } from '../../types';
import { directorScope } from '../../lib/directorScope';
import ThemeToggle from './ThemeToggle';
import { TEAM_ITEMS, getTeamIcon, isHiddenTeam } from './sidebarTeamItems';
import { MANAGEMENT_DATA_CHANGED_EVENT } from '../../lib/managementDataEvents';
import {
  canAccessCorrectiveActions,
  canAccessInsights,
  canAccessPlanning,
  canSeeReportsNav,
  getRoleDisplayLabel,
  hasAllTeamsScope,
  isScopedDirectorRole,
  isManagerRole,
} from '../../lib/access';
import { useFunctionScope } from '../../features/executive/useFunctionScope';
import { prepareBalancedScorecardTeamParams } from '../team/balancedScorecardNavigation';
import SghHeartSvg from './SghHeartSvg';

const FunctionViewerNav = lazy(() => import('./FunctionViewerNav'));

interface SidebarProps {
  isOpen: boolean;
  setIsOpen: (val: boolean) => void;
  isCollapsed?: boolean;
  onToggleCollapsed?: () => void;
}

const LEVELS: Array<{ name: 'Employee'; icon: React.ReactNode; color: string }> = [
  { name: 'Employee', icon: <Users size={17} />, color: 'bg-[var(--sgh-cyan-primary)]' },
];

const DIRECTOR_LEVELS: Array<{ name: PerformanceLevel; icon: React.ReactNode; color: string }> = [
  { name: 'Employee', icon: <Users size={17} />, color: 'bg-[var(--sgh-cyan-primary)]' },
  { name: 'Managerial', icon: <UsersRound size={17} />, color: 'bg-[var(--sgh-emerald-primary)]' },
  { name: 'Corporate', icon: <Building2 size={17} />, color: 'bg-[var(--sgh-cyan-deep)]' },
];

const slugifyTeam = (teamName: string) =>
  teamName
    .trim()
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

const prettyTeamLabel = (teamName: string) =>
  teamName.length <= 3
    ? teamName.toUpperCase()
    : teamName.replace(/\b\w/g, (char) => char.toUpperCase());

const Sidebar = ({ isOpen, setIsOpen, isCollapsed = false, onToggleCollapsed = () => {} }: SidebarProps) => {
  const { pathname } = useLocation();
  const [searchParams] = useSearchParams();
  const selectedLevel = searchParams.get('performance_level');
  const { role } = useUserRole();
  const { currentUser, logout } = useAuth();
  const assigned = directorScope(role, currentUser);
  const scopedDirector = isScopedDirectorRole(role);
  const { data: performanceCatalog } = usePerformanceCatalog();
  const functionScope = useFunctionScope();
  const queryClient = useQueryClient();
  const session = performanceSessionKey();
  const { data: configured = {} } = useQuery({
    queryKey: ['team-configs', 'sidebar', session],
    // Small config reads can finish across StrictMode remounts: the query cache
    // shares their in-flight promise instead of sending the request twice.
    queryFn: async () => {
      const result = await apiFetch<{ success: boolean; data: Array<{ team: string; performance_levels?: Record<string, unknown> }> }>('/api/config/teams');
      if (!result.success) throw new Error('Team configuration unavailable');
      return Object.fromEntries((Array.isArray(result.data) ? result.data : []).map((config) => [
        normalizeTeamName(config.team), Object.keys(config.performance_levels || {}),
      ]));
    },
    staleTime: Infinity,
    retry: false,
  });
  const { data: managementTeams = [] } = useQuery({
    queryKey: ['management-team-configs', 'sidebar', session],
    queryFn: async () => {
      const result = await apiFetch<{
        success: boolean;
        data: string[];
        scopes?: Array<{ id: string; name: string; team_level: 'management' }>;
      }>('/api/team-management/management-kpi-config/teams');
      if (!result.success || !Array.isArray(result.data)) throw new Error('Management teams unavailable');
      return Array.isArray(result.scopes) ? result.scopes
        : result.data.map((name) => ({ id: name, name, team_level: 'management' as const }));
    },
    staleTime: Infinity,
    retry: false,
  });
  const [levelOpen, setLevelOpen] = useState<Record<PerformanceLevel | 'Management', boolean>>({
    Employee: !selectedLevel || selectedLevel === 'All' || selectedLevel === 'Employee',
    Management: selectedLevel === 'Managerial' || selectedLevel === 'Corporate',
    Managerial: selectedLevel === 'Managerial',
    Corporate: selectedLevel === 'Corporate',
  });
  const [regionOpen, setRegionOpen] = useState<Record<string, boolean>>({
    'Employee-egy': true,
    'Employee-uae': true,
  });
  const [sharedOpen, setSharedOpen] = useState(true);

  const loadManagementTeams = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['management-team-configs', 'sidebar', session] });
  }, [queryClient, session]);

  useEffect(() => {
    window.addEventListener(MANAGEMENT_DATA_CHANGED_EVENT, loadManagementTeams);
    return () => window.removeEventListener(MANAGEMENT_DATA_CHANGED_EVENT, loadManagementTeams);
  }, [loadManagementTeams]);

  const scopedTeams = useMemo(() => {
    if (hasAllTeamsScope(role, currentUser)) return null;
    if (isScopedDirectorRole(role)) return new Set((performanceCatalog?.scopes ?? []).map((scope) => normalizeTeamName(scope.team)));
    return new Set((currentUser?.accessible_teams || []).map(normalizeTeamName));
  }, [currentUser, role, performanceCatalog?.scopes]);

  const directorTeams = scopedDirector ? [...new Map((performanceCatalog?.scopes ?? [])
    .filter((scope) => !isHiddenTeam(scope.team))
    .map((scope) => {
      const team = canonicalTeamName(scope.team);
      const level = scope.performance_level as PerformanceLevel;
      return [`${team}:${level}`, { team, level }] as const;
    })).values()].sort((a, b) => a.team.localeCompare(b.team) || a.level.localeCompare(b.level)) : [];

  const availableFromData = useMemo(() => {
    const result = new Set<string>();
    (performanceCatalog?.scopes || []).forEach((scope) => {
      result.add(`${normalizeTeamName(scope.team)}:${scope.performance_level || 'Employee'}`);
    });
    return result;
  }, [performanceCatalog?.scopes]);
  const visibleTeams = (level: PerformanceLevel, region: 'egy' | 'uae') => TEAM_ITEMS.filter((item) => {
    const teamKey = normalizeTeamName(item.team);
    if (item.region !== region || (scopedTeams && !scopedTeams.has(teamKey) && !(
      item.team === CALL_CENTER_TEAM && [...scopedTeams].some((team) => isCallCenterTeam(team))
    ))) return false;
    return level === 'Employee'
      || configured[teamKey]?.includes(level)
      || availableFromData.has(`${teamKey}:${level}`);
  });

  const managementItems = useMemo(() => managementTeams
    .map((teamScope) => ({
      id: teamScope.id,
      name: prettyTeamLabel(teamScope.name),
      path: `/team/${slugifyTeam(teamScope.name)}`,
      icon: getTeamIcon(teamScope.name),
      team: teamScope.name,
    }))
    .filter(
      (item) => !isHiddenTeam(item.team)
        && (!scopedTeams || scopedTeams.has(normalizeTeamName(item.team))),
    ), [managementTeams, scopedTeams]);

  const marketingVisible = shouldShowMarketingNavigation(availableFromData, scopedTeams);
  const rcmVisible = Boolean(performanceCatalog?.scopes?.some((scope) => isRcmTeam(scope.team)))
    && (!scopedTeams || [...scopedTeams].some((team) => isRcmTeam(team)));

  // Team drilldowns retain their context. Returning home carries dates only:
  // page-specific team/function/level filters must not narrow the company view.
  // Assigned director boundaries are applied separately below.
  const linkFor = (path: string, performanceLevel?: PerformanceLevel) => {
    const params = path === '/executive'
      ? new URLSearchParams([...searchParams].filter(([key]) => ['period', 'month', 'year'].includes(key)))
      : performanceLevel === 'Managerial' || performanceLevel === 'Corporate'
      ? prepareBalancedScorecardTeamParams(searchParams, performanceLevel)
      : new URLSearchParams(searchParams);
    if (performanceLevel && performanceLevel !== 'Managerial' && performanceLevel !== 'Corporate') {
      params.set('performance_level', performanceLevel);
    }
    if (assigned.branchLocked) {
      params.delete('branches');
      params.delete('location');
      params.delete('branch');
      if (assigned.branch) params.set('branch', assigned.branch);
    }
    if (assigned.regionLocked) {
      params.delete('region');
      if (assigned.region) params.set('region', assigned.region);
    }
    const query = params.toString();
    return `${path}${query ? `?${query}` : ''}`;
  };

  const renderLink = (
    item: { id?: string; name: string; path: string; icon: React.ReactNode },
    performanceLevel?: PerformanceLevel,
    nested = false,
    resetQuery = false,
    activeScope?: 'employee' | 'management',
  ) => {
    const effectiveSelectedLevel = selectedLevel || 'Employee';
    const levelMatches = activeScope === 'management'
      ? effectiveSelectedLevel === 'Managerial' || effectiveSelectedLevel === 'Corporate'
      : activeScope === 'employee'
        ? effectiveSelectedLevel === 'Employee'
        : !performanceLevel || effectiveSelectedLevel === performanceLevel;
    const active = pathname === item.path && levelMatches;
    const destination = resetQuery
      ? `${item.path}${performanceLevel ? `?performance_level=${performanceLevel}` : ''}`
      : linkFor(item.path, performanceLevel);
    return (
      <Link
        key={`${item.id || item.path}-${performanceLevel || 'general'}`}
        to={destination}
        aria-current={active ? 'page' : undefined}
        aria-label={isCollapsed ? item.name : undefined}
        title={isCollapsed || scopedDirector ? item.name : undefined}
        data-tooltip={isCollapsed ? item.name : undefined}
        onClick={() => setIsOpen(false)}
        className={`sidebar-tooltip-trigger flex min-h-11 items-center justify-between rounded-lg py-1.5 text-[12px] font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sgh-cyan-primary)] xl:min-h-9 ${isCollapsed ? 'xl:justify-center xl:px-2' : nested ? 'pl-8 pr-3' : 'px-3'} ${active ? 'active-nav-item' : 'inactive-nav-item'}`}
        style={{
          color: active ? 'var(--sidebar-active-text)' : 'var(--sidebar-text)',
          background: active ? 'var(--sidebar-active-bg)' : undefined,
          border: active ? '1px solid var(--sidebar-active-border)' : '1px solid transparent',
        }}
      >
        <span className={`flex min-w-0 flex-1 items-center gap-2.5 ${isCollapsed ? 'xl:justify-center' : ''}`}>
          <span style={{ color: active ? 'var(--sidebar-active-text)' : 'var(--text-faint)' }}>{item.icon}</span>
          <span className={isCollapsed ? 'truncate xl:hidden' : 'truncate'}>{item.name}</span>
        </span>
        {active && <span className={`h-1.5 w-1.5 rounded-full bg-current opacity-70 ${isCollapsed ? 'xl:hidden' : ''}`} />}
      </Link>
    );
  };

  // Function Viewer gets its own read-only navigation (FunctionViewerNav).
  // Keep the legacy Function Viewer experience isolated. Function Directors
  // have the same function boundary but also receive their assigned read pages.
  const isFunctionViewer = role === 'Function Viewer';
  const isSelfOnly = role === 'Agent' || role === 'Employee';
  const canSeeBroadNavigation = !isSelfOnly && !isFunctionViewer;
  const canSeeCorrectiveActions = canAccessCorrectiveActions(role);
  const roleLabel = getRoleDisplayLabel(role);
  const isManager = isManagerRole(role);
  const managerTeams = currentUser?.accessible_teams ?? [];
  // Manager (Mustafa, binding): Executive, their team, Reports, Corrective Actions, Planning — no Insights.
  const teamsItem = hasAllTeamsScope(role, currentUser) || managerTeams.length || isScopedDirectorRole(role)
    ? [isManager && managerTeams.length === 1
      ? { name: `My Team · ${managerTeams[0]}`, path: `/team/${slugifyTeam(managerTeams[0])}`, icon: <UsersRound size={18} /> }
      : { name: isManager ? 'Assigned Teams' : 'All Teams', path: '/team/all', icon: <UsersRound size={18} /> }]
    : [];
  const planningItem = { name: 'Planning', path: '/planning', icon: <CalendarCheck size={18} /> };
  const generalItems: Array<{ name: string; path: string; icon: React.ReactNode; resetQuery?: boolean }> = canSeeBroadNavigation
    ? [
        { name: 'Executive Summary', path: '/executive', icon: <Gauge size={18} /> },
        ...(!scopedDirector ? teamsItem : []),
        ...(canSeeReportsNav(role) ? [{ name: 'Reports', path: '/reports', icon: <FileBarChart size={18} /> }] : []),
        // Plain /insights: Insights keeps its own filters in the URL
        // (period/region/function/team/level), and the sidebar link is the
        // way back to the default view, so never carry the query (BUG-1b).
        ...(canAccessInsights(role) ? [{ name: 'Insights', path: '/insights', icon: <Lightbulb size={18} />, resetQuery: true }] : []),
        ...(canAccessPlanning(role) && !isManager ? [planningItem] : []),
        ...(canSeeCorrectiveActions
          ? [{ name: 'Corrective Actions', path: '/corrective-actions', icon: <ShieldAlert size={18} /> }]
          : []),
        ...(canAccessPlanning(role) && isManager ? [planningItem] : []),
      ]
    : [{ name: 'My Profile', path: `/employee/${currentUser?.employee_id || currentUser?.id || ''}`, icon: <User size={18} /> }];

  return (
    <aside
      aria-label="Primary navigation"
      className={`app-sidebar fixed left-0 top-0 z-40 flex h-dvh shrink-0 flex-col transition-[width,transform] duration-300 xl:translate-x-0 ${isCollapsed ? 'is-collapsed' : 'is-expanded'} ${isOpen ? 'translate-x-0' : '-translate-x-full'} sidebar-navigation`}
      style={{ background: 'var(--sidebar-bg)', borderRight: '1px solid var(--sidebar-border)', boxShadow: '4px 0 20px rgba(0,0,0,0.04)' }}
    >
      <div className={`flex items-center justify-between py-5 ${isCollapsed ? 'gap-1 px-1 xl:gap-1' : 'gap-3 px-5'}`}>
        <div className={`flex min-w-0 items-center ${isCollapsed ? 'gap-1 xl:shrink-0' : 'gap-3'}`}>
          <div className={`shrink-0 rounded-xl border border-[rgba(0,163,224,0.30)] bg-[var(--sgh-gradient-button)] shadow-[var(--sgh-glow-button)] ${isCollapsed ? 'p-1 xl:rounded-lg' : 'p-1.5'}`}>
            <SghHeartSvg size={isCollapsed ? 22 : 26} glow />
          </div>
          <div className={isCollapsed ? 'xl:hidden' : ''}>
            <h1 className="text-[14px] font-extrabold tracking-tight text-[var(--text-primary)]">SGH Hub</h1>
            <span className="mt-0.5 block text-[10px] font-bold uppercase tracking-widest text-[var(--sgh-cyan-primary)]">Intelligence</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={isCollapsed ? 'Expand navigation sidebar' : 'Minimize navigation sidebar'}
          title={isCollapsed ? 'Expand sidebar' : 'Minimize sidebar'}
          className={`hidden min-h-9 min-w-9 shrink-0 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--sidebar-hover-bg)] hover:text-[var(--sgh-cyan-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sgh-cyan-primary)] xl:flex ${isCollapsed ? 'xl:min-h-8 xl:min-w-8' : ''}`}
        >
          {isCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
        </button>
        <button onClick={() => setIsOpen(false)} aria-label="Close navigation sidebar" className="min-h-11 min-w-11 rounded-lg text-[var(--text-muted)] xl:hidden">
          <X size={18} className="mx-auto" />
        </button>
      </div>

      <div className={`mb-2 px-5 ${isCollapsed ? 'xl:hidden' : ''}`}><p className="text-label text-[0.625rem] text-[var(--text-faint)]">{isFunctionViewer ? 'FUNCTION VIEWER' : 'DASHBOARDS'}</p></div>
      <nav className="custom-scrollbar flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
        {isFunctionViewer ? (
          functionScope.loadError ? (
            <div role="alert" className="px-3 py-2 text-xs text-[var(--text-muted)]">Unable to verify function access. Refresh and try again.</div>
          ) : !functionScope.ready ? (
            <div role="status" className="px-3 py-2 text-xs text-[var(--text-muted)]">Loading your functions…</div>
          ) : (
            <Suspense fallback={<div role="status" className="px-3 py-2 text-xs text-[var(--text-muted)]">Loading navigation…</div>}>
              <FunctionViewerNav
                allowed={functionScope.allowed}
                catalogTeams={(performanceCatalog?.scopes || []).map((scope) => scope.team)}
                renderLink={(item, nested) => renderLink(item, undefined, nested, true)}
                isCollapsed={isCollapsed}
              />
            </Suspense>
          )
        ) : generalItems.map((item) => renderLink(item, undefined, false, item.resetQuery))}

        {scopedDirector && DIRECTOR_LEVELS.map((level) => {
          const teams = directorTeams.filter((team) => team.level === level.name);
          if (!teams.length) return null;
          const isLevelOpen = levelOpen[level.name];
          const groupId = `director-teams-${level.name.toLowerCase()}`;
          return (
            <div key={level.name} className={`sidebar-nav-group mt-2 ${isCollapsed ? 'xl:mt-1.5' : ''}`}>
              <button
                type="button"
                aria-label={`${level.name} teams`}
                aria-expanded={isLevelOpen}
                aria-controls={isLevelOpen ? groupId : undefined}
                title={isCollapsed ? level.name : undefined}
                data-tooltip={isCollapsed ? level.name : undefined}
                onClick={() => setLevelOpen((state) => ({ ...state, [level.name]: !state[level.name] }))}
                className={`sidebar-tooltip-trigger sidebar-nav-group-trigger flex min-h-11 w-full items-center gap-2.5 rounded-xl px-3 text-left text-sm font-extrabold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sgh-cyan-primary)] ${isCollapsed ? 'xl:justify-center xl:px-2' : ''}`}
              >
                <span className={`h-4 w-1 rounded-full ${level.color}`} />
                <span className="text-[var(--text-faint)]">{level.icon}</span>
                <span className={`flex-1 ${isCollapsed ? 'xl:hidden' : ''}`}>{level.name}</span>
                <span aria-hidden="true" className={`rounded-md bg-[var(--bg-sunken)] px-1.5 py-0.5 text-[10px] text-[var(--text-muted)] ${isCollapsed ? 'xl:hidden' : ''}`}>{teams.length}</span>
                <ChevronDown size={14} className={`transition-transform ${isLevelOpen ? '' : '-rotate-90'} ${isCollapsed ? 'xl:hidden' : ''}`} />
              </button>
              <AnimatePresence initial={false}>
                {isLevelOpen && (
                  <motion.div id={groupId} role="group" aria-label={`${level.name} teams`} initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="space-y-0.5 overflow-hidden">
                    {teams.map(({ team }) => renderLink({ name: team, path: `/team/${slugifyTeam(team)}`, icon: getTeamIcon(team) }, level.name, true))}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}
        {canSeeBroadNavigation && !scopedDirector && LEVELS.map((level) => {
          const regions = [
            { id: 'egy' as const, label: 'Offshore EGY', color: 'bg-[var(--sgh-cyan-primary)]' },
            { id: 'uae' as const, label: 'UAE Region', color: 'bg-[var(--sgh-emerald-primary)]' },
          ].map((region) => ({ ...region, teams: visibleTeams(level.name, region.id) })).filter((region) => region.teams.length);
          if (!regions.length) return null;
          const isLevelOpen = levelOpen[level.name];
          return (
            <div key={level.name} className={`sidebar-nav-group mt-2 ${isCollapsed ? 'xl:mt-1.5' : ''}`}>
              <button
                type="button"
                aria-expanded={isLevelOpen}
                aria-label={isCollapsed ? level.name : undefined}
                title={isCollapsed ? level.name : undefined}
                data-tooltip={isCollapsed ? level.name : undefined}
                onClick={() => setLevelOpen((state) => ({ ...state, [level.name]: !isLevelOpen }))}
                className={`sidebar-tooltip-trigger sidebar-nav-group-trigger flex min-h-11 w-full items-center gap-2.5 rounded-xl px-3 text-left text-sm font-extrabold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sgh-cyan-primary)] ${isCollapsed ? 'xl:justify-center xl:px-2' : ''}`}
              >
                <span className={`h-4 w-1 rounded-full ${level.color}`} />
                <span className="text-[var(--text-faint)]">{level.icon}</span>
                <span className={`flex-1 ${isCollapsed ? 'xl:hidden' : ''}`}>{level.name}</span>
                <ChevronDown size={14} className={`transition-transform ${isLevelOpen ? '' : '-rotate-90'} ${isCollapsed ? 'xl:hidden' : ''}`} />
              </button>
              <AnimatePresence initial={false}>
                {isLevelOpen && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                    {regions.map((region) => {
                      const key = `${level.name}-${region.id}`;
                      const isRegionOpen = regionOpen[key] ?? true;
                      return (
                        <div key={key} className={`ml-3 border-l border-[var(--border-light)] pl-2 ${isCollapsed ? 'xl:ml-0 xl:border-l-0 xl:pl-0' : ''}`}>
                          <button
                            type="button"
                            aria-expanded={isRegionOpen}
                            aria-label={isCollapsed ? region.label : undefined}
                            title={isCollapsed ? region.label : undefined}
                            data-tooltip={isCollapsed ? region.label : undefined}
                            onClick={() => setRegionOpen((state) => ({ ...state, [key]: !isRegionOpen }))}
                            className={`sidebar-tooltip-trigger flex min-h-10 w-full items-center gap-2 px-2 text-left text-[11px] font-extrabold uppercase tracking-wider text-[var(--text-faint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sgh-cyan-primary)] ${isCollapsed ? 'xl:justify-center xl:px-1' : ''}`}
                          >
                            <span className={`h-3 w-1 rounded-full ${region.color}`} />
                            <span className={`flex-1 ${isCollapsed ? 'xl:hidden' : ''}`}>{region.label}</span>
                            <ChevronDown size={13} className={`transition-transform ${isRegionOpen ? '' : '-rotate-90'} ${isCollapsed ? 'xl:hidden' : ''}`} />
                          </button>
                          {isRegionOpen && <div className="space-y-0.5">{region.teams.map((item) => renderLink(item, level.name, true))}</div>}
                        </div>
                      );
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })}

        {canSeeBroadNavigation && !scopedDirector && (marketingVisible || rcmVisible) && (
          <div className={`sidebar-nav-group mt-2 ${isCollapsed ? 'xl:mt-1.5' : ''}`}>
            <button
              type="button"
              aria-expanded={sharedOpen}
              aria-label={isCollapsed ? 'Shared Functions' : undefined}
              title={isCollapsed ? 'Shared Functions' : undefined}
              data-tooltip={isCollapsed ? 'Shared Functions' : undefined}
              onClick={() => setSharedOpen((open) => !open)}
              className={`sidebar-tooltip-trigger sidebar-nav-group-trigger flex min-h-11 w-full items-center gap-2.5 rounded-xl px-3 text-left text-sm font-extrabold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sgh-cyan-primary)] ${isCollapsed ? 'xl:justify-center xl:px-2' : ''}`}
            >
              <span className="h-4 w-1 rounded-full bg-violet-500" />
              <span className="text-[var(--text-faint)]"><Layers size={17} /></span>
              <span className={`flex-1 ${isCollapsed ? 'xl:hidden' : ''}`}>Shared Functions</span>
              <ChevronDown size={14} className={`transition-transform ${sharedOpen ? '' : '-rotate-90'} ${isCollapsed ? 'xl:hidden' : ''}`} />
            </button>
            <AnimatePresence initial={false}>
                {sharedOpen && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                    <div className={`ml-3 border-l border-[var(--border-light)] pl-2 ${isCollapsed ? 'xl:ml-0 xl:border-l-0 xl:pl-0' : ''}`}>
                      {rcmVisible && renderLink(
                        { name: RCM_TEAM, path: '/team/rcm', icon: getTeamIcon(RCM_TEAM) },
                        'Employee',
                        true,
                        true,
                        'employee',
                      )}
                      {marketingVisible && renderLink(
                        { name: 'Marketing', path: '/team/marketing', icon: <Megaphone size={17} /> },
                        'Employee',
                        true,
                        true,
                        'employee',
                      )}
                    </div>
                  </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        {canSeeBroadNavigation && !scopedDirector && managementItems.length > 0 && (() => {
          const isLevelOpen = levelOpen.Management;
          return (
            <div key="Management" className={`sidebar-nav-group mt-2 ${isCollapsed ? 'xl:mt-1.5' : ''}`}>
              <button
                type="button"
                aria-expanded={isLevelOpen}
                aria-label={isCollapsed ? 'Management' : undefined}
                title={isCollapsed ? 'Management' : undefined}
                data-tooltip={isCollapsed ? 'Management' : undefined}
                onClick={() => setLevelOpen((state) => ({ ...state, Management: !isLevelOpen }))}
                className={`sidebar-tooltip-trigger sidebar-nav-group-trigger flex min-h-11 w-full items-center gap-2.5 rounded-xl px-3 text-left text-sm font-extrabold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--sgh-cyan-primary)] ${isCollapsed ? 'xl:justify-center xl:px-2' : ''}`}
              >
                <span className="h-4 w-1 rounded-full bg-amber-500" />
                <span className="text-[var(--text-faint)]"><Building2 size={17} /></span>
                <span className={`flex-1 ${isCollapsed ? 'xl:hidden' : ''}`}>Management</span>
                <ChevronDown size={14} className={`transition-transform ${isLevelOpen ? '' : '-rotate-90'} ${isCollapsed ? 'xl:hidden' : ''}`} />
              </button>
              <AnimatePresence initial={false}>
                {isLevelOpen && (
                  <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                    <div className={`ml-3 border-l border-[var(--border-light)] pl-2 ${isCollapsed ? 'xl:ml-0 xl:border-l-0 xl:pl-0' : ''}`}>
                      <div className="space-y-0.5">
                        {managementItems.map((item) => renderLink(item, 'Corporate', true, false, 'management'))}
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          );
        })()}

      </nav>

      <div className={`mt-auto shrink-0 space-y-2 border-t border-[var(--border-light)] p-3 ${isCollapsed ? 'xl:p-2' : ''}`}>
        <div className={isCollapsed ? 'sidebar-collapsed-theme' : ''}><ThemeToggle variant="pill" /></div>
        {/* Settings link for all non-Agent roles; SettingsView soft-locks non-Admins (General Manager included). */}
        {!isSelfOnly && !isFunctionViewer && renderLink({ name: 'Settings', path: '/settings', icon: <Settings size={18} /> })}
        <div className={`sidebar-user-menu flex items-center justify-between gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-raised)] p-2.5 shadow-sm ${isCollapsed ? 'xl:justify-center xl:p-2' : ''}`}>
          <div className={`flex min-w-0 items-center gap-2 ${isCollapsed ? 'xl:justify-center' : ''}`}>
            <div className="sidebar-user-avatar flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold text-white shadow-sm" style={{ background: 'var(--sidebar-active-text)' }}>
              {currentUser ? currentUser.name.split(' ').map((name) => name[0]).join('') : 'U'}
            </div>
            <div className={`min-w-0 ${isCollapsed ? 'xl:hidden' : ''}`}>
              <p className="truncate text-xs font-bold text-[var(--text-primary)]">{currentUser?.name}</p>
              {isFunctionViewer
                ? <p className="mt-0.5 flex items-center gap-1 truncate text-[10px] font-semibold uppercase tracking-wider text-[var(--text-faint)]"><Eye size={11} aria-hidden="true" /><span title={roleLabel}>Read-only</span><span className="sr-only"> · {roleLabel}</span></p>
                : <p className="mt-0.5 truncate text-[10px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">{roleLabel}</p>}
            </div>
          </div>
          <button onClick={logout} aria-label="Log out" title="Log out" data-tooltip="Log out" className="sidebar-logout-button sidebar-tooltip-trigger min-h-9 min-w-9 rounded-lg text-[var(--text-muted)] transition-colors hover:bg-red-100 hover:text-red-600">
            <LogOut size={14} className="mx-auto" />
          </button>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
