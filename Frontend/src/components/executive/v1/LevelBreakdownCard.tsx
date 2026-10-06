import { Layers } from 'lucide-react';
import { getGradeTone } from '../../../constants/grades';
import type { ExecutiveLevel } from '../../../features/executive/types';
import { arrow, fmtScore, fmtSigned, scoreTone, toneColor } from '../../../features/executive/format';
import { ExecCard, ExecCardHeader, GradeSquare, ScoreText, SoftEmpty } from './ExecPrimitives';

export default function LevelBreakdownCard({ levels }: { levels: ExecutiveLevel[] }) {
  return (
    <ExecCard aria-labelledby="exec-levels-title">
      <ExecCardHeader titleId="exec-levels-title" icon={Layers} iconBg="var(--exec-info-bg)" iconColor="var(--exec-info-text)" title="Level breakdown" subtitle="Score, grade and headcount by performance level" />
      {levels.length ? (
        <ul className="flex flex-col">
          {levels.map((level) => {
            const tone = getGradeTone(level.score);
            return (
              <li key={level.level} className="flex items-center gap-[12px] border-b border-[var(--insights-row-border)] py-[10px] last:border-b-0" data-testid="level-row">
                <GradeSquare score={level.score} />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">{level.level}</span>
                  <span className="text-[11px] text-[var(--text-muted)]">{level.employees} {level.employees === 1 ? 'person' : 'people'}</span>
                </span>
                <span aria-hidden="true" className="hidden h-[6px] w-[90px] rounded-[3px] bg-[var(--insights-track)] sm:block">
                  <span className="block h-full rounded-[3px]" style={{ width: `${Math.min(100, level.score ?? 0)}%`, background: tone.solid }} />
                </span>
                <span className="flex w-[64px] flex-col items-end">
                  <ScoreText score={level.score} className="text-[13px]">{fmtScore(level.score)}</ScoreText>
                  <span className="text-[11px]" style={{ color: toneColor(scoreTone(level.change)) }}>{level.change === null ? '—' : `${arrow(level.change)} ${fmtSigned(level.change)}`}</span>
                </span>
              </li>
            );
          })}
        </ul>
      ) : <SoftEmpty>No level data for this month.</SoftEmpty>}
    </ExecCard>
  );
}
