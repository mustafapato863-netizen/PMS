import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import {
  Activity, ChevronDown, HeartPulse, LogOut, Settings, User, Users, X, Megaphone,
  FileBarChart,
  Lightbulb,
  ClipboardCheck,
  Building2,
  Layers,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useUserRole } from '../../context/RoleContext';
import { useAuth } from '../../context/auth';
import { usePerformanceCatalog } from '../../hooks/api/usePerformanceCatalog';
import { apiFetch } from '../../lib/apiClient';
import { normalizeTeamName } from '../../hooks/api/useKpiWeights';
import { shouldShowMarketingNavigation } from '../../features/marketing/navigation';
import type { PerformanceLevel } from '../../types';
import { isCallCenterTeam, CALL_CENTER_TEAM, isRcmTeam, RCM_TEAM } from '../../types';
import ThemeToggle from './ThemeToggle';
import { TEAM_ITEMS, getTeamIcon } from './sidebarTeamItems';
import { MANAGEMENT_DATA_CHANGED_EVENT } from '../../lib/managementDataEvents';
import { prepareBalancedScorecardTeamParams } from '../team/balancedScorecardNavigation';

interface SidebarProps {
  isOpen: boolean;
  setIsOpen: (val: boolean) => void;
  isCollapsed?: boolean;
  onToggleCollapsed?: () => void;
}

const LEVELS: Array<{ name: 'Employee'; icon: React.ReactNode; color: string }> = [
  { name: 'Employee', icon: <Users size={17} />, color: 'bg-blue-500' },
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
  const { data: performanceCatalog } = usePerformanceCatalog();
  const [configured, setConfigured] = useState<Record<string, string[]>>({});
  const [managementTeams, setManagementTeams] = useState<Array<{
    id: string;
    name: string;
    team_level: 'management';
  }>>([]);
  const [levelOpen, setLevelOpen] = useState<Record<'Employee' | 'Management', boolean>>({
    Employee: !selectedLevel || selectedLevel === 'All' || selectedLevel === 'Employee',
    Management: selectedLevel === 'Managerial' || selectedLevel === 'Corporate',
  });
  const [regionOpen, setRegionOpen] = useState<Record<string, boolean>>({
    'Employee-egy': true,
    'Employee-uae': true,
  });
  const [sharedOpen, setSharedOpen] = useState(true);

  const loadManagementTeams = useCallback(() => {
    apiFetch<{
      success: boolean;
      data: string[];
      scopes?: Array<{ id: string; name: string; team_level: 'management' }>;
    }>('/api/team-management/management-kpi-config/teams')
      .then((result) => {
        if (!result.success || !Array.isArray(result.data)) return;
        setManagementTeams(
          Array.isArray(result.scopes)
            ? result.scopes
            : result.data.map((name) => ({ id: name, name, team_level: 'management' as const })),
        );
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    apiFetch<{ success: boolean; data: Array<{ team: string; performance_levels?: Record<string, unknown> }> }>('/api/config/teams')
      .then((result) => {
        if (!result.success) return;
        setConfigured(Object.fromEntries(result.data.map((config) => [
          normalizeTeamName(config.team),
          Object.keys(config.performance_levels || {}),
        ])));
      })
      .catch(() => {});

    loadManagementTeams();
    window.addEventListener(MANAGEMENT_DATA_CHANGED_EVENT, loadManagementTeams);
    return () => window.removeEventListener(MANAGEMENT_DATA_CHANGED_EVENT, loadManagementTeams);
  }, [loadManagementTeams]);

  const scopedTeams = useMemo(() => {
    if (currentUser?.is_general_manager || role === 'Admin') return null;
    return new Set((currentUser?.accessible_teams || []).map(normalizeTeamName));
  }, [currentUser?.accessible_teams, currentUser?.is_general_manager, role]);

  const availableFromData = useMemo(() => {
    const result = new Set<string>();
    performanceCatalog?.scopes.forEach((scope) => {
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
    .filter((item) => !scopedTeams || scopedTeams.has(normalizeTeamName(item.team))), [managementTeams, scopedTeams]);

  const marketingVisible = shouldShowMarketingNavigation(availableFromData, scopedTeams);
  const rcmVisible = performanceCatalog?.scopes.some((scope) => isRcmTeam(scope.team))
    && (!scopedTeams || [...scopedTeams].some((team) => isRcmTeam(team)));

  const linkFor = (path: string, performanceLevel?: PerformanceLevel) => {
    const params = performanceLevel === 'Managerial' || performanceLevel === 'Corporate'
      ? prepareBalancedScorecardTeamParams(searchParams, performanceLevel)
      : new URLSearchParams(searchParams);
    if (performanceLevel && performanceLevel !== 'Managerial' && performanceLevel !== 'Corporate') {
      params.set('performance_level', performanceLevel);
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
        title={isCollapsed ? item.name : undefined}
        onClick={() => setIsOpen(false)}
        className={`flex min-h-10 items-center justify-between rounded-xl py-2 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${isCollapsed ? 'xl:justify-center xl:px-2' : nested ? 'pl-9 pr-3' : 'px-3'} ${active ? 'active-nav-item' : 'inactive-nav-item'}`}
        style={{
          color: active ? 'var(--sidebar-active-text)' : 'var(--sidebar-text)',
          background: active ? 'var(--sidebar-active-bg)' : undefined,
          border: active ? '1px solid var(--sidebar-active-border)' : '1px solid transparent',
        }}
      >
        <span className={`flex min-w-0 flex-1 items-center gap-3 ${isCollapsed ? 'xl:justify-center' : ''}`}>
          <span style={{ color: active ? 'var(--sidebar-active-text)' : 'var(--text-faint)' }}>{item.icon}</span>
          <span className={isCollapsed ? 'truncate xl:hidden' : 'truncate'}>{item.name}</span>
        </span>
        {active && <span className={`h-1.5 w-1.5 rounded-full bg-current opacity-70 ${isCollapsed ? 'xl:hidden' : ''}`} />}
      </Link>
    );
  };

  const canSeeBroadNavigation = role !== 'Agent';
  const generalItems = canSeeBroadNavigation
    ? [
        { name: 'Executive Summary', path: '/executive', icon: <Activity size={18} /> },
        ...(role === 'Admin' || currentUser?.is_general_manager || currentUser?.accessible_teams?.length
          ? [{ name: role === 'Manager' ? 'Assigned Teams' : 'All Teams', path: '/team/all', icon: <Users size={18} /> }]
          : []),
        ...(role === 'Admin'
          ? [
              { name: 'Reports', path: '/reports', icon: <FileBarChart size={18} /> },
              { name: 'Insights', path: '/insights', icon: <Lightbulb size={18} /> },
              { name: 'Planning', path: '/planning', icon: <ClipboardCheck size={18} /> },
              { name: 'Design System', path: '/design-system', icon: <Palette size={18} /> },
            ]
          : []),
      ]
    : [{ name: 'My Profile', path: `/employee/${currentUser?.employee_id || currentUser?.id || ''}`, icon: <User size={18} /> }];

  return (
    <aside
      aria-label="Primary navigation"
      className={`fixed left-0 top-0 z-40 flex h-dvh w-[272px] shrink-0 flex-col transition-[width,transform] duration-300 xl:translate-x-0 ${isCollapsed ? 'xl:w-[84px] is-collapsed' : 'is-expanded'} ${isOpen ? 'translate-x-0' : '-translate-x-full'} sidebar-navigation`}
      style={{ background: 'var(--sidebar-bg)', borderRight: '1px solid var(--sidebar-border)', boxShadow: '4px 0 20px rgba(0,0,0,0.04)' }}
    >
      <div className={`flex items-center justify-between gap-3 py-5 ${isCollapsed ? 'px-3 xl:justify-center' : 'px-5'}`}>
        <div className={`flex items-center gap-3 ${isCollapsed ? 'xl:justify-center' : ''}`}>
          <div className="rounded-xl border border-blue-400/20 bg-gradient-to-br from-blue-500 to-indigo-600 p-2 shadow-[0_4px_12px_rgba(59,130,246,0.30)]">
            <HeartPulse size={22} className="text-white" />
          </div>
          <div className={isCollapsed ? 'xl:hidden' : ''}>
            <h1 className="text-[15px] font-extrabold tracking-tight text-[var(--text-primary)]">SGH Hub</h1>
            <span className="mt-0.5 block text-[10px] font-bold uppercase tracking-widest text-blue-600">Intelligence</span>
          </div>
        </div>
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-label={isCollapsed ? 'Expand navigation sidebar' : 'Minimize navigation sidebar'}
          title={isCollapsed ? 'Expand sidebar' : 'Minimize sidebar'}
          className="hidden min-h-9 min-w-9 items-center justify-center rounded-lg text-[var(--text-muted)] transition-colors hover:bg-[var(--sidebar-hover-bg)] hover:text-blue-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 xl:flex"
        >
          {isCollapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}
        </button>
        <button onClick={() => setIsOpen(false)} aria-label="Close navigation sidebar" className="min-h-11 min-w-11 rounded-lg text-[var(--text-muted)] xl:hidden">
          <X size={18} className="mx-auto" />
        </button>
      </div>

      <div className={`mb-2 px-5 ${isCollapsed ? 'xl:hidden' : ''}`}><p className="text-label text-[0.625rem] text-[var(--text-faint)]">DASHBOARDS</p></div>
      <nav className="custom-scrollbar flex-1 space-y-0.5 overflow-y-auto px-3 pb-3">
        {generalItems.map((item) => renderLink(item))}

        {canSeeBroadNavigation && LEVELS.map((level) => {
          const regions = [
            { id: 'egy' as const, label: 'Offshore EGY', color: 'bg-blue-500' },
            { id: 'uae' as const, label: 'UAE Region', color: 'bg-emerald-500' },
          ].map((region) => ({ ...region, teams: visibleTeams(level.name, region.id) })).filter((region) => region.teams.length);
          if (!regions.length) return null;
          const isLevelOpen = levelOpen[level.name];
          return (
            <div key={level.name} className={`mt-3 ${isCollapsed ? 'xl:mt-2' : ''}`}>
              <button
                type="button"
                aria-expanded={isLevelOpen}
                onClick={() => setLevelOpen((state) => ({ ...state, [level.name]: !isLevelOpen }))}
                className={`flex min-h-11 w-full items-center gap-2.5 rounded-xl px-3 text-left text-sm font-extrabold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${isCollapsed ? 'xl:justify-center xl:px-2' : ''}`}
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
                            onClick={() => setRegionOpen((state) => ({ ...state, [key]: !isRegionOpen }))}
                            className={`flex min-h-10 w-full items-center gap-2 px-2 text-left text-[11px] font-extrabold uppercase tracking-wider text-[var(--text-faint)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${isCollapsed ? 'xl:justify-center xl:px-1' : ''}`}
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

        {canSeeBroadNavigation && (marketingVisible || rcmVisible) && (
          <div className={`mt-3 ${isCollapsed ? 'xl:mt-2' : ''}`}>
            <button
              type="button"
              aria-expanded={sharedOpen}
              onClick={() => setSharedOpen((open) => !open)}
              className={`flex min-h-11 w-full items-center gap-2.5 rounded-xl px-3 text-left text-sm font-extrabold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${isCollapsed ? 'xl:justify-center xl:px-2' : ''}`}
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

        {canSeeBroadNavigation && managementItems.length > 0 && (() => {
          const isLevelOpen = levelOpen.Management;
          return (
            <div key="Management" className={`mt-3 ${isCollapsed ? 'xl:mt-2' : ''}`}>
              <button
                type="button"
                aria-expanded={isLevelOpen}
                onClick={() => setLevelOpen((state) => ({ ...state, Management: !isLevelOpen }))}
                className={`flex min-h-11 w-full items-center gap-2.5 rounded-xl px-3 text-left text-sm font-extrabold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${isCollapsed ? 'xl:justify-center xl:px-2' : ''}`}
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
        {role !== 'Agent' && renderLink({ name: 'Settings', path: '/settings', icon: <Settings size={18} /> })}
        <div className={`sidebar-user-menu flex items-center justify-between gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--glass-bg)] p-2.5 ${isCollapsed ? 'xl:justify-center xl:p-2' : ''}`}>
          <div className={`flex min-w-0 items-center gap-2 ${isCollapsed ? 'xl:justify-center' : ''}`}>
            <div className="sidebar-user-avatar flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 text-[11px] font-bold text-white">
              {currentUser ? currentUser.name.split(' ').map((name) => name[0]).join('') : 'U'}
            </div>
            <div className={`min-w-0 ${isCollapsed ? 'xl:hidden' : ''}`}>
              <p className="truncate text-xs font-bold text-[var(--text-primary)]">{currentUser?.name}</p>
              <p className="mt-0.5 truncate text-[10px] font-semibold uppercase tracking-wider text-[var(--text-faint)]">{role}</p>
            </div>
          </div>
          <button onClick={logout} aria-label="Log out" title="Log out" className="min-h-9 min-w-9 rounded-lg text-[var(--text-muted)] transition-colors hover:bg-red-100 hover:text-red-600">
            <LogOut size={14} className="mx-auto" />
          </button>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
