import { expect, test, type Browser, type Page } from '@playwright/test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

/**
 * Read-only part-by-part checks against the already-running local app.
 *
 * Each part's on-screen result:
 * - sign-in: Executive Summary hero, including its score basis label
 * - executive: company Functions section and the People average label
 * - function-summary: the opened function's summary (executive-function) and that function's name
 * - team: the team title and the employee roster heading
 * - employee: Employee Profile plus the Employee directory, which renders only after a person loads
 * - insights: Insights heading and Performance & Breakdown Summary
 * - planning: Planning heading and the plans or follow-up subtitle
 * - corrective-actions: Corrective Actions heading and the All actions tab
 * - monthly-review: Monthly Presentation heading and the overall score inside the overview
 * - account: Account settings heading and Your access
 * - logged-out-gate: /monthly-presentation shows the login form and not the Monthly Presentation
 *
 * A role that cannot open a guarded page is blocked, not failed, after the test sees the page refused.
 * Credentials stay in PMS_E2E_USERNAME and PMS_E2E_PASSWORD. This file never writes them.
 */

const baseURL = process.env.PMS_E2E_URL ?? 'http://127.0.0.1:5173';
const apiURL = (process.env.PMS_E2E_API_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, '');

const ALLOWED: Record<string, readonly string[]> = {
  'function-summary': ['Admin', 'General Manager', 'Performance Team', 'Function Viewer', 'Function Director', 'Branch Director', 'Regional Manager'],
  insights: ['Admin', 'General Manager', 'Performance Team'],
  planning: ['Admin', 'General Manager', 'Manager', 'Performance Team'],
  'corrective-actions': ['Admin', 'Executive', 'General Manager', 'Manager', 'Performance Team'],
  'monthly-review': ['Admin', 'General Manager', 'Performance Team', 'Manager', 'Executive', 'Viewer', 'Employee', 'Agent', 'Regional Manager', 'Branch Director'],
};

class PartBlocked extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'PartBlocked';
  }
}

let serverBlock: string | null = null;
let sessionReady = false;
let sessionBlock: string | null = null;
let signedInRole = '';

const username = process.env.PMS_E2E_USERNAME ?? '';
const password = process.env.PMS_E2E_PASSWORD ?? '';
const credentialBlock = username && password
  ? null
  : 'PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset';

function assertLocal(url: string) {
  const host = new URL(url).hostname;
  if (host !== '127.0.0.1' && host !== 'localhost') {
    throw new Error(`Refusing non-local target ${url}`);
  }
}

function stateFile(): string {
  const dir = process.env.PMS_E2E_OUTPUT || os.tmpdir();
  return path.join(dir, 'pms-e2e-storage-state.json');
}

function shotFile(name: string): string {
  const dir = process.env.PMS_E2E_OUTPUT || path.join(os.tmpdir(), 'pms-e2e-parts');
  return path.join(dir, `${name}.png`);
}

function viewFor(role: string): 'corporate' | 'managerial' | 'function' {
  if (role === 'Manager') return 'managerial';
  if (role === 'Function Viewer' || role === 'Function Director') return 'function';
  return 'corporate';
}

async function probe(url: string): Promise<string | null> {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(8_000) });
    if (!response.ok) return `${url} returned HTTP ${response.status}`;
    return null;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return `${url} is not reachable (${message})`;
  }
}

async function runPart(name: string, page: Page | null, body: () => Promise<string>) {
  if (serverBlock) {
    console.log(`E2E_PART ${name} BLOCKED ${serverBlock}`);
    test.skip(true, serverBlock);
  }
  if (name !== 'logged-out-gate' && credentialBlock) {
    console.log(`E2E_PART ${name} BLOCKED ${credentialBlock}`);
    test.skip(true, credentialBlock);
  }
  if (name !== 'sign-in' && name !== 'logged-out-gate' && !sessionReady) {
    const reason = sessionBlock ?? 'no signed-in session from the sign-in part';
    console.log(`E2E_PART ${name} BLOCKED ${reason}`);
    test.skip(true, reason);
  }
  try {
    const detail = await body();
    console.log(`E2E_PART ${name} PASSED ${detail}`);
  } catch (error) {
    if (error instanceof PartBlocked) {
      console.log(`E2E_PART ${name} BLOCKED ${error.message}`);
      test.skip(true, error.message);
    }
    const message = error instanceof Error ? error.message.replace(/\s+/g, ' ').slice(0, 500) : String(error);
    console.log(`E2E_PART ${name} FAILED ${message}`);
    if (page) await page.screenshot({ path: shotFile(name), fullPage: true }).catch(() => undefined);
    throw error;
  }
}

async function signIn(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Username', { exact: true }).fill(username);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await page.waitForURL(/\/(executive|change-password)(?:\?|$)/, { timeout: 60_000 });
  if (page.url().includes('/change-password')) {
    throw new PartBlocked('account must change its password before the workspace opens; this suite does not change passwords');
  }
  await expect(page.locator('#exec-hero-title')).toBeVisible();
  const basis = page.getByText(/^(People average|Leader scorecard|Team score)$/).first();
  await expect(basis).toBeVisible();
  signedInRole = await page.evaluate(() => window.localStorage.getItem('pms_user_role') ?? '');
  const headline = (await page.locator('#exec-hero-title').innerText()).replace(/\s+/g, ' ').trim();
  return `${(await basis.innerText()).trim()}; headline=${headline}`;
}

async function withSession(browser: Browser, name: string, body: (page: Page) => Promise<string>) {
  if (serverBlock || credentialBlock || !sessionReady) {
    await runPart(name, null, async () => '');
    return;
  }
  const context = await browser.newContext({ storageState: stateFile() });
  const page = await context.newPage();
  try {
    await runPart(name, page, () => body(page));
  } finally {
    await context.close();
  }
}

async function refuseWhenRoleCannot(page: Page, part: string, route: string, leaked: () => Promise<number>) {
  const allowed = ALLOWED[part] ?? [];
  if (allowed.includes(signedInRole)) return;
  await page.goto(route);
  if (new URL(page.url()).pathname === '/login') {
    throw new Error('signed-in session was returned to the login page');
  }
  const routePattern = new RegExp(`${route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?:\\?|$)`);
  await expect(page).not.toHaveURL(routePattern);
  expect(await leaked()).toBe(0);
  throw new PartBlocked(`signed-in role ${signedInRole || 'unknown'} is not allowed to open ${route}; the page was refused`);
}

test.describe('product parts', () => {
test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  assertLocal(baseURL);
  assertLocal(apiURL);
  const frontend = await probe(baseURL);
  const api = await probe(`${apiURL}/api/health`);
  serverBlock = [frontend, api].filter(Boolean).join('; ') || null;
});

test.afterAll(async () => {
  await fs.rm(stateFile(), { force: true });
});

test('sign-in shows the executive hero', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await runPart('sign-in', page, async () => {
      try {
        const detail = await signIn(page);
        await context.storageState({ path: stateFile() });
        sessionReady = true;
        return detail;
      } catch (error) {
        sessionBlock = error instanceof PartBlocked ? error.message : 'sign-in did not open a workspace session';
        throw error;
      }
    });
  } finally {
    await context.close();
  }
});

test('executive summary shows functions and the people average', async ({ browser }) => {
  await withSession(browser, 'executive', async (page) => {
    await page.goto('/executive');
    await expect(page.locator('#exec-hero-title')).toBeVisible();
    const headline = (await page.locator('#exec-hero-title').innerText()).replace(/\s+/g, ' ').trim();
    const view = viewFor(signedInRole);
    if (view !== 'corporate') {
      const basis = page.getByText(/^(People average|Leader scorecard|Team score)$/).first();
      await expect(basis).toBeVisible();
      return `view=${view}; basis=${(await basis.innerText()).trim()}; headline=${headline}`;
    }
    await expect(page.getByTestId('executive-corporate')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Functions', exact: true })).toBeVisible();
    await expect(page.getByText('People average', { exact: true }).first()).toBeVisible();
    return `Functions; People average; headline=${headline}`;
  });
});

test('function summary opens from a function card', async ({ browser }) => {
  await withSession(browser, 'function-summary', async (page) => {
    await refuseWhenRoleCannot(page, 'function-summary', '/function-summary', () => page.getByTestId('executive-function').count());
    await page.goto('/executive');
    const link = page.getByRole('link', { name: /^View .+ function$/ }).first();
    await expect(link).toBeVisible();
    const label = (await link.getAttribute('aria-label')) ?? '';
    const functionName = label.replace(/^View /, '').replace(/ function$/, '');
    await link.click();
    await expect(page).toHaveURL(/\/function-summary\/.+/);
    const summary = page.getByTestId('executive-function');
    await expect(summary).toBeVisible();
    await expect(summary.getByText(functionName).first()).toBeVisible();
    const headline = (await page.locator('#exec-hero-title').innerText()).replace(/\s+/g, ' ').trim();
    return `function=${functionName}; headline=${headline}`;
  });
});

test('team page shows the roster', async ({ browser }) => {
  await withSession(browser, 'team', async (page) => {
    await page.goto('/executive');
    const teams = page.locator('aside').getByRole('link', { name: /^(All Teams|Assigned Teams)$/ });
    await expect(teams).toBeVisible();
    await teams.click();
    await expect(page).toHaveURL(/\/team\//);
    const title = page.locator('.team-header-title');
    await expect(title).toBeVisible();
    const roster = page.getByRole('heading', { name: /^(Employee roster|Top and bottom performers)$/ });
    await expect(roster).toBeVisible();
    const titleText = (await title.innerText()).replace(/\s+/g, ' ').trim();
    const rosterText = (await roster.innerText()).replace(/\s+/g, ' ').trim();
    return `team=${titleText}; ${rosterText}`;
  });
});

test('employee profile opens from the roster', async ({ browser }) => {
  await withSession(browser, 'employee', async (page) => {
    await page.goto('/executive');
    const teams = page.locator('aside').getByRole('link', { name: /^(All Teams|Assigned Teams)$/ });
    await expect(teams).toBeVisible();
    await teams.click();
    await expect(page).toHaveURL(/\/team\//);
    await expect(page.locator('.team-header-title')).toBeVisible();
    const profile = page.locator('a[href*="/employee/"]').first();
    await expect(profile).toBeVisible();
    await profile.click();
    await expect(page).toHaveURL(/\/employee\//);
    await expect(page.getByRole('heading', { name: 'Employee Profile', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Employee directory', exact: true })).toBeVisible();
    return 'Employee Profile; Employee directory';
  });
});

test('insights shows the performance summary', async ({ browser }) => {
  await withSession(browser, 'insights', async (page) => {
    await refuseWhenRoleCannot(page, 'insights', '/insights', () => page.getByRole('heading', { name: 'Insights', exact: true }).count());
    await page.goto('/insights');
    const denied = page.getByText('Unable to load insights');
    await expect(page.getByRole('heading', { name: 'Insights', exact: true }).or(denied)).toBeVisible();
    if (await denied.isVisible()) throw new Error((await denied.locator('..').innerText()).replace(/\s+/g, ' ').trim());
    await expect(page.getByRole('heading', { name: 'Performance & Breakdown Summary', exact: true })).toBeVisible();
    return 'Insights; Performance & Breakdown Summary';
  });
});

test('planning shows the workspace', async ({ browser }) => {
  await withSession(browser, 'planning', async (page) => {
    await refuseWhenRoleCannot(page, 'planning', '/planning', () => page.getByRole('heading', { name: 'Planning', exact: true }).count());
    await page.goto('/planning');
    const denied = page.getByText('Unable to load planning workspace.');
    await expect(page.getByRole('heading', { name: 'Planning', exact: true }).or(denied)).toBeVisible();
    if (await denied.isVisible()) throw new Error((await denied.innerText()).replace(/\s+/g, ' ').trim());
    const subtitle = page.getByText(/Turn performance insights into owned, measurable actions\.|Follow up open actions across plans and corrective actions\./);
    await expect(subtitle.first()).toBeVisible();
    return `Planning; ${(await subtitle.first().innerText()).trim()}`;
  });
});

test('corrective actions lists the action workspace', async ({ browser }) => {
  await withSession(browser, 'corrective-actions', async (page) => {
    await refuseWhenRoleCannot(page, 'corrective-actions', '/corrective-actions', () => page.getByRole('heading', { name: 'Corrective Actions', exact: true }).count());
    await page.goto('/corrective-actions');
    await expect(page.getByRole('heading', { name: 'Corrective Actions', exact: true })).toBeVisible();
    await expect(page.getByRole('tab', { name: 'All actions' })).toBeVisible();
    return 'Corrective Actions; All actions';
  });
});

test('monthly review shows the presentation overview', async ({ browser }) => {
  await withSession(browser, 'monthly-review', async (page) => {
    await refuseWhenRoleCannot(page, 'monthly-review', '/monthly-presentation', () => page.getByRole('heading', { name: 'Monthly Presentation', exact: true }).count());
    await page.goto('/monthly-presentation');
    const overview = page.getByTestId('monthly-overview-page');
    await expect(overview).toBeVisible();
    await expect(overview.getByRole('heading', { name: 'Monthly Presentation', exact: true })).toBeVisible();
    const score = overview.getByTestId('overall-score-value');
    await expect(score).toBeVisible();
    const scoreText = (await score.innerText()).replace(/\s+/g, ' ').trim();
    expect(scoreText).toMatch(/\d/);
    return `Monthly Presentation; overall score ${scoreText}`;
  });
});

test('account shows access for the signed-in user', async ({ browser }) => {
  await withSession(browser, 'account', async (page) => {
    await page.goto('/account');
    await expect(page.getByRole('heading', { name: 'Account settings', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Your access', exact: true })).toBeVisible();
    await expect(page.getByText('Your profile, password and workspace appearance.')).toBeVisible();
    return 'Account settings; Your access';
  });
});

test('logged-out visit to monthly review shows the login form', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  try {
    await runPart('logged-out-gate', page, async () => {
      await page.goto('/monthly-presentation');
      await expect(page).toHaveURL(/\/login(?:\?|$)/);
      await expect(page.getByLabel('Username', { exact: true })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Sign In', exact: true })).toBeVisible();
      await expect(page.getByTestId('monthly-overview-page')).toHaveCount(0);
      await expect(page.getByRole('heading', { name: 'Monthly Presentation', exact: true })).toHaveCount(0);
      return 'Username; Sign In; monthly review refused';
    });
  } finally {
    await context.close();
  }
});
});
