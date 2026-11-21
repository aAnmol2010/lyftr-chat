import { defineConfig } from "@playwright/test";
export default defineConfig({
  use: {
    baseURL: "http://127.0.0.1:4317",
    launchOptions: process.env.CHROME_PATH
      ? { executablePath: process.env.CHROME_PATH }
      : {},
  },
  webServer: {
    command: "npm run dev -- --port 4317 --strictPort",
    url: "http://127.0.0.1:4317",
    reuseExistingServer: false,
  },
});
