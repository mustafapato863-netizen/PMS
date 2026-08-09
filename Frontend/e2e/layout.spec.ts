import AxeBuilder from '@axe-core/playwright';
import { expect, test } from './fixtures';

async function expectNoPageOverflow(page: import('@playwright/test').Page) {
  const dimensions = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    offenders: Array.from(document.querySelectorAll('body *'))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName.toLowerCase(),
          className: typeof element.className === 'string' ? element.className : '',
          left: Math.round(rect.left),
          right: Math.round(rect.right),
        };
      })
      .filter((item) => item.right > document.documentElement.clientWidth + 1 || item.left < -1)
      .slice(0, 8),
  }));
  expect(
    dimensions.scrollWidth,
    `Unexpected horizontal overflow: ${JSON.stringify(dimensions.offenders)}`,
  ).toBeLessThanOrEqual(dimensions.clientWidth);
}

test('dashboard shell, filters, cards, and tables stay within desktop viewport', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1366, height: 768 });
  await auditPage.goto('/executive');
  await expect(auditPage.getByRole('heading', { name: 'Executive Overview' })).toBeVisible();
  await expect(auditPage.getByLabel('Filter by region')).toBeVisible();
  await expect(auditPage.getByLabel('Filter by branch')).toBeVisible();
  await expect(auditPage.getByLabel('Filter by month').last()).toBeVisible();
  await expect(auditPage.locator('aside')).toBeInViewport();
  await expectNoPageOverflow(auditPage);

  const tables = auditPage.locator('table');
  if (await tables.count()) {
    await expect(tables.first()).toBeVisible();
  }
});

test('tablet uses the off-canvas sidebar without compressing content', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1024, height: 768 });
  await auditPage.goto('/executive');
  const sidebarBox = await auditPage.locator('aside').boundingBox();
  const mainBox = await auditPage.locator('main').boundingBox();
  const clientWidth = await auditPage.evaluate(() => document.documentElement.clientWidth);
  expect((sidebarBox?.x ?? 0) + (sidebarBox?.width ?? 0)).toBeLessThanOrEqual(0);
  expect(mainBox?.width).toBe(clientWidth);
  await expect(auditPage.getByRole('button', { name: 'Open navigation sidebar' })).toBeVisible();
  await expectNoPageOverflow(auditPage);
});

test('mobile navigation and header controls remain reachable', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 390, height: 844 });
  await auditPage.goto('/executive');
  await expectNoPageOverflow(auditPage);

  const headerRight = await auditPage.locator('header').evaluate((header) => (
    Math.max(...Array.from(header.querySelectorAll('*')).map((element) => element.getBoundingClientRect().right))
  ));
  expect(headerRight).toBeLessThanOrEqual(390);

  await auditPage.getByRole('button', { name: 'Open navigation sidebar' }).click();
  await expect(auditPage.locator('aside')).toBeInViewport();
  await auditPage.getByRole('button', { name: 'Close navigation sidebar' }).click();
  await expect(auditPage.locator('aside')).not.toBeInViewport();
});

test('profile dialog fits the mobile viewport and has a dialog name', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 390, height: 844 });
  await auditPage.goto('/executive');
  await auditPage.getByRole('button', { name: 'Open user menu' }).click();
  const profileMenuItem = auditPage.getByRole('menuitem', { name: 'My profile' });
  await expect(profileMenuItem).toBeVisible();
  // WebKit can detach the animated menu item during its actionability checks.
  // Dispatching the semantic click after visibility keeps the interaction deterministic.
  await profileMenuItem.dispatchEvent('click');

  const dialog = auditPage.getByRole('dialog');
  await expect(dialog).toBeVisible();
  const box = await dialog.boundingBox();
  expect(box?.x).toBeGreaterThanOrEqual(0);
  expect(box?.y).toBeGreaterThanOrEqual(0);
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(390);
  expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(844);
});

test('key routes render without page overflow', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 390, height: 844 });
  const routes = [
    ['/insights', 'Insights'],
    ['/employee/SGHD70149', 'Employee Profile'],
    ['/team/inbound', 'Inbound'],
    ['/team/marketing?performance_level=Employee', 'Marketing Overview'],
  ] as const;

  for (const [route, heading] of routes) {
    await auditPage.goto(route);
    await expect(
      auditPage.getByRole('heading', { name: heading, exact: false }).first(),
    ).toBeVisible();
    await expectNoPageOverflow(auditPage);
  }
});

test('automated accessibility scan has no serious shell violations', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1366, height: 768 });
  await auditPage.goto('/executive');
  await expect(auditPage.locator('header[aria-label="Application header"]')).toHaveCSS('opacity', '1');
  await auditPage.waitForFunction(() => {
    const heading = Array.from(document.querySelectorAll('h2'))
      .find((element) => element.textContent?.trim() === 'Executive Overview');
    let container = heading?.parentElement;
    while (container && !container.classList.contains('max-w-[1600px]')) {
      container = container.parentElement;
    }
    return container ? Number(getComputedStyle(container).opacity) >= 0.99 : false;
  });
  const results = await new AxeBuilder({ page: auditPage }).analyze();
  const serious = results.violations.filter((violation) => (
    violation.impact === 'serious' || violation.impact === 'critical'
  ));
  expect(serious).toEqual([]);
});
