import { test, expect } from "@playwright/test";

test("analyzed reports are listed, reopened, and deleted per browser", async ({
  page,
}) => {
  await page.goto("/");
  const history = page.getByRole("region", { name: "Recent reports" });
  await expect(history).toBeVisible();
  const encoded = await page.evaluate(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 40;
    canvas.height = 30;
    canvas.getContext("2d")!.fillRect(0, 0, 40, 30);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  const name = `history-${Date.now()}.png`;
  await page.getByLabel("Select an image").setInputFiles({
    name,
    mimeType: "image/png",
    buffer: Buffer.from(encoded, "base64"),
  });
  await page.getByRole("button", { name: "Analyze image" }).click();
  await expect(history.getByText(name)).toBeVisible({ timeout: 120000 });

  await page.reload();
  await history.getByText(name).click();
  await expect(page.getByText("SAVED REPORT")).toBeVisible();
  await expect(page.getByText("40 × 30")).toBeVisible();

  await history
    .getByRole("button", { name: `Delete saved report ${name}` })
    .click();
  await expect(history.getByText(name)).toHaveCount(0);
  await expect(
    page.getByRole("region", { name: "Analysis results" }),
  ).toHaveCount(0);
});
