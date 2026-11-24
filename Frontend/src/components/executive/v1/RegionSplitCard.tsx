import { Globe } from 'lucide-react';
import type { ExecutiveRegion, ExecutivePeriod, ExecutiveRangeBlock } from '../../../features/executive/types';
import { arrow, fmtScore, fmtSigned, scoreTone } from '../../../features/executive/format';
import { formatShare } from './execModel';
import { coveredPeriodLabel, vsLabel } from '../../../features/executive/periodLabels';
import { ExecCard, ExecCardHeader, GradePill, ScoreText, SoftEmpty, ToneText } from './ExecPrimitives';
import { gradeGradientVar } from './gradeGradient';

export default function RegionSplitCard({
  regions,
  previous,
  range = null,
  embedded = false,
}: {
  regions: ExecutiveRegion[];
  previous: ExecutivePeriod | null;
  range?: ExecutiveRangeBlock | null;
  /** Render inline inside a parent ExecCard (Figma Corporate Row 4 unified right card). */
  embedded?: boolean;
}) {
  const vs = vsLabel(previous, range, 'vs last');
  const rangeText = range ? ` · ${coveredPeriodLabel(null, range)}` : '';
  const share = [...regions]
    .filter((region) => region.gap_share_percent !== null)
    .sort((l, r) => (r.gap_share_percent ?? 0) - (l.gap_share_percent ?? 0))[0];

  const body = (
    <>
      <ExecCardHeader
        titleId="exec-regions-title"
        icon={Globe}
        iconBg="var(--exec-info-bg)"
        iconColor="var(--exec-info-text)"
        title="Region split"
        subtitle={`${regions.map((region) => region.region).join(' vs ') || 'Regions'} · people average, ranked by share of the gap${rangeText}`}
      />
      {regions.length ? (
        <div className="flex flex-col gap-[10px]">
          {regions.map((region) => (
            <div
              key={region.region}
              className="pms-glass-stage flex flex-col gap-[7px] rounded-[12px] px-[14px] py-[11px]"
              data-testid="region-box"
            >
              {/* Line 1: Region badge + label on left, score + GradePill on right */}
              <div className="flex flex-wrap items-center justify-between gap-[8px]">
                <div className="flex min-w-0 items-center gap-[8px]">
                  <span
                    className="shrink-0 rounded-[6px] px-[7px] py-[2px] text-[12px] font-bold text-[var(--exec-info-text)]"
                    style={{ background: 'var(--exec-info-bg)' }}
                  >
                    {region.region}
                  </span>
                  <span className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">
                    {region.label}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-[8px]">
                  <ScoreText score={region.score} className="text-[18px] tabular-nums">
                    {fmtScore(region.score)}
                  </ScoreText>
                  <GradePill score={region.score} className="!px-[7px] !py-[1px]" />
                </div>
              </div>

              {/* Line 2: Smooth grade-gradient bar */}
              <div aria-hidden="true" className="h-[6px] w-full overflow-hidden rounded-full bg-[var(--insights-track)]">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${Math.min(100, Math.max(0, region.score ?? 0))}%`, background: gradeGradientVar(region.score) }}
                />
              </div>

              {/* Line 3: Compact metadata + vs 100 / vs prev trend */}
              <div className="flex flex-wrap items-center justify-between gap-x-[12px] gap-y-[3px] text-[12px]">
                <span className="text-[var(--text-muted)]">
                  {region.employees} {region.employees === 1 ? 'person' : 'people'} · {region.teams_count} {region.teams_count === 1 ? 'team' : 'teams'}
                  {region.gap_share_percent != null ? ` · ${formatShare(region.gap_share_percent)}% of the gap` : ''}
                  {region.headcount_share_percent != null ? ` · ${Math.round(region.headcount_share_percent)}% of people` : ''}
                </span>
                <div className="flex shrink-0 items-center gap-[10px] tabular-nums">
                  <ToneText tone={region.gap !== null && region.gap < 0 ? 'bad' : 'good'} className="text-[12px] font-bold">
                    {arrow(region.gap)} {fmtSigned(region.gap)} vs 100
                  </ToneText>
                  <ToneText tone={scoreTone(region.change)} className="text-[12px] font-bold">
                    {arrow(region.change)} {fmtSigned(region.change)} {vs}
                  </ToneText>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <SoftEmpty>No regional data for this scope.</SoftEmpty>
      )}
      {share && regions.length > 1 && share.headcount_share_percent !== null && (
        <p className="text-[12px] text-[var(--text-muted)]">
          {share.region} gap share: {Math.round(share.gap_share_percent ?? 0)}% of the company gap from {Math.round(share.headcount_share_percent)}% of headcount.
        </p>
      )}
    </>
  );

  if (embedded) {
    return (
      <section aria-labelledby="exec-regions-title" className="flex min-w-0 flex-col gap-[12px]">
        {body}
      </section>
    );
  }

  return <ExecCard aria-labelledby="exec-regions-title">{body}</ExecCard>;
}
