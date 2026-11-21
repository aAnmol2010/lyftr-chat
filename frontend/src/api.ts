export type Metadata = {
  resolution_source: "LLM_CACHE" | "LIVE_INFERENCE";
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  key_id: string | null;
  fallback_attempts: number;
};
type ChatRequest = {
  session_id: string;
  message: string;
  system_prompt?: string;
};
export async function sendChat(
  request: ChatRequest,
): Promise<{ reply: string; metadata: Metadata }> {
  const url = (
    import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
  ).replace(/\/$/, "");
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 90_000);
  try {
    const res = await fetch(url + "/chat", {
      signal: controller.signal,
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const body = await res.json().catch(() => null);
    if (!res.ok)
      throw new Error(
        typeof body?.detail === "string"
          ? body.detail
          : res.status === 422
            ? "Check your message and try again."
            : "The chat service is unavailable. Please retry.",
      );
    const m = body?.metadata;
    if (
      typeof body?.reply !== "string" ||
      !m ||
      !["LLM_CACHE", "LIVE_INFERENCE"].includes(m.resolution_source) ||
      typeof m.model !== "string" ||
      ![m.latency_ms, m.input_tokens, m.output_tokens].every(Number.isInteger)
    ) {
      throw new Error(
        "The service returned an incomplete reply. Please retry.",
      );
    }
    return body;
  } catch (error) {
    if (controller.signal.aborted)
      throw new Error("The request timed out. Please try again.");
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}
