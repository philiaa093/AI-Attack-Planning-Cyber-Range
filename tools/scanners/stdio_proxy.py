"""Container-local HTTP proxy; its only upstream is the host's stdio safety gate."""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Length", "0") != "0":
            self.send_error(405)
            return
        print(json.dumps({"method": self.command, "url": self.path}), flush=True)
        line = sys.stdin.buffer.readline(4 * 1024 * 1024 + 1)
        if not line or len(line) > 4 * 1024 * 1024:
            raise RuntimeError("Gate channel unavailable")
        response = json.loads(line)
        body = response["body"].encode("utf-8")
        self.send_response_only(response["status"])
        for name, value in response["headers"].items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    do_HEAD = do_GET


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8081), Proxy)
    server.timeout = 1
    print('{"ready":true}', flush=True)
    server.serve_forever()
