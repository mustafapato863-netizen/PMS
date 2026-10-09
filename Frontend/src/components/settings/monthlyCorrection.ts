/**
 * Full-scope impact proof and the query prefixes already used by performance
 * and settings caches. Sample preview is not an approval proof.
 *
 * Performance prefixes cover catalog, scoped summary, records, summary records,
 * employee history, and bounded team data. Settings prefixes cover team config,
 * KPI weights, and the balanced scorecard refresh used by settings.
 *
 * Committed apply and rollback also refresh the optional executive summary,
 * the live report-center aggregate, and the insights workspace. Saved report
 * artifacts, story drafts, plans, and human-authored actions stay out of that
 * set. EmployeeProfileView reads summary records and legacy performance data.
 * useEmployeeProfile is a separate unused helper; omitting its query key is
 * not acceptance of a stale profile score.
 */

import type { QueryClient } from '@tanstack/react-query';

export const IMPACT_PAGE_SIZE = 8;

export const FIXED_MISMATCH_NOTE = 'Stored workbook targets differ from the approved fixed target. A new upload is still blocked while they differ. This historical preview does not change the workbook targets.';

export const ZERO_RECORD_NOTE = 'The draft rules were validated. No stored employees are in this month, so this is not an employee impact.';

export const ROLLBACK_CONFIRM_NOTE = 'Rollback restores the saved before-apply values for this revision. Keeping current records leaves them untouched.';

export const EVIDENCE_CHANGED_NOTE = 'Stored evidence changed. Rollback made no changes, and this month\'s records and history were left untouched.';

export type ImpactConflict = {
  recordId: string | null;
  kpiKey: string;
  workbookTarget: number | null;
  approvedTarget: number | null;
};

export type ImpactKpi = {
  kpiKey: string;
  actual: number | null;
  workbookTarget: number | null;
  appliedTarget: number | null;
  weight: number | null;
  beforeAchievement: number | null;
  afterAchievement: number | null;
  beforeContribution: number | null;
  afterContribution: number | null;
};

export type ImpactComparison = {
  recordId: string | null;
  employeeId: string | null;
  employeeCode: string | null;
  beforeScore: number | null;
  afterScore: number | null;
  beforeGrade: string | null;
  afterGrade: string | null;
  kpis: ImpactKpi[];
};

export type ImpactProof = {
  versionId: string;
  scopeId: string;
  year: number;
  month: number;
  writes: number | null;
  configValidated: boolean;
  zeroAffected: boolean;
  affectedCount: number | null;
  scoredEmployees: number | null;
  changedCount: number | null;
  unchangedCount: number | null;
  conflicts: ImpactConflict[];
  missingEvidence: unknown[];
  comparisons: ImpactComparison[];
  rulesChecksum: string | null;
  sourceFingerprint: string | null;
  proofStored: boolean;
  satisfiesApprovalGate: boolean;
};

export type ReportingSelection = {
  scopeId: string;
  year: number;
  month: number;
};

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : null;
}

function readConflict(value: unknown): ImpactConflict | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as { record_id?: unknown; kpi_key?: unknown; workbook_target?: unknown; approved_target?: unknown; fixed_target?: unknown };
  const kpiKey = text(row.kpi_key);
  if (!kpiKey) return null;
  return {
    recordId: text(row.record_id),
    kpiKey,
    workbookTarget: finiteNumber(row.workbook_target),
    approvedTarget: finiteNumber(row.approved_target) ?? finiteNumber(row.fixed_target),
  };
}

function readKpi(value: unknown): ImpactKpi | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as Record<string, unknown>;
  const kpiKey = text(row.kpi_key);
  if (!kpiKey) return null;
  return {
    kpiKey,
    actual: finiteNumber(row.actual),
    workbookTarget: finiteNumber(row.workbook_target),
    appliedTarget: finiteNumber(row.applied_target),
    weight: finiteNumber(row.weight),
    beforeAchievement: finiteNumber(row.before_achievement),
    afterAchievement: finiteNumber(row.after_achievement),
    beforeContribution: finiteNumber(row.before_contribution),
    afterContribution: finiteNumber(row.after_contribution),
  };
}

function readComparison(value: unknown): ImpactComparison | null {
  if (!value || typeof value !== 'object') return null;
  const row = value as Record<string, unknown>;
  return {
    recordId: text(row.record_id),
    employeeId: text(row.employee_id),
    employeeCode: text(row.employee_code),
    beforeScore: finiteNumber(row.before_score),
    afterScore: finiteNumber(row.after_score),
    beforeGrade: text(row.before_grade),
    afterGrade: text(row.after_grade),
    kpis: Array.isArray(row.kpis) ? row.kpis.flatMap((item) => {
      const parsed = readKpi(item);
      return parsed ? [parsed] : [];
    }) : [],
  };
}

export function parseImpactProof(data: unknown): ImpactProof | null {
  if (!data || typeof data !== 'object') return null;
  const body = data as Record<string, unknown>;
  const versionId = text(body.version_id);
  const scopeId = text(body.scope_id);
  const year = finiteNumber(body.year);
  const month = finiteNumber(body.month);
  if (!versionId || !scopeId || year == null || month == null) return null;
  return {
    versionId,
    scopeId,
    year,
    month,
    writes: finiteNumber(body.writes),
    configValidated: body.config_validated === true,
    zeroAffected: body.zero_affected === true,
    affectedCount: finiteNumber(body.affected_count),
    scoredEmployees: finiteNumber(body.scored_employees),
    changedCount: finiteNumber(body.changed_count),
    unchangedCount: finiteNumber(body.unchanged_count),
    conflicts: Array.isArray(body.conflicts) ? body.conflicts.flatMap((item) => {
      const parsed = readConflict(item);
      return parsed ? [parsed] : [];
    }) : [],
    missingEvidence: Array.isArray(body.missing_evidence) ? body.missing_evidence : [],
    comparisons: Array.isArray(body.comparisons) ? body.comparisons.flatMap((item) => {
      const parsed = readComparison(item);
      return parsed ? [parsed] : [];
    }) : [],
    rulesChecksum: text(body.rules_checksum),
    sourceFingerprint: text(body.source_fingerprint),
    proofStored: body.proof_stored === true,
    satisfiesApprovalGate: body.satisfies_approval_gate === true,
  };
}

export function proofAuthorizesApproval(proof: ImpactProof | null, versionId: string, selection: ReportingSelection): proof is ImpactProof {
  if (!proof || !versionId) return false;
  return proof.satisfiesApprovalGate
    && proof.proofStored
    && proof.configValidated
    && proof.writes === 0
    && proof.missingEvidence.length === 0
    && proof.versionId === versionId
    && proof.scopeId === selection.scopeId
    && proof.year === selection.year
    && proof.month === selection.month;
}

export function formatImpactSummary(proof: ImpactProof): string {
  if (proof.zeroAffected) return ZERO_RECORD_NOTE;
  const parts = [
    proof.affectedCount != null ? `${proof.affectedCount} stored records` : null,
    proof.scoredEmployees != null ? `${proof.scoredEmployees} scored` : null,
    proof.changedCount != null ? `${proof.changedCount} changed` : null,
    proof.unchangedCount != null ? `${proof.unchangedCount} unchanged` : null,
  ].filter((part): part is string => Boolean(part));
  return parts.length
    ? `Full-scope impact for this saved draft: ${parts.join(', ')}.`
    : 'Full-scope impact was returned without employee counts.';
}

export function displayNumber(value: number | null): string {
  return value == null ? '—' : String(value);
}

export function formatKpiLine(kpi: ImpactKpi): string {
  const parts = [kpi.kpiKey];
  if (kpi.actual != null) parts.push(`actual ${kpi.actual}`);
  if (kpi.workbookTarget != null) parts.push(`workbook target ${kpi.workbookTarget}`);
  if (kpi.appliedTarget != null) parts.push(`applied target ${kpi.appliedTarget}`);
  if (kpi.weight != null) parts.push(`weight ${kpi.weight}`);
  if (kpi.beforeAchievement != null) parts.push(`before achievement ${kpi.beforeAchievement}`);
  if (kpi.afterAchievement != null) parts.push(`after achievement ${kpi.afterAchievement}`);
  if (kpi.beforeContribution != null) parts.push(`before contribution ${kpi.beforeContribution}`);
  if (kpi.afterContribution != null) parts.push(`after contribution ${kpi.afterContribution}`);
  return parts.join(', ');
}

export function pageSlice<T>(items: readonly T[], page: number, size = IMPACT_PAGE_SIZE): { page: number; pages: number; rows: T[] } {
  const pages = Math.max(1, Math.ceil(items.length / size) || 1);
  const current = Math.min(Math.max(Number.isFinite(page) ? page : 0, 0), pages - 1);
  const start = current * size;
  return { page: current, pages, rows: items.slice(start, start + size) };
}

export function periodQueryKey(scopeId: string, year: number, month: number) {
  return ['evaluation-settings', 'period', scopeId, year, month] as const;
}

export function uncommittedLifecycleQueryKeys(selection: ReportingSelection) {
  return [
    periodQueryKey(selection.scopeId, selection.year, selection.month),
    ['team-config'],
    ['team-configs'],
    ['kpi-weights'],
    ['balanced-scorecard'],
  ] as const;
}

export function committedEvidenceQueryKeys() {
  return [
    ['performance'],
    ['executive', 'summary'],
    ['reports', 'center'],
    ['insights', 'workspace'],
  ] as const;
}

export function lifecycleQueryKeys(selection: ReportingSelection) {
  return [
    periodQueryKey(selection.scopeId, selection.year, selection.month),
    ...committedEvidenceQueryKeys(),
    ['team-config'],
    ['team-configs'],
    ['kpi-weights'],
    ['balanced-scorecard'],
  ] as const;
}

export function cancelAndInvalidate(queryClient: QueryClient, keys: readonly (readonly unknown[])[]) {
  keys.forEach((queryKey) => {
    const key = [...queryKey];
    void queryClient.cancelQueries({ queryKey: key });
    void queryClient.invalidateQueries({ queryKey: key });
  });
}

/** Draft, revise, and approve refresh settings only. Scores stay where they were. */
export function invalidateDraftLifecycle(queryClient: QueryClient, selection: ReportingSelection) {
  cancelAndInvalidate(queryClient, uncommittedLifecycleQueryKeys(selection));
}

/** Apply and rollback refresh live evidence and the legacy performance module cache. */
export function invalidateCommittedEvidence(
  queryClient: QueryClient,
  selection: ReportingSelection,
  refresh: () => void,
) {
  cancelAndInvalidate(queryClient, lifecycleQueryKeys(selection));
  refresh();
}

export function isStaleProofCode(code: string | undefined): boolean {
  return code === 'stale_preview' || code === 'preview_required';
}

export function formatApplyResult(data: unknown): string {
  const body = data && typeof data === 'object' ? data as { revision_id?: unknown; affected_count?: unknown; applied_count?: unknown } : {};
  const revision = text(body.revision_id);
  const count = finiteNumber(body.affected_count) ?? finiteNumber(body.applied_count);
  if (!revision && count == null) return 'Apply finished for this month. The response did not include a revision id.';
  if (!revision) return `Apply finished for this month for ${count} stored records.`;
  if (count == null) return `Apply recorded revision ${revision}.`;
  return `Apply recorded revision ${revision} for ${count} stored records.`;
}

export function formatRollbackResult(data: unknown): string {
  const body = data && typeof data === 'object' ? data as { status?: unknown; restored_revision_id?: unknown } : {};
  if (body.status !== 'rolled_back') return 'Rollback did not report a rolled-back status. Records and history were left unchanged.';
  if (typeof body.restored_revision_id === 'string' && body.restored_revision_id) {
    return `Rollback restored the saved before-apply values. Restored revision ${body.restored_revision_id}.`;
  }
  return 'Rollback restored the saved before-apply values. No older approved version was reactivated.';
}

export function formatReviseNotice(version: { resumed?: boolean; source_version_id?: string | null; source_checksum?: string | null }): string {
  const resumed = version.resumed === true
    ? 'Existing draft resumed unchanged. The approved version was not overwritten.'
    : 'Revision draft opened for this month. The approved version remains in history.';
  const source = version.source_version_id ? ` Source version ${version.source_version_id}.` : '';
  const checksum = version.source_checksum ? ` Source checksum ${version.source_checksum}.` : '';
  return `${resumed}${source}${checksum}`;
}
