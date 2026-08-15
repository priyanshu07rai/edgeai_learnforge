"""
LearnForge — Lightweight SPA-aware static file server.
Serves the dist/ folder and falls back to index.html for unknown routes
(required for React Router client-side routing).
"""
import sys
import os
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

DIST_DIR = Path(__file__).parent / "dist"

class SPAHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    def do_GET(self):
        # Resolve requested path under dist/
        relative = self.path.split("?")[0].lstrip("/")
        file_path = DIST_DIR / relative

        # If the file doesn't exist and it's not an asset, serve index.html
        # so React Router can handle it client-side.
        if not file_path.exists() and not relative.startswith("assets/"):
            self.path = "/index.html"

        return super().do_GET()

    def log_message(self, format, *args):
        pass  # Suppress access logs to keep terminal clean

    def end_headers(self):
        # Security & caching headers
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache, must-revalidate")
        super().end_headers()


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5173

    if not DIST_DIR.exists():
        print(f"ERROR: dist/ folder not found at {DIST_DIR}", flush=True)
        sys.exit(1)

    server = HTTPServer((host, port), SPAHandler)
    print(f"LearnForge frontend serving on http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
