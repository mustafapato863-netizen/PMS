import { AlertTriangle, BarChart3, Database, FileText } from 'lucide-react';
import type { ManagementAnalysisTableData, ScoreMovementBridgeData, StoryBlockData, StoryReportBlock } from '../../../features/reports/types';
import { InlineLoadingBadge } from '../../common/SkeletonLoader';

const titleCase = (value: string) => value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const display = (value: unknown) => value === null || value === undefined || value === '' ? 'N/A' : typeof value === 'number' ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value);

const tone = (value: number | null | undefined) => (value || 0) < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-700 dark:text-emerald-400';
const points = (value: number | null | undefined) => value === null || value === undefined ? 'N/A' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;

function MovementBridge({ data }: { data: ScoreMovementBridgeData }) {
  const effects = [
    ...data.kpi_contribution_movements.map((item) => ({ label: item.label, value: item.score_point_change })),
    { label: 'Joiners', value: data.joiner_effect }, { label: 'Leavers', value: data.leaver_effect },
    { label: 'Scope mix', value: data.population_scope_mix_effect }, { label: 'Configuration', value: data.configuration_version_effect },
    { label: 'Incomparable data', value: data.missing_incomparable_data_effect }, { label: 'Residual', value: data.residual },
  ].filter((item) => item.value !== null && item.value !== undefined);
  const maximum = Math.max(1, ...effects.map((item) => Math.abs(Number(item.value))));
  return <div className="space-y-4">
    <div className="grid grid-cols-3 gap-2"><div className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800"><p className="text-[9px] font-bold uppercase text-slate-500">{data.comparison_period || 'Previous'}</p><p className="text-xl font-black">{display(data.previous_overall_score)}%</p></div><div className="rounded-lg bg-blue-50 p-3 text-center dark:bg-blue-950/30"><p className="text-[9px] font-bold uppercase text-blue-600">Movement</p><p className={`text-xl font-black ${tone(data.total_score_point_change)}`}>{points(data.total_score_point_change)}</p></div><div className="rounded-lg bg-slate-50 p-3 text-right dark:bg-slate-800"><p className="text-[9px] font-bold uppercase text-slate-500">{data.current_period || 'Current'}</p><p className="text-xl font-black">{display(data.current_overall_score)}%</p></div></div>
    <div className="space-y-2">{effects.slice(0, 10).map((item) => <div key={item.label} className="grid grid-cols-[120px_1fr_62px] items-center gap-2 text-[10px]"><span className="truncate font-semibold text-slate-600 dark:text-slate-300">{item.label}</span><span className="relative h-2 rounded-full bg-slate-100 dark:bg-slate-800"><span className={`absolute h-2 rounded-full ${Number(item.value) < 0 ? 'right-1/2 bg-rose-500' : 'left-1/2 bg-emerald-500'}`} style={{ width: `${Math.max(2, Math.abs(Number(item.value)) / maximum * 48)}%` }} /></span><b className={tone(Number(item.value))}>{points(Number(item.value))}</b></div>)}</div>
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 text-[10px] dark:border-slate-700"><span>{data.matched_employee_count} matched · {data.joiner_count} joiners · {data.leaver_count} leavers</span><span className={`rounded-full px-2 py-1 font-extrabold uppercase ${data.reconciliation_state === 'reconciled' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-700'}`}>{data.reconciliation_state}</span></div>
    <p className="text-xs leading-5 text-slate-600 dark:text-slate-300">{data.narrative}</p>
  </div>;
}

const MANAGEMENT_COLUMNS: Record<string, Array<[string, string]>> = {
  lowest_kpis_weighted_impact: [['rank', '#'], ['name', 'KPI'], ['team', 'Scope'], ['actual', 'Actual'], ['target', 'Target'], ['lost_points', 'Lost %']],
  lowest_employees_current_period: [['rank', '#'], ['employee', 'Employee'], ['team', 'Team'], ['current_score', 'Score'], ['weakest_scored_kpi', 'Weakest KPI'], ['weighted_lost_points', 'Lost %']],
  three_month_consecutive_low_performers: [['employee', 'Employee'], ['team', 'Team'], ['three_month_average', '3M Avg'], ['trend', 'Trend'], ['repeated_weakest_kpi', 'Repeated KPI'], ['current_action_status', 'Action']],
  applied_configuration_audit: [['severity', 'Severity'], ['issue', 'Issue'], ['scope', 'Scope'], ['kpi', 'KPI'], ['effect_on_analysis', 'Analysis effect'], ['recommended_correction', 'Correction']],
  root_cause_evidence_matrix: [['cause_title', 'Cause'], ['classification', 'Class'], ['confidence', 'Confidence'], ['scope', 'Scope'], ['linked_kpi', 'KPI'], ['impact_type', 'Evidence measure']],
};

const managementCell = (type: string, row: Record<string, unknown>, key: string) => {
  const value = display(row[key]);
  if (type === 'lowest_kpis_weighted_impact' && ['actual', 'target'].includes(key) && row[key] !== null && row[key] !== undefined) return `${value} ${display(row.unit)}`;
  if (['lost_points', 'weighted_lost_points'].includes(key) && row[key] !== null && row[key] !== undefined) return `${value}%`;
  return value;
};

function ManagementTable({ type, data, limit }: { type: string; data: ManagementAnalysisTableData; limit: number }) {
  const rows = data.rows || [];
  const columns = MANAGEMENT_COLUMNS[type] || [];
  return <div className="space-y-3"><div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700"><table className="w-full min-w-[680px] text-[10px]"><thead className="bg-slate-50 text-slate-500 dark:bg-slate-800"><tr>{columns.map(([key, label]) => <th key={key} className="px-3 py-2 text-left font-extrabold uppercase">{label}</th>)}</tr></thead><tbody>{rows.slice(0, limit).map((row, index) => <tr key={`${row.employee_id || row.key || row.code || index}`} className="border-t border-slate-100 align-top dark:border-slate-800">{columns.map(([key]) => <td key={key} className={`max-w-48 whitespace-normal px-3 py-2 font-medium leading-4 ${['lost_points', 'weighted_lost_points', 'trend'].includes(key) && Number(row[key]) < 0 ? 'text-rose-600' : 'text-slate-700 dark:text-slate-300'}`}>{managementCell(type, row, key)}</td>)}</tr>)}</tbody></table></div>
    {data.configuration_issues_excluded?.length ? <p className="rounded-lg bg-amber-50 px-3 py-2 text-[10px] font-semibold text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">{data.configuration_issues_excluded.length} configuration issue(s) excluded from ranking.</p> : null}
    {data.insufficient_history?.length ? <p className="rounded-lg bg-slate-50 px-3 py-2 text-[10px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">{data.insufficient_history.length} employee(s) have insufficient consecutive history and were not classified.</p> : null}
    {rows.length > limit ? <p className="text-[10px] font-bold text-slate-500">Showing {limit} of {rows.length}</p> : null}
  </div>;
}

const BlockLoadingState = ({ title }: { title: string }) => <div role="status" aria-label={`Loading ${title}`} aria-busy="true" className="overflow-hidden rounded-xl border border-blue-500/10 bg-gradient-to-br from-blue-50/80 via-white to-slate-50 p-4 dark:from-blue-950/25 dark:via-slate-900 dark:to-slate-900">
  <span className="sr-only">Loading {title}</span>
  <div className="mb-4 flex items-center gap-3"><span className="relative grid h-9 w-9 place-items-center rounded-xl bg-blue-600/10"><span className="absolute h-4 w-4 animate-ping rounded-full bg-blue-500/20 motion-reduce:animate-none" /><span className="h-2.5 w-2.5 rounded-full bg-blue-600" /></span><div><p className="text-xs font-extrabold text-slate-700 dark:text-slate-200">Preparing live data</p><p className="mt-0.5 text-[10px] text-slate-500">Applying scope and permissions…</p></div></div>
  <div className="space-y-2.5">{[72, 90, 58].map((width, index) => <div key={width} className="flex items-center gap-3 rounded-lg border border-slate-200/70 bg-white/80 px-3 py-2.5 dark:border-slate-700/70 dark:bg-slate-800/70"><span className="h-7 w-7 shrink-0 animate-pulse rounded-lg bg-blue-100 dark:bg-blue-900/50" /><div className="min-w-0 flex-1 space-y-1.5"><span className="block h-2.5 animate-pulse rounded-full bg-slate-200 dark:bg-slate-700" style={{ width: `${width}%`, animationDelay: `${index * 80}ms` }} /><span className="block h-2 w-2/5 animate-pulse rounded-full bg-slate-100 dark:bg-slate-800" /></div></div>)}</div>
</div>;

export default function BlockRenderer({ block, blockData, isEditing = false, onSelect }: {
  block: StoryReportBlock;
  blockData?: StoryBlockData;
  isEditing?: boolean;
  onSelect?: () => void;
}) {
  const payload = (blockData?.data || {}) as Record<string, unknown>;
  const metrics = Array.isArray(payload.metrics) ? payload.metrics as Array<Record<string, unknown>> : [];
  const rows = Array.isArray(payload.rows) ? payload.rows as Array<Record<string, unknown>> : [];
  const series = Array.isArray(payload.series) ? payload.series as Array<Record<string, unknown>> : [];
  const items = Array.isArray(payload.items) ? payload.items as Array<Record<string, unknown>> : [];
  const narrative = typeof payload.narrative === 'string' ? payload.narrative : '';
  const rowSummary = payload.row_summary && typeof payload.row_summary === 'object' ? payload.row_summary as { shown?: number; total?: number } : null;
  const noData = !blockData || blockData.state !== 'ready';
  const managementTable = Object.prototype.hasOwnProperty.call(MANAGEMENT_COLUMNS, block.type);

  return <section onClick={onSelect} className={`h-full min-h-0 overflow-auto rounded-xl border bg-white p-4 text-left shadow-sm transition dark:bg-slate-900 ${isEditing ? 'cursor-pointer hover:border-blue-400' : ''} ${blockData?.state === 'permission_denied' ? 'border-red-200' : 'border-slate-200 dark:border-slate-700'}`}>
    <div className="mb-3 flex items-center justify-between gap-3"><h4 className="truncate text-sm font-extrabold text-slate-800 dark:text-slate-100">{block.config.title || titleCase(block.type)}</h4>{blockData ? <span className="rounded-md bg-slate-100 px-2 py-1 text-[9px] font-bold uppercase tracking-wide text-slate-500 dark:bg-slate-800">{blockData.source_periods.join(' vs ') || titleCase(blockData.state)}</span> : <InlineLoadingBadge />}</div>
    {!blockData ? <BlockLoadingState title={block.config.title || titleCase(block.type)} /> : noData ? <div className="flex min-h-24 flex-col items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-center text-slate-500 dark:bg-slate-950"><Database size={20} className="mb-2" /><p className="text-xs font-bold">{titleCase(blockData.state)}</p>{blockData.warnings.map((warning) => <p key={warning} className="mt-1 text-[10px]">{warning}</p>)}</div> : block.type === 'overall_score_movement_bridge' ? <MovementBridge data={payload as unknown as ScoreMovementBridgeData} /> : managementTable ? <ManagementTable type={block.type} data={payload as unknown as ManagementAnalysisTableData} limit={block.config.row_limit} /> : <>
      {metrics.length > 0 && <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">{metrics.slice(0, 4).map((metric, index) => <div key={`${metric.label}-${index}`} className="rounded-lg bg-slate-50 p-3 dark:bg-slate-800"><p className="truncate text-[10px] font-bold uppercase text-slate-500">{display(metric.label)}</p><p className="mt-1 text-xl font-black text-slate-900 dark:text-white">{display(metric.display ?? metric.value)}</p>{Boolean(metric.change_display) && <p className={`mt-1 text-[10px] font-bold ${metric.movement === 'negative' ? 'text-red-600' : 'text-emerald-600'}`}>{display(metric.change_display)}</p>}</div>)}</div>}
      {(series.length > 0 || items.length > 0) && <div className="space-y-2">{[...series, ...items].slice(0, 8).map((item, index) => { const value = Number(item.value ?? item.impact ?? 0); const width = Math.max(3, Math.min(100, Math.abs(value))); return <div key={`${item.label}-${index}`} className="grid grid-cols-[minmax(90px,1fr)_2fr_64px] items-center gap-2 text-[10px]"><span className="truncate font-semibold text-slate-600 dark:text-slate-300">{display(item.label)}</span><span className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800"><span className={`block h-full rounded-full ${value < 0 ? 'bg-rose-500' : 'bg-emerald-500'}`} style={{ width: `${width}%` }} /></span><b className={value < 0 ? 'text-rose-600' : 'text-emerald-600'}>{display(item.display ?? value)}</b></div>; })}</div>}
      {rows.length > 0 && <div><div className="overflow-hidden rounded-lg border border-slate-100 dark:border-slate-800"><table className="w-full table-fixed text-[9px]"><thead className="bg-slate-50 text-slate-500 dark:bg-slate-800"><tr>{Object.keys(rows[0]).filter((key) => !['employee_id', 'is_below', 'validation', 'projection_assumptions'].includes(key)).slice(0, 5).map((key) => <th key={key} className="truncate px-2 py-2 text-left uppercase">{titleCase(key)}</th>)}</tr></thead><tbody>{rows.slice(0, Math.min(block.config.row_limit, 6)).map((row, rowIndex) => <tr key={rowIndex} className="border-t border-slate-100 dark:border-slate-800">{Object.keys(rows[0]).filter((key) => !['employee_id', 'is_below', 'validation', 'projection_assumptions'].includes(key)).slice(0, 5).map((key) => <td key={key} className="truncate px-2 py-2 font-medium text-slate-700 dark:text-slate-300">{display(row[key])}</td>)}</tr>)}</tbody></table></div>{rowSummary && Number(rowSummary.total || 0) > Number(rowSummary.shown || 0) && <p className="mt-2 text-[10px] font-bold text-[var(--text-muted)]">Showing {rowSummary.shown} of {rowSummary.total}</p>}</div>}
      {narrative && <div className="flex gap-3 rounded-lg bg-blue-50/70 p-3 text-xs leading-5 text-slate-700 dark:bg-blue-950/30 dark:text-slate-300"><FileText size={16} className="mt-0.5 shrink-0 text-blue-600" /><p>{narrative}</p></div>}
      {!metrics.length && !rows.length && !series.length && !items.length && !narrative && <div className="flex min-h-20 items-center justify-center text-xs text-slate-400"><BarChart3 className="mr-2" size={16} />No displayable values returned.</div>}
      {blockData?.warnings.map((warning) => <div key={warning} className="mt-2 flex gap-2 text-[10px] font-semibold text-amber-700"><AlertTriangle size={12} />{warning}</div>)}
    </>}
  </section>;
}
