"""Standard library HTTP server. No framework, no install, one command to run.

Logging deliberately never records the question. The product promise is that
nothing personal is stored, and a web log full of people's circumstances would
break that promise quietly, which is the worst way to break one.
"""
from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .. import config, store
from ..pipeline import answer, plan

WEB = config.ROOT / "web"


class Handler(SimpleHTTPRequestHandler):
    # The fixture corpus lives in one in-memory connection that requests take turns
    # on. The crawled corpus is a file, so each request opens its own connection and
    # /api/plan answers while /api/answer is still writing. Threads matter either
    # way: without them a browser's idle preconnect socket blocks every request.
    conn = None
    shared = False
    lock = threading.Lock()

    @contextmanager
    def _db(self):
        if type(self).shared:
            with type(self).lock:
                yield type(self).conn
        else:
            conn = store.open_conn()
            try:
                yield conn
            finally:
                conn.close()

    def _question(self, parsed):
        params = parse_qs(parsed.query)
        question = (params.get("q") or [""])[0].strip()
        language = (params.get("lang") or [None])[0]
        if not question:
            return None, None, (400, {"error": "q is required"})
        if len(question) > 500:
            return None, None, (400, {"error": "question too long"})
        return question, language, None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def end_headers(self):
        # Static files carry no cache header by default, so a browser keeps serving
        # yesterday's page after an edit. Revalidate every time; it is one file.
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    # Quiet the default logger, which prints the full request line including the
    # query string, and therefore the question.
    def log_message(self, fmt, *args):  # noqa: A002
        return

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            return self._json(200, self._health())
        if parsed.path == "/api/plan":
            question, language, err = self._question(parsed)
            if err:
                return self._json(*err)
            with self._db() as conn:
                return self._json(200, plan(question, conn=conn, language=language))
        if parsed.path == "/api/answer":
            question, language, err = self._question(parsed)
            if err:
                return self._json(*err)
            with self._db() as conn:
                response = answer(question, conn=conn, language=language)
            meta = response.get("meta", {})
            print(f"  answered len={len(question)} lang={response['language']} "
                  f"refusal={(response.get('refusal') or {}).get('class')} "
                  f"conf={response.get('confidence')} ms={meta.get('elapsed_ms')}")
            return self._json(200, response)
        return super().do_GET()

    def _health(self) -> dict:
        with self._db() as conn:
            counts = store.counts(conn) if conn else {}
        return {"status": "ok", "demo_mode": config.DEMO_MODE,
                "provider": config.LLM_PROVIDER, "embedder": config.EMBED_PROVIDER,
                "score_floor": config.SCORE_FLOOR, **counts}

    def _json(self, status: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def serve(port: int | None = None, host: str = "127.0.0.1") -> None:
    port = port or int(os.environ.get("PORT", "8000"))
    use_fixture = not config.DB_PATH.exists() or os.environ.get("SAAL_FIXTURE") == "1"
    if use_fixture:
        from ..testing import fixture_conn
        Handler.conn, Handler.shared = fixture_conn(), True
        print("no crawled corpus found, serving the synthetic fixture corpus")
        print(f"corpus: {store.counts(Handler.conn)}")
    else:
        with store.connect() as conn:
            print(f"corpus: {store.counts(conn)}")
    print(f"provider: {config.LLM_PROVIDER}  demo_mode: {config.DEMO_MODE}")
    print(f"http://{host}:{port}")
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    serve()
