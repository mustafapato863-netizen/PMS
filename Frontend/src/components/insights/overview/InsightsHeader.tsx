import type { ReactNode } from 'react';
import { Calendar, Layers } from 'lucide-react';
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
}) {
  const dropdownOptions = [...(allLabel ? [{ value: '', label: allLabel }] : []), ...options];
  return (
    <div className={`flex min-w-0 flex-col items-start gap-[4px] ${widthClass}`}>
      <div className="flex items-center gap-[6px]" aria-hidden="true">
        <span className={`text-[10px] font-semibold uppercase leading-normal tracking-[0.6px] ${primary ? 'text-[var(--insights-accent-text)]' : 'text-[var(--text-muted)]'}`}>{label}</span>
        {primary && <span className="rounded-full bg-[var(--insights-accent-tag)] px-[6px] py-px text-[9px] font-semibold leading-normal text-[var(--insights-accent-text)]">Primary</span>}
      </div>
      <CustomDropdown
        ariaLabel={ariaLabel}
        value={value}
        options={dropdownOptions}
        onChange={(next) => onChange(String(next))}
        icon={icon}
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
}) {
  return (
    <header className="flex flex-col gap-[16px] pb-[4px] xl:flex-row xl:items-end">
      <div className="flex min-w-0 flex-1 flex-col gap-[4px] leading-normal">
        <h1 className="text-[32px] font-bold leading-normal tracking-[-0.48px] text-[var(--insights-heading)]">Insights</h1>
        <p className="text-[14px] font-normal text-[var(--text-secondary)]">Understand what happened, why it happened, and what to do next.</p>
      </div>
      <div className="flex flex-wrap items-end gap-[10px]" role="group" aria-label="Insights filters">
        <LabeledFilter
          label="Date"
          ariaLabel="Insight period"
          value={period}
          options={periodOptions}
          onChange={onPeriodChange}
          widthClass="w-[140px]"
          icon={<Calendar className="size-[16px] text-[var(--text-secondary)]" strokeWidth={1.5} />}
        />
        <LabeledFilter label="Regions" ariaLabel="Region" value={region} options={regionOptions} allLabel="All regions" onChange={onRegionChange} widthClass="w-[136px]" />
        <LabeledFilter
          primary
          label="Functions"
          ariaLabel="Function"
          value={functionValue}
          options={functionOptions}
          allLabel="All functions"
          onChange={onFunctionChange}
          widthClass="w-[168px]"
          icon={<Layers className="size-[16px] text-[var(--insights-accent)]" strokeWidth={1.5} />}
        />
        <LabeledFilter label="Teams" ariaLabel="Team" value={team} options={teamOptions} allLabel="All teams" onChange={onTeamChange} widthClass="w-[168px]" />
        <LabeledFilter label="Levels" ariaLabel="Performance level" value={level} options={levelOptions} allLabel="All levels" onChange={onLevelChange} widthClass="w-[132px]" />
      </div>
    </header>
  );
}
