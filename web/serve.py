"""Try the web app locally: python web/serve.py   then open http://localhost:8000

Rebuilds the engine bundle first, then serves this folder. Browsers only run JavaScript modules
served as text/javascript, and on some Windows machines Python's built-in server guesses a
different type from the registry, so the types are set here explicitly.
"""

import functools
import http.server
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TYPES = {".js": "text/javascript", ".json": "application/json", ".wasm": "application/wasm", ".css": "text/css", ".html": "text/html"}


class Handler(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **TYPES}


def main(port=8000):
    sys.path.insert(0, str(HERE))
    import build_engine

    build_engine.build()
    handler = functools.partial(Handler, directory=str(HERE))
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"MiniSpice is running at http://localhost:{port}  (Ctrl+C to stop)")
        server.serve_forever()


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
