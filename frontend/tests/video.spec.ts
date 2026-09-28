import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { readFile } from "node:fs/promises";

test("video report has real sampled scores, seeking, filtering, and export", async ({
  page,
}, testInfo) => {
  const clip = testInfo.outputPath("sample.mp4");
  const python = path.resolve(
    "..",
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  execFileSync(python, [
    path.resolve("../backend/test_video.py"),
    "--fixture",
    clip,
  ]);
  await page.goto("/");
  await page.getByRole("button", { name: "Video", exact: true }).click();
  await page.getByLabel("Select a video").setInputFiles(clip);
  await page
    .getByRole("button", { name: "Analyze video", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Image", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("region", { name: "Video frame timeline" }),
  ).toBeVisible({ timeout: 120000 });
  await expect(
    page.getByRole("region", { name: "Temporal consistency evidence" }),
  ).toBeVisible();
  const pendingDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export report" }).click();
  const download = await pendingDownload;
  expect(download.suggestedFilename()).toMatch(/\.json$/);
  const result = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(result.summary.sampled_frames).toBe(12);
  if (process.env.REQUIRE_MODEL === "1") {
    expect(result.model.status).toBe("completed");
    expect(result.summary.scored_frames).toBe(12);
  }
  await expect(
    page.getByRole("region", { name: "Video frame timeline" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Inspect frame at 0:01.00" }).click();
  await expect
    .poll(() =>
      page
        .getByLabel("Analysis video player")
        .evaluate((element: HTMLVideoElement) => element.currentTime),
    )
    .toBeCloseTo(1, 1);
  await page.getByLabel("Flagged only").check();
  await expect(page.getByRole("button", { name: /Inspect frame/ })).toHaveCount(
    result.summary.flagged_frames,
  );
  await page.getByLabel("Flagged only").uncheck();
  await page.screenshot({
    path: testInfo.outputPath("video-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("video-mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Image", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "Analysis results" }),
  ).toHaveCount(0);
});
