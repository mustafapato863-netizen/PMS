import path from 'node:path';
import { expect, test } from './fixtures';

async function stabilize(page: import('@playwright/test').Page) {
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        caret-color: transparent !important;
      }
      html {
        scrollbar-width: none !important;
      }
      html::-webkit-scrollbar {
        display: none !important;
      }
    `,
  });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForFunction(() => {
    const root = document.documentElement as HTMLElement & {
      dataset: DOMStringMap & { visualHeight?: string; visualStableSince?: string };
    };
    const height = String(root.scrollHeight);
    if (root.dataset.visualHeight !== height) {
      root.dataset.visualHeight = height;
      root.dataset.visualStableSince = String(Date.now());
      return false;
    }
    return Date.now() - Number(root.dataset.visualStableSince || Date.now()) >= 750;
  }, undefined, { polling: 100, timeout: 20_000 });
}

test('executive dashboard visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1366, height: 768 });
  await auditPage.goto('/executive');
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('executive-1366x768.png', { fullPage: true });
});

test('mobile dashboard visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 390, height: 844 });
  await auditPage.goto('/executive');
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('executive-390x844.png', { fullPage: true });
});

test('insights visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1366, height: 900 });
  await auditPage.goto('/insights');
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('insights-1366x900.png', { fullPage: true });
});

test('employee visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1366, height: 900 });
  await auditPage.goto('/employee/SGHD70149');
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('employee-1366x900.png', { fullPage: true });
});

test('team visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1366, height: 900 });
  await auditPage.goto('/team/inbound');
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('team-inbound-1366x900.png', { fullPage: true });
});

test('marketing visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1366, height: 900 });
  await auditPage.goto('/team/marketing?performance_level=Employee');
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('marketing-1366x900.png', { fullPage: true });
});

test('insights expanded filters visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1366, height: 900 });
  await auditPage.goto('/insights');
  await auditPage.getByRole('button', { name: /Filters/i }).click();
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('insights-filters-open-1366x900.png', { fullPage: true });
});

test('mobile navigation open visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 390, height: 844 });
  await auditPage.goto('/executive');
  await auditPage.getByRole('button', { name: 'Open navigation sidebar' }).click();
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('navigation-open-390x844.png');
});

test('profile dialog visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 390, height: 844 });
  await auditPage.goto('/executive');
  await auditPage.getByRole('button', { name: 'Open user menu' }).click();
  const profileMenuItem = auditPage.getByRole('menuitem', { name: 'My profile' });
  await expect(profileMenuItem).toBeVisible();
  await profileMenuItem.dispatchEvent('click');
  await expect(auditPage.getByRole('dialog')).toBeVisible();
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('profile-dialog-390x844.png');
});

test('empty team state visual baseline', async ({ auditPage }) => {
  await auditPage.setViewportSize({ width: 1366, height: 900 });
  await auditPage.goto('/team/coding');
  await expect(auditPage.getByRole('heading', { name: 'Coding', exact: false }).first()).toBeVisible();
  await stabilize(auditPage);
  await expect(auditPage).toHaveScreenshot('team-empty-1366x900.png', { fullPage: true });
});

test('native Edge final desktop evidence', async ({ auditPage }, testInfo) => {
  test.skip(testInfo.project.name !== 'edge', 'Native Edge-only evidence capture');

  for (const viewport of [
    { width: 1366, height: 768 },
    { width: 1536, height: 864 },
    { width: 1920, height: 1080 },
  ]) {
    await auditPage.setViewportSize(viewport);
    await auditPage.goto('/executive');
    await stabilize(auditPage);
    await auditPage.screenshot({
      path: path.resolve(
        'artifacts/ui-final',
        `executive-edge-${viewport.width}x${viewport.height}.png`,
      ),
      fullPage: true,
    });
  }
});
