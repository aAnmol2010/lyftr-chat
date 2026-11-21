import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import sleep


class GeminiFixture(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        sleep(0.12)
        reply = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": "Hello from the local test fixture."}],
                    },
                    "finishReason": "STOP",
                    "index": 0,
                }
            ],
            "usageMetadata": {
                "promptTokenCount": len(json.dumps(request)) // 4,
                "candidatesTokenCount": 8,
            },
            "modelVersion": "gemini-2.5-flash-lite",
        }
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


ThreadingHTTPServer(("0.0.0.0", 9000), GeminiFixture).serve_forever()
