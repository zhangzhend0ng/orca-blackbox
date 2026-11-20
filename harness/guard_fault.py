"""Run-local transport fault. Always forwards the real guard, never invents OK."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import urllib.request


class GuardTransport:
    def __init__(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # HTTP headers contain a local credential; never log them.

            def do_GET(self):
                if self.path != "/status":
                    self.send_error(404)
                    return
                try:
                    request = urllib.request.Request("http://127.0.0.1:39772/status",
                        headers={"X-Guard-Token": self.headers.get("X-Guard-Token", "")})
                    with opener.open(request, timeout=1) as response:
                        data = response.read(16385)
                    if len(data) > 16384:
                        raise ValueError("guard_response_limit")
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception:
                    self.send_error(503)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.closed = False

    def close(self):
        if not self.closed:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
            self.closed = True
