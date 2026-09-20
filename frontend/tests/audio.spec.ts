import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

test("audio segments, real scores, seeking, export, and mobile layout", async ({
  page,
}, testInfo) => {
  const clip = testInfo.outputPath("sample.wav");
  const python = path.resolve(
    "..",
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  execFileSync(python, [
    path.resolve("../backend/test_audio.py"),
    "--fixture",
    clip,
  ]);
  await page.goto("/");
  await page.getByRole("button", { name: "Audio", exact: true }).click();
  await page.getByLabel("Select an audio file").setInputFiles(clip);
  await page
    .getByRole("button", { name: "Analyze audio", exact: true })
    .click();
  await expect(
    page.getByRole("region", { name: "Audio segment timeline" }),
  ).toBeVisible({ timeout: 120000 });
  const pendingDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export report" }).click();
  const download = await pendingDownload;
  const result = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(result.audio_summary.total_segments).toBe(2);
  if (process.env.REQUIRE_MODEL === "1") {
    expect(result.model.status).toBe("completed");
    expect(result.audio_summary.scored_segments).toBe(2);
    expect(result.ai_score).toBeGreaterThanOrEqual(0);
    expect(result.ai_score).toBeLessThanOrEqual(1);
  }
  await page
    .getByRole("button", { name: "Inspect audio segment at 0:06.0" })
    .click();
  await expect
    .poll(() =>
      page
        .getByLabel("Analysis audio player")
        .evaluate((element: HTMLAudioElement) => element.currentTime),
    )
    .toBeCloseTo(6, 1);
  await page.getByLabel("Flagged only").check();
  await expect(
    page.getByRole("button", { name: /Inspect audio segment/ }),
  ).toHaveCount(result.audio_summary.flagged_segments);
  await page.getByLabel("Flagged only").uncheck();
  await page.screenshot({
    path: testInfo.outputPath("audio-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("audio-mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Video", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Analysis results" }),
  ).toHaveCount(0);
});
