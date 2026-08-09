import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  Award,
  AlertTriangle,
  Eye,
  MessageSquare,
  Clock,
  User,
  ChevronRight,
  ChevronDown,
  Users,
  ClipboardCheck,
  UserCheck,
  Check,
  Phone,
  HeartPulse,
  Target,
  Code,
  Headphones,
  Pill,
  Send,
  Briefcase,
} from 'lucide-react';
import type { ActionType } from '../../types';
import { summarizeRootCauses } from '../../utils/rootCauseInsights';

interface ActionsSummaryCardProps {
  month: string;
  stats: {
    total: number;
    byType: Record<string, number>;
    rootCauses: Record<string, number>;
    employeesActioned: number;
    actions: Array<{
      id: string;
      employee_id: string;
      employee_name: string;
      team: string;
      month: string;
      action_type: ActionType;
      action_text: string;
      root_cause_note: string;
      created_by: string;
      created_at: string;
      synced: boolean;
    }>;
  };
}

const ACTION_TYPE_CONFIG: Record<ActionType, { icon: React.ReactNode; barClass: string; class: string }> = {
  Training:  { icon: <BookOpen size={13} />,    barClass: 'bg-blue-500 dark:bg-blue-400',    class: 'action-Training' },
  Reward:    { icon: <Award size={13} />,        barClass: 'bg-emerald-500 dark:bg-emerald-400', class: 'action-Reward' },
  PIP:       { icon: <AlertTriangle size={13} />, barClass: 'bg-red-500 dark:bg-red-400',      class: 'action-PIP' },
  Monitor:   { icon: <Eye size={13} />,          barClass: 'bg-amber-500 dark:bg-amber-400',  class: 'action-Monitor' },
  Coaching:  { icon: <MessageSquare size={13} />, barClass: 'bg-purple-500 dark:bg-purple-400', class: 'action-Coaching' },
};

const getTeamVisual = (team: string): { label: string; icon: React.ReactNode; className: string } => {
  const normalizedTeam = team.toLowerCase().replace(/[^a-z0-9]+/g, '');

  if (normalizedTeam.includes('preapprovals')) {
    return { label: 'Pre-Approvals', icon: <ClipboardCheck size={15} />, className: 'bg-purple-500/10 text-purple-600 dark:text-purple-400' };
  }
  if (normalizedTeam.includes('inbounduae')) {
    return { label: 'Inbound UAE', icon: <HeartPulse size={15} />, className: 'bg-rose-500/10 text-rose-600 dark:text-rose-400' };
  }
  if (normalizedTeam.includes('inbound')) {
    return { label: 'Inbound', icon: <Headphones size={15} />, className: 'bg-blue-500/10 text-blue-600 dark:text-blue-400' };
  }
  if (normalizedTeam.includes('outbound')) {
    return { label: 'Outbound', icon: <Phone size={15} />, className: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' };
  }
  if (normalizedTeam.includes('sales')) {
    return { label: 'Sales', icon: <Target size={15} />, className: 'bg-amber-500/10 text-amber-600 dark:text-amber-400' };
  }
  if (normalizedTeam.includes('coding')) {
    return { label: 'Coding', icon: <Code size={15} />, className: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400' };
  }
  if (normalizedTeam.includes('csr')) {
    return { label: 'CSR', icon: <Headphones size={15} />, className: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400' };
  }
  if (normalizedTeam.includes('pharmacy')) {
    return { label: 'Pharmacy', icon: <Pill size={15} />, className: 'bg-teal-500/10 text-teal-600 dark:text-teal-400' };
  }
  if (normalizedTeam.includes('submission')) {
    return { label: team, icon: <Send size={15} />, className: 'bg-orange-500/10 text-orange-600 dark:text-orange-400' };
  }

  return { label: team, icon: <Briefcase size={15} />, className: 'bg-slate-500/10 text-slate-600 dark:text-slate-400' };
};

const ActionsSummaryCard = ({ month, stats }: ActionsSummaryCardProps) => {
  const [selectedTeam, setSelectedTeam] = useState('All Teams');
  const [isTeamMenuOpen, setIsTeamMenuOpen] = useState(false);
  const teamMenuRef = useRef<HTMLDivElement>(null);

  const teams = useMemo(() => {
    return Array.from(new Set(stats.actions.map((action) => action.team).filter(Boolean))).sort((a, b) => a.localeCompare(b));
  }, [stats.actions]);

  const effectiveTeam = selectedTeam !== 'All Teams' && !teams.includes(selectedTeam)
    ? 'All Teams'
    : selectedTeam;
  const visibleActions = useMemo(() => {
    if (effectiveTeam === 'All Teams') return stats.actions;
    return stats.actions.filter((action) => action.team === effectiveTeam);
  }, [effectiveTeam, stats.actions]);

  const visibleStats = useMemo(() => summarizeRootCauses(visibleActions), [visibleActions]);

  const topRootCauses = Object.entries(visibleStats.rootCauses)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 3);

  const rootCauseRows = useMemo(() => {
    if (effectiveTeam !== 'All Teams') {
      return topRootCauses.map(([cause, count]) => ({ team: effectiveTeam, cause, count }));
    }

    return teams
      .map((team) => {
        const teamStats = summarizeRootCauses(stats.actions.filter((action) => action.team === team));
        const [topCause] = Object.entries(teamStats.rootCauses)
          .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

        return topCause ? { team, cause: topCause[0], count: topCause[1] } : null;
      })
      .filter((row): row is { team: string; cause: string; count: number } => row !== null)
      .sort((a, b) => b.count - a.count || a.team.localeCompare(b.team));
  }, [effectiveTeam, stats.actions, teams, topRootCauses]);

  const pendingFollowUp = visibleActions
    .filter((a) => !a.synced)
    .slice(0, 5);

  const hasData = visibleStats.total > 0;

  useEffect(() => {
    if (!isTeamMenuOpen) return;

    const closeOnOutsideClick = (event: MouseEvent) => {
      if (!teamMenuRef.current?.contains(event.target as Node)) setIsTeamMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsTeamMenuOpen(false);
    };

    document.addEventListener('mousedown', closeOnOutsideClick);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutsideClick);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [isTeamMenuOpen]);

  const selectTeam = (team: string) => {
    setSelectedTeam(team);
    setIsTeamMenuOpen(false);
  };

  return (
    <div className="space-y-5">
      {/* Team filter */}
      <div ref={teamMenuRef} className="relative z-20">
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={isTeamMenuOpen}
          onClick={() => setIsTeamMenuOpen((open) => !open)}
          className={`group flex min-h-12 w-full items-center gap-3 rounded-xl border bg-[var(--bg-surface)] px-3.5 text-left shadow-sm transition-all hover:border-blue-300 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:hover:border-blue-500/50 ${
            isTeamMenuOpen ? 'border-blue-400 ring-2 ring-blue-500/15' : 'border-[var(--border-medium)]'
          }`}
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-blue-500/10 text-blue-600 dark:bg-blue-500/15 dark:text-blue-400">
            <Users size={16} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">Filter by team</span>
            <span className="block truncate text-sm font-bold text-[var(--text-primary)]">{effectiveTeam}</span>
          </span>
          <span className="hidden text-[10px] font-semibold text-[var(--text-muted)] sm:block">
            {visibleStats.total} {visibleStats.total === 1 ? 'action' : 'actions'}
          </span>
          <ChevronDown
            size={16}
            className={`shrink-0 text-[var(--text-muted)] transition-transform ${isTeamMenuOpen ? 'rotate-180' : ''}`}
          />
        </button>

        {isTeamMenuOpen && (
          <div
            role="listbox"
            aria-label="Filter actions by team"
            className="absolute inset-x-0 top-[calc(100%+8px)] overflow-hidden rounded-xl border border-[var(--border-medium)] bg-[var(--bg-surface)] p-1.5 shadow-xl"
          >
            {['All Teams', ...teams].map((team) => {
              const isSelected = team === effectiveTeam;
              return (
                <button
                  key={team}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => selectTeam(team)}
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${
                    isSelected
                      ? 'bg-blue-500/10 font-bold text-blue-700 dark:bg-blue-500/15 dark:text-blue-300'
                      : 'font-medium text-[var(--text-primary)] hover:bg-[var(--bg-sunken)]'
                  }`}
                >
                  <span className={`flex h-7 w-7 items-center justify-center rounded-md ${isSelected ? 'bg-blue-500/15' : 'bg-[var(--bg-sunken)]'}`}>
                    <Users size={14} />
                  </span>
                  <span className="min-w-0 flex-1 truncate">{team}</span>
                  {isSelected && <Check size={16} className="shrink-0" />}
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="action-summary-stat action-summary-stat-blue flex min-h-[94px] flex-col items-center justify-center rounded-xl border p-2.5 text-center">
          <ClipboardCheck size={16} className="mb-1" />
          <div className="text-2xl font-extrabold leading-none">{visibleStats.total}</div>
          <div className="action-summary-stat-label mt-1.5 text-[11px] font-bold leading-tight">Actions This Month</div>
        </div>
        <div className="action-summary-stat action-summary-stat-emerald flex min-h-[94px] flex-col items-center justify-center rounded-xl border p-2.5 text-center">
          <UserCheck size={16} className="mb-1" />
          <div className="text-2xl font-extrabold leading-none">{visibleStats.employeesActioned}</div>
          <div className="action-summary-stat-label mt-1.5 text-[11px] font-bold leading-tight">Employees Actioned</div>
        </div>
        <div className="action-summary-stat action-summary-stat-amber flex min-h-[94px] flex-col items-center justify-center rounded-xl border p-2.5 text-center">
          <Clock size={16} className="mb-1" />
          <div className="text-2xl font-extrabold leading-none">{pendingFollowUp.length}</div>
          <div className="action-summary-stat-label mt-1.5 text-[11px] font-bold leading-tight">Pending Sync</div>
        </div>
      </div>

      {/* Action Type Breakdown */}
      <div>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--text-muted)]">Breakdown by Action Type</h4>
          <span className="max-w-[120px] truncate rounded-full bg-[var(--bg-sunken)] px-2 py-1 text-[10px] font-bold text-[var(--text-secondary)]">
            {effectiveTeam}
          </span>
        </div>
        {!hasData ? (
          <p className="text-xs text-[var(--text-muted)] italic">No actions recorded for {month}.</p>
        ) : (
          <div className="space-y-2.5">
            {(Object.keys(ACTION_TYPE_CONFIG) as ActionType[]).map((type) => {
              const count = visibleStats.byType[type] || 0;
              const pct = visibleStats.total > 0 ? (count / visibleStats.total) * 100 : 0;
              const cfg = ACTION_TYPE_CONFIG[type];
              return (
                <div key={type} className="group flex items-center gap-3">
                  <div
                    className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-bold min-w-[90px] ${cfg.class}`}
                  >
                    {cfg.icon} {type}
                  </div>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--bg-sunken)]">
                    <div
                      className={`h-full rounded-full ${cfg.barClass}`}
                      style={{ transform: `scaleX(${pct / 100})`, transformOrigin: 'left', transition: 'transform 0.5s' }}
                    />
                  </div>
                  <span className="w-6 text-right text-xs font-bold text-[var(--text-secondary)]">{count}x</span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Top Root Causes */}
      {rootCauseRows.length > 0 && (
        <div className="border-t border-[var(--border-light)] pt-5">
          <div className="mb-3 flex items-center gap-1.5">
            <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--text-muted)]">
              {effectiveTeam === 'All Teams' ? 'Top Root Cause by Team' : `Top Root Causes · ${effectiveTeam}`}
            </h4>
            <span
              title="Shows the KPI most frequently recorded in corrective actions."
              className="flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-[var(--border-medium)] text-[9px] font-bold text-[var(--text-muted)]"
            >
              i
            </span>
          </div>

          <div className="overflow-hidden rounded-xl border border-[var(--border-light)]">
            <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)_auto] gap-2 bg-[var(--bg-sunken)] px-3 py-2 text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
              <span>Team</span>
              <span>Top Root Cause</span>
                <span className="text-right">Action mentions</span>
            </div>
            <div className="divide-y divide-[var(--border-light)]">
              {rootCauseRows.map(({ team, cause, count }, i) => {
                const teamVisual = getTeamVisual(team);
                return (
                  <div
                    key={`${team}-${cause}`}
                    className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.25fr)_auto] items-center gap-2 px-3 py-2.5 transition-colors hover:bg-[var(--bg-sunken)]"
                  >
                    <div className="flex min-w-0 items-center gap-2" title={team}>
                      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${teamVisual.className}`}>
                        {teamVisual.icon}
                      </span>
                      <span className="truncate text-xs font-semibold text-[var(--text-primary)]">{teamVisual.label}</span>
                    </div>
                    <div className="flex min-w-0 items-center gap-2">
                      <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white ${
                        i === 0 ? 'bg-red-500' : i === 1 ? 'bg-orange-400' : 'bg-amber-400'
                      }`}>
                        {i + 1}
                      </span>
                      <span className="truncate text-xs font-medium text-[var(--text-primary)]" title={cause}>{cause}</span>
                    </div>
                    <span className="text-right text-xs font-extrabold text-[var(--text-secondary)]">{count}x</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Pending Follow-Up */}
      {pendingFollowUp.length > 0 && (
        <div>
          <h4 className="text-xs font-bold uppercase tracking-wider text-[var(--text-muted)] mb-3 flex items-center gap-1.5">
            <Clock size={12} /> Pending Sync (Offline)
          </h4>
          <div className="space-y-1.5">
            {pendingFollowUp.map((action) => (
              <div
                key={action.id}
                className="flex items-center gap-2 px-3 py-2 bg-amber-500/5 dark:bg-amber-500/12 border border-amber-500/15 dark:border-amber-500/30 rounded-lg"
              >
                <User size={12} className="text-amber-600 shrink-0" />
                <span className="text-xs font-bold text-amber-700 dark:text-amber-400 flex-1 truncate">{action.employee_name}</span>
                <span
                  className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${ACTION_TYPE_CONFIG[action.action_type]?.class || ''}`}
                >
                  {action.action_type}
                </span>
                <ChevronRight size={12} className="text-amber-400" />
              </div>
            ))}
          </div>
        </div>
      )}

      {!hasData && (
        <div className="py-6 text-center">
          <MessageSquare size={28} className="mx-auto text-[var(--border-strong)] mb-2" />
          <p className="text-sm text-[var(--text-muted)] font-medium">
            No corrective actions recorded for <span className="font-bold">{month}</span>.
          </p>
          <p className="text-xs text-[var(--text-faint)] mt-1">Go to a team's dashboard to add actions.</p>
        </div>
      )}
    </div>
  );
};

export default ActionsSummaryCard;

