import { describe, expect, it } from 'vitest';
import {
  accessibleRegions, actionMix, buildDeckSearch, canReopenDraft, displayActionState, expectedImpact, filterRegionRows, gradeMix,
  isCriticalKpi, isMonthAvailable, maskNamesInText, isOverdueForPeriod, kpiBadge, isMiss, kpiMovementTone, lastCompleteMonth, nameMasker,
  outlookLine, parseDeckParams, pdfFileName, periodFromKey, periodRegionActions, regionMoM, regionTeams, teamReadiness,
  type DeckAction,
} from './model';

const kpi = (weight: number, achievement_percent: number | null, actual: number | null = achievement_percent) => ({ key: `k${weight}${achievement_percent}`, label: 'K', weight, actual, achievement_percent });
const act = (over: Partial<DeckAction>): DeckAction => ({ id: '1', title: 't', team: 'Coding EGY', region: 'EGY', month: 'September', year: 2026, status: 'Open', priority: 'Low', due_date: '2026-09-20', owner: 'Hana', linked_kpi_key: null, completion_note: null, ...over });

describe('readiness rule v1', () => {
  it('critical KPI means weight >= 0.25 (fraction or percent)', () => {
    expect(isCriticalKpi({ weight: 0.25 })).toBe(true);
    expect(isCriticalKpi({ weight: 0.2499 })).toBe(false);
    expect(isCriticalKpi({ weight: 30 })).toBe(true);
  });
  it('Ready when every critical KPI >= 100 and no open High action', () => {
    expect(teamReadiness([kpi(0.4, 100), kpi(0.3, 120), kpi(0.1, 40)], 0).status).toBe('ready');
  });
  it('Partial when a critical KPI is 70-99.9', () => {
    expect(teamReadiness([kpi(0.4, 99.9), kpi(0.3, 100)], 0).status).toBe('partial');
    expect(teamReadiness([kpi(0.4, 70)], 0).status).toBe('partial');
  });
  it('Partial when a High action is open even if all green', () => {
    expect(teamReadiness([kpi(0.4, 110)], 1).status).toBe('partial');
  });
  it('Not ready when a critical KPI is below 70, regardless of actions', () => {
    expect(teamReadiness([kpi(0.4, 69.9), kpi(0.3, 100)], 0).status).toBe('not_ready');
    expect(teamReadiness([kpi(0.4, 50)], 3).status).toBe('not_ready');
  });
  it('No data when a critical KPI has no value; missing non-critical KPIs are ignored', () => {
    expect(teamReadiness([kpi(0.4, null), kpi(0.3, 50)], 0).status).toBe('no_data');
    expect(teamReadiness([kpi(0.4, 100), kpi(0.1, null)], 0).status).toBe('ready');
    expect(teamReadiness([], 0).status).toBe('no_data');
  });
});

describe('direction colors', () => {
  it('higher_better: up is good, down is bad', () => {
    expect(kpiMovementTone(2, 'higher_better')).toBe('good');
    expect(kpiMovementTone(-2, 'higher_is_better')).toBe('bad');
  });
  it('lower_better: down is good, up is bad', () => {
    expect(kpiMovementTone(-1, 'lower_better')).toBe('good');
    expect(kpiMovementTone(1, 'lower')).toBe('bad');
  });
  it('unknown direction and flat / missing deltas stay grey', () => {
    expect(kpiMovementTone(5, null)).toBe('neutral');
    expect(kpiMovementTone(5, 'sideways')).toBe('neutral');
    expect(kpiMovementTone(0.01, 'higher_better')).toBe('neutral');
    expect(kpiMovementTone(null, 'higher_better')).toBe('neutral');
  });
});

describe('no-data badge', () => {
  it('null actual or achievement is no_data, never a miss', () => {
    expect(kpiBadge(null)).toBe('no_data');
    expect(kpiBadge(80, null)).toBe('no_data');
    expect(isMiss('no_data')).toBe(false);
    expect(isMiss(kpiBadge(65))).toBe(true);
    expect(kpiBadge(100)).toBe('on_track');
  });
  it('empty completion note becomes "No note" (null), never a number', () => {
    expect(expectedImpact({ completion_note: '  ' })).toBeNull();
    expect(expectedImpact({ completion_note: '"Back under 5 days"' })).toBe('"Back under 5 days"');
  });
});

describe('overdue against the end of the selected month', () => {
  const end = periodFromKey('2026-09')!.endDate;
  it('period end is the last day of the month', () => expect(end).toBe('2026-09-30'));
  it('due before period end and still open is overdue', () => {
    expect(isOverdueForPeriod(act({ due_date: '2026-09-20' }), end)).toBe(true);
    expect(displayActionState(act({ due_date: '2026-09-20', status: 'In Progress' }), end)).toBe('Overdue');
  });
  it('due after the period end is not overdue, whatever today is', () => {
    expect(isOverdueForPeriod(act({ due_date: '2026-10-07' }), end)).toBe(false);
    expect(isOverdueForPeriod(act({ due_date: '2026-09-30' }), end)).toBe(false);
  });
  it('completed / cancelled / undated actions are never overdue', () => {
    expect(isOverdueForPeriod(act({ status: 'Completed' }), end)).toBe(false);
    expect(isOverdueForPeriod(act({ status: 'Cancelled' }), end)).toBe(false);
    expect(isOverdueForPeriod(act({ due_date: null }), end)).toBe(false);
  });
  it('outlook is qualitative and says no improvement when there are no actions', () => {
    expect(outlookLine(actionMix([], end))).toMatch(/no improvement is expected/);
    expect(outlookLine(actionMix([act({})], end))).toMatch(/1 overdue/);
  });
});

describe('region isolation', () => {
  it('EGY and UAE team sets never overlap; UAE has no Call Center; IP Offshore is Egypt-only', () => {
    const egy = regionTeams('EGY'); const uae = regionTeams('UAE');
    expect(egy.filter((t) => uae.includes(t))).toEqual([]);
    expect(uae).not.toContain('Call Center');
    expect(uae).not.toContain('Pre-Approvals IP Offshore');
    expect(egy).toContain('Pre-Approvals IP Offshore');
  });
  it('rows of the other region or other teams are dropped', () => {
    const rows = [{ team: 'Coding EGY', region: 'EGY' }, { team: 'Coding EGY', region: 'UAE' }, { team: 'Pre-Approvals OP Dubai', region: 'UAE' }, { team: 'Finance', region: 'EGY' }];
    expect(filterRegionRows('EGY', rows)).toEqual([{ team: 'Coding EGY', region: 'EGY' }]);
    expect(filterRegionRows('UAE', rows)).toEqual([{ team: 'Pre-Approvals OP Dubai', region: 'UAE' }]);
  });
  it('actions are scoped to the region and the locked month/year', () => {
    const p = periodFromKey('2026-09')!;
    const list = [act({ id: 'a' }), act({ id: 'b', month: 'August' }), act({ id: 'c', year: 2025 }), act({ id: 'd', team: 'Pre-Approvals OP Dubai', region: 'UAE' })];
    expect(periodRegionActions(list, 'EGY', p).map((a) => a.id)).toEqual(['a']);
    expect(periodRegionActions(list, 'UAE', p).map((a) => a.id)).toEqual(['d']);
  });
  it('single-region users only get their region; Regional Manager without grants gets none', () => {
    expect(accessibleRegions({ role: 'Regional Manager', accessible_regions: ['UAE'] })).toEqual(['UAE']);
    expect(accessibleRegions({ role: 'Regional Manager', accessible_regions: [] })).toEqual([]);
    expect(accessibleRegions({ role: 'Admin' })).toEqual(['EGY', 'UAE']);
    expect(accessibleRegions({ role: 'Executive', accessible_regions: ['Other'] })).toEqual(['EGY', 'UAE']);
  });
  it('grade mix excludes Partial teams', () => {
    const mix = gradeMix([{ team: 'Coding EGY', score: 96 }, { team: 'Call Center', score: 50 }, { team: 'Resubmission', score: null }], ['Call Center']);
    expect(mix).toEqual({ A: 1, B: 0, C: 0, D: 0, E: 0 });
  });
});

describe('strict month lock', () => {
  it('last complete month opens on the 5th', () => {
    expect(lastCompleteMonth(new Date(2026, 9, 21))).toBe('2026-09');
    expect(lastCompleteMonth(new Date(2026, 10, 4))).toBe('2026-09');
    expect(lastCompleteMonth(new Date(2026, 10, 5))).toBe('2026-10');
    expect(lastCompleteMonth(new Date(2026, 0, 3))).toBe('2025-11');
  });
  it('future / current months are not available', () => {
    const today = new Date(2026, 9, 21);
    expect(isMonthAvailable('2026-09', today)).toBe(true);
    expect(isMonthAvailable('2026-10', today)).toBe(false);
  });
  it('periodFromKey rejects bad input', () => {
    expect(periodFromKey('2026-13')).toBeNull();
    expect(periodFromKey('latest')).toBeNull();
    expect(periodFromKey('2026-02')!.endDate).toBe('2026-02-28');
    expect(periodFromKey('2026-09')!.label).toBe('September 2026');
  });
  it('region MoM only when adjacent and like-for-like; otherwise not available', () => {
    expect(regionMoM({ score_change: 1.8, basis_context: { like_for_like: true } }, true)).toBe(1.8);
    expect(regionMoM({ score_change: 1.8, basis_context: { like_for_like: false } }, true)).toBeNull();
    expect(regionMoM({ score_change: 1.8 }, false)).toBeNull();
    expect(regionMoM({ score_change: null }, true)).toBeNull();
    expect(regionMoM(null, true)).toBeNull();
  });
});

describe('URL params', () => {
  it('parses region, month, present, print and slide anchors', () => {
    expect(parseDeckParams('?region=uae&month=2026-09&mode=present&print=1', '#s08')).toEqual({ region: 'uae', month: '2026-09', present: true, print: true, slide: 8 });
    expect(parseDeckParams('?region=ALL&month=bad', '#s12')).toEqual({ region: null, month: null, present: false, print: false, slide: null });
    expect(parseDeckParams('?region=EGY', '#s01').region).toBe('egy');
  });
  it('builds a canonical search that keeps other params', () => {
    expect(buildDeckSearch('?region=egy&month=2026-09&mask=1', { region: 'uae' })).toBe('?region=uae&month=2026-09&mask=1');
    expect(buildDeckSearch('?region=egy&month=2026-09&mode=present', { present: false })).toBe('?region=egy&month=2026-09');
    expect(buildDeckSearch('?region=egy', { month: '2026-08', print: true })).toBe('?region=egy&month=2026-08&print=1');
  });
  it('PDF file name is per region and period', () => expect(pdfFileName('EGY', '2026-09')).toBe('PMS_Monthly_EGY_2026-09.pdf'));
});

describe('mask names and Draft/Final', () => {
  it('masks consistently as Person A, B, ...', () => {
    const m = nameMasker();
    expect([m('Hana'), m('Karim'), m('Hana'), m('')]).toEqual(['Person A', 'Person B', 'Person A', '—']);
  });
  it('reopening as Draft is Admin-only', () => {
    expect(canReopenDraft('Admin')).toBe(true);
    expect(canReopenDraft('General Manager')).toBe(false);
    expect(canReopenDraft('Regional Manager')).toBe(false);
  });
});

describe('masking names inside free text', () => {
  it('replaces every known name, whole words, case-insensitive, longest first', () => {
    const m = nameMasker();
    const names = ['Hana', 'Hana Mostafa', 'Karim Fathy', 'Ali'];
    const out = maskNamesInText('hana mostafa and KARIM FATHY will coach Hana; Alina and Ali stay', names, m);
    expect(out).toBe('Person A and Person B will coach Person C; Alina and Person D stay');
    expect(out).not.toMatch(/hana|karim|fathy|mostafa/i);
    expect(m('Hana Mostafa')).toBe('Person A');
  });
  it('keeps aliases consistent with the people column', () => {
    const m = nameMasker();
    expect(m('Mona Adel')).toBe('Person A');
    expect(maskNamesInText('Escalate to Mona  Adel.', ['Mona Adel'], m)).toBe('Escalate to Person A.');
  });
  it('treats regex characters in names literally', () => {
    expect(maskNamesInText('Ask J. (Lead) now', ['J. (Lead)'], nameMasker())).toBe('Ask Person A now');
  });
  it('returns null (hide) when there is no name list', () => {
    expect(maskNamesInText('Hana will fix it', [], nameMasker())).toBeNull();
    expect(maskNamesInText('Hana will fix it', ['', null], nameMasker())).toBeNull();
  });
});
