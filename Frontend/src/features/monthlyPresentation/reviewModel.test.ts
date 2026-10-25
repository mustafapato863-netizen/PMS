import { describe, expect, it } from 'vitest';
import type { ExecRecord } from '../executive/compose';
import { periodFromKey } from './model';
import {
  buildMonthlyReview, decisionStatus, followUpUrl, isBelowTarget, mapReviewAction, outcomeOf, prepareReviewDrivers, summaryRecordsUrl,
  type ReviewAction,
} from './reviewModel';

const today = new Date(2026, 9, 21);
const period = periodFromKey('2026-09')!;

function record(over: Partial<ExecRecord> & Pick<ExecRecord, 'employeeId' | 'name' | 'score' | 'period'>): ExecRecord {
  return {
    team: 'Coding EGY', region: 'EGY', position: null, level: 'Employee', branches: [], kpis: [],
    ...over,
  };
}

const sep = { year: 2026, month: 'September', key: '2026-09' };
const aug = { year: 2026, month: 'August', key: '2026-08' };
const jul = { year: 2026, month: 'July', key: '2026-07' };

function action(over: Partial<ReviewAction>): ReviewAction {
  return {
    id: 'a', employeeId: 'E', employeeName: 'Cam', team: 'Coding EGY', position: null, month: 'September', year: 2026,
    actionType: 'Coaching', actionText: 'Weekly review', rootCause: 'Capacity', ownerId: 'o', ownerName: 'Hana',
    priority: 'High', status: 'Open', followUpState: null, dueDate: '2026-10-30', evidence: null,
    createdAt: '2026-09-01', completedAt: null, ...over,
  };
}

describe('request guards', () => {
  it('summary-records requires region, year and month', () => {
    expect(summaryRecordsUrl('EGY', 2026, 'September')).toBe('/api/performance/summary-records?region=EGY&year=2026&month=September');
    expect(() => summaryRecordsUrl('  ', 2026, 'September')).toThrow(/region, year and month/);
    expect(() => summaryRecordsUrl('EGY', 2026, ' ')).toThrow(/region, year and month/);
    expect(() => summaryRecordsUrl('EGY', Number.NaN, 'September')).toThrow(/region, year and month/);
  });
  it('follow-up requires region and month and does not send a year', () => {
    expect(followUpUrl('UAE', 'August')).toBe('/api/corrective-actions/follow-up?region=UAE&month=August');
    expect(() => followUpUrl('', 'August')).toThrow(/region and month/);
  });
});

describe('below target', () => {
  it('is grade C or lower, so 90 is excluded and 89.9 is included', () => {
    expect(isBelowTarget(90)).toBe(false);
    expect(isBelowTarget(95)).toBe(false);
    expect(isBelowTarget(89.9)).toBe(true);
    expect(isBelowTarget(70)).toBe(true);
    expect(isBelowTarget(null)).toBe(false);
  });
});

describe('decision status', () => {
  it('an open action due before today is overdue, and a missing action is no decision', () => {
    expect(decisionStatus(null, today)).toBe('no_decision');
    expect(decisionStatus(action({ dueDate: '2026-10-01', status: 'Open' }), today)).toBe('overdue');
    expect(decisionStatus(action({ dueDate: '2026-10-01', status: 'Completed' }), today)).toBe('completed');
    expect(decisionStatus(action({ followUpState: 'overdue', dueDate: '2026-12-01' }), today)).toBe('overdue');
  });
  it('reads the follow-up manager_action and treats a literal None root cause as empty', () => {
    const mapped = mapReviewAction({ id: '1', manager_action: 'Coaching: Sit with the queue', manager_notes: 'None', year: '2026', employee_id: 'EG-1' });
    expect(mapped.actionType).toBe('Coaching');
    expect(mapped.actionText).toBe('Sit with the queue');
    expect(mapped.rootCause).toBeNull();
    expect(mapped.year).toBe(2026);
  });
});

describe('outcomes', () => {
  it('rounds to one decimal before calling a score unchanged', () => {
    expect(outcomeOf(80.04, 80.0)).toBe('Unchanged');
    expect(outcomeOf(80, 81)).toBe('Improved');
    expect(outcomeOf(80, 79)).toBe('Declined');
    expect(outcomeOf(null, 80)).toBe('not_scored');
  });
});

describe('the register', () => {
  const records = [
    record({ employeeId: 'A', name: 'Ada', score: 96, period: sep }),
    record({ employeeId: 'B', name: 'Ben', score: 85, period: sep, kpis: [kpi('TAT', 0.4, 8, 5), kpi('Quality', 0.9, 90, 95)] }),
    record({ employeeId: 'C', name: 'Cam', score: 60, period: sep }),
    record({ employeeId: 'A', name: 'Ada', score: 95, period: aug }),
    record({ employeeId: 'B', name: 'Ben', score: 80, period: aug }),
    record({ employeeId: 'C', name: 'Cam', score: 70, period: aug }),
    record({ employeeId: 'B', name: 'Ben', score: 88, period: jul }),
    record({ employeeId: 'C', name: 'Cam', score: 75, period: jul }),
    record({ employeeId: 'D', name: 'Dee', score: 82, period: sep, region: 'UAE', team: 'Pre-Approvals OP Dubai' }),
  ];

  function build(actions: ReviewAction[] | null, over: Partial<Parameters<typeof buildMonthlyReview>[0]> = {}) {
    return buildMonthlyReview({ code: 'EGY', period, records, actions, fn: null, team: null, role: 'Admin', today, ...over });
  }

  it('lists grade C, D and E only, flags a missing decision, and sorts overdue first', () => {
    const review = build([
      action({ id: 'late', employeeId: 'C', employeeName: 'Cam', dueDate: '2026-09-01', status: 'Open' }),
      action({ id: 'done', employeeId: 'B', employeeName: 'Ben', status: 'Completed', dueDate: '2026-09-20', completedAt: '2026-09-18' }),
    ]);
    expect(review.rows.map((row) => row.name)).toEqual(['Cam', 'Ben']);
    expect(review.rows.map((row) => row.status)).toEqual(['overdue', 'completed']);
    expect(review.rows.some((row) => row.name === 'Ada')).toBe(false);
    expect(review.summary.hero.label).toBe('Egypt');
    expect(review.emptyMonth).toBe(false);
  });

  it('shows No decision yet, and a cancelled action still counts as a decision', () => {
    const review = build([action({ id: 'x', employeeId: 'C', status: 'Cancelled', evidence: 'Stopped' })]);
    const ben = review.rows.find((row) => row.name === 'Ben')!;
    const cam = review.rows.find((row) => row.name === 'Cam')!;
    expect(ben.status).toBe('no_decision');
    expect(cam.status).toBe('cancelled');
    expect(review.coverage).toMatchObject({ total: 1, peopleWithDecision: 1, noDecision: 1, open: 0, overdue: 0, coveragePercent: 50 });
  });

  it('does not also count an overdue action as open', () => {
    const review = build([
      action({ id: 'late', employeeId: 'C', dueDate: '2026-09-01', status: 'In Progress' }),
      action({ id: 'open', employeeId: 'C', dueDate: '2026-11-01', status: 'Open' }),
    ]);
    expect(review.rows.find((row) => row.name === 'Cam')?.status).toBe('overdue');
    expect(review.coverage).toMatchObject({ total: 2, overdue: 1, open: 1, inProgress: 0, peopleWithDecision: 1, noDecision: 1 });
  });

  it('picks the worst KPI by achievement ratio', () => {
    const ben = build([]).rows.find((row) => row.name === 'Ben')!;
    expect(ben.worst).toMatchObject({ label: 'TAT', actual: 8, target: 5 });
    expect(ben.change).toBe(5);
  });

  it('drops the other region', () => {
    expect(build([]).rows.some((row) => row.name === 'Dee')).toBe(false);
    const uae = buildMonthlyReview({ code: 'UAE', period, records, actions: [], fn: null, team: null, role: 'Admin', today });
    expect(uae.rows.map((row) => row.name)).toEqual(['Dee']);
    expect(uae.summary.hero.employees).toBe(1);
  });

  it('does not fall back to another month when the locked month is empty', () => {
    const review = buildMonthlyReview({
      code: 'EGY', period: periodFromKey('2026-06')!, records, actions: [], fn: null, team: null, role: 'Admin', today,
    });
    expect(review.emptyMonth).toBe(true);
    expect(review.rows).toEqual([]);
  });
});

describe('additions from existing data', () => {
  const records = [
    record({ employeeId: 'A', name: 'Ada', score: 96, period: sep }),
    record({ employeeId: 'B', name: 'Ben', score: 85, period: sep }),
    record({ employeeId: 'C', name: 'Cam', score: 60, period: sep }),
    record({ employeeId: 'A', name: 'Ada', score: 90, period: aug }),
    record({ employeeId: 'B', name: 'Ben', score: 85, period: aug }),
    record({ employeeId: 'C', name: 'Cam', score: 70, period: aug }),
    record({ employeeId: 'B', name: 'Ben', score: 92, period: jul }),
    record({ employeeId: 'C', name: 'Cam', score: 75, period: jul }),
    record({ employeeId: 'U', name: 'Noor', score: 88, period: sep, region: 'UAE', team: 'Coding', branches: ['dubai', 'sharjah'] }),
    record({ employeeId: 'U', name: 'Noor', score: 80, period: aug, region: 'UAE', team: 'Coding', branches: ['dubai'] }),
  ];

  const review = buildMonthlyReview({
    code: 'EGY', period, records, role: 'Performance Team', fn: null, team: null, today,
    actions: [
      action({ id: 'prev', employeeId: 'C', employeeName: 'Cam', month: 'August', year: 2026, actionType: 'Training', actionText: 'Course' }),
      action({ id: 'reward', employeeId: 'A', employeeName: 'Ada', actionType: 'Reward', actionText: 'Bonus', status: 'Completed', dueDate: null, completedAt: '2026-09-10', createdAt: '2026-09-01', ownerName: null, ownerId: null }),
      action({
        id: 'late-close', employeeId: 'B', employeeName: 'Ben', status: 'Completed', dueDate: '2026-09-05',
        completedAt: '2026-09-12', createdAt: '2026-09-01', ownerName: 'Hana',
      }),
      action({ id: 'open', employeeId: 'C', employeeName: 'Cam', dueDate: '2026-09-01', status: 'Open', ownerName: 'Hana' }),
    ],
  });

  it('rates last month by the score before and after, and leaves unscored rows out of the rate', () => {
    expect(review.effects.rows.map((row) => row.outcome)).toEqual(['Declined']);
    expect(review.effects.byType).toEqual([{ type: 'Training', improved: 0, scored: 1, rate: 0 }]);
    expect(outcomeOf(80.04, null)).toBe('not_scored');
  });

  it('flags a two-month and a three-month run of below-target grades', () => {
    expect(review.repeats.map((row) => [row.name, row.streak])).toEqual([['Cam', 3], ['Ben', 2]]);
  });

  it('moves grades with A as the best grade', () => {
    expect(review.up.map((row) => `${row.name} ${row.from} to ${row.to}`)).toEqual(['Ada B to A']);
    expect(review.down.map((row) => `${row.name} ${row.from} to ${row.to}`)).toEqual(['Cam D to E']);
  });

  it('recognises grade A and B and the reward decision', () => {
    expect(review.top.map((row) => row.name)).toEqual(['Ada']);
    expect(review.rewards.map((row) => row.actionType)).toEqual(['Reward']);
  });

  it('counts closed on time separately from a late completion and from overdue', () => {
    const hana = review.owners.find((row) => row.owner === 'Hana')!;
    expect(hana).toMatchObject({ decisions: 2, closedOnTime: 0, overdue: 1 });
    expect(hana.averageDays).toBe(11);
    expect(review.owners.find((row) => row.owner === 'Unassigned')?.closedOnTime).toBe(1);
  });

  it('compares UAE branches only, and a person can sit in more than one branch', () => {
    expect(review.branches).toEqual([]);
    const uae = buildMonthlyReview({ code: 'UAE', period, records, actions: [], fn: null, team: null, role: 'Admin', today });
    const dubai = uae.branches.find((row) => row.value === 'dubai')!;
    const sharjah = uae.branches.find((row) => row.value === 'sharjah')!;
    expect(dubai).toMatchObject({ employees: 1, score: 88, change: 8 });
    expect(sharjah).toMatchObject({ employees: 1, score: 88, change: null });
  });
});

describe('selection cuts', () => {
  it('keeps a Marketing role on the function and only that role in the register', () => {
    const records = [
      record({ employeeId: 'W', name: 'Wes', score: 98, period: sep, team: 'Marketing', position: 'Web Developer' }),
      record({ employeeId: 'C', name: 'Cora', score: 75, period: sep, team: 'Marketing', position: 'Copywriter' }),
      record({ employeeId: 'C', name: 'Cora', score: 80, period: aug, team: 'Marketing', position: 'Copywriter' }),
      record({ employeeId: 'A', name: 'Ada', score: 96, period: sep, team: 'Coding EGY' }),
    ];
    const review = buildMonthlyReview({
      code: 'EGY', period, records, role: 'Admin', today, fn: 'Marketing', team: null, position: 'Copywriter',
      actions: [
        action({ id: 'role', employeeId: null, employeeName: null, team: 'Copywriter', actionType: 'Reward', actionText: 'Bonus', ownerName: 'Nada' }),
        action({ id: 'wes', employeeId: 'W', employeeName: 'Wes', team: 'Marketing', actionType: 'Reward', actionText: 'Spot bonus', ownerName: 'Nada' }),
      ],
    });
    expect(review.emptyMonth).toBe(false);
    expect(review.summary.hero.score).toBe(75);
    expect(review.summary.scope.view).toBe('function');
    expect(review.rows.map((row) => row.name)).toEqual(['Cora']);
    expect(review.rows[0].position).toBe('Copywriter');
    const counts = review.summary.grade_distribution!.counts;
    expect(review.rows.length).toBe(counts.C + counts.D + counts.E);
    expect(review.rewards.map((row) => row.id)).toEqual(['role']);
    expect(review.owners.map((row) => row.owner)).toEqual(['Nada']);
    expect(review.top.map((row) => row.name)).not.toContain('Wes');
  });

  it('does not pull a September reward for someone who was on the team only in July', () => {
    const records = [
      record({ employeeId: 'J', name: 'Joe', score: 80, period: jul }),
      record({ employeeId: 'C', name: 'Cam', score: 60, period: sep }),
      record({ employeeId: 'C', name: 'Cam', score: 70, period: aug }),
      record({ employeeId: 'C', name: 'Cam', score: 75, period: jul }),
    ];
    const review = buildMonthlyReview({
      code: 'EGY', period, records, role: 'Admin', today, fn: 'RCM', team: 'Coding EGY',
      actions: [
        action({ id: 'joe-reward', employeeId: 'J', employeeName: 'Joe', actionType: 'Reward', actionText: 'Bonus', status: 'Completed' }),
        action({ id: 'cam', employeeId: 'C', employeeName: 'Cam', actionType: 'Coaching' }),
      ],
    });
    expect(review.rows.map((row) => row.name)).toEqual(['Cam']);
    expect(review.rewards).toEqual([]);
    expect(review.owners).toEqual([expect.objectContaining({ owner: 'Hana', decisions: 1 })]);
    const counts = review.summary.grade_distribution!.counts;
    expect(review.rows.length).toBe(counts.C + counts.D + counts.E);
  });

  it('names the earlier month compose used, and leaves the register change empty when last month has no score', () => {
    const october = periodFromKey('2026-10')!;
    const review = buildMonthlyReview({
      code: 'EGY', period: october, role: 'Admin', today, fn: null, team: null, actions: [],
      records: [
        record({ employeeId: 'C', name: 'Cam', score: 70, period: { year: 2026, month: 'October', key: '2026-10' } }),
        record({ employeeId: 'C', name: 'Cam', score: 80, period: aug }),
      ],
    });
    expect(review.close.results.join(' ')).toContain('August 2026');
    expect(review.close.results.join(' ')).not.toContain('versus last month');
    expect(review.rows.map((row) => row.change)).toEqual([null]);
  });

  it('keeps a driver with no team when insights were already limited to that team', () => {
    const prepared = prepareReviewDrivers([
      { id: 'd1', driver: 'Speed', scope: '', impact_points: -2, direction: 'negative', insight_id: 'i1' },
      { id: 'd2', driver: 'Other', scope: 'Pharmacy', impact_points: -1, direction: 'negative', insight_id: 'i2' },
    ], [], { fn: 'RCM', team: 'Coding EGY' });
    const review = buildMonthlyReview({
      code: 'EGY', period, role: 'Admin', today, fn: 'RCM', team: 'Coding EGY', actions: [],
      records: [
        record({ employeeId: 'C', name: 'Cam', score: 60, period: sep }),
        record({ employeeId: 'C', name: 'Cam', score: 70, period: aug }),
      ],
      drivers: prepared,
    });
    expect(review.summary.drivers.negative.map((driver) => driver.kpi_label)).toContain('Speed');
    expect(review.summary.drivers.negative.map((driver) => driver.kpi_label)).not.toContain('Other');
    const marketing = prepareReviewDrivers([
      { id: 'd1', driver: 'Speed', scope: '', impact_points: -2, direction: 'negative', insight_id: 'i1' },
      { id: 'd2', driver: 'Other', scope: 'Coding EGY', impact_points: -1, direction: 'negative', insight_id: 'i2' },
    ], [], { fn: 'Marketing', team: null });
    expect(marketing.drivers.map((driver) => driver.scope)).toEqual(['Marketing']);
  });
});

function kpi(label: string, ratio: number, actual: number, target: number): ExecRecord['kpis'][number] {
  return {
    kpi_key: label.toLowerCase(), label, unit: 'days', direction: 'lower_better',
    actual_value: actual, target_value: target, achievement_ratio: ratio, weight_applied: 1, contribution: 1,
  };
}
