import { expect, test as base, type Page } from '@playwright/test';

const auditUser = {
  id: 'ui-audit-admin',
  name: 'UI Audit Admin',
  username: 'ui-audit',
  role: 'Admin',
  accessible_teams: [],
  is_general_manager: true,
  accessible_team_count: 0,
  total_team_count: 2,
};

const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString('base64url');
const auditToken = `${encode({ alg: 'none', typ: 'JWT' })}.${encode({
  user_id: auditUser.id,
  sub: auditUser.username,
  role: auditUser.role,
  username: auditUser.name,
  exp: 4_102_444_800,
})}.audit`;

const baseRecord = {
  year: 2026,
  region: 'EGY',
  status: 'Meets',
  performance_level: 'Employee',
  calls: { inbound: 120, outbound: 30, total_handled: 145, abandoned: 5, aht_raw: '00:02:45' },
  geo: {
    bookings: { dubai: 80, sharjah: 20, ajman: 5, clinics: 10 },
    attended: { dubai: 60, sharjah: 16, ajman: 4, clinics: 8 },
  },
  actual: { booking_rate: 0.75, attend_rate: 0.8, abandon_rate: 0.03 },
  achievement: { booking_ach: 1, attend_ach: 1 },
  raw_data: {},
};

const performanceRecords = [
  {
    ...baseRecord,
    position: 'Account Manager',
    identity: {
      name: 'Dina Samir',
      employee_id: 'SGHD70149',
      team: 'Marketing',
      month: 'June',
      position: 'Account Manager',
      region: 'EGY',
    },
    evaluation: { score: 95, grade: 'A' },
    kpi_values: [
      {
        kpi_key: 'campaign_delivery',
        label: 'Campaign delivery',
        unit: '%',
        direction: 'higher_better',
        actual_value: 1,
        target_value: 1,
        achievement_ratio: 1,
        weight_applied: 0.5,
        contribution: 0.5,
      },
      {
        kpi_key: 'modification_rate',
        label: 'Modification Rate',
        unit: '%',
        direction: 'lower_better',
        actual_value: 0.0364,
        target_value: 0.15,
        achievement_ratio: 1,
        weight_applied: 0.5,
        contribution: 0.5,
      },
    ],
  },
  {
    ...baseRecord,
    position: 'Agent',
    identity: {
      name: 'Omar Hassan',
      employee_id: 'SGHD70002',
      team: 'Inbound',
      month: 'June',
      position: 'Agent',
      region: 'EGY',
    },
    evaluation: { score: 91, grade: 'B' },
    kpi_values: [
      {
        kpi_key: 'attendance',
        label: 'Patient Attendance Rate',
        unit: '%',
        direction: 'higher_better',
        actual_value: 0.8,
        target_value: 0.75,
        achievement_ratio: 1,
        weight_applied: 0.7,
        contribution: 0.7,
      },
      {
        kpi_key: 'booking',
        label: 'Booking Conversion',
        unit: '%',
        direction: 'higher_better',
        actual_value: 0.75,
        target_value: 0.45,
        achievement_ratio: 1,
        weight_applied: 0.3,
        contribution: 0.3,
      },
    ],
  },
];

const marketingConfig = {
  team: 'Marketing',
  db_name: 'Marketing',
  region: 'EGY',
  performance_level: 'Employee',
  grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
  available_positions: ['Account Manager'],
  positions: {
    'Account Manager': {
      kpis: [
        {
          key: 'campaign_delivery',
          label: 'Campaign delivery',
          perspective: 'Internal Process',
          weight: 0.5,
          direction: 'higher_better',
          unit: '%',
          color: '#2563EB',
          display_order: 1,
        },
        {
          key: 'modification_rate',
          label: 'Modification Rate',
          perspective: 'Internal Process',
          weight: 0.5,
          direction: 'lower_better',
          unit: '%',
          color: '#DC2626',
          display_order: 2,
        },
      ],
    },
  },
};

const teamConfigs = [
  {
    team: 'Inbound',
    db_name: 'Inbound',
    region: 'EGY',
    employee_id_col: 'Employee ID',
    employee_name_col: 'Employee Name',
    grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
    kpis: [
      {
        key: 'attendance',
        label: 'Patient Attendance Rate',
        weight: 0.7,
        direction: 'higher_better',
        unit: '%',
        color: '#2563EB',
        actual_col: 'Attendance',
        target_col: 'Attendance Target',
      },
      {
        key: 'booking',
        label: 'Booking Conversion',
        weight: 0.3,
        direction: 'higher_better',
        unit: '%',
        color: '#10B981',
        actual_col: 'Booking',
        target_col: 'Booking Target',
      },
    ],
  },
];

const insight = {
  id: 'modification-rate-opportunity',
  severity: 'opportunity',
  insight_type: 'kpi_driver',
  title: 'Modification Rate is performing better than target',
  explanation: 'Modification Rate is 3.64% against a maximum target of 15%.',
  scope: 'Marketing · Account Manager',
  impact_points: 4.5,
  trend_label: 'Improving compared with previous period',
  priority_reason: 'The lower-better KPI is within target.',
  status: 'open',
  team: 'Marketing',
  performance_level: 'Employee',
  position: 'Account Manager',
  employee_id: 'SGHD70149',
  kpi_key: 'modification_rate',
  detail: {
    current_value: 0.0364,
    previous_value: 0.04,
    target_value: 0.15,
    unit: '%',
    direction: 'lower_better',
    impact_points: 4.5,
    affected_teams: ['Marketing'],
    affected_positions: ['Account Manager'],
    affected_employees: ['SGHD70149'],
    evidence: [{ label: 'Current value', value: '3.64%' }],
    warnings: [],
    recommended_focus: 'Maintain the current review process.',
  },
  planning_context: {
    source_insight_id: 'modification-rate-opportunity',
    team: 'Marketing',
    kpi_key: 'modification_rate',
  },
};

const insightsWorkspace = {
  summary: {
    critical: 0,
    at_risk: 0,
    opportunities: 1,
    data_issues: 0,
    critical_issues: 0,
    negative_weighted_drivers: 0,
    positive_weighted_drivers: 1,
    weighted_negative_impact: 0,
    weighted_positive_impact: 4.5,
    weighted_net_impact: 4.5,
    analyzed_kpis: 2,
    expected_kpis: 2,
    coverage_percent: 100,
  },
  priority_insights: [insight],
  team_analyses: [insight],
  performance_drivers: [{
    id: 'driver-1',
    driver: 'Modification Rate',
    scope: insight.scope,
    impact_points: 4.5,
    direction: 'positive',
    insight_id: insight.id,
  }],
  risks: [],
  opportunities: [insight],
  data_issues: [],
  people_contribution_analysis: {
    kpi_key: 'modification_rate',
    kpi_label: 'Modification Rate',
    unit: '%',
    direction: 'lower_better',
    total_employees: 1,
    negative_contributors: 0,
    positive_contributors: 1,
    data_issues: 0,
    rows: [{
      employee_id: 'SGHD70149',
      employee_name: 'Dina Samir',
      team: 'Marketing',
      performance_level: 'Employee',
      position: 'Account Manager',
      kpi_key: 'modification_rate',
      kpi_label: 'Modification Rate',
      unit: '%',
      direction: 'lower_better',
      current_value: 0.0364,
      target_value: 0.15,
      gap: 0.1136,
      weighted_impact: 4.5,
      trend: -0.0036,
      severity: 'Good',
      classification: 'positive',
    }],
  },
  kpi_trend: {
    kpi_key: 'modification_rate',
    kpi_label: 'Modification Rate',
    unit: '%',
    direction: 'lower_better',
    points: [
      { period: { year: 2026, month: 'May', key: '2026-05' }, actual_value: 0.04, target_value: 0.15, measured_records: 1 },
      { period: { year: 2026, month: 'June', key: '2026-06' }, actual_value: 0.0364, target_value: 0.15, measured_records: 1 },
    ],
  },
  team_summaries: [{
    team: 'Marketing',
    current_score: 95,
    previous_score: 90,
    score_change: 5,
    impacted_employees: 1,
    total_employees: 1,
    critical: 0,
    at_risk: 0,
    opportunities: 1,
    main_insight_id: insight.id,
    main_cause: insight.title,
  }],
  options: {
    periods: [{ year: 2026, month: 'June', key: '2026-06' }],
    regions: ['EGY'],
    teams: ['Inbound', 'Marketing'],
    performance_levels: ['Employee'],
    positions: ['Account Manager', 'Agent'],
    employees: [{ id: 'SGHD70149', name: 'Dina Samir', team: 'Marketing', position: 'Account Manager' }],
    kpis: [{ key: 'modification_rate', label: 'Modification Rate' }],
    severities: ['critical', 'risk', 'opportunity', 'information'],
    insight_types: ['performance', 'kpi_driver', 'employee_risk', 'opportunity', 'data_quality'],
    statuses: ['open'],
  },
  comparison: {
    current: { year: 2026, month: 'June', key: '2026-06' },
    previous: { year: 2026, month: 'May', key: '2026-05' },
    is_adjacent: true,
    note: null,
  },
  deferred_capabilities: [],
};

export async function installAuditSession(page: Page) {
  await page.addInitScript(({ token, user }) => {
    localStorage.setItem('pms_token', token);
    localStorage.setItem('pms_user_role', 'Admin');
    localStorage.setItem('pms_session_v1', JSON.stringify(user));
    localStorage.setItem('pms_theme', 'light');
  }, { token: auditToken, user: auditUser });

  await page.route('**/socket.io/**', (route) => route.abort());
  await page.route('http://127.0.0.1:8000/api/**', async (route) => {
    const url = new URL(route.request().url());
    let data: unknown = [];
    let extra: Record<string, unknown> = {};

    if (url.pathname === '/api/auth/me') data = auditUser;
    else if (url.pathname === '/api/performance' && url.searchParams.get('team') === 'Marketing') {
      data = performanceRecords.filter((record) => record.identity.team === 'Marketing');
    } else if (url.pathname === '/api/performance') data = performanceRecords;
    else if (url.pathname === '/api/config/teams/Marketing') data = marketingConfig;
    else if (url.pathname === '/api/config/teams') data = teamConfigs;
    else if (url.pathname === '/api/insights/workspace') data = insightsWorkspace;
    else if (url.pathname === '/api/team-management/management-kpi-config/teams') {
      data = ['Marketing'];
      extra = {
        scopes: [{ id: 'marketing-management', name: 'Marketing', team_level: 'management' }],
      };
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data, ...extra }),
    });
  });
}

export const test = base.extend<{ auditPage: Page }>({
  auditPage: async ({ page }, provide) => {
    await installAuditSession(page);
    await provide(page);
  },
});

export { expect };
