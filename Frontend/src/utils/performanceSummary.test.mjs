import test from 'node:test';
import assert from 'node:assert/strict';
import { calculatePerformanceSummary } from './performanceSummary.js';

const records = [
  { team: 'Coding', month: 'May', region: 'UAE', branch: 'dubai', score: 90, gradeClass: 'A', employee_id: '1' },
  { team: 'Coding', month: 'May', region: 'UAE', branch: 'dubai', score: 80, gradeClass: 'B', employee_id: '2' },
  { team: 'CSR', month: 'May', region: 'UAE', branch: 'sharjah', score: 70, gradeClass: 'C', employee_id: '3' },
  { team: 'Pharmacy', month: 'June', region: 'UAE', branch: 'ajman', score: 60, gradeClass: 'D', employee_id: '4' },
  { team: 'Submission', month: 'May', region: 'UAE', branch: 'clinics', score: 50, gradeClass: 'E', employee_id: '5' },
];

test('calculates counts and averages from shared records', () => {
  const summary = calculatePerformanceSummary(records, { month: 'May', region: 'UAE', branch: 'all' });
  assert.equal(summary.totalAgents, 4);
  assert.equal(summary.uniqueTeamCount, 3);
  assert.equal(summary.averagePerformanceScore, 72.5);
  assert.equal(summary.classABCount, 2);
  assert.equal(summary.classABPercentage, 50);
  assert.equal(summary.classDECount, 1);
  assert.equal(summary.classDEPercentage, 25);
});

test('filters by branch and team alias', () => {
  const branchSummary = calculatePerformanceSummary(records, { month: 'May', region: 'UAE', branch: 'sharjah' });
  assert.equal(branchSummary.totalAgents, 1);
  assert.equal(branchSummary.teamsUsed[0], 'CSR');

  const teamSummary = calculatePerformanceSummary(records, { month: 'May', team: 'coding' });
  assert.equal(teamSummary.totalAgents, 2);
  assert.equal(teamSummary.uniqueTeamCount, 1);
});

test('uses legacy team thresholds when gradeClass is not supplied', () => {
  const summary = calculatePerformanceSummary([
    { team: 'CSR', month: 'May', score: 92, employee_id: '1' },
    { team: 'CSR', month: 'May', score: 87, employee_id: '2' },
    { team: 'CSR', month: 'May', score: 76, employee_id: '3' },
    { team: 'CSR', month: 'May', score: 60, employee_id: '4' },
  ], { month: 'May' });

  assert.deepEqual(summary.classCounts, { A: 0, B: 1, C: 1, D: 1, E: 1 });
});
