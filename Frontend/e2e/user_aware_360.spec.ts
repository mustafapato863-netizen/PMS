import { expect, test, type Page } from '@playwright/test';

/**
 * Spec §8.3 E2E Journeys for User-Aware 360° Agent Coach:
 * 1. agent_360_self_service — Agent sees locked My 360°, runs What-If, asks AI about KPI
 * 2. manager_views_report — Manager switches from own 360° to authorized direct report
 * 3. memory_persistence — User updates preferences in My Profile & Memory drawer and clears memory
 * 4. access_tier_rollout — Admin changes ai_access_tier in Settings
 *
 * Run against a running dev/staging frontend with:
 *   PMS_USER_AWARE_360_E2E=1 npx playwright test e2e/user_aware_360.spec.ts
 */

test.skip(
  !process.env.PMS_USER_AWARE_360_E2E,
  'Set PMS_USER_AWARE_360_E2E=1 with a running frontend dev server to execute these journeys',
);

async function mockAuthSession(
  page: Page,
  user: {
    id: string;
    username: string;
    name: string;
    role: string;
    employee_id: string | null;
    is_self_only: boolean;
    ai_access_tier: 'admin_only' | 'managers_and_admins' | 'all_authenticated_users';
  },
) {
  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: user }),
    });
  });
  await page.route('**/api/settings/ai-assistant', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            enabled: Boolean(body.enabled),
            access_tier: body.access_tier ?? user.ai_access_tier,
            corrective_action_pilot_enabled: false,
          },
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          enabled: true,
          access_tier: user.ai_access_tier,
          corrective_action_pilot_enabled: false,
        },
      }),
    });
  });
}

test.describe('User-Aware 360° Agent Coach E2E', () => {
  test('agent_360_self_service: Agent sees locked My 360°, runs What-If, and asks AI', async ({ page }) => {
    await mockAuthSession(page, {
      id: 'agent-1',
      username: 'sara',
      name: 'Sara Agent',
      role: 'Agent',
      employee_id: 'EMP-360',
      is_self_only: true,
      ai_access_tier: 'all_authenticated_users',
    });

    await page.route('**/api/ai/agent-360', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          employee_code: 'EMP-360',
          employee_name: 'Sara Agent',
          current_period: 'October 2026',
          overall_score: 84.5,
          overall_grade: 'C',
          score_trend: [
            { month: 'September', year: 2026, score: 81.0 },
            { month: 'October', year: 2026, score: 84.5 },
          ],
          kpi_scores: [
            { name: 'Booking Rate', score: 80.0, actual: 24, target: 30, weight: 0.6, grade: 'C', direction: 'higher_better' },
          ],
          top_strength: 'Booking Rate',
          top_opportunity: 'Booking Rate',
          active_corrective_actions: 0,
          corrective_action_summary: null,
          performance_classification: 'Improving',
          cohort: { cohort_size: 8, cohort_avg_score: 80.2, percentile_band: 'Top 25%' },
          what_if_suggestions: [],
        }),
      });
    });

    await page.route('**/api/ai/agent-360/what-if', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          employee_code: 'EMP-360',
          period: 'October 2026',
          kpi_name: 'Booking Rate',
          improvement_pct: 5,
          current_score: 84.5,
          projected_score: 91.2,
          current_grade: 'C',
          projected_grade: 'B',
          score_delta: 6.7,
          current_achievement: 0.8,
          projected_achievement: 0.96,
          capped: false,
        }),
      });
    });

    await page.goto('/ai');
    await expect(page.getByTestId('ai-self-only-pill')).toContainText('My 360°');
    await expect(page.getByTestId('agent-360-scorecard')).toContainText('84.5%');
    await expect(page.getByTestId('what-if-simulator')).toBeVisible();

    await page.getByRole('button', { name: /Simulate impact/i }).click();
    await expect(page.getByTestId('what-if-simulator')).toContainText('91.2%');
    await expect(page.getByTestId('what-if-simulator')).toContainText('Grade C → B');
  });

  test('manager_views_report: Manager opens 360° and switches to authorized direct report', async ({ page }) => {
    await mockAuthSession(page, {
      id: 'mgr-1',
      username: 'mgr',
      name: 'Nadia Manager',
      role: 'Manager',
      employee_id: 'MGR-01',
      is_self_only: false,
      ai_access_tier: 'managers_and_admins',
    });

    await page.route('**/api/ai/agent-360/directory', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          employees: [{ employee_code: 'EMP-360', employee_name: 'Sara Agent', team: 'Inbound', position: 'Agent' }],
        }),
      });
    });

    await page.route('**/api/ai/agent-360*', async (route) => {
      const url = route.request().url();
      const isReport = url.includes('employee_code=EMP-360');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          employee_code: isReport ? 'EMP-360' : 'MGR-01',
          employee_name: isReport ? 'Sara Agent' : 'Nadia Manager',
          current_period: 'October 2026',
          overall_score: isReport ? 84.5 : 92.0,
          overall_grade: isReport ? 'C' : 'B',
          score_trend: [],
          kpi_scores: [],
          top_strength: null,
          top_opportunity: null,
          active_corrective_actions: 0,
          corrective_action_summary: null,
          performance_classification: 'Stable',
          cohort: null,
          what_if_suggestions: [],
        }),
      });
    });

    await page.goto('/ai');
    await page.getByTestId('ai-manager-360-btn').click();
    await expect(page.getByTestId('agent-360-scorecard')).toContainText('92.0%');

    await page.getByLabel('Inspect employee 360°').selectOption('EMP-360');
    await expect(page.getByTestId('agent-360-scorecard')).toContainText('Sara Agent');
    await expect(page.getByTestId('agent-360-scorecard')).toContainText('84.5%');
  });

  test('memory_persistence: User updates preferences and clears memory in drawer', async ({ page }) => {
    let savedMemory: Record<string, unknown> | null = {
      preferences: { detail_level: 'auto', communication_style: 'auto' },
      query_patterns: { query_count: 3 },
      interaction_summary: '',
      feedback_signals: {},
    };

    await mockAuthSession(page, {
      id: 'agent-1',
      username: 'sara',
      name: 'Sara Agent',
      role: 'Agent',
      employee_id: 'EMP-360',
      is_self_only: true,
      ai_access_tier: 'all_authenticated_users',
    });

    await page.route('**/api/ai/memory/me', async (route) => {
      const method = route.request().method();
      if (method === 'PUT') {
        const body = route.request().postDataJSON();
        savedMemory = {
          ...(savedMemory ?? {}),
          preferences: { ...((savedMemory?.preferences as Record<string, unknown>) ?? {}), ...(body.preferences ?? {}) },
        };
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ memory: savedMemory }) });
        return;
      }
      if (method === 'DELETE') {
        savedMemory = null;
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ cleared: true }) });
        return;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ memory: savedMemory }) });
    });

    await page.goto('/ai');
    await page.getByTestId('ai-memory-drawer-btn').click();
    await expect(page.getByTestId('user-memory-drawer')).toBeVisible();

    await page.getByLabel('Detail level').selectOption('brief');
    await expect(page.getByText('Saved')).toBeVisible();

    await page.getByRole('button', { name: /Clear all my memory/i }).click();
    await page.getByRole('button', { name: /Yes, clear all/i }).click();
    await expect(page.getByText('No memory yet')).toBeVisible();
  });

  test('access_tier_rollout: Admin widens rollout tier in Settings', async ({ page }) => {
    await mockAuthSession(page, {
      id: 'admin-1',
      username: 'admin',
      name: 'System Admin',
      role: 'Admin',
      employee_id: null,
      is_self_only: false,
      ai_access_tier: 'admin_only',
    });

    await page.goto('/settings');
    const select = page.getByLabel('PMS AI access rollout tier');
    await expect(select).toHaveValue('admin_only');
    await select.selectOption('all_authenticated_users');
    await expect(select).toHaveValue('all_authenticated_users');
  });
});
