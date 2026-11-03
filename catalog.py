"""Laborator 4 SI - catalogul AI al "domeniului" laboratorului.

Publică ai-catalog.json la http://127.0.0.1:8080/.well-known/ai-catalog.json
Fișierul este citit la FIECARE cerere: îl puteți modifica fără să reporniți catalogul.
Rulare: python catalog.py
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FILE = Path(__file__).parent / "ai-catalog.json"
PATH = "/.well-known/ai-catalog.json"
PORT = 8080


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != PATH:
            self.send_error(404, "Nu există. Încercați " + PATH)
            return
        body = FILE.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/ai-catalog+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # un rând scurt pe cerere
        print("catalog:", self.command, self.path)


if __name__ == "__main__":
    print(f"Catalog AI: http://127.0.0.1:{PORT}{PATH}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
