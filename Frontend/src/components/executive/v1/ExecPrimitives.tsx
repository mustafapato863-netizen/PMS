/**
 * Executive v1 building blocks (Figma 44:2). Surfaces reuse the Insights
 * tokens; scores only ever use the --pms-grade-* palette (95/90/80/70).
 */
import type { ReactNode } from 'react';
import { ArrowRight, Info, type LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { getGradeClassOrNull, getGradeTone } from '../../../constants/grades';
import { isLowerBetter, toneColor, type Tone } from '../../../features/executive/format';

export function ExecCard({ children, className = '', as: Tag = 'section', ...rest }: { children: ReactNode; className?: string; as?: 'section' | 'div' | 'article'; 'aria-label'?: string; 'aria-labelledby'?: string; 'data-testid'?: string }) {
  return (
    <Tag
      {...rest}
      className={`flex min-w-0 flex-col gap-[16px] rounded-[12px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[20px] py-[18px] shadow-[var(--exec-card-shadow)] ${className}`}
    >
      {children}
    </Tag>
  );
}

export function ExecCardHeader({ icon: Icon, iconBg, iconColor, title, subtitle, action, titleId }: {
  icon: LucideIcon; iconBg: string; iconColor: string; title: ReactNode; subtitle?: ReactNode; action?: ReactNode; titleId?: string;
}) {
  return (
    <div className="flex w-full flex-wrap items-center gap-[10px]">
      <span aria-hidden="true" className="flex size-[30px] shrink-0 items-center justify-center rounded-[8px]" style={{ background: iconBg }}>
        <Icon className="size-[17px]" style={{ color: iconColor }} strokeWidth={1.75} />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
        <h2 id={titleId} className="text-[15px] font-semibold leading-normal text-[var(--insights-heading)]">{title}</h2>
        {subtitle && <p className="text-[12px] leading-normal text-[var(--text-muted)]">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

const softButton = 'inline-flex shrink-0 items-center gap-[4px] rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)] transition-colors hover:bg-[var(--insights-accent-tag)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)]';

export function SoftLink({ to, children, ariaLabel }: { to: string; children: ReactNode; ariaLabel?: string }) {
  return (
    <Link to={to} aria-label={ariaLabel} className={softButton}>
      {children}
      <ArrowRight aria-hidden="true" className="size-[13px]" strokeWidth={2} />
    </Link>
  );
}

export function SoftButton({ onClick, children, icon: Icon, disabled, title }: { onClick?: () => void; children: ReactNode; icon?: LucideIcon; disabled?: boolean; title?: string }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title} className={`${softButton} disabled:cursor-not-allowed disabled:opacity-55`}>
      {Icon && <Icon aria-hidden="true" className="size-[13px]" strokeWidth={2} />}
      {children}
    </button>
  );
}

export function GradePill({ score, className = '' }: { score: number | null | undefined; className?: string }) {
  const grade = getGradeClassOrNull(score ?? null);
  const tone = getGradeTone(score ?? null);
  return (
    <span
      data-grade={grade ?? 'na'}
      className={`inline-flex shrink-0 items-center rounded-full px-[8px] py-[2px] text-[11px] font-bold leading-normal ${className}`}
      style={{ background: tone.badgeBg, color: tone.badgeText }}
    >
      {grade ? `Grade ${grade}` : 'No grade'}
    </span>
  );
}

export function GradeSquare({ score }: { score: number | null | undefined }) {
  const grade = getGradeClassOrNull(score ?? null);
  const tone = getGradeTone(score ?? null);
  return (
    <span aria-label={grade ? `Grade ${grade}` : 'No grade'} className="inline-flex size-[24px] shrink-0 items-center justify-center rounded-[6px] text-[12px] font-bold" style={{ background: tone.badgeBg, color: tone.badgeText }}>
      {grade ?? '–'}
    </span>
  );
}

export function ScoreText({ score, className = 'text-[26px]', children }: { score: number | null | undefined; className?: string; children: ReactNode }) {
  return <span className={`font-bold leading-[1.1] ${className}`} style={{ color: getGradeTone(score ?? null).text }}>{children}</span>;
}

export function StatLabel({ children, icon: Icon }: { children: ReactNode; icon?: LucideIcon }) {
  return (
    <span className="inline-flex items-center gap-[5px] text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]">
      {Icon && <Icon aria-hidden="true" className="size-[14px]" strokeWidth={1.75} />}
      {children}
    </span>
  );
}

export function ToneText({ tone, children, className = 'text-[13px] font-bold' }: { tone: Tone; children: ReactNode; className?: string }) {
  return <span data-tone={tone} className={className} style={{ color: toneColor(tone) }}>{children}</span>;
}

export function Chip({ icon: Icon, children }: { icon?: LucideIcon; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-[5px] rounded-full bg-[var(--exec-chip-bg)] px-[10px] py-[4px] text-[11px] font-semibold text-[var(--exec-chip-text)]">
      {Icon && <Icon aria-hidden="true" className="size-[11px]" strokeWidth={2} />}
      {children}
    </span>
  );
}

/** ↑ better / ↓ better tag (KPI direction; #15 `direction` / `kpi_direction`). */
export function DirectionTag({ direction }: { direction: string | null | undefined }) {
  if (!direction) return null;
  const lower = isLowerBetter(direction);
  return (
    <span
      data-direction={lower ? 'lower_better' : 'higher_better'}
      className="inline-flex shrink-0 items-center rounded-[4px] px-[5px] py-px text-[10px] font-semibold leading-normal"
      style={{ background: lower ? 'var(--exec-dir-lower-bg)' : 'var(--exec-dir-higher-bg)', color: lower ? 'var(--exec-dir-lower-text)' : 'var(--exec-dir-higher-text)' }}
    >
      {lower ? '↓ better' : '↑ better'}
    </span>
  );
}

export function StatusPill({ tone, icon: Icon, children }: { tone: 'danger' | 'warning' | 'info' | 'success' | 'neutral'; icon?: LucideIcon; children: ReactNode }) {
  const palette = {
    danger: ['var(--exec-neg-bg)', 'var(--exec-neg-text)'],
    warning: ['var(--exec-warning-bg)', 'var(--exec-warning-text)'],
    info: ['var(--exec-info-bg)', 'var(--exec-info-text)'],
    success: ['var(--exec-pos-bg)', 'var(--exec-pos-text)'],
    neutral: ['var(--exec-chip-bg)', 'var(--exec-chip-text)'],
  }[tone];
  return (
    <span className="inline-flex shrink-0 items-center gap-[4px] rounded-full px-[8px] py-[2px] text-[11px] font-semibold leading-normal" style={{ background: palette[0], color: palette[1] }}>
      {Icon && <Icon aria-hidden="true" className="size-[11px]" strokeWidth={2} />}
      {children}
    </span>
  );
}

export function Footnote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-[6px] text-[11px] leading-[1.45] text-[var(--text-muted)]">
      <Info aria-hidden="true" className="mt-px size-[12px] shrink-0" strokeWidth={1.75} />
      <span>{children}</span>
    </p>
  );
}

export function SoftEmpty({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-[8px] rounded-[10px] border border-dashed border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] px-[14px] py-[12px] text-[12px] text-[var(--text-muted)]">
      <Info aria-hidden="true" className="size-[14px] shrink-0" strokeWidth={1.75} />
      <span>{children}</span>
    </div>
  );
}


/** Tiny trend line (function cards, team rows). */
export function Sparkline({
  values,
  height = 34,
  width = 120,
  className = '',
  label,
  latestValue,
  latestValueLabel,
  pointLabels,
}: {
  values: Array<number | null>;
  height?: number;
  width?: number;
  className?: string;
  label?: string;
  latestValue?: number | null;
  latestValueLabel?: string;
  pointLabels?: string[];
}) {
  const hasLatestValue = typeof latestValue === 'number' && Number.isFinite(latestValue) && Boolean(latestValueLabel);
  const points = values
    .map((value, index) => ({ value, index }))
    .filter((point): point is { value: number; index: number } => typeof point.value === 'number' && Number.isFinite(point.value));
  if (!points.length) return <div aria-hidden="true" style={{ height }} className={className} />;

  const min = Math.min(...points.map((point) => point.value));
  const max = Math.max(...points.map((point) => point.value));
  const center = (max + min) / 2;
  const span = Math.max(max - min, 4);
  const domainMin = center - span / 2;
  const domainMax = center + span / 2;
  const plotLeft = 5;
  const plotRight = width - (hasLatestValue ? 72 : 5);
  const step = (plotRight - plotLeft) / Math.max(values.length - 1, 1);
  const top = 6;
  const bottom = height - 6;
  const y = (value: number) => top + (bottom - top) * (1 - (value - domainMin) / (domainMax - domainMin));
  const chartPoints = points.map((point) => ({
    ...point,
    x: plotLeft + point.index * step,
    y: y(point.value),
  }));
  const last = chartPoints[chartPoints.length - 1];
  const first = chartPoints[0];
  const curve = chartPoints.reduce((path, point, index) => {
    if (index === 0) return `M${point.x.toFixed(1)},${point.y.toFixed(1)}`;
    const previous = chartPoints[index - 1];
    const before = chartPoints[index - 2] ?? previous;
    const after = chartPoints[index + 1] ?? point;
    const control1X = previous.x + (point.x - before.x) / 6;
    const control1Y = Math.max(top, Math.min(bottom, previous.y + (point.y - before.y) / 6));
    const control2X = point.x - (after.x - previous.x) / 6;
    const control2Y = Math.max(top, Math.min(bottom, point.y - (after.y - previous.y) / 6));
    return `${path} C${control1X.toFixed(1)},${control1Y.toFixed(1)} ${control2X.toFixed(1)},${control2Y.toFixed(1)} ${point.x.toFixed(1)},${point.y.toFixed(1)}`;
  }, '');
  const area = chartPoints.length > 1 ? `${curve} L${last.x.toFixed(1)},${bottom} L${first.x.toFixed(1)},${bottom} Z` : '';
  const delta = chartPoints.length > 1 ? last.value - chartPoints[chartPoints.length - 2].value : 0;
  const color = delta < -0.05 ? 'var(--insights-negative)' : delta > 0.05 ? 'var(--insights-positive)' : 'var(--insights-accent)';
  const latestTone = getGradeTone(latestValue);
  const accessibleLabel = label
    ? `${label}${hasLatestValue ? `, latest score ${latestValueLabel}` : ''}`
    : undefined;
  const badgeTop = Math.max(13, Math.min(height - 13, last.y));

  return (
    <div className={`relative w-full ${className}`} style={{ height }}>
      <svg
        role={accessibleLabel ? 'img' : undefined}
        aria-label={accessibleLabel}
        aria-hidden={accessibleLabel ? undefined : true}
        data-testid="sparkline-chart"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="absolute inset-0 block size-full overflow-visible"
      >
        <line x1={plotLeft} y1={bottom} x2={plotRight} y2={bottom} stroke="var(--insights-row-border)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        {area && <path d={area} fill={color} opacity="0.08" />}
        {chartPoints.length > 1 && (
          <path data-testid="sparkline-line" d={curve} fill="none" stroke={color} strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
        )}
        {chartPoints.map((point) => (
          <circle
            key={`${point.index}-${point.value}`}
            cx={point.x}
            cy={point.y}
            r={point.index === last.index ? 3.5 : 2}
            fill={point.index === last.index ? 'var(--bg-surface)' : color}
            stroke={color}
            strokeWidth={point.index === last.index ? 2 : 0}
            vectorEffect="non-scaling-stroke"
          >
            {pointLabels?.[point.index] && <title>{pointLabels[point.index]}</title>}
          </circle>
        ))}
      </svg>
      {hasLatestValue && (
        <span
          aria-hidden="true"
          data-testid="sparkline-latest-score"
          className="pointer-events-none absolute z-[1] -translate-y-1/2 whitespace-nowrap rounded-full border px-[8px] py-[4px] text-[10px] font-bold leading-none shadow-sm"
          style={{
            left: `${(last.x / width) * 100}%`,
            top: `${(badgeTop / height) * 100}%`,
            transform: 'translate(6px, -50%)',
            background: latestTone.badgeBg,
            borderColor: latestTone.border,
            color: latestTone.badgeText,
          }}
        >
          {latestValueLabel}
        </span>
      )}
    </div>
  );
}
