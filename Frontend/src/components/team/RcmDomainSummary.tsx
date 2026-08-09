import { ArrowUpRight, BadgeDollarSign, ClipboardCheck, Code, RefreshCw, Send } from 'lucide-react';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import { RCM_DOMAIN_LABELS, rcmDomainForTeam, type RcmDomainFilter } from '../../types';

interface RcmDomainSummaryProps {
  rows: TeamAgentRow[];
  onDomainSelect: (domain: Exclude<RcmDomainFilter, 'all'>) => void;
}

const DOMAINS: Array<Exclude<RcmDomainFilter, 'all'>> = ['pre_approvals', 'submission', 're_submission', 'coding'];

const DOMAIN_META: Record<Exclude<RcmDomainFilter, 'all'>, {
  icon: typeof BadgeDollarSign;
  tone: string;
  accent: string;
  glow: string;
}> = {
  pre_approvals: {
    icon: ClipboardCheck,
    tone: 'bg-violet-500/10 text-violet-600 dark:bg-violet-400/15 dark:text-violet-300',
    accent: 'bg-violet-500',
    glow: 'hover:border-violet-300/80 hover:shadow-[0_0_28px_rgba(139,92,246,0.24)] dark:hover:border-violet-400/60 dark:hover:shadow-[0_0_34px_rgba(167,139,250,0.25)]',
  },
  submission: {
    icon: Send,
    tone: 'bg-blue-500/10 text-blue-600 dark:bg-blue-400/15 dark:text-blue-300',
    accent: 'bg-blue-500',
    glow: 'hover:border-blue-300/80 hover:shadow-[0_0_28px_rgba(59,130,246,0.24)] dark:hover:border-blue-400/60 dark:hover:shadow-[0_0_34px_rgba(96,165,250,0.25)]',
  },
  re_submission: {
    icon: RefreshCw,
    tone: 'bg-emerald-500/10 text-emerald-600 dark:bg-emerald-400/15 dark:text-emerald-300',
    accent: 'bg-emerald-500',
    glow: 'hover:border-emerald-300/80 hover:shadow-[0_0_28px_rgba(16,185,129,0.24)] dark:hover:border-emerald-400/60 dark:hover:shadow-[0_0_34px_rgba(52,211,153,0.25)]',
  },
  coding: {
    icon: Code,
    tone: 'bg-amber-500/10 text-amber-600 dark:bg-amber-400/15 dark:text-amber-300',
    accent: 'bg-amber-500',
    glow: 'hover:border-amber-300/80 hover:shadow-[0_0_28px_rgba(245,158,11,0.24)] dark:hover:border-amber-400/60 dark:hover:shadow-[0_0_34px_rgba(251,191,36,0.25)]',
  },
};

const RcmDomainSummary = ({ rows, onDomainSelect }: RcmDomainSummaryProps) => {
  const availableDomains = DOMAINS.map((domain) => ({
    domain,
    domainRows: rows.filter((row) => rcmDomainForTeam(row.raw.identity.team) === domain),
  })).filter(({ domainRows }) => domainRows.length > 0);

  return (
    <section className="glass-panel rounded-xl p-4 shadow-sm sm:p-6" aria-labelledby="rcm-domain-summary">
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <BadgeDollarSign size={20} className="text-blue-600" />
          <h3 id="rcm-domain-summary" className="heading-3">RCM Domain Summary</h3>
        </div>
        <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">
          Revenue Cycle Management domains keep their own KPI definitions and scorecards.
        </p>
      </div>
      {availableDomains.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {availableDomains.map(({ domain, domainRows }) => {
        const average = domainRows.length > 0
          ? domainRows.reduce((sum, row) => sum + row.score, 0) / domainRows.length
          : 0;
        const Icon = DOMAIN_META[domain].icon;
        return (
          <button
            key={domain}
            type="button"
            onClick={() => onDomainSelect(domain)}
            aria-label={`Open ${RCM_DOMAIN_LABELS[domain]} domain`}
            className={`group relative overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 text-left transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${DOMAIN_META[domain].glow}`}
          >
            <span className={`pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full opacity-10 blur-2xl transition-opacity duration-200 group-hover:opacity-30 ${DOMAIN_META[domain].accent}`} />
            <div className="flex items-center gap-3">
              <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${DOMAIN_META[domain].tone}`}>
                <Icon size={19} />
              </span>
              <div>
                <h4 className="text-sm font-extrabold text-[var(--text-primary)]">{RCM_DOMAIN_LABELS[domain]}</h4>
                <p className="text-xs font-semibold text-[var(--text-muted)]">{domainRows.length} employees</p>
              </div>
            </div>
            <div className="mt-4 flex items-end justify-between gap-3">
              <div>
                <div className="text-2xl font-extrabold text-[var(--text-primary)]">
                  {domainRows.length > 0 ? `${average.toFixed(1)}%` : 'No data'}
                </div>
                <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">Average employee score</p>
              </div>
              <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-light)] text-[var(--text-muted)] transition-all duration-200 group-hover:border-current group-hover:text-[var(--text-primary)]" aria-hidden="true">
                <ArrowUpRight size={16} />
              </span>
            </div>
          </button>
          );
          })}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-[var(--border-light)] px-4 py-6 text-sm font-semibold text-[var(--text-secondary)]">
          No RCM domains have data for the selected filters.
        </p>
      )}
    </section>
  );
};

export default RcmDomainSummary;
