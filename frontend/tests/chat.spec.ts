import { test, expect } from "@playwright/test";

test("sends only the new turn, renders usage and recovers after a failed draft", async ({
  page,
}) => {
  const requests: Record<string, string>[] = [];
  await page.route("**/chat", async (route) => {
    const body = route.request().postDataJSON();
    requests.push(body);
    const failure = requests.length === 2;
    await route.fulfill({
      status: failure ? 503 : 200,
      json: failure
        ? { detail: "all providers unavailable" }
        : {
            session_id: body.session_id,
            reply: "Ready to help.",
            metadata: {
              model: "gemini/test",
              resolution_source: "LIVE_INFERENCE",
              latency_ms: 812,
              input_tokens: 42,
              output_tokens: 9,
              key_id: "key_1",
              fallback_attempts: 0,
            },
          },
    });
  });
  await page.goto("/");
  const input = page.getByTestId("chat-input");
  await input.fill("First");
  await page.getByTestId("send-button").click();
  const reply = page.getByTestId("assistant-message").first();
  for (const [id, value] of Object.entries({
    "meta-source": "LIVE_INFERENCE",
    "meta-model": "gemini/test",
    "meta-latency": "812 ms",
    "meta-input-tokens": "42",
    "meta-output-tokens": "9",
  })) {
    await expect(reply.getByTestId(id)).toHaveText(value);
  }
  await expect(input).toHaveValue("");
  await input.fill("Second");
  await input.press("Enter");
  await expect(page.getByRole("alert")).toContainText(
    "all providers unavailable",
  );
  await expect(input).toHaveValue("Second");
  await input.press("Enter");
  await expect(page.getByTestId("assistant-message")).toHaveCount(2);
  expect(requests[2]).toEqual({
    session_id: requests[0].session_id,
    message: "Second",
  });
  await page.reload();
  await input.fill("First");
  await input.press("Enter");
  await expect(page.getByTestId("assistant-message")).toHaveCount(1);
  expect(requests[3].session_id).not.toBe(requests[0].session_id);
});

test("validation errors leave the draft available for correction", async ({
  page,
}) => {
  await page.route("**/chat", (route) =>
    route.fulfill({
      status: 422,
      json: { detail: [{ msg: "String too long" }] },
    }),
  );
  await page.goto("/");
  await page.getByTestId("chat-input").fill("x".repeat(4001));
  await page.getByTestId("send-button").click();
  await expect(page.getByRole("alert")).toContainText("Check your message");
  await expect(page.getByTestId("chat-input")).toHaveValue("x".repeat(4001));
  await expect(page.getByTestId("assistant-message")).toHaveCount(0);
});

test("can compose a message when randomUUID is unavailable", async ({
  page,
}) => {
  await page.addInitScript(() =>
    Object.defineProperty(Crypto.prototype, "randomUUID", { value: undefined }),
  );
  await page.goto("/");
  await expect(page.getByTestId("chat-input")).toBeVisible();
  await expect(page.locator(".sid code")).toHaveText(/^[a-f0-9]{32}$/);
});

test("a timed-out request restores the draft", async ({ page }) => {
  await page.clock.install();
  await page.route("**/chat", () => {});
  await page.goto("/");
  const input = page.getByTestId("chat-input");
  await input.fill("Still there?");
  await input.press("Enter");
  await expect(page.getByRole("status")).toBeVisible();
  await page.clock.fastForward(91000);
  await expect(page.getByRole("alert")).toContainText("timed out");
  await expect(input).toHaveValue("Still there?");
});
