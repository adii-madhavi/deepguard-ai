import { test, expect } from "@playwright/test";

test("image upload produces an exportable report and works on mobile", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "A closer look. A clearer picture." }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Analyze image" }),
  ).toBeDisabled();
  // Generate a valid PNG in the browser; the backend receives and decodes real bytes.
  const encoded = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 48;
    const context = canvas.getContext("2d")!;
    context.fillStyle = "#147d70";
    context.fillRect(0, 0, 64, 48);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page
    .getByLabel("Select an image")
    .setInputFiles({
      name: "test-image.png",
      mimeType: "image/png",
      buffer: Buffer.from(encoded, "base64"),
    });
  await expect(page.getByAltText("Selected image preview")).toBeVisible();
  const pendingAnalysis = page.waitForResponse(
    (response) =>
      response.url().endsWith("/analyze") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Analyze image" }).click();
  const analysis = await (await pendingAnalysis).json();
  if (process.env.REQUIRE_MODEL === "1") {
    expect(analysis.model.status).toBe("completed");
    expect(analysis.ai_score).toBeGreaterThanOrEqual(0);
    expect(analysis.ai_score).toBeLessThanOrEqual(1);
  }
  await expect(
    page.getByRole("region", { name: "Analysis results" }),
  ).toBeVisible({ timeout: 120000 });
  await expect(page.getByText("64 × 48")).toBeVisible();
  const pendingDownload = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export report" }).click();
  expect((await pendingDownload).suggestedFilename()).toMatch(
    /^deepguard-.*\.json$/,
  );
  await page.screenshot({ path: "test-results/desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Export report" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Remove selected image" }).click();
  await expect(
    page.getByRole("region", { name: "Analysis results" }),
  ).toHaveCount(0);
});
