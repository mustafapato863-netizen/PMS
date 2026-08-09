import { expect, test } from './fixtures';

test('deletes a generated report after confirmation', async ({ auditPage }) => {
  let deleted = false;

  await auditPage.route('**/api/reports/templates', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ success: true, data: [] }),
  }));
  await auditPage.route('**/api/reports/options', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      success: true,
      data: {
        periods: [{ year: 2026, month: 'June', key: '2026-06' }],
        teams: [],
        regions: [],
        performance_levels: [],
        positions: [],
        employees: [],
        grades: [],
        statuses: [],
        can_export: true,
      },
    }),
  }));
  await auditPage.route('**/api/reports?**', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({
      success: true,
      data: {
        items: deleted ? [] : [{
          id: 'report-1',
          name: 'June Team Report',
          report_type: 'team_marketing',
          period: 'June 2026',
          created_at: '2026-07-22T16:09:00Z',
          format: 'pptx',
          file_name: 'June_Team_Report.pptx',
          download_url: '/api/reports/report-1/download',
        }],
        total: deleted ? 0 : 1,
        page: 1,
        page_size: 10,
      },
    }),
  }));
  await auditPage.route('**/api/reports/report-1', async (route) => {
    expect(route.request().method()).toBe('DELETE');
    deleted = true;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        message: 'Generated report deleted',
        data: { id: 'report-1', name: 'June Team Report' },
      }),
    });
  });

  await auditPage.goto('/reports');
  await expect(auditPage.getByText('June Team Report')).toBeVisible();
  await auditPage.getByRole('button', { name: 'Delete June Team Report' }).click();
  await expect(auditPage.getByRole('alertdialog', { name: 'Delete this report?' })).toBeVisible();
  await auditPage.getByRole('button', { name: 'Delete report' }).click();

  await expect(auditPage.getByText('June Team Report deleted successfully.')).toBeVisible();
  await expect(auditPage.getByText('No generated reports yet.')).toBeVisible();
});
