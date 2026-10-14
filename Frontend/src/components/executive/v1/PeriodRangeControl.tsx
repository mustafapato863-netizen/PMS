import { Calendar } from 'lucide-react';
import CustomDropdown from '../../common/CustomDropdown';
import type { FilterOption } from '../../insights/overview/InsightsHeader';
import { presetIdFor, rangePresets, type RangePresetId, type RangeSelection } from '../../../features/executive/rangeParams';

export type PeriodMode = 'month' | 'range';

/**
 * Month (default) or Range. A range has presets and a From / To pair; only months in the catalog can be picked,
 * and From can never be after To.
 */
export default function PeriodRangeControl({
  mode, onModeChange, period, periodOptions, onPeriodChange, periodAriaLabel, selection, catalogKeys, onSelectionChange,
}: {
  mode: PeriodMode;
  onModeChange: (mode: PeriodMode) => void;
  /** Month mode: the selected month (YYYY-MM) and its choices. */
  period: string;
  periodOptions: FilterOption[];
  onPeriodChange: (value: string) => void;
  periodAriaLabel?: string;
  /** Range mode: the range in the URL, if any. */
  selection: RangeSelection | null;
  /** Months that exist in the catalog, YYYY-MM, ascending. */
  catalogKeys: string[];
  onSelectionChange: (selection: RangeSelection) => void;
}) {
  const anchor = mode === 'range' && selection ? selection.to : period;
  const presets = rangePresets(anchor);
  const activePreset: RangePresetId | null = selection ? presetIdFor(selection, anchor) : null;
  const from = selection?.from ?? '';
  const to = selection?.to ?? '';
  const fromChoices = catalogKeys.filter((key) => !to || key <= to);
  const toChoices = catalogKeys.filter((key) => !from || key >= from);

  const choose = (next: RangeSelection) => onSelectionChange(next);
  const switchToRange = () => {
    onModeChange('range');
    const preset = rangePresets(period).find((item) => item.id === 'last3');
    if (preset) choose(preset.selection);
  };

  return (
    <div className="flex min-w-0 flex-col gap-[8px]" data-testid="period-range-control">
      <div role="group" aria-label="Period mode" className="inline-flex w-fit overflow-hidden rounded-[8px] border border-[var(--border-medium)] text-[12px] font-semibold">
        <button type="button" aria-pressed={mode === 'month'} onClick={() => onModeChange('month')}
          className={`px-[10px] py-[6px] ${mode === 'month' ? 'bg-[var(--insights-accent-soft)] text-[var(--insights-accent-text)]' : 'text-[var(--text-secondary)]'}`}>Month</button>
        <button type="button" aria-pressed={mode === 'range'} onClick={switchToRange}
          className={`px-[10px] py-[6px] ${mode === 'range' ? 'bg-[var(--insights-accent-soft)] text-[var(--insights-accent-text)]' : 'text-[var(--text-secondary)]'}`}>Range</button>
      </div>

      {mode === 'month' ? (
        <div className="flex min-w-0 items-center gap-[8px]">
          <Calendar aria-hidden="true" className="size-[16px] text-[var(--text-secondary)]" strokeWidth={1.5} />
          <CustomDropdown ariaLabel={periodAriaLabel} value={period} options={periodOptions} onChange={(next) => onPeriodChange(String(next))} className="w-[140px]" />
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-[6px]">
            {presets.map((preset) => (
              <button key={preset.id} type="button" aria-pressed={activePreset === preset.id} onClick={() => choose(preset.selection)}
                className={`rounded-full border px-[10px] py-[4px] text-[12px] font-semibold ${activePreset === preset.id ? 'border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] text-[var(--insights-accent-text)]' : 'border-[var(--border-medium)] text-[var(--text-secondary)]'}`}>
                {preset.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-[8px] text-[12px] text-[var(--text-secondary)]">
            <label className="flex items-center gap-[6px]">From
              <select aria-label="From month" value={from} onChange={(event) => choose({ from: event.target.value, to: to || event.target.value })}
                className="rounded-[8px] border border-[var(--border-medium)] bg-[var(--bg-surface)] px-[8px] py-[5px] text-[12px] text-[var(--text-primary)]">
                {fromChoices.map((key) => <option key={key} value={key}>{key}</option>)}
              </select>
            </label>
            <label className="flex items-center gap-[6px]">To
              <select aria-label="To month" value={to} onChange={(event) => choose({ from: from || event.target.value, to: event.target.value })}
                className="rounded-[8px] border border-[var(--border-medium)] bg-[var(--bg-surface)] px-[8px] py-[5px] text-[12px] text-[var(--text-primary)]">
                {toChoices.map((key) => <option key={key} value={key}>{key}</option>)}
              </select>
            </label>
          </div>
        </>
      )}
    </div>
  );
}
