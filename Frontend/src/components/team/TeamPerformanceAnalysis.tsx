import { useMemo, useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp, Lightbulb, TrendingDown, TrendingUp } from 'lucide-react';
import type { InsightItem } from '../../features/insights/types';

interface TeamPerformanceAnalysisProps {
  insights: InsightItem[];
  loading?: boolean;
}

const severityStyles: Record<InsightItem['severity'], string> = {
  critical: 'border-rose-300/70 bg-rose-500/[0.055] text-rose-700 dark:border-rose-500/25 dark:text-rose-300',
  risk: 'border-amber-300/70 bg-amber-500/[0.055] text-amber-700 dark:border-amber-500/25 dark:text-amber-300',
  opportunity: 'border-emerald-300/70 bg-emerald-500/[0.055] text-emerald-700 dark:border-emerald-500/25 dark:text-emerald-300',
  information: 'border-blue-300/70 bg-blue-500/[0.055] text-blue-700 dark:border-blue-500/25 dark:text-blue-300',
};

const severityLabel: Record<InsightItem['severity'], string> = {
  critical: 'Critical gap',
  risk: 'Needs attention',
  opportunity: 'Positive driver',
  information: 'Information',
};

const TeamPerformanceAnalysis = ({ insights, loading = false }: TeamPerformanceAnalysisProps) => {
  const [showAll, setShowAll] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const analysisItems = useMemo(
    () => insights.filter((item) => ['performance', 'kpi_driver', 'opportunity'].includes(item.insight_type)),
    [insights],
  );
  const visibleItems = showAll ? analysisItems : analysisItems.slice(0, 3);
  const recommendations = useMemo(
    () => [...new Set(analysisItems
      .filter((item) => item.insight_type === 'kpi_driver' || item.insight_type === 'opportunity')
      .map((item) => item.detail.recommended_focus)
      .filter(Boolean))].slice(0, 3),
    [analysisItems],
  );

  if (loading) {
    return <div className="mt-5 h-20 animate-pulse rounded-xl bg-[var(--bg-sunken)]" aria-label="Loading performance analysis" />;
  }
  if (!analysisItems.length) return null;

  return (
    <section className="mt-5 border-t border-[var(--border-light)] pt-4" aria-labelledby="team-performance-analysis-title">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-extrabold text-[var(--text-primary)]">
          <Lightbulb size={15} className="text-violet-600 dark:text-violet-400" />
          <h4 id="team-performance-analysis-title">Performance Analysis</h4>
        </div>
        {analysisItems.length > 3 && (
          <button
            type="button"
            onClick={() => setShowAll((current) => !current)}
            aria-expanded={showAll}
            className="inline-flex min-h-8 items-center gap-1 rounded-lg border border-[var(--border-medium)] px-2.5 text-[10px] font-extrabold text-[var(--text-secondary)] transition hover:bg-[var(--bg-sunken)]"
          >
            {showAll ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {showAll ? 'Show priority only' : `Show all ${analysisItems.length}`}
          </button>
        )}
      </div>

      <div className="space-y-2">
        {visibleItems.map((item) => {
          const isExpanded = expandedId === item.id;
          const positive = item.impact_points !== null && item.impact_points > 0;
          const TrendIcon = positive ? TrendingUp : TrendingDown;
          return (
            <div key={item.id} className={`overflow-hidden rounded-xl border ${severityStyles[item.severity]}`}>
              <button
                type="button"
                onClick={() => setExpandedId((current) => current === item.id ? null : item.id)}
                aria-expanded={isExpanded}
                className="flex w-full items-start gap-3 px-3.5 py-3 text-left"
              >
                <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-current/10">
                  {item.severity === 'opportunity' ? <TrendingUp size={15} /> : <AlertTriangle size={15} />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-xs font-extrabold text-[var(--text-primary)]">{item.title}</span>
                  <span className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] font-semibold text-[var(--text-muted)]">
                    <TrendIcon size={11} />
                    {item.trend_label}
                    {item.impact_points !== null && (
                      <strong className={positive ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'}>
                        {item.impact_points > 0 ? '+' : ''}{item.impact_points.toFixed(1)}%
                      </strong>
                    )}
                  </span>
                </span>
                <span className="hidden shrink-0 rounded-md bg-current/10 px-2 py-1 text-[9px] font-extrabold uppercase sm:inline-flex">
                  {severityLabel[item.severity]}
                </span>
                {isExpanded ? <ChevronUp size={14} className="mt-1 shrink-0" /> : <ChevronDown size={14} className="mt-1 shrink-0" />}
              </button>
              {isExpanded && (
                <div className="border-t border-current/10 px-4 py-3 text-[11px] font-medium leading-relaxed text-[var(--text-secondary)]">
                  <p>{item.explanation}</p>
                  <p className="mt-2 font-bold text-violet-700 dark:text-violet-300">Recommended focus: {item.detail.recommended_focus}</p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {recommendations.length > 0 && (
        <div className="mt-3 flex flex-col gap-2 rounded-xl border border-violet-500/15 bg-violet-500/[0.055] p-3">
          <span className="text-[10px] font-extrabold text-violet-700 dark:text-violet-300">Recommended focus</span>
          <div className="flex flex-wrap gap-2">
            {recommendations.map((recommendation) => (
              <span key={recommendation} className="rounded-md border border-violet-500/20 bg-[var(--bg-surface)] px-2.5 py-1 text-[9px] font-bold text-violet-700 dark:text-violet-300">
                {recommendation}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};

export default TeamPerformanceAnalysis;
