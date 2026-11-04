import { defineConfig } from "@playwright/test";
import { existsSync } from "node:fs";
// All test endpoints are loopback; never send local test traffic to a corporate HTTP proxy.
for (const key of [
  "HTTP_PROXY",
  "HTTPS_PROXY",
  "ALL_PROXY",
  "http_proxy",
  "https_proxy",
  "all_proxy",
])
  delete process.env[key];
process.env.NO_PROXY = "127.0.0.1,localhost";
const chrome =
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ||
  (existsSync("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    : undefined);
export default defineConfig({
  testDir: "tests/browser",
  fullyParallel: false,
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: "http://127.0.0.1:18774",
    viewport: { width: 1440, height: 1000 },
    launchOptions: { executablePath: chrome },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: ".venv/bin/python -m scripts.e2e_server",
      env: { E2E_API_PORT: "18770" },
      url: "http://127.0.0.1:18770/api/v1/health",
      reuseExistingServer: false,
      timeout: 60000,
    },
    {
      command:
        ".venv/bin/uvicorn examples.host_server:app --host 127.0.0.1 --port 18771",
      url: "http://127.0.0.1:18771/openapi.json",
      reuseExistingServer: false,
      env: {
        ENVIRONMENT: "development",
        AGENT_API: "http://127.0.0.1:18770/api/v1",
      },
      timeout: 30000,
    },
    {
      command: "npm run dev -w web -- --port 18774 --strictPort",
      url: "http://127.0.0.1:18774",
      reuseExistingServer: false,
      env: {
        AGENT_BACKEND_ORIGIN: "http://127.0.0.1:18770",
        HOST_BACKEND_ORIGIN: "http://127.0.0.1:18771",
      },
      timeout: 30000,
    },
  ],
});
