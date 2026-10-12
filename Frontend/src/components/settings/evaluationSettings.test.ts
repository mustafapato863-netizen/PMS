import { describe, expect, it } from 'vitest';

import { applyVersion, contractLabel, lineFormulaSupported, lockedDirectionLabel, selectOpenVersion, toPeriodData, versionFromPayload, type EvaluationVersion } from './evaluationSettings';

const line = { kpi_key: 'QualityErrors', weight: 1, direction: 'higher_better', target: 55, target_mode: 'fixed' };

function version(id: string, status: string, versionNumber: number): EvaluationVersion {
  return { id, status, version_number: versionNumber, lines: [line], checksum: `sum-${id}` };
}

describe('evaluation period selection', () => {
  it('keeps a draft ahead of an older approved version and ignores a missing revisions array', () => {
    const period = toPeriodData({
      versions: [version('approved-1', 'approved', 2), version('draft-1', 'draft', 3)],
      scope: { readiness: 'supported' },
    });
    expect(period.versionId).toBe('draft-1');
    expect(period.revisions).toEqual([]);
    expect(period.scope?.readiness).toBe('supported');
  });

  it('uses the last approved row in payload order and reads server revisions only', () => {
    const period = toPeriodData({
      versions: [version('approved-1', 'approved', 2), version('approved-2', 'approved', 4)],
      revisions: [
        { id: 'rev-1', version_id: 'approved-2', status: 'active', created_at: '2026-07-20', affected_count: 2, can_rollback: true },
        { id: 'rev-0', version_id: 'approved-1', status: 'rolled_back', can_rollback: false },
        { id: '', status: 'active', can_rollback: true },
      ],
    });
    expect(selectOpenVersion(period.history)?.id).toBe('approved-2');
    expect(period.versionId).toBe('approved-2');
    expect(period.revisions.map((item) => [item.id, item.canRollback, item.affectedCount])).toEqual([
      ['rev-1', true, 2],
      ['rev-0', false, null],
    ]);
  });

  it('reads the upload contract and keeps it when a later payload omits it', () => {
    const period = toPeriodData({
      versions: [{
        ...version('draft-1', 'draft', 3),
        contract: 'reference_workbook',
        revision_choice: {
          available: true,
          contract: 'reference_workbook',
          code: 'adopt_operational_upload',
          message: 'Admin can adopt the operational upload contract explicitly.',
        },
        lines: [{ ...line, kpi_key: 'Other', row_selection: 'utz_or_abandon' }],
      }],
      scope: { readiness: 'supported' },
    });
    expect(period.contract).toBe('reference_workbook');
    expect(contractLabel(period.contract)).toBe('Reference workbook');
    expect(contractLabel('operational_upload')).toBe('Original upload');
    expect(lockedDirectionLabel('higher_better')).toBe('Higher is better');
    expect(lockedDirectionLabel('lower_better')).toBe('Lower is better');
    expect(lockedDirectionLabel('custom_index')).toBe('custom_index');
    expect(period.revisionChoice).toMatchObject({ available: true, code: 'adopt_operational_upload' });
    expect(period.lines[0]?.row_selection).toBe('utz_or_abandon');

    const kept = applyVersion(period, { id: 'draft-1', notes: 'Saved.' });
    expect(kept.contract).toBe('reference_workbook');
    expect(kept.revisionChoice?.code).toBe('adopt_operational_upload');

    const adopted = applyVersion(period, versionFromPayload({
      id: 'draft-2',
      status: 'draft',
      checksum: 'sum-draft-2',
      contract: 'operational_upload',
      revision_choice: {
        available: false,
        contract: 'operational_upload',
        code: null,
        message: 'This version uses the operational upload contract.',
      },
      lines: [{ ...line, kpi_key: 'Attendance', label: 'Attendance' }],
    }));
    expect(adopted.versionId).toBe('draft-2');
    expect(adopted.contract).toBe('operational_upload');
    expect(adopted.revisionChoice?.available).toBe(false);
    expect(adopted.lines.map((item) => item.kpi_key)).toEqual(['Attendance']);
    expect(toPeriodData({ versions: [version('coding', 'draft', 1)] }).contract).toBeNull();
    expect(toPeriodData({ versions: [version('coding', 'draft', 1)] }).revisionChoice).toBeNull();
  });

  it('does not treat an unsupported direction or target source as editable', () => {
    expect(lineFormulaSupported(line)).toBe(true);
    expect(lineFormulaSupported({ ...line, direction: 'custom_index' })).toBe(false);
    expect(lineFormulaSupported({ ...line, target_mode: 'formula' })).toBe(false);
  });
});
