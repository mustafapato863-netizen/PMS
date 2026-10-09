import { describe, expect, it } from 'vitest';

import {
  IMPACT_PAGE_SIZE,
  displayNumber,
  formatApplyResult,
  formatImpactSummary,
  formatKpiLine,
  formatRollbackResult,
  isStaleProofCode,
  committedEvidenceQueryKeys,
  lifecycleQueryKeys,
  uncommittedLifecycleQueryKeys,
  pageSlice,
  parseImpactProof,
  periodQueryKey,
  proofAuthorizesApproval,
} from './monthlyCorrection';

const selection = { scopeId: 'scope-1', year: 2026, month: 7 };

function proofBody(overrides: Record<string, unknown> = {}) {
  return {
    version_id: 'draft-1',
    scope_id: 'scope-1',
    year: 2026,
    month: 7,
    writes: 0,
    config_validated: true,
    zero_affected: false,
    affected_count: 1,
    scored_employees: 1,
    changed_count: 1,
    unchanged_count: 0,
    conflicts: [],
    missing_evidence: [],
    comparisons: [],
    rules_checksum: 'rules-1',
    source_fingerprint: 'finger-1',
    proof_stored: true,
    satisfies_approval_gate: true,
    ...overrides,
  };
}

describe('monthly impact proof', () => {
  it('rejects a sample-style result that does not satisfy the approval gate', () => {
    const parsed = parseImpactProof(proofBody({ satisfies_approval_gate: false, proof_stored: false }));
    expect(proofAuthorizesApproval(parsed, 'draft-1', selection)).toBe(false);
  });

  it('reads workbook and approved targets that are present and leaves missing numbers blank', () => {
    const parsed = parseImpactProof(proofBody({
      conflicts: [
        { record_id: 'rec-1', kpi_key: 'QualityErrors', workbook_target: 60, approved_target: 55 },
        { kpi_key: 'Calls', fixed_target: 10 },
      ],
    }));
    expect(parsed?.conflicts).toEqual([
      { recordId: 'rec-1', kpiKey: 'QualityErrors', workbookTarget: 60, approvedTarget: 55 },
      { recordId: null, kpiKey: 'Calls', workbookTarget: null, approvedTarget: 10 },
    ]);
    expect(displayNumber(null)).toBe('—');
    expect(formatKpiLine({
      kpiKey: 'QualityErrors',
      actual: 60,
      workbookTarget: null,
      appliedTarget: 55,
      weight: null,
      beforeAchievement: null,
      afterAchievement: null,
      beforeContribution: null,
      afterContribution: null,
    })).toBe('QualityErrors, actual 60, applied target 55');
  });

  it('describes zero stored records as validation rather than employee impact', () => {
    const parsed = parseImpactProof(proofBody({ zero_affected: true, affected_count: 0, scored_employees: 0, changed_count: 0, unchanged_count: 0 }));
    expect(formatImpactSummary(parsed!)).toMatch(/not an employee impact/);
    expect(proofAuthorizesApproval(parsed, 'draft-1', selection)).toBe(true);
  });

  it('pages stored employees by eight', () => {
    const rows = Array.from({ length: 9 }, (_, index) => index + 1);
    expect(IMPACT_PAGE_SIZE).toBe(8);
    expect(pageSlice(rows, 0).rows).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    expect(pageSlice(rows, 1)).toMatchObject({ page: 1, pages: 2, rows: [9] });
  });

  it('formats apply and rollback without inventing a count or a restored version', () => {
    expect(formatApplyResult({ revision_id: 'revision-1', applied_count: 2 })).toBe('Apply recorded revision revision-1 for 2 stored records.');
    expect(formatApplyResult({ revision_id: 'revision-1' })).toBe('Apply recorded revision revision-1.');
    expect(formatRollbackResult({ revision_id: 'revision-1', status: 'rolled_back', restored_basis: [], restored_revision_id: null })).toMatch(/No older approved version was reactivated/);
    expect(isStaleProofCode('stale_preview')).toBe(true);
    expect(isStaleProofCode('preview_required')).toBe(true);
    expect(isStaleProofCode('draft_exists')).toBe(false);
  });

  it('invalidates the real evaluation period and performance and settings prefixes', () => {
    expect(uncommittedLifecycleQueryKeys(selection)).toEqual([
      periodQueryKey('scope-1', 2026, 7),
      ['team-config'],
      ['team-configs'],
      ['kpi-weights'],
      ['balanced-scorecard'],
    ]);
    expect(committedEvidenceQueryKeys()).toEqual([
      ['performance'],
      ['executive', 'summary'],
      ['reports', 'center'],
      ['insights', 'workspace'],
    ]);
    expect(lifecycleQueryKeys(selection)).toEqual([
      periodQueryKey('scope-1', 2026, 7),
      ['performance'],
      ['executive', 'summary'],
      ['reports', 'center'],
      ['insights', 'workspace'],
      ['team-config'],
      ['team-configs'],
      ['kpi-weights'],
      ['balanced-scorecard'],
    ]);
    const roots = lifecycleQueryKeys(selection).map((key) => String(key[0]));
    expect(roots).not.toContain('employee');
    expect(roots).not.toContain('planning');
    expect(roots).not.toContain('corrective-actions');
    const reportKeys = lifecycleQueryKeys(selection).filter((key) => String(key[0]) === 'reports');
    expect(reportKeys.every((key) => String(key[1]) === 'center')).toBe(true);
  });
});
