import { describe, expect, it } from 'vitest';

import { lineFormulaSupported, selectOpenVersion, toPeriodData, type EvaluationVersion } from './evaluationSettings';

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

  it('does not treat an unsupported direction or target source as editable', () => {
    expect(lineFormulaSupported(line)).toBe(true);
    expect(lineFormulaSupported({ ...line, direction: 'custom_index' })).toBe(false);
    expect(lineFormulaSupported({ ...line, target_mode: 'formula' })).toBe(false);
  });
});
