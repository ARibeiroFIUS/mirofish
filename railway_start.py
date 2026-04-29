import http.server
import mimetypes
import os
import posixpath
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = APP_ROOT / "frontend" / "dist"
BACKEND_URL = "http://127.0.0.1:5001"
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def start_backend():
    env = os.environ.copy()
    env.setdefault("FLASK_HOST", "127.0.0.1")
    env.setdefault("FLASK_PORT", "5001")
    env.setdefault("FLASK_DEBUG", "False")
    env.setdefault("PYTHONUNBUFFERED", "1")

    return subprocess.Popen(
        [str(APP_ROOT / "backend" / ".venv" / "bin" / "python"), "run.py"],
        cwd=APP_ROOT / "backend",
        env=env,
    )


def wait_for_backend(proc, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"{BACKEND_URL}/health", timeout=2) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


class RailwayHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self.handle_request()

    def do_HEAD(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request()

    def do_PUT(self):
        self.handle_request()

    def do_PATCH(self):
        self.handle_request()

    def do_DELETE(self):
        self.handle_request()

    def handle_request(self):
        parsed = urllib.parse.urlsplit(self.path)
        if parsed.path == "/health" or parsed.path.startswith("/api/"):
            self.proxy_to_backend()
            return
        self.serve_static(parsed.path)

    def proxy_to_backend(self):
        body = None
        content_length = self.headers.get("Content-Length")
        if content_length:
            body = self.rfile.read(int(content_length))

        target = f"{BACKEND_URL}{self.path}"
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        request = urllib.request.Request(
            target,
            data=body,
            headers=headers,
            method=self.command,
        )

        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                self.send_response(response.status)
                self.copy_headers(response.headers)
                if self.command != "HEAD":
                    shutil.copyfileobj(response, self.wfile)
        except urllib.error.HTTPError as error:
            self.send_response(error.code)
            self.copy_headers(error.headers)
            if self.command != "HEAD":
                self.wfile.write(error.read())
        except Exception as error:
            message = f"Backend unavailable: {error}".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(message)

    def copy_headers(self, headers):
        for key, value in headers.items():
            if key.lower() not in HOP_BY_HOP_HEADERS:
                self.send_header(key, value)
        self.end_headers()

    def serve_static(self, request_path):
        if not STATIC_ROOT.exists():
            self.send_error(500, "Frontend build not found")
            return

        normalized = posixpath.normpath(urllib.parse.unquote(request_path)).lstrip("/")
        candidate = (STATIC_ROOT / normalized).resolve()
        try:
            candidate.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self.send_error(403)
            return

        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.exists():
            candidate = STATIC_ROOT / "index.html"

        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        content = candidate.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(content)

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()


def main():
    backend = start_backend()

    def shutdown(signum, frame):
        backend.terminate()
        try:
            backend.wait(timeout=20)
        except subprocess.TimeoutExpired:
            backend.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    if not wait_for_backend(backend):
        backend.terminate()
        raise SystemExit("Backend failed to become healthy")

    port = int(os.environ.get("PORT", "8080"))
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), RailwayHandler)
    print(f"MiroFish Railway gateway listening on 0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
