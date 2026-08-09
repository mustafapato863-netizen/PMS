const TEAM_ALIASES = {
  inbound: 'Inbound',
  outbound: 'Outbound',
  'inbounduae': 'Inbound UAE',
  'preapprovalsipoffshore': 'Pre-Approvals IP Offshore',
  sales: 'Sales',
  coding: 'Coding',
  csr: 'CSR',
  pharmacy: 'Pharmacy',
  submission: 'Submission',
  resubmission: 'Re-Submission',
};

export function normalizeTeamName(teamName = '') {
  return String(teamName).trim().toLowerCase().replace(/[^a-z0-9]/g, '');
}

function normalizeRegion(region = '') {
  return String(region || '').trim().toUpperCase();
}

function normalizeMonth(month = '') {
  return String(month || '').trim().toLowerCase();
}

function normalizeScore(score) {
  const n = Number(score);
  if (!Number.isFinite(n) || n <= 0) return 0;
  if (n <= 1) return n * 100;
  return Math.min(n, 100);
}

function getGradeClass(record) {
  if (record?.gradeClass && ['A', 'B', 'C', 'D', 'E'].includes(record.gradeClass)) {
    return record.gradeClass;
  }
  const score = normalizeScore(record?.score ?? record?.evaluation?.score ?? 0);
  if (score >= 95) return 'A';
  if (score >= 90) return 'B';
  if (score >= 80) return 'C';
  if (score >= 70) return 'D';
  return 'E';
}

function getRecordField(record, key) {
  if (!record) return undefined;
  if (record[key] !== undefined) return record[key];
  if (record.identity && record.identity[key] !== undefined) return record.identity[key];
  if (record.raw && record.raw[key] !== undefined) return record.raw[key];
  if (record.raw_data && record.raw_data[key] !== undefined) return record.raw_data[key];
  return undefined;
}

function matchesBranch(record, branch) {
  if (!branch || branch === 'all') return true;
  const target = String(branch).toLowerCase();
  const directBranch = String(record?.branch || '').toLowerCase();
  if (directBranch) return directBranch === target;
  const rawTeam = String(record?.raw_data?.Team || record?.raw_data?.['Out Team'] || record?.raw_data?.team || '').toUpperCase();
  if (!rawTeam) return false;
  if (target === 'dubai') return rawTeam.includes('DUBAI');
  if (target === 'sharjah') return rawTeam.includes('SHJ') || rawTeam.includes('SHARJAH') || rawTeam.includes('SHARQA');
  if (target === 'ajman') return rawTeam.includes('AJM') || rawTeam.includes('AJMAN');
  if (target === 'clinics') return rawTeam.includes('CLINIC');
  return true;
}

function matchesFilters(record, filters = {}) {
  const month = filters.month ?? 'All';
  const region = filters.region ?? 'All';
  const branch = filters.branch ?? 'all';
  const team = filters.team ?? null;

  if (month !== 'All' && normalizeMonth(getRecordField(record, 'month')) !== normalizeMonth(month)) return false;
  if (region !== 'All' && normalizeRegion(getRecordField(record, 'region')) !== normalizeRegion(region)) return false;
  if (!matchesBranch(record, branch)) return false;
  if (team && normalizeTeamName(getRecordField(record, 'team')) !== normalizeTeamName(team)) return false;
  return true;
}

export function calculatePerformanceSummary(records = [], filters = {}) {
  const filtered = (Array.isArray(records) ? records : []).filter((record) => matchesFilters(record, filters));
  const teamsUsed = [...new Set(filtered.map((record) => {
    const rawTeam = getRecordField(record, 'team') || '';
    return TEAM_ALIASES[normalizeTeamName(rawTeam)] || rawTeam;
  }).filter(Boolean))];

  const classCounts = { A: 0, B: 0, C: 0, D: 0, E: 0 };
  let scoreSum = 0;

  for (const record of filtered) {
    const score = normalizeScore(getRecordField(record, 'score') ?? record?.evaluation?.score ?? 0);
    scoreSum += score;
    const gradeClass = getGradeClass(record);
    if (classCounts[gradeClass] !== undefined) {
      classCounts[gradeClass] += 1;
    }
  }

  const totalAgents = filtered.length;
  const uniqueTeamCount = teamsUsed.length;
  const averagePerformanceScore = totalAgents > 0 ? scoreSum / totalAgents : 0;
  const classABCount = classCounts.A + classCounts.B;
  const classDECount = classCounts.D + classCounts.E;

  return {
    totalAgents,
    uniqueTeamCount,
    averagePerformanceScore,
    classABCount,
    classABPercentage: totalAgents > 0 ? (classABCount / totalAgents) * 100 : 0,
    classDECount,
    classDEPercentage: totalAgents > 0 ? (classDECount / totalAgents) * 100 : 0,
    recordsUsed: filtered,
    teamsUsed,
    classCounts,
  };
}
