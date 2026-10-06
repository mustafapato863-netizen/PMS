import type { ReactNode } from 'react';
import { Calendar, Layers, Lock } from 'lucide-react';
import CustomDropdown from '../../common/CustomDropdown';

export interface FilterOption {
  value: string;
  label: string;
}

function LabeledFilter({
  label,
  ariaLabel,
  value,
  options,
  allLabel,
  onChange,
  widthClass,
  icon,
  primary = false,
  menuMinWidth,
  locked = false,
}: {
  label: string;
  ariaLabel: string;
  value: string;
  options: FilterOption[];
  allLabel?: string;
  onChange: (value: string) => void;
  widthClass: string;
  icon?: ReactNode;
  primary?: boolean;
  menuMinWidth?: number;
  /** Fixed by the viewer's role (Manager): shows a lock + "Scoped" and cannot be changed. */
  locked?: boolean;
}) {
  const dropdownOptions = [...(allLabel ? [{ value: '', label: allLabel }] : []), ...options];
  return (
    <div className={`flex min-w-0 flex-col items-start gap-[4px] ${widthClass}`}>
      <div className="flex items-center gap-[6px]" aria-hidden="true">
        <span className={`text-[10px] font-semibold uppercase leading-normal tracking-[0.6px] ${primary ? 'text-[var(--insights-accent-text)]' : 'text-[var(--text-muted)]'}`}>{label}</span>
        {primary && <span className="rounded-full bg-[var(--insights-accent-tag)] px-[6px] py-px text-[9px] font-semibold leading-normal text-[var(--insights-accent-text)]">Primary</span>}
        {locked && (
          <span className="inline-flex items-center gap-[3px] text-[9px] font-semibold leading-normal text-[var(--text-muted)]">
            <Lock className="size-[10px]" strokeWidth={2} />
            Scoped
          </span>
        )}
      </div>
      {locked ? (
        <div
          role="group"
          aria-label={`${ariaLabel}: ${dropdownOptions.find((option) => option.value === value)?.label ?? value} (fixed by your role)`}
          data-locked="true"
          className={[
            'flex h-[34px] w-full items-center gap-[8px] rounded-[8px] border pl-[12px] pr-[10px] text-[13px] font-medium',
            'bg-[var(--exec-tile-bg,var(--bg-sunken))] text-[var(--text-secondary)]',
            primary ? 'border-[1.5px] border-[var(--insights-accent)]' : 'border-[var(--insights-card-border)]',
          ].join(' ')}
        >
          {icon}
          <span className="min-w-0 flex-1 truncate">{dropdownOptions.find((option) => option.value === value)?.label ?? value}</span>
          <Lock aria-hidden="true" className="size-[13px] text-[var(--text-muted)]" strokeWidth={1.75} />
        </div>
      ) : (
      <CustomDropdown
        ariaLabel={ariaLabel}
        value={value}
        options={dropdownOptions}
        onChange={(next) => onChange(String(next))}
        icon={icon}
        menuMinWidth={menuMinWidth}
        className="w-full"
        chevronClassName={`size-[16px]! ${primary ? 'text-[var(--insights-accent-text)]!' : ''}`}
        buttonClassName={[
          'h-[34px] w-full rounded-[8px]! py-0! pl-[12px]! pr-[10px]! gap-[8px]! text-[13px]! font-medium! shadow-none!',
          'bg-[var(--bg-surface)]! text-[var(--insights-heading)]!',
          primary
            ? 'border-[1.5px]! border-[var(--insights-accent)]! shadow-[0_0_0_3px_var(--insights-accent-ring)]!'
            : 'border-[var(--insights-card-border)]!',
        ].join(' ')}
      />
      )}
    </div>
  );
}

/**
 * Figma 18:12 — title block + DATE / REGIONS / FUNCTIONS (primary) / TEAMS / LEVELS
 * filters. Options arrive already cascaded (Region → Function → Team → Level).
 */
export default function InsightsHeader({
  period,
  periodOptions,
  onPeriodChange,
  region,
  regionOptions,
  onRegionChange,
  functionValue,
  functionOptions,
  onFunctionChange,
  team,
  teamOptions,
  onTeamChange,
  level,
  levelOptions,
  onLevelChange,
  title = 'Insights',
  subtitle = 'Understand what happened, why it happened, and what to do next.',
  titleBadge,
  locked,
  functionSlot,
  teamAllLabel = 'All teams',
  groupLabel = 'Insights filters',
  periodAriaLabel = 'Insight period',
  rowFrom = 'xl',
}: {
  period: string;
  periodOptions: FilterOption[];
  onPeriodChange: (value: string) => void;
  region: string;
  regionOptions: FilterOption[];
  onRegionChange: (value: string) => void;
  functionValue: string;
  functionOptions: FilterOption[];
  onFunctionChange: (value: string) => void;
  team: string;
  teamOptions: FilterOption[];
  onTeamChange: (value: string) => void;
  level: string;
  levelOptions: FilterOption[];
  onLevelChange: (value: string) => void;
  /** Page title / subtitle (Executive + Function Summary reuse this header). */
  title?: string;
  subtitle?: ReactNode;
  titleBadge?: ReactNode;
  locked?: { region?: boolean; function?: boolean; team?: boolean };
  /** Replaces the Functions dropdown (Function Viewer's function switcher). */
  functionSlot?: ReactNode;
  /** "All" entry of the Teams filter (Function Summary: "All RCM teams"). */
  teamAllLabel?: string;
  groupLabel?: string;
  periodAriaLabel?: string;
  /** Breakpoint where title and filters share one row (longer titles need 2xl). */
  rowFrom?: 'xl' | '2xl';
}) {
  return (
    <header className={`flex flex-col gap-[16px] pb-[4px] ${rowFrom === '2xl' ? '2xl:flex-row 2xl:items-end' : 'xl:flex-row xl:items-end'}`}>
      <div className="flex min-w-0 flex-1 flex-col gap-[4px] leading-normal">
        <div className="flex flex-wrap items-center gap-[10px]">
          <h1 className="text-[32px] font-bold leading-normal tracking-[-0.48px] text-[var(--insights-heading)]">{title}</h1>
          {titleBadge}
        </div>
        <p className="text-[14px] font-normal text-[var(--text-secondary)]">{subtitle}</p>
      </div>
      <div className="flex flex-wrap items-end gap-[10px]" role="group" aria-label={groupLabel}>
        <LabeledFilter
          label="Date"
          ariaLabel={periodAriaLabel}
          value={period}
          options={periodOptions}
          onChange={onPeriodChange}
          widthClass="w-[140px]"
          icon={<Calendar className="size-[16px] text-[var(--text-secondary)]" strokeWidth={1.5} />}
        />
        <LabeledFilter label="Regions" ariaLabel="Region" value={region} options={regionOptions} allLabel="All regions" onChange={onRegionChange} widthClass="w-[136px]" locked={locked?.region} />
        {functionSlot ?? <LabeledFilter
          locked={locked?.function}
          primary
          label="Functions"
          ariaLabel="Function"
          value={functionValue}
          options={functionOptions}
          allLabel="All functions"
          onChange={onFunctionChange}
          widthClass="w-[168px]"
          icon={<Layers className="size-[16px] text-[var(--insights-accent)]" strokeWidth={1.5} />}
        />}
        <LabeledFilter label="Teams" ariaLabel="Team" value={team} options={teamOptions} allLabel={teamAllLabel} onChange={onTeamChange} widthClass="w-[168px]" menuMinWidth={260} locked={locked?.team} />
        <LabeledFilter label="Levels" ariaLabel="Performance level" value={level} options={levelOptions} allLabel="All levels" onChange={onLevelChange} widthClass="w-[132px]" />
      </div>
    </header>
  );
}
