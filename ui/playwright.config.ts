import { defineConfig, devices } from '@playwright/test';
export default defineConfig({
  testDir: './e2e', timeout: 30000, fullyParallel: true,
  workers: 2,
  expect: { timeout: 15000 },
  use: { baseURL: 'http://127.0.0.1:8767', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
    { name: 'dark', use: { ...devices['Desktop Chrome'], colorScheme: 'dark' } },
    { name: 'mobile', use: { ...devices['Pixel 7'] } },
  ],
  webServer: { command: `${process.env.CORSAIR_UI_PYTHON || 'uv run --locked python'} e2e/server.py`,
    url: 'http://127.0.0.1:8767/api/health', reuseExistingServer: false, timeout: 120000 },
});
