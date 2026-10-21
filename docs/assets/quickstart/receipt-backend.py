"""CPU-only HTTP fixture with backend-owned nonce receipts for the Quickstart."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    args.receipt.touch(exist_ok=True)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            nonce = self.headers.get("X-Docs-Nonce", "")
            if nonce and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", nonce):
                with lock, args.receipt.open("a") as out:
                    out.write(nonce + "\n")
            body = json.dumps({"marker": "backend-llama"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = reply
        do_POST = reply

    server = ThreadingHTTPServer((args.listen, args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
