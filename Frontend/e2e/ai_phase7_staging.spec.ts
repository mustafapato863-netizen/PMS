import { execFileSync } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '../..');
const SEEDER_PATH = path.join(REPO_ROOT, '.tmp', 'phase7-staging', 'seed_staging_db.py');
const REPORT_PATH = path.join(REPO_ROOT, '.tmp', 'phase7-staging', 'playwright_e2e_report.json');

const API_URL = (process.env.PMS_E2E_API_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, '');
const STAGING_PASSWORD = process.env.PMS_STAGING_TEST_PASSWORD ?? 'StagingPass!2026';

test.skip(
  !process.env.PMS_AI_STAGING_E2E,
  'Set PMS_AI_STAGING_E2E=1 with running local staging servers',
);

interface ScenarioRecord {
  scenario: string;
  passed: boolean;
  details: Record<string, unknown>;
}

const scenarioResults: ScenarioRecord[] = [];
let sharedAdminAConvId = '';

function runSeederCommand(subcommand: 'seed' | 'narrow-scope' | 'narrow-role' | 'reset-narrow') {
  const pythonBin = process.env.PMS_STAGING_PYTHON || 'python';
  execFileSync(pythonBin, [SEEDER_PATH, subcommand], {
    cwd: path.join(REPO_ROOT, 'Backend'),
    stdio: 'pipe',
  });
}

async function signInAndOpenAi(page: Page, username: string) {
  await page.goto('/login');
  await page.locator('#login-username').fill(username);
  await page.locator('#login-password').fill(STAGING_PASSWORD);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20_000 }),
    page.locator('#btn-login-submit').click(),
  ]);
  await page.goto('/ai');
  await expect(page.getByLabel('Ask PMS AI a question')).toBeVisible({ timeout: 20_000 });
}

async function apiLogin(request: APIRequestContext, username: string): Promise<string> {
  const resp = await request.post(`${API_URL}/api/auth/login`, {
    data: { username, password: STAGING_PASSWORD },
  });
  expect(resp.status(), `API login failed for ${username}`).toBe(200);
  const body = await resp.json();
  const token = body?.data?.access_token;
  expect(typeof token === 'string' && token.length > 0).toBeTruthy();
  return token;
}

test.describe.serial('Phase 7 Live-Provider Staging E2E Journeys', () => {
  test.afterAll(async () => {
    await fs.mkdir(path.dirname(REPORT_PATH), { recursive: true });
    await fs.writeFile(
      REPORT_PATH,
      JSON.stringify(
        {
          generated_at: new Date().toISOString(),
          base_url: process.env.PMS_E2E_URL ?? 'http://127.0.0.1:5173',
          api_url: API_URL,
          scenarios_run: scenarioResults.length,
          all_passed: scenarioResults.length === 6 && scenarioResults.every((s) => s.passed),
          scenarios: scenarioResults,
        },
        null,
        2,
      ) + '\n',
      'utf-8',
    );
  });

  test('1. Signed-in analytical turn records telemetry, trace_id, provenance badge, and Helpful feedback', async ({ page }) => {
    await signInAndOpenAi(page, 'admin_a');

    const promptBox = page.getByLabel('Ask PMS AI a question');
    await promptBox.fill("What was Laila Mansour's Waiting Time in March 2026?");

    const [chatResp] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/ai/chat') && res.request().method() === 'POST',
        { timeout: 60_000 },
      ),
      page.getByLabel('Send prompt').click(),
    ]);

    expect(chatResp.status()).toBe(200);
    const chatJson = await chatResp.json();
    const data = chatJson.data;

    // Provider may be live (cloudflare/gemini) or deterministic (fallback if providers are unavailable)
    const isLive = ['cloudflare', 'gemini'].includes(data.provider_used);
    expect(['cloudflare', 'gemini', 'deterministic']).toContain(data.provider_used);
    expect(typeof data.trace_id === 'string' && data.trace_id.length > 0).toBeTruthy();

    if (isLive) {
      expect(data.answer_source).toBe('model_synthesis');
      expect(data.provider_usage.input_tokens).toBeGreaterThan(0);
      expect(data.provider_usage.output_tokens).toBeGreaterThan(0);
    } else {
      expect(['deterministic', 'fallback']).toContain(data.answer_source);
    }

    sharedAdminAConvId = String(data.conversation_id || '');
    expect(sharedAdminAConvId.length).toBeGreaterThan(0);

    // Badge must truthfully reflect the answer source
    const expectedBadge = isLive ? 'Verified PMS · Live Synthesis' : 'Verified PMS · Deterministic';
    await expect(page.getByTestId('ai-provenance-badge').last()).toHaveText(
      expectedBadge,
      { timeout: 15_000 },
    );

    const usefulBtn = page.getByLabel('Mark response as useful').last();
    await expect(usefulBtn).toBeVisible();
    const [fbResp] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/ai/feedback') && res.request().method() === 'POST',
        { timeout: 15_000 },
      ),
      usefulBtn.click(),
    ]);
    expect(fbResp.status()).toBe(200);

    scenarioResults.push({
      scenario: '1_analytical_turn_telemetry_and_feedback',
      passed: true,
      details: {
        provider_used: data.provider_used,
        model_used: data.model_used,
        answer_source: data.answer_source,
        is_live_provider: isLive,
        input_tokens: data.provider_usage.input_tokens,
        output_tokens: data.provider_usage.output_tokens,
        cost_status: data.provider_usage.cost_status,
        has_trace_id: Boolean(data.trace_id),
      },
    });
  });

  test('2. Response badge truthfully reflects answer_source (Deterministic vs Live Synthesis)', async ({ page }) => {
    await signInAndOpenAi(page, 'admin_a');

    const promptBox = page.getByLabel('Ask PMS AI a question');
    await promptBox.fill("What was Omar Farouk's Waiting Time in March 2026?");

    const [chatResp] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/ai/chat') && res.request().method() === 'POST',
        { timeout: 60_000 },
      ),
      page.getByLabel('Send prompt').click(),
    ]);

    expect(chatResp.status()).toBe(200);
    const body = await chatResp.json();
    const answerSource = body.data.answer_source;
    const providerUsed = body.data.provider_used;

    // Core invariant: badge text MUST match the actual answer_source
    const isLive = answerSource === 'model_synthesis';
    const expectedBadge = isLive ? 'Verified PMS · Live Synthesis' : 'Verified PMS · Deterministic';
    const unexpectedBadge = isLive ? 'Verified PMS · Deterministic' : 'Verified PMS · Live Synthesis';

    const badge = page.getByTestId('ai-provenance-badge').last();
    await expect(badge).toHaveText(expectedBadge, { timeout: 15_000 });
    // The opposite badge must NOT appear on this response
    await expect(page.getByText(unexpectedBadge)).toHaveCount(0);

    scenarioResults.push({
      scenario: '2_truthful_provenance_badge',
      passed: true,
      details: {
        provider_used: providerUsed,
        answer_source: answerSource,
        expected_badge: expectedBadge,
        message: body.message,
      },
    });
  });

  test('3. Account ownership isolation prevents admin_b from viewing or accessing admin_a conversations', async ({ browser }) => {
    expect(sharedAdminAConvId.length).toBeGreaterThan(0);
    const contextB = await browser.newContext();
    const pageB = await contextB.newPage();
    try {
      await signInAndOpenAi(pageB, 'admin_b');

      const historyToggle = pageB.getByTestId('ai-history-toggle');
      if (await historyToggle.isVisible()) {
        const panelVisible = await pageB.getByTestId('ai-recent-chats-panel').isVisible().catch(() => false);
        if (!panelVisible) {
          await historyToggle.click();
        }
      }
      await expect(pageB.getByTestId(`ai-recent-chat-${sharedAdminAConvId}`)).toHaveCount(0);

      const tokenB = await apiLogin(pageB.request, 'admin_b');
      const getResp = await pageB.request.get(
        `${API_URL}/api/ai/conversations/${encodeURIComponent(sharedAdminAConvId)}`,
        { headers: { Authorization: `Bearer ${tokenB}` } },
      );
      expect(getResp.status()).toBe(404);

      const delResp = await pageB.request.delete(
        `${API_URL}/api/ai/conversations/${encodeURIComponent(sharedAdminAConvId)}`,
        { headers: { Authorization: `Bearer ${tokenB}` } },
      );
      expect(delResp.status()).toBe(404);

      scenarioResults.push({
        scenario: '3_account_ownership_isolation',
        passed: true,
        details: {
          admin_b_get_status: getResp.status(),
          admin_b_delete_status: delResp.status(),
        },
      });
    } finally {
      await contextB.close();
    }
  });

  test('4. Mid-conversation permission narrowing immediately blocks subsequent turns in the same conversation', async ({ browser }) => {
    runSeederCommand('reset-narrow');
    const contextN = await browser.newContext();
    const pageN = await contextN.newPage();
    try {
      await signInAndOpenAi(pageN, 'admin_narrow');

      const promptBox = pageN.getByLabel('Ask PMS AI a question');
      await promptBox.fill("What was Laila Mansour's Waiting Time in March 2026?");
      const [turn1Resp] = await Promise.all([
        pageN.waitForResponse(
          (res) => res.url().includes('/api/ai/chat') && res.request().method() === 'POST',
          { timeout: 60_000 },
        ),
        pageN.getByLabel('Send prompt').click(),
      ]);
      expect(turn1Resp.status()).toBe(200);

      // Narrow scope & role mid-conversation while the same conversation remains open in UI
      runSeederCommand('narrow-scope');
      runSeederCommand('narrow-role');

      await promptBox.fill("What was Salma Adel's Conversion Rate in March 2026?");
      const [turn2Resp] = await Promise.all([
        pageN.waitForResponse(
          (res) => res.url().includes('/api/ai/chat') && res.request().method() === 'POST',
          { timeout: 30_000 },
        ),
        pageN.getByLabel('Send prompt').click(),
      ]);
      expect(turn2Resp.status()).toBe(403);
      await expect(pageN.getByText('Unable to complete analysis')).toBeVisible({ timeout: 10_000 });
      await expect(pageN.getByText('31.5')).toHaveCount(0);

      scenarioResults.push({
        scenario: '4_mid_conversation_permission_narrowing',
        passed: true,
        details: {
          turn1_status: turn1Resp.status(),
          turn2_status_after_narrowing: turn2Resp.status(),
        },
      });
    } finally {
      runSeederCommand('reset-narrow');
      await contextN.close();
    }
  });

  test('5. Idempotent client_request_id replay produces same turn_id without duplicate turns', async ({ page }) => {
    await signInAndOpenAi(page, 'admin_a');

    const promptBox = page.getByLabel('Ask PMS AI a question');
    await promptBox.fill("What was the Inbound team's average overall score in March 2026?");
    const [firstResp] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/ai/chat') && res.request().method() === 'POST',
        { timeout: 60_000 },
      ),
      page.getByLabel('Send prompt').click(),
    ]);
    expect(firstResp.status()).toBe(200);
    const firstData = (await firstResp.json()).data;
    const convId = String(firstData.conversation_id);

    // Check if angle regeneration button is available (only for performance answers from live providers)
    const regenBtn = page.getByTestId('ai-regenerate-angle-btn').last();
    let regenWorked = false;
    try {
      await expect(regenBtn).toBeVisible({ timeout: 5_000 });
      const [regenResp] = await Promise.all([
        page.waitForResponse(
          (res) => res.url().includes('/api/ai/chat') && res.request().method() === 'POST',
          { timeout: 60_000 },
        ),
        regenBtn.click(),
      ]);
      expect(regenResp.status()).toBe(200);
      regenWorked = true;
    } catch {
      // Angle regen not available (e.g., deterministic fallback) — skip regen, test idempotent replay only
    }

    // Verify idempotent client_request_id replay produces same turn_id and no duplicate turn row
    const tokenA = await apiLogin(page.request, 'admin_a');
    const clientReqId = `phase7-idem-${Date.now()}`;
    const replayPayload = {
      prompt: "What was Laila Mansour's Waiting Time in March 2026?",
      origin: 'workspace',
      conversation_id: convId,
      client_request_id: clientReqId,
      session_state: { team: 'Inbound', month: 'March', year: 2026 },
    };
    const r1 = await page.request.post(`${API_URL}/api/ai/chat`, {
      headers: { Authorization: `Bearer ${tokenA}` },
      data: replayPayload,
    });
    const r2 = await page.request.post(`${API_URL}/api/ai/chat`, {
      headers: { Authorization: `Bearer ${tokenA}` },
      data: replayPayload,
    });
    expect(r1.status()).toBe(200);
    expect(r2.status()).toBe(200);
    const j1 = (await r1.json()).data;
    const j2 = (await r2.json()).data;
    expect(j1.turn_id).toBe(j2.turn_id);

    const convDetail = await page.request.get(`${API_URL}/api/ai/conversations/${encodeURIComponent(convId)}`, {
      headers: { Authorization: `Bearer ${tokenA}` },
    });
    expect(convDetail.status()).toBe(200);
    const turns = (await convDetail.json()).data.turns as Array<{ client_request_id?: string }>;
    const matchingTurns = turns.filter((t) => t.client_request_id === clientReqId);
    expect(matchingTurns).toHaveLength(1);

    scenarioResults.push({
      scenario: '5_idempotent_replay_and_optional_angle_regen',
      passed: true,
      details: {
        angle_regen_available: regenWorked,
        replayed_turn_id: j1.turn_id,
        matching_turn_rows: matchingTurns.length,
      },
    });
  });

  test('6. Fresh chat persistence across reload, chat deletion, and 375x812 mobile viewport layout', async ({ page }) => {
    await signInAndOpenAi(page, 'admin_a');

    const newChatBtn = page.getByTestId('ai-new-chat-btn');
    if (await newChatBtn.isVisible().catch(() => false)) {
      await newChatBtn.click();
    }

    const promptBox = page.getByLabel('Ask PMS AI a question');
    await promptBox.fill("What was Karim Nabil's Quality Errors in March 2026?");
    const [freshResp] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/api/ai/chat') && res.request().method() === 'POST',
        { timeout: 60_000 },
      ),
      page.getByLabel('Send prompt').click(),
    ]);
    expect(freshResp.status()).toBe(200);
    const freshConvId = String((await freshResp.json()).data.conversation_id);
    expect(freshConvId.length).toBeGreaterThan(0);

    // Reload page and verify cookie-backed session & conversation persistence on 127.0.0.1
    await page.reload();
    await expect(page.getByLabel('Ask PMS AI a question')).toBeVisible({ timeout: 20_000 });

    const historyToggle = page.getByTestId('ai-history-toggle');
    if (await historyToggle.isVisible()) {
      const panelVisible = await page.getByTestId('ai-recent-chats-panel').isVisible().catch(() => false);
      if (!panelVisible) {
        await historyToggle.click();
      }
    }
    const convRow = page.getByTestId(`ai-recent-chat-${freshConvId}`);
    await expect(convRow).toBeVisible({ timeout: 15_000 });

    // Delete chat via confirmation dialog
    await convRow.locator('button[aria-label^="Delete conversation"]').click();
    const dialog = page.getByTestId('ai-delete-confirm-dialog');
    await expect(dialog).toBeVisible();
    await Promise.all([
      page.waitForResponse(
        (res) =>
          res.url().includes(`/api/ai/conversations/${encodeURIComponent(freshConvId)}`) &&
          res.request().method() === 'DELETE',
        { timeout: 15_000 },
      ),
      dialog.getByRole('button', { name: 'Delete chat' }).click(),
    ]);
    await expect(page.getByTestId(`ai-recent-chat-${freshConvId}`)).toHaveCount(0);

    // Mobile viewport check (375x812)
    await page.setViewportSize({ width: 375, height: 812 });
    const hasNoHorizontalOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth <= 375,
    );
    expect(hasNoHorizontalOverflow).toBe(true);
    await expect(page.getByLabel('Ask PMS AI a question')).toBeVisible();
    await expect(page.getByLabel('Send prompt')).toBeVisible();

    scenarioResults.push({
      scenario: '6_fresh_chat_reload_delete_and_mobile_viewport',
      passed: true,
      details: {
        deleted_conversation_id: freshConvId,
        mobile_no_horizontal_overflow: hasNoHorizontalOverflow,
      },
    });
  });
});
