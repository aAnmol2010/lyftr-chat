import { useEffect, useRef, useState } from "react";
import { sendChat, type Metadata } from "./api";

type Turn = { message: string; reply: string; metadata: Metadata };
function Receipt({ meta: m }: { meta: Metadata }) {
  return (
    <dl className="receipt">
      {[
        ["Source", "meta-source", m.resolution_source],
        ["Model", "meta-model", m.model],
        ["Latency", "meta-latency", m.latency_ms + " ms"],
        ["Input tokens", "meta-input-tokens", m.input_tokens],
        ["Output tokens", "meta-output-tokens", m.output_tokens],
      ].map(([label, id, value]) => (
        <div key={id}>
          <dt>{label}</dt>
          <dd data-testid={id}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function App() {
  const [session] = useState(
    () =>
      crypto.randomUUID?.() ??
      Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) =>
        byte.toString(16).padStart(2, "0"),
      ).join(""),
  );
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [prompt, setPrompt] = useState("");
  const [savedPrompt, setSavedPrompt] = useState("");
  const [pending, setPending] = useState("");
  const [error, setError] = useState("");
  const busy = useRef(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (turns.length || pending || error)
      end.current?.scrollIntoView({ block: "nearest" });
  }, [turns, pending, error]);
  async function send() {
    const message = draft.trim();
    if (!message || busy.current) return;
    busy.current = true;
    setError("");
    setPending(message);
    setDraft("");
    try {
      const response = await sendChat({
        session_id: session,
        message,
        ...(prompt !== savedPrompt ? { system_prompt: prompt } : {}),
      });
      setTurns((previous) => [
        ...previous,
        { message, reply: response.reply, metadata: response.metadata },
      ]);
      setSavedPrompt(prompt);
    } catch (e) {
      setError(
        e instanceof TypeError
          ? "Could not reach the chat service. Please retry."
          : e instanceof Error
            ? e.message
            : "Please retry.",
      );
      setDraft(message);
    } finally {
      busy.current = false;
      setPending("");
      requestAnimationFrame(() => input.current?.focus());
    }
  }
  return (
    <>
      <header>
        <span className="brand">
          <b aria-hidden="true">↗</b> Lyftr
        </span>
        <span className="divider">/</span> Chat workspace
      </header>
      <main>
        <section className="conversation" aria-label="Conversation">
          <div className="topline">
            <h1>Conversation</h1>
            <button
              className="new"
              onClick={() => location.reload()}
              disabled={!!pending}
            >
              ＋ New chat
            </button>
          </div>
          <div className="messages" aria-live="polite">
            {!turns.length && !pending && !error && (
              <div className="empty">
                <span className="mark" aria-hidden="true">
                  ↗
                </span>
                <h2>Start a conversation.</h2>
                <p>Ask a question or set a system prompt for this chat.</p>
              </div>
            )}
            {turns.map((turn, i) => (
              <article key={i}>
                <div className="user">
                  <small>You</small>
                  <p>{turn.message}</p>
                </div>
                <div className="assistant" data-testid="assistant-message">
                  <small>Lyftr</small>
                  <p>{turn.reply}</p>
                  <Receipt meta={turn.metadata} />
                </div>
              </article>
            ))}
            {pending && (
              <article>
                <div className="user">
                  <small>You</small>
                  <p>{pending}</p>
                </div>
                <p role="status">Waiting for a reply…</p>
              </article>
            )}
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <div ref={end} />
          </div>
          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <textarea
              aria-label="Message"
              data-testid="chat-input"
              ref={input}
              placeholder="Write a message…"
              value={draft}
              disabled={!!pending}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <button
              data-testid="send-button"
              disabled={!!pending || !draft.trim()}
            >
              Send ↑
            </button>
          </form>
        </section>
        <aside>
          <h2>Session settings</h2>
          <label htmlFor="system">System prompt</label>
          <textarea
            id="system"
            maxLength={4000}
            data-testid="system-prompt-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={!!pending}
            placeholder="e.g. Answer in short paragraphs."
          />
          <p>Applies to your next message and later turns in this chat.</p>
          <div className="sid">
            <small>Session ID</small>
            <code>{session}</code>
          </div>
        </aside>
      </main>
    </>
  );
}
