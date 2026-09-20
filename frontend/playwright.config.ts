import { defineConfig } from "@playwright/test";

export default defineConfig({
  workers: 1,
  testDir: "./tests",
  timeout: 150000,
  use: {
    baseURL: "http://127.0.0.1:3000",
    browserName: "chromium",
    channel: "chrome",
    headless: true,
  },
});
