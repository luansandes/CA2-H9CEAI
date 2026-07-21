import json
import os
from http.server import BaseHTTPRequestHandler

from openai import OpenAI


MAX_MESSAGES = 20
MAX_MESSAGE_LENGTH = 8_000
ALLOWED_ROLES = {"user", "assistant"}


def allowed_origins():
    configured = os.environ.get("FRONTEND_ORIGIN", "")
    origins = {origin.strip() for origin in configured.split(",") if origin.strip()}
    origins.update({"http://localhost:8000", "http://127.0.0.1:8000"})
    return origins


class handler(BaseHTTPRequestHandler):
    def _origin(self):
        origin = self.headers.get("Origin", "")
        return origin if origin in allowed_origins() else ""

    def _send_json(self, status, payload):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self):
        origin = self._origin()
        if not origin:
            self._send_json(403, {"error": "Origin is not allowed."})
            return

        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Vary", "Origin")
        self.end_headers()

    def do_POST(self):
        if self.headers.get("Origin") and not self._origin():
            self._send_json(403, {"error": "Origin is not allowed."})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0 or content_length > 200_000:
                raise ValueError("Invalid request size.")

            body = json.loads(self.rfile.read(content_length))
            messages = body.get("messages")
            if not isinstance(messages, list) or not messages:
                raise ValueError("A non-empty messages array is required.")

            cleaned_messages = []
            for item in messages[-MAX_MESSAGES:]:
                if not isinstance(item, dict):
                    raise ValueError("Each message must be an object.")
                role = item.get("role")
                content = item.get("content")
                if role not in ALLOWED_ROLES or not isinstance(content, str):
                    raise ValueError("Each message needs a valid role and text content.")
                content = content.strip()
                if not content or len(content) > MAX_MESSAGE_LENGTH:
                    raise ValueError("A message is empty or too long.")
                cleaned_messages.append({"role": role, "content": content})

            client = OpenAI()
            response = client.responses.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-5.6-sol"),
                instructions=(
                    "You are a helpful, concise assistant. Answer clearly and be honest "
                    "when you are uncertain."
                ),
                input=cleaned_messages,
            )
            self._send_json(200, {"message": response.output_text})
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": str(error)})
        except Exception as error:
            print(f"Chat request failed: {error}")
            self._send_json(500, {"error": "The assistant is temporarily unavailable."})

