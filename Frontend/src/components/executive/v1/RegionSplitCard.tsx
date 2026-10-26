import { Globe } from 'lucide-react';
import { getGradeTone } from '../../../constants/grades';
import type { ExecutiveRegion, ExecutivePeriod, ExecutiveRangeBlock } from '../../../features/executive/types';
import { arrow, fmtScore, fmtSigned, scoreTone } from '../../../features/executive/format';
import { formatShare } from './execModel';
import { coveredPeriodLabel, vsLabel } from '../../../features/executive/periodLabels';
import { ExecCard, ExecCardHeader, GradePill, ScoreText, SoftEmpty, StatLabel, ToneText } from './ExecPrimitives';

export default function RegionSplitCard({ regions, previous, range = null }: { regions: ExecutiveRegion[]; previous: ExecutivePeriod | null; range?: ExecutiveRangeBlock | null }) {
  const vs = vsLabel(previous, range, 'vs last');
  const rangeText = range ? ` · ${coveredPeriodLabel(null, range)}` : '';
  const share = [...regions].filter((region) => region.gap_share_percent !== null).sort((l, r) => (r.gap_share_percent ?? 0) - (l.gap_share_percent ?? 0))[0];
  return (
    <ExecCard aria-labelledby="exec-regions-title">
      <ExecCardHeader titleId="exec-regions-title" icon={Globe} iconBg="var(--exec-info-bg)" iconColor="var(--exec-info-text)" title="Region split" subtitle={`${regions.map((region) => region.region).join(' vs ') || 'Regions'} · people average, ranked by share of the gap${rangeText}`} />
      {regions.length ? (
        <div className="flex flex-col gap-[12px]">
          {regions.map((region) => {
            const tone = getGradeTone(region.score);
            return (
              <div key={region.region} className="flex flex-col gap-[10px] rounded-[10px] bg-[var(--exec-tile-bg)] p-[14px]" data-testid="region-box">
                <div className="flex flex-wrap items-center gap-[8px]">
                  <span className="rounded-[5px] bg-[var(--exec-info-bg)] px-[6px] py-px text-xs font-bold text-[var(--exec-info-text)]">{region.region}</span>
                  <span className="flex-1 text-[13px] font-semibold text-[var(--insights-heading)]">{region.label}</span>
                  <GradePill score={region.score} />
                </div>
                <div className="flex flex-wrap items-end gap-x-[16px] gap-y-[4px]">
                  <ScoreText score={region.score} className="text-[24px]">{fmtScore(region.score)}</ScoreText>
                  <div className="flex flex-col gap-[2px]">
                    <StatLabel>vs 100</StatLabel>
                    <ToneText tone={region.gap !== null && region.gap < 0 ? 'bad' : 'good'} className="text-[12px] font-bold">{arrow(region.gap)} {fmtSigned(region.gap)}</ToneText>
                  </div>
                  <div className="flex flex-col gap-[2px]">
                    <StatLabel>{vs}</StatLabel>
                    <ToneText tone={scoreTone(region.change)} className="text-[12px] font-bold">{arrow(region.change)} {fmtSigned(region.change)}</ToneText>
                  </div>
                </div>
                <div aria-hidden="true" className="h-[8px] w-full rounded-full bg-[var(--insights-track)]">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.max(0, region.score ?? 0))}%`, background: tone.solid }} />
                </div>
                <span className="text-xs text-[var(--text-muted)]">
                  {region.employees} employees · {region.teams_count} teams
                  {region.gap_share_percent != null ? ` · ${formatShare(region.gap_share_percent)}% of the gap` : ''}
                  {region.headcount_share_percent != null ? ` · ${Math.round(region.headcount_share_percent)}% of people` : ''}
                </span>
              </div>
            );
          })}
        </div>
      ) : <SoftEmpty>No regional data for this scope.</SoftEmpty>}
      {share && regions.length > 1 && share.headcount_share_percent !== null && (
        <p className="text-xs text-[var(--text-muted)]">
          {share.region} gap share: {Math.round(share.gap_share_percent ?? 0)}% of the company gap from {Math.round(share.headcount_share_percent)}% of headcount.
        </p>
      )}
    </ExecCard>
  );
}
