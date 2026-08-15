"""
LearnForge — SPA static file server + reverse proxy to FastAPI backend.

Routes:
  /assets/*          → serve from dist/assets/
  /favicon.ico etc   → serve from dist/
  /                  → serve dist/index.html (React SPA)
  /dashboard (etc)   → serve dist/index.html (React Router routes)
  Everything else    → proxy to http://localhost:8000 (FastAPI backend)
"""
import sys
import http.client
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import mimetypes

DIST_DIR = Path(__file__).parent / "dist"
BACKEND_HOST = "localhost"
BACKEND_PORT = 8000

# React Router routes served by index.html (SPA)
SPA_ROUTES = {"", "/", "/dashboard"}

# File extensions that are definitely frontend static assets
STATIC_EXTENSIONS = {
    ".js", ".css", ".html", ".ico", ".png", ".jpg", ".jpeg",
    ".gif", ".svg", ".woff", ".woff2", ".ttf", ".eot", ".map",
    ".webp", ".json", ".txt"
}


def is_static_asset(path: str) -> bool:
    p = path.split("?")[0]
    return Path(p).suffix.lower() in STATIC_EXTENSIONS


def file_in_dist(path: str):
    relative = path.split("?")[0].lstrip("/")
    candidate = DIST_DIR / relative
    return candidate if candidate.is_file() else None


class LearnForgeHandler(BaseHTTPRequestHandler):

    def _proxy_to_backend(self):
        try:
            conn = http.client.HTTPConnection(BACKEND_HOST, BACKEND_PORT, timeout=1800)
            body_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(body_len) if body_len > 0 else None
            forward_headers = {
                k: v for k, v in self.headers.items()
                if k.lower() not in ("host", "connection", "transfer-encoding")
            }
            forward_headers["Host"] = f"{BACKEND_HOST}:{BACKEND_PORT}"
            conn.request(self.command, self.path, body=body, headers=forward_headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            for header, value in resp.getheaders():
                if header.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(header, value)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp.read())
        except (ConnectionRefusedError, OSError) as e:
            self.send_error(502, f"Backend unavailable: {e}")

    def _serve_index(self):
        index = DIST_DIR / "index.html"
        if not index.exists():
            self.send_error(503, "App not built. Run start.sh first.")
            return
        content = index.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    def _serve_file(self, file_path):
        content = file_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        if file_path.suffix in (".js", ".css", ".woff2", ".woff"):
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _handle(self):
        path_only = self.path.split("?")[0].rstrip("/") or "/"
        if path_only in SPA_ROUTES:
            return self._serve_index()
        found = file_in_dist(self.path)
        if found:
            return self._serve_file(found)
        if is_static_asset(self.path):
            self.send_error(404, f"Static file not found: {self.path}")
            return
        self._proxy_to_backend()

    def do_GET(self):    self._handle()
    def do_POST(self):   self._proxy_to_backend()
    def do_PUT(self):    self._proxy_to_backend()
    def do_DELETE(self): self._proxy_to_backend()

    def log_message(self, fmt, *args):
        status = args[1] if len(args) > 1 else "???"
        path = args[0].split(" ")[1] if " " in args[0] else args[0]
        if not path.startswith("/assets/") or str(status) != "200":
            print(f"[LearnForge] {status} {path}", flush=True)


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5173
    if not DIST_DIR.exists() or not (DIST_DIR / "index.html").exists():
        print(f"ERROR: dist/index.html not found. Run start.sh first.", flush=True)
        sys.exit(1)
    server = HTTPServer((host, port), LearnForgeHandler)
    print(f"[LearnForge] Server on http://{host}:{port}/  (backend proxied to {BACKEND_HOST}:{BACKEND_PORT})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
