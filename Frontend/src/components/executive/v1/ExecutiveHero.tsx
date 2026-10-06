import { Activity, Calendar, Layers, Upload, Users, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { getGradeTone } from '../../../constants/grades';
import type { ExecutiveSummary } from '../../../features/executive/types';
import { arrow, fmtDate, fmtScore, fmtSigned, scoreTone, toneColor } from '../../../features/executive/format';
import { formatPeriod } from '../../../features/executive/compose';
import { Chip, GradePill } from './ExecPrimitives';
import ScoreTrendChart from './ScoreTrendChart';
import { heroHeadline, heroNarrative } from './execModel';

function Stat({ label, value, valueColor, sub, subColor }: { label: string; value: ReactNode; valueColor: string; sub: ReactNode; subColor?: string }) {
  return (
    <div className="flex min-w-[88px] flex-col gap-[4px]">
      <span className="text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]">{label}</span>
      <span className="text-[26px] font-bold leading-[1.1]" style={{ color: valueColor }}>{value}</span>
      <span className="text-[11px] font-medium" style={{ color: subColor ?? 'var(--text-muted)' }}>{sub}</span>
    </div>
  );
}

const Divider = () => <span aria-hidden="true" className="hidden h-[44px] w-px self-center bg-[var(--exec-card-border)] sm:block" />;

const EYEBROW: Record<ExecutiveSummary['scope']['view'], { label: string; icon: LucideIcon }> = {
  corporate: { label: 'Company performance', icon: Activity },
  managerial: { label: 'Team performance', icon: Users },
  function: { label: 'Function performance', icon: Layers },
};



export default function ExecutiveHero({ summary }: { summary: ExecutiveSummary }) {
  const { hero, period, trend, scope, data_status: status, meta } = summary;
  const tone = getGradeTone(hero.score);
  const eyebrow = EYEBROW[scope.view];
  const EyebrowIcon = eyebrow.icon;
  const narrative = heroNarrative(summary);
  const changeTone = scoreTone(hero.change);
  const previousLabel = period.previous ? `vs ${formatPeriod(period.previous)}` : 'vs last month';
  const comparison = hero.comparison;
  const upload = !meta.unavailable.includes('upload_meta') ? status.last_upload : null;
  const chartTitle = scope.view === 'corporate' ? 'Company score — last 6 months' : scope.view === 'managerial' ? 'Team score — last 6 months' : 'Function score — last 6 months';

  return (
    <section aria-labelledby="exec-hero-title" className="grid gap-[24px] rounded-[12px] border border-[var(--insights-summary-border)] bg-[var(--insights-summary-bg)] px-[28px] py-[24px] shadow-[var(--insights-summary-shadow)] xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-[16px]">
        <div className="flex flex-wrap items-center gap-[8px]">
          <span aria-hidden="true" className="flex size-[26px] items-center justify-center rounded-[7px] bg-[var(--insights-accent-tag)]">
            <EyebrowIcon className="size-[14px] text-[var(--insights-accent)]" strokeWidth={2} />
          </span>
          <span className="text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--insights-accent-text)]">{eyebrow.label}</span>
          <GradePill score={hero.score} />
        </div>
        <h2 id="exec-hero-title" className="text-[26px] font-bold leading-[1.3] text-[var(--insights-heading)]">{heroHeadline(summary)}</h2>
        {narrative && <p className="text-[13px] leading-[1.5] text-[var(--text-secondary)]">{narrative}</p>}
        <div className="flex flex-wrap items-start gap-x-[18px] gap-y-[12px]">
          <Stat label="Current" value={fmtScore(hero.score)} valueColor={tone.text} sub={tone.grade ? `${tone.grade} · ${tone.label}` : 'No grade'} subColor={tone.text} />
          <Divider />
          <Stat label="Target" value={fmtScore(hero.target, 1)} valueColor="var(--insights-heading)" sub={scope.view === 'corporate' ? 'Company-wide' : 'Score target'} />
          <Divider />
          <Stat label="Gap" value={fmtSigned(hero.gap)} valueColor={hero.gap !== null && hero.gap < 0 ? 'var(--insights-negative)' : 'var(--insights-positive)'} sub="score − target" />
          <Divider />
          <Stat
            label={previousLabel}
            value={fmtSigned(hero.change)}
            valueColor={toneColor(changeTone)}
            sub={hero.previous_score !== null ? `${arrow(hero.change)} ${fmtScore(hero.previous_score)} → ${fmtScore(hero.score)}` : 'No previous month'}
            subColor={toneColor(changeTone)}
          />
          {comparison && comparison.score !== null && (
            <>
              <Divider />
              <Stat
                label={`vs ${comparison.label}`}
                value={fmtSigned(comparison.difference)}
                valueColor={toneColor(scoreTone(comparison.difference))}
                sub={`${comparison.label}: ${fmtScore(comparison.score)}`}
              />
            </>
          )}
        </div>
        <div className="flex flex-wrap gap-[8px]">
          <Chip icon={Users}>{hero.employees.toLocaleString('en-US')} employees</Chip>
          {scope.view === 'corporate'
            ? <Chip icon={Layers}>{hero.functions_count} functions · {hero.teams_count} teams</Chip>
            : scope.view === 'function' ? <Chip icon={Layers}>{hero.teams_count} teams</Chip> : null}
          {upload
            ? <Chip icon={Upload}>Data uploaded {fmtDate(upload.uploaded_at)}</Chip>
            : <Chip icon={Calendar}>{formatPeriod(period.effective)} data</Chip>}
        </div>
      </div>
      <ScoreTrendChart points={trend} title={chartTitle} comparisonLabel={comparison?.label ?? null} />
    </section>
  );
}
