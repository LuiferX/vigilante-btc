#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""serve-estado.py — HTTP SOLO localhost:8000 con docs/ + estado.json.

Solo stdlib (http.server). Escucha en 127.0.0.1 a proposito:
la Page publica (GitHub Pages) lee estado.json por fetch de su propio
origen tras `git push` de docs/, NO contra este servidor.

ADVERTENCIA: NO expongas este puerto a internet sin auth (reverse proxy
con usuario/clave o tunel SSH). Sin auth, cualquiera leeria tu estado.
Por eso el bind es 127.0.0.1 y verify.sh falla si ve 0.0.0.0:8000.

Rutas:
  /               -> docs/index.html (o listado de docs/)
  /<archivo>      -> docs/<archivo>
  /estado.json    -> <repo>/estado.json (para preview local)

Env overrides: VIGILANTE_REPO (def /opt/vigilante), BIND (def 127.0.0.1),
PORT (def 8000). Cache: Cache-Control: no-store en todo.
"""

import functools
import http.server
import json
import os

REPO = os.environ.get("VIGILANTE_REPO", "/opt/vigilante")
DOCS = os.path.join(REPO, "docs")
ESTADO = os.path.join(REPO, "estado.json")
BIND = os.environ.get("BIND", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

if BIND not in ("127.0.0.1", "::1", "localhost"):
    raise SystemExit("Por seguridad solo se permite bind en localhost (BIND=%s)" % BIND)


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/estado.json":
            try:
                with open(ESTADO, "rb") as fh:
                    data = fh.read()
                # Valida que sea JSON antes de servirlo.
                json.loads(data.decode("utf-8"))
            except FileNotFoundError:
                self.send_error(404, "estado.json aun no generado")
                return
            except (ValueError, UnicodeDecodeError):
                self.send_error(500, "estado.json corrupto")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()

    def log_message(self, fmt, *args):  # log sobrio a stdout (journald)
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    os.makedirs(DOCS, exist_ok=True)
    handler = functools.partial(Handler, directory=DOCS)
    with http.server.ThreadingHTTPServer((BIND, PORT), handler) as srv:
        print("sirviendo %s (+ estado.json) en http://%s:%d (solo localhost)" % (DOCS, BIND, PORT))
        srv.serve_forever()
