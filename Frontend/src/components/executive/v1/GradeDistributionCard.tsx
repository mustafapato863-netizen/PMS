import { BarChart3 } from 'lucide-react';
import { GRADE_CLASSES, GRADE_PALETTE, gradeTokenVar } from '../../../constants/grades';
import { movementTone } from './execModel';
import type { ExecutiveGradeDistribution, ExecutivePeriod } from '../../../features/executive/types';
import { ExecCard, ExecCardHeader, Footnote, SoftEmpty } from './ExecPrimitives';


export default function GradeDistributionCard({ distribution, previous }: { distribution: ExecutiveGradeDistribution | null; previous: ExecutivePeriod | null }) {
  const vs = previous ? previous.month : 'last month';
  return (
    <ExecCard aria-labelledby="exec-grades-title">
      <ExecCardHeader
        titleId="exec-grades-title"
        icon={BarChart3}
        iconBg="var(--pms-grade-a-badge-bg)"
        iconColor="var(--pms-grade-a-text)"
        title="Grade distribution"
        subtitle={distribution ? `${distribution.total} employees · movement vs ${vs.slice(0, 3)}` : 'Grade mix'}
      />
      {distribution && distribution.total > 0 ? (
        <>
          <div aria-hidden="true" className="flex h-[10px] w-full overflow-hidden rounded-full bg-[var(--insights-track)]">
            {GRADE_CLASSES.map((grade) => (
              <div key={grade} style={{ width: `${distribution.percents[grade]}%`, background: gradeTokenVar(grade, 'solid') }} />
            ))}
          </div>
          <ul className="flex flex-col gap-[10px]">
            {GRADE_CLASSES.map((grade) => {
              const movement = distribution.movement?.[grade] ?? null;
              const tone = movement === null ? 'neutral' : movementTone(grade, movement);
              return (
                <li key={grade} className="flex items-center gap-[10px]" data-testid={`grade-row-${grade}`}>
                  <span className="flex size-[24px] shrink-0 items-center justify-center rounded-[6px] text-[12px] font-bold" style={{ background: gradeTokenVar(grade, 'badge-bg'), color: gradeTokenVar(grade, 'badge-text') }}>{grade}</span>
                  <div className="flex min-w-0 flex-1 flex-col gap-[4px]">
                    <div className="flex items-center gap-[8px]">
                      <span className="flex-1 truncate text-[13px] font-medium text-[var(--insights-heading)]">{GRADE_PALETTE[grade].label}</span>
                      <span className="text-[13px] font-bold text-[var(--insights-heading)]">{distribution.counts[grade]}</span>
                      <span className="w-[40px] text-right text-[11px] text-[var(--text-muted)]">{distribution.percents[grade].toFixed(1)}%</span>
                    </div>
                    <div aria-hidden="true" className="h-[6px] w-full rounded-[3px] bg-[var(--insights-track)]">
                      <div className="h-full rounded-[3px]" style={{ width: `${distribution.percents[grade]}%`, background: gradeTokenVar(grade, 'solid') }} />
                    </div>
                  </div>
                  <span
                    data-tone={tone}
                    className="w-[36px] text-right text-[12px] font-bold"
                    style={{ color: tone === 'good' ? 'var(--insights-positive)' : tone === 'bad' ? 'var(--insights-negative)' : 'var(--text-muted)' }}
                  >
                    {movement === null ? '—' : movement === 0 ? '0' : `${movement > 0 ? '▲' : '▼'} ${movement > 0 ? '+' : '\u2212'}${Math.abs(movement)}`}
                  </span>
                </li>
              );
            })}
          </ul>
          <Footnote>▲/▼ = headcount change vs {vs}. Green = healthier mix. Grades use the 95 / 90 / 80 / 70 cut-offs.</Footnote>
        </>
      ) : <SoftEmpty>No graded employees for this scope.</SoftEmpty>}
    </ExecCard>
  );
}
