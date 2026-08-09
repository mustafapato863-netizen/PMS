import { defineConfig, devices } from '@playwright/test';

const edgeExecutable = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

export default defineConfig({
  testDir: './e2e',
  outputDir: 'artifacts/playwright-results',
  snapshotPathTemplate: 'e2e/__screenshots__/{projectName}/{arg}{ext}',
  timeout: 45_000,
  expect: {
    timeout: 30_000,
    toHaveScreenshot: {
      animations: 'disabled',
      maxDiffPixelRatio: 0.01,
    },
  },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 4,
  reporter: [['list'], ['html', { outputFolder: 'artifacts/playwright-report', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    locale: 'en-US',
    timezoneId: 'Africa/Cairo',
    colorScheme: 'light',
    reducedMotion: 'reduce',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    {
      name: 'edge',
      use: {
        ...devices['Desktop Edge'],
        launchOptions: { executablePath: edgeExecutable },
      },
    },
  ],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
