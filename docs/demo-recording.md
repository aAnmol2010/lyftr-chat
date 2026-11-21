# Record the Lyftr Chat demo

Aim for 2 minutes 20 seconds. Record your screen and your own microphone. For rehearsal, open the local demo on port 3100 and use `http://localhost:8100` as the API. For the submission take, use the public frontend and public backend with two working Gemini keys.

Before recording, open the frontend, a terminal, and the public repository in separate tabs. In the terminal set `API` to the backend origin and run `SID="video-$(date +%s)"`. Pick a fresh word or number for the opening message on every take so you can show a cold request. Copy that message before sending it.

| Time | On screen | Suggested narration |
| --- | --- | --- |
| 0:00–0:15 | Show the public frontend address, then run the health command below. | “This chat uses React, FastAPI and Gemini. The health endpoint shows how many provider keys are loaded and whether response caching is enabled.” |
| 0:15–0:45 | Send “Remember my project name is Atlas-731. Reply with its name.” Substitute your fresh identifier. Ask “What name did I give you?” Point to the metadata for each reply. | “The backend loads the conversation for this session, so the second turn can recall the name. Each reply shows its model, elapsed milliseconds and the tokens used for that request.” |
| 0:45–1:05 | Reload, paste the exact opening message, and show the cached reply beside its metadata. | “Reloading starts a new session. The first message and system prompt match the original request, so LiteLLM serves the stored answer. The reply and usage match, and the latency is measured again.” |
| 1:05–1:40 | Run the fallback command below. Point to the reply, key ID and fallback count. | “This header simulates a rate limit on key one for this request. Key two still calls Gemini. The response identifies the key that answered and the one failed attempt.” |
| 1:40–2:10 | Save and display the successful session history. Send the wildcard failure. Compare history again. | “SQLite contains one successful user and assistant pair. With every key unavailable the server returns HTTP 503. Comparing the two history responses shows that the failed turn added nothing.” |
| 2:10–2:20 | Show the public repository and its README. | “The repository includes the Docker setup, automated tests and commands to reproduce these checks.” |

Run the commands individually so the response stays on screen. They require curl, Python 3 and a shell. Keep the same terminal open for the whole take.

```sh
curl -fsS "$API/health" | python3 -m json.tool

curl -fsS "$API/chat" -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: key_1=429' \
  -d "{\"session_id\":\"$SID\",\"message\":\"Greet the viewer in one sentence.\"}" | python3 -m json.tool

BEFORE=$(mktemp)
curl -fsS "$API/sessions/$SID/messages" > "$BEFORE"
python3 -m json.tool "$BEFORE"

curl -sS -w '\nHTTP %{http_code}\n' "$API/chat" -H 'Content-Type: application/json' \
  -H 'X-Simulate-Failure: *=429' \
  -d "{\"session_id\":\"$SID\",\"message\":\"Try one more turn.\"}"

AFTER=$(mktemp)
curl -fsS "$API/sessions/$SID/messages" > "$AFTER"
cmp "$BEFORE" "$AFTER" && echo 'History unchanged'
```

Before submitting, play the uploaded video signed out. Check its duration, microphone audio and legibility of the reply metadata and the 503 response. Open the frontend, backend health page and GitHub links signed out as well.
