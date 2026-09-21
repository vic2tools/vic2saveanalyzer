#!/usr/bin/env python3
"""
A stand-in for the report host, for testing the Share button without deploying.

Speaks the same two things `host/worker.js` speaks -- POST /upload, and GET
/r/<id> -- and applies the same checks: the size cap, the marks that say this
is one of the analyzer's own reports, and the Content-Security-Policy that
sandboxes whatever it serves. The policy is read out of worker.js at startup
rather than copied here, so the two cannot drift apart.

    python3 mock_host.py 8753

Then put http://127.0.0.1:8753 into the analyzer under
Share -> Upload to a report host. The link it hands back opens in a browser
like a real one would.
"""

import http.server
import json
import os
import re
import secrets
import sys

# The Worker sits next to this, whatever the checkout is called.
WORKER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "host", "worker.js")
MAX_BYTES = 32 * 1024 * 1024
HEAD_BYTES = 96 * 1024
WANTED_HEAD = [b"<!DOCTYPE html>", b"<title>Campaign returns</title>",
               b"const PACKED"]
HELD = {}


def policy():
    """The Content-Security-Policy, lifted out of the Worker itself."""
    try:
        with open(WORKER, encoding="utf-8") as fh:
            block = re.search(r"const POLICY = \[(.*?)\]\.join", fh.read(),
                              re.S).group(1)
        return "; ".join(re.findall(r'"([^"]+)"', block))
    except Exception:
        return "default-src 'none'; script-src 'unsafe-inline'"


POLICY = policy()


class Host(http.server.BaseHTTPRequestHandler):
    def _json(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if self.path.rstrip("/") != "/upload":
            return self._json(404, {"error": "not found"})
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BYTES:
            return self._json(413, {"error": "reports over 32 MB are not taken"})
        body = self.rfile.read(size)
        if not body:
            return self._json(400, {"error": "empty upload"})
        head, tail = body[:HEAD_BYTES], body[-4096:]
        if not all(m in head for m in WANTED_HEAD) or b"</html>" not in tail:
            return self._json(400, {"error": "this is not a Victoria 2 "
                                             "campaign report"})
        key, secret = secrets.token_urlsafe(9), secrets.token_urlsafe(12)
        HELD[key] = (body, secret, self.headers.get("X-Report-Name", ""))
        here = "http://%s" % self.headers.get("Host", "127.0.0.1")
        print("  kept %.1f MB as %s  (%s)"
              % (len(body) / 1048576.0, key,
                 self.headers.get("X-Report-Name", "unnamed")))
        self._json(200, {"url": "%s/r/%s" % (here, key),
                         "delete": "%s/d/%s?k=%s" % (here, key, secret),
                         "keeps_until_days": 400})

    def do_GET(self):
        if self.path.startswith("/r/"):
            held = HELD.get(self.path[3:])
            if not held:
                return self._json(404, {"error": "no report here"})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", POLICY)
            self.send_header("Content-Length", str(len(held[0])))
            self.end_headers()
            self.wfile.write(held[0])
            return
        if self.path.startswith("/d/"):
            key = self.path[3:].split("?")[0]
            given = self.path.split("k=")[-1] if "k=" in self.path else ""
            held = HELD.get(key)
            if not held:
                return self._json(404, {"error": "already gone"})
            if given != held[1]:
                return self._json(403, {"error": "not the right link"})
            del HELD[key]
            print("  took down %s" % key)
            return self._json(200, {"ok": True})
        self._json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8753
    print("Pretending to be a report host on http://127.0.0.1:%d" % port)
    print("Policy served with every report:\n  %s\n" % POLICY)
    print("Put that address into Share -> Upload to a report host. Ctrl-C to "
          "stop; nothing is written to disk.\n")
    try:
        http.server.ThreadingHTTPServer(("127.0.0.1", port),
                                        Host).serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
