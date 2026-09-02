/**
 * Standalone Demo Mock Data Provider
 * Provides complete, pre-configured multi-tier data for offline/demo presentations.
 */

export const mockUser = {
  id: 'demo-admin-01',
  name: 'Sarah Al-Mansoor',
  username: 'sarah.m',
  role: 'Admin',
  accessible_teams: ['Inbound', 'Marketing', 'Outbound', 'CSR', 'Coding', 'Pharmacy'],
  is_general_manager: true,
  accessible_team_count: 6,
  total_team_count: 6,
};

export const mockTeamConfigs: Record<string, unknown> = {
  Marketing: {
    team: 'Marketing',
    db_name: 'Marketing',
    region: 'EGY',
    performance_level: 'Employee',
    kpis: [
      { key: 'campaign_delivery', name: 'Campaign delivery', weight: 0.5, unit: '%', direction: 'higher_better', target: 1.0 },
      { key: 'modification_rate', name: 'Modification Rate', weight: 0.5, unit: '%', direction: 'lower_better', target: 0.15 },
    ],
    performance_levels: {
      Corporate: {
        kpis: [
          { key: 'revenue_growth', name: 'Revenue Growth', weight: 0.4, unit: '%', direction: 'higher_better', target: 0.95 },
          { key: 'customer_acquisition_cost', name: 'Customer Acquisition Cost', weight: 0.3, unit: 'AED', direction: 'lower_better', target: 250 },
          { key: 'brand_reach', name: 'Brand Reach & Impressions', weight: 0.3, unit: '%', direction: 'higher_better', target: 0.90 },
        ],
      },
      Managerial: {
        kpis: [
          { key: 'budget_adherence', name: 'Budget Adherence', weight: 0.35, unit: '%', direction: 'higher_better', target: 0.95 },
          { key: 'campaign_roi', name: 'Campaign ROI Index', weight: 0.35, unit: '%', direction: 'higher_better', target: 0.92 },
          { key: 'turnaround_time', name: 'Asset Turnaround Time', weight: 0.30, unit: 'hrs', direction: 'lower_better', target: 24 },
        ],
      },
    },
  },
  Inbound: {
    team: 'Inbound',
    db_name: 'Inbound',
    region: 'EGY',
    performance_level: 'Employee',
    kpis: [
      { key: 'attendance', name: 'Patient Attendance Rate', weight: 0.7, unit: '%', direction: 'higher_better', target: 0.75 },
      { key: 'booking', name: 'Booking Conversion', weight: 0.3, unit: '%', direction: 'higher_better', target: 0.45 },
    ],
  },
};

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

export const mockPerformanceRecords = [
  // === DINA SAMIR (Marketing) - 3 Consecutive Months ===
  {
    ...baseRecord,
    position: 'Account Manager',
    identity: { name: 'Dina Samir', employee_id: 'SGHD70149', team: 'Marketing', month: 'April', position: 'Account Manager', region: 'EGY' },
    evaluation: { score: 88.5, grade: 'B' },
    kpi_values: [
      { kpi_key: 'campaign_delivery', label: 'Campaign delivery', unit: '%', direction: 'higher_better', actual_value: 0.88, target_value: 1, achievement_ratio: 0.88, weight_applied: 0.5, contribution: 0.44 },
      { kpi_key: 'modification_rate', label: 'Modification Rate', unit: '%', direction: 'lower_better', actual_value: 0.065, target_value: 0.15, achievement_ratio: 1, weight_applied: 0.5, contribution: 0.5 },
    ],
  },
  {
    ...baseRecord,
    position: 'Account Manager',
    identity: { name: 'Dina Samir', employee_id: 'SGHD70149', team: 'Marketing', month: 'May', position: 'Account Manager', region: 'EGY' },
    evaluation: { score: 92.0, grade: 'A' },
    kpi_values: [
      { kpi_key: 'campaign_delivery', label: 'Campaign delivery', unit: '%', direction: 'higher_better', actual_value: 0.94, target_value: 1, achievement_ratio: 0.94, weight_applied: 0.5, contribution: 0.47 },
      { kpi_key: 'modification_rate', label: 'Modification Rate', unit: '%', direction: 'lower_better', actual_value: 0.045, target_value: 0.15, achievement_ratio: 1, weight_applied: 0.5, contribution: 0.5 },
    ],
  },
  {
    ...baseRecord,
    position: 'Account Manager',
    identity: { name: 'Dina Samir', employee_id: 'SGHD70149', team: 'Marketing', month: 'June', position: 'Account Manager', region: 'EGY' },
    evaluation: { score: 95.0, grade: 'A' },
    kpi_values: [
      { kpi_key: 'campaign_delivery', label: 'Campaign delivery', unit: '%', direction: 'higher_better', actual_value: 1.0, target_value: 1, achievement_ratio: 1, weight_applied: 0.5, contribution: 0.5 },
      { kpi_key: 'modification_rate', label: 'Modification Rate', unit: '%', direction: 'lower_better', actual_value: 0.0364, target_value: 0.15, achievement_ratio: 1, weight_applied: 0.5, contribution: 0.5 },
    ],
  },

  // === OMAR HASSAN (Inbound) - 3 Consecutive Months ===
  {
    ...baseRecord,
    position: 'Agent',
    identity: { name: 'Omar Hassan', employee_id: 'SGHD70002', team: 'Inbound', month: 'April', position: 'Agent', region: 'EGY' },
    evaluation: { score: 82.0, grade: 'B' },
    kpi_values: [
      { kpi_key: 'attendance', label: 'Patient Attendance Rate', unit: '%', direction: 'higher_better', actual_value: 0.72, target_value: 0.75, achievement_ratio: 0.96, weight_applied: 0.7, contribution: 0.672 },
      { kpi_key: 'booking', label: 'Booking Conversion', unit: '%', direction: 'higher_better', actual_value: 0.42, target_value: 0.45, achievement_ratio: 0.933, weight_applied: 0.3, contribution: 0.28 },
    ],
  },
  {
    ...baseRecord,
    position: 'Agent',
    identity: { name: 'Omar Hassan', employee_id: 'SGHD70002', team: 'Inbound', month: 'May', position: 'Agent', region: 'EGY' },
    evaluation: { score: 87.0, grade: 'B' },
    kpi_values: [
      { kpi_key: 'attendance', label: 'Patient Attendance Rate', unit: '%', direction: 'higher_better', actual_value: 0.76, target_value: 0.75, achievement_ratio: 1.0, weight_applied: 0.7, contribution: 0.7 },
      { kpi_key: 'booking', label: 'Booking Conversion', unit: '%', direction: 'higher_better', actual_value: 0.48, target_value: 0.45, achievement_ratio: 1.0, weight_applied: 0.3, contribution: 0.3 },
    ],
  },
  {
    ...baseRecord,
    position: 'Agent',
    identity: { name: 'Omar Hassan', employee_id: 'SGHD70002', team: 'Inbound', month: 'June', position: 'Agent', region: 'EGY' },
    evaluation: { score: 91.0, grade: 'B' },
    kpi_values: [
      { kpi_key: 'attendance', label: 'Patient Attendance Rate', unit: '%', direction: 'higher_better', actual_value: 0.80, target_value: 0.75, achievement_ratio: 1.0, weight_applied: 0.7, contribution: 0.7 },
      { kpi_key: 'booking', label: 'Booking Conversion', unit: '%', direction: 'higher_better', actual_value: 0.75, target_value: 0.45, achievement_ratio: 1.0, weight_applied: 0.3, contribution: 0.3 },
    ],
  },

  // === YOUSSEF NABIL (Inbound) - 3 Consecutive Months ===
  {
    ...baseRecord,
    position: 'Agent',
    identity: { name: 'Youssef Nabil', employee_id: 'SGHD70003', team: 'Inbound', month: 'April', position: 'Agent', region: 'EGY' },
    evaluation: { score: 78.0, grade: 'C' },
    kpi_values: [
      { kpi_key: 'attendance', label: 'Patient Attendance Rate', unit: '%', direction: 'higher_better', actual_value: 0.68, target_value: 0.75, achievement_ratio: 0.906, weight_applied: 0.7, contribution: 0.634 },
      { kpi_key: 'booking', label: 'Booking Conversion', unit: '%', direction: 'higher_better', actual_value: 0.40, target_value: 0.45, achievement_ratio: 0.888, weight_applied: 0.3, contribution: 0.266 },
    ],
  },
  {
    ...baseRecord,
    position: 'Agent',
    identity: { name: 'Youssef Nabil', employee_id: 'SGHD70003', team: 'Inbound', month: 'May', position: 'Agent', region: 'EGY' },
    evaluation: { score: 84.0, grade: 'B' },
    kpi_values: [
      { kpi_key: 'attendance', label: 'Patient Attendance Rate', unit: '%', direction: 'higher_better', actual_value: 0.74, target_value: 0.75, achievement_ratio: 0.986, weight_applied: 0.7, contribution: 0.69 },
      { kpi_key: 'booking', label: 'Booking Conversion', unit: '%', direction: 'higher_better', actual_value: 0.46, target_value: 0.45, achievement_ratio: 1.0, weight_applied: 0.3, contribution: 0.3 },
    ],
  },
  {
    ...baseRecord,
    position: 'Agent',
    identity: { name: 'Youssef Nabil', employee_id: 'SGHD70003', team: 'Inbound', month: 'June', position: 'Agent', region: 'EGY' },
    evaluation: { score: 88.0, grade: 'B' },
    kpi_values: [
      { kpi_key: 'attendance', label: 'Patient Attendance Rate', unit: '%', direction: 'higher_better', actual_value: 0.78, target_value: 0.75, achievement_ratio: 1.0, weight_applied: 0.7, contribution: 0.7 },
      { kpi_key: 'booking', label: 'Booking Conversion', unit: '%', direction: 'higher_better', actual_value: 0.52, target_value: 0.45, achievement_ratio: 1.0, weight_applied: 0.3, contribution: 0.3 },
    ],
  },
];

export const mockBalancedScorecardResponse = {
  success: true,
  data: {
    team: 'Marketing',
    month: 'June',
    year: 2026,
    performance_level: 'Corporate',
    overall_score: 91.0,
    overall_grade: 'A',
    status: 'Excellent',
    strategy_map: {
      vision: 'Accelerate Enterprise Growth & Market Leadership in Healthcare Services',
      perspectives: [
        {
          id: 'financial',
          name: 'Financial Perspective',
          score: 96.0,
          weight: 0.30,
          status: 'Exceeded',
          kpis: [
            { name: 'Revenue Growth Index', actual: 95.0, target: 90.0, unit: '%', achievement: 100.0, weight: 0.6 },
            { name: 'Budget Adherence Rate', actual: 93.0, target: 95.0, unit: '%', achievement: 97.8, weight: 0.4 },
          ],
        },
        {
          id: 'customer',
          name: 'Customer & Market Perspective',
          score: 94.0,
          weight: 0.25,
          status: 'Exceeded',
          kpis: [
            { name: 'Patient Booking Conversion', actual: 75.0, target: 65.0, unit: '%', achievement: 100.0, weight: 0.5 },
            { name: 'Customer Satisfaction (CSAT)', actual: 92.5, target: 90.0, unit: '%', achievement: 100.0, weight: 0.5 },
          ],
        },
        {
          id: 'internal_process',
          name: 'Internal Process Perspective',
          score: 92.0,
          weight: 0.25,
          status: 'Achieved',
          kpis: [
            { name: 'Campaign Delivery SLA', actual: 98.0, target: 95.0, unit: '%', achievement: 100.0, weight: 0.6 },
            { name: 'Modification Rejection Rate', actual: 3.64, target: 15.0, unit: '%', achievement: 100.0, weight: 0.4 },
          ],
        },
        {
          id: 'learning_growth',
          name: 'Learning & Organizational Growth',
          score: 90.0,
          weight: 0.20,
          status: 'Achieved',
          kpis: [
            { name: 'Leadership Development Training', actual: 24.0, target: 20.0, unit: 'hrs', achievement: 100.0, weight: 0.5 },
            { name: 'Knowledge Base Certification %', actual: 88.0, target: 85.0, unit: '%', achievement: 100.0, weight: 0.5 },
          ],
        },
      ],
    },
    management_roster: [
      { name: 'Sarah Al-Mansoor', role: 'Head of Growth', score: 95.0, grade: 'A', rank: 1, total_subordinates: 14, status: 'Top Performer' },
      { name: 'Ahmed Khaled', role: 'Operational Lead', score: 91.5, grade: 'A', rank: 2, total_subordinates: 18, status: 'On Target' },
    ],
  },
};
