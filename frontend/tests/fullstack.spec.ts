import { test, expect } from "@playwright/test";
test("browser reaches configured backend and receives a cache hit after reload", async ({
  page,
}) => {
  test.skip(!process.env.STACK_URL, "Requires a running full stack");
  await page.goto(process.env.STACK_URL!);
  const prompt = "Say hello. Reference " + Date.now();
  for (const expected of ["LIVE_INFERENCE", "LLM_CACHE"]) {
    await page.getByTestId("chat-input").fill(prompt);
    await page.getByTestId("send-button").click();
    await expect(page.getByTestId("meta-source")).toHaveText(expected, {
      timeout: 60000,
    });
    await page.reload();
  }
});
