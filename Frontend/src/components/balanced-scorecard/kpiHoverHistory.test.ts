import { describe, expect, it } from 'vitest';
import { resolveKpiHoverHistory } from './kpiHoverHistory';

describe('resolveKpiHoverHistory', () => {
  it('prefers hovered KPI history when available', () => {
    const hoveredHistory = [{ month: 'June', score: 91 }];
    const selectedHistory = [{ month: 'May', score: 44 }];

    expect(resolveKpiHoverHistory(hoveredHistory, selectedHistory)).toBe(hoveredHistory);
  });

  it('falls back to selected KPI history when hovered history is missing', () => {
    const selectedHistory = [{ month: 'May', score: 44 }];

    expect(resolveKpiHoverHistory(undefined, selectedHistory)).toBe(selectedHistory);
  });
});
