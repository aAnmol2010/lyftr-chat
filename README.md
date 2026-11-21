# Lyftr Chat

A React chat client backed by FastAPI, Gemini through LiteLLM, and persistent SQLite history. Each reply shows its source, model, latency and input/output token counts.

## Live URLs

- [Live chat on Render](https://lyftr-chat-dc7y.onrender.com/)
- [Railway API](https://lyftr-chat-lyftr-chat1.up.railway.app) and [health check](https://lyftr-chat-lyftr-chat1.up.railway.app/health)
- [Public GitHub repository](https://github.com/aAnmol2010/lyftr-chat)

For deployment, build the backend using `backend/` as the Docker context. Run one replica with a writable persistent disk at `/data`, both credentials in the service's secret store, `DATABASE_URL=sqlite:////data/app.db`, `ENABLE_FAILURE_SIMULATION=true`, and `ALLOWED_ORIGINS` set to the frontend HTTPS origin. The container honors the host's `PORT`. Its entrypoint sets ownership of the mounted /data directory, then runs the service as UID 10001. On a platform that enforces a non-root entrypoint, provision the disk writable by that UID. Verify history survives a restart on the selected host. Build the frontend using `frontend/` as the root, `npm ci && npm run build`, output directory `dist`, and the public HTTPS backend origin in `VITE_API_BASE_URL`. Rebuild after changing that variable. Verify the two services, the GitHub repository and the narrated video while signed out.

## Run locally: with Docker and without

**Docker.** Install Docker Compose and Make. From the repository root:

```sh
test -f .env || cp .env.example .env
make up
```

Add two distinct working Gemini credentials to the ignored `.env` as `LLM_API_KEYS=first,second`. Run `make up` again after editing. The frontend and history endpoint can start with no keys. Readiness and chat return JSON 503 until the pool is configured. The configurable default is `gemini/gemini-3.5-flash-lite`. Check access to the selected model for both credentials.

Use `make down` to stop. The named volume preserves history. If port 3000 is occupied, set `FRONTEND_PORT=3100` and `ALLOWED_ORIGINS=http://localhost:3100` together.

**Native.** Install Python 3.12, uv, Node 22 and npm. Copy the environment example as above. In one terminal, from the repository root:

```sh
set -a
. ./.env
set +a
cd backend
export DATABASE_URL=sqlite:///./data/app.db
uv sync --frozen
uv run uvicorn app.main:create_app --factory --port 8000
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

**Credential-free integration stack.** This test overlay supplies a local Gemini-compatible HTTP service with a clearly labeled fixture reply and test usage values. The production image and ordinary Compose configuration use Gemini. From the repository root:

```sh
make demo
python3 scripts/verify_live.py http://localhost:8100
```

Open [the fixture-backed chat](http://localhost:3100). The verifier prints a session ID. Run `make demo-down` then `make demo`, wait for readiness, and fetch `http://localhost:8100/sessions/<id>/messages` to see the original conversation after recreation. This separate project uses its own SQLite volume. `make demo-down` stops it.

## Design decisions: key fallback, caching, SQLite session storage

- Each key receives a stable positional alias. The embedded LiteLLM Router follows an ordered fallback list, with no same-key retries and a bounded request deadline. A successful response reports the serving alias and the number of earlier failed attempts. When all deployments fail, the API returns 503.
- The failure header selects dedicated error deployments for that request only. The surviving aliases use the usual provider transport. Simulated calls bypass cache reads and writes, so a warm reply cannot mask exhaustion.
- LiteLLM's built-in local cache stores validated reply text and per-request usage under the provider-qualified model and full ordered roles and content. Equivalent conversations can reuse an answer across sessions. Hits retain the original usage and measure fresh latency. Entries expire after 600 seconds, can be evicted at the pinned SDK’s 200-entry capacity, and disappear on backend restart. The gateway calls LiteLLM’s built-in cache directly so it can skip both lookup and storage during failure simulation and cache only validated responses. Two identical cold requests arriving together can both reach the provider.
- An async lock orders turns in each session. The model receives the most recent 20 complete turns by default (configure MAX_HISTORY_TURNS), followed by the new message. SQLite retains the full transcript for the history endpoint. Reads and writes during chat run off the event loop. A short SQLite transaction commits the prompt change, user message, assistant reply and metadata together after inference. SQLite write-ahead logging and a named disk volume support local persistence. Session IDs are bearer-like identifiers for this public demo. Use generated IDs and nonsensitive prompts.

## Verification: how to see failover, cache hits and per-message token usage

Run `python3 scripts/verify_live.py <backend-url>` against a configured backend. It makes inference requests, verifies all three endpoints, and checks clean 422/503 errors and unchanged history. A new run uses a unique prompt. Replace `<backend-url>` with the actual origin.

In the browser, send an opening message and a follow-up. Each assistant reply has its own usage and latency. Reload and send the same opening message with the same system prompt to see `LLM_CACHE`. Use a unique opening message for a cold demonstration.

```sh
curl -s http://localhost:8000/health
curl -s http://localhost:8000/chat -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=429' -d '{"session_id":"demo","message":"Say hello"}'
curl -s http://localhost:8000/sessions/demo/messages
```

A healthy second key returns a real reply, `key_id=key_2` and `fallback_attempts=1`. Replace the header value with `*=429` to get the exact 503 detail. The header accepts 429, 500, 502 and 503. With simulation disabled it is ignored.

Compose and the example environment enable failure simulation for evaluation. A native run with the variable unset disables it. The public chat endpoint has no authentication or application-level rate limit. Configure provider spending limits and host-level request limits before opening it to public traffic.

Run the backend suite with `cd backend && uv sync --frozen && uv run pytest -q`. The routing tests need localhost sockets. In `frontend/`, run `npm ci && npm run build && npx playwright install chromium && npm test`. Set `STACK_URL` to the running frontend origin to include the full-stack browser check. Alternatively point `CHROME_PATH` at a local Chromium or Chrome executable.

## Setup Used: your editor and AI tools

Codex desktop with the Superpowers workflow for planning, implementation and independent review. The project uses uv for the Python lockfile, npm for frontend dependencies, and Docker Compose for local integration.

## Bonus features (if any): what you added beyond the requirements and why

The optional session prompt accepts up to 4000 characters after trimming. Clearing it restores the configured default on the next successful turn. Failed sends retain the draft for an explicit retry. The credential-free test overlay lets reviewers exercise the transport, router, cache, database and browser together before configuring provider access.
