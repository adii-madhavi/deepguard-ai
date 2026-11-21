import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";

test("video report separates timing and embedded speech, with offset-aware seeking", async ({
  page,
}, testInfo) => {
  const clip = testInfo.outputPath("shifted-av.mp4");
  const python = path.resolve(
    "..",
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  execFileSync(python, [
    path.resolve("../backend/test_av.py"),
    "--fixture",
    clip,
  ]);
  await page.goto("/");
  await page.getByRole("button", { name: "Video", exact: true }).click();
  await page.getByLabel("Select a video").setInputFiles(clip);
  await page
    .getByRole("button", { name: "Analyze video", exact: true })
    .click();
  const section = page.getByRole("region", {
    name: "Audio and video consistency",
    exact: true,
  });
  await expect(section).toBeVisible({ timeout: 120000 });
  await expect(
    section.getByText("Track boundaries differ", { exact: true }),
  ).toBeVisible();
  await expect(
    section.getByText("Lip-sync cue: No steady face found", { exact: true }),
  ).toBeVisible();
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export report" }).click();
  const download = await pending;
  const report = JSON.parse(await readFile((await download.path())!, "utf8"));
  expect(report.av_timing.start_offset_seconds).toBeGreaterThan(0.8);
  expect(report.embedded_audio.audio_summary.total_segments).toBe(2);
  expect(report.lip_sync.status).toBe("no_face");
  if (process.env.REQUIRE_MODEL === "1") {
    expect(report.model.status).toBe("completed");
    expect(report.embedded_audio.model.status).toBe("completed");
  }
  await section
    .getByRole("button", { name: "Inspect audio segment at 0:06.0" })
    .click();
  await expect
    .poll(() =>
      section
        .getByLabel("Embedded audio video player")
        .evaluate((element: HTMLVideoElement) => element.currentTime),
    )
    .toBeCloseTo(6 + report.embedded_audio.playback_offset_seconds, 1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("av-mobile.png"),
    fullPage: true,
  });
});
