import { defineConfig, devices } from '@playwright/test';

const output = process.env.PMS_E2E_OUTPUT;

export default defineConfig({
  testDir: './e2e',
  timeout: 180_000,
  expect: { timeout: 90_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: 'list',
  outputDir: output ? `${output.replace(/\\/g, '/')}/playwright-output` : 'e2e/artifacts/parts',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: process.env.PMS_E2E_URL ?? 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
});
