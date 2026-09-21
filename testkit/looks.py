#!/usr/bin/env python3
"""
Take a picture of a built report, so somebody can look at it.

Everything else here counts things. Counting found eight tabs, eight
tables and three hundred and fifty-two rows in a report whose first page
was blank, because the panel it opened on still had its children and every
section inside them was hidden. Looking at it found that in one glance.

    python3 testkit/looks.py out/report.html shot.png [tab-wars]

The report unpacks and draws after the page loads, and Firefox screenshots
at load, so this holds the load event open with an image served slowly
from the loopback address -- the page's own work carries on while it
waits. Pass a tab id to click it a moment before the shot.

Nothing here can pass or fail on its own; it is for eyes. `boots.py` is
the automated half, and it now checks the one thing this caught.
"""

import base64
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

# One transparent pixel, served late.
PIXEL = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAj"
    "CB0C8AAAAASUVORK5CYII=")


def slow_pixel(delay):
    """A server that answers one image after `delay`. (port, stop)."""
    class Slow(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                # noqa: N802
            time.sleep(delay)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(PIXEL)))
            self.end_headers()
            self.wfile.write(PIXEL)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Slow)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1], server.shutdown


def shoot(report, out, tab=None, delay=7, size="1500,1400"):
    """Screenshot `report` once it has had time to draw itself."""
    firefox = shutil.which("firefox")
    if firefox is None:
        return False
    port, stop = slow_pixel(delay)
    holding = tempfile.mkdtemp(prefix="vic2looks")
    try:
        profile = os.path.join(holding, "profile")
        os.makedirs(profile)
        with open(os.path.join(profile, "user.js"), "w") as fh:
            fh.write('user_pref("datareporting.policy.dataSubmissionEnabled",'
                     ' false);\n')
        with open(report, encoding="utf-8") as fh:
            html = fh.read()
        wait = ('<img src="http://127.0.0.1:%d/slow.png" '
                'style="position:fixed;left:-99px">' % port)
        click = ("<script>window.addEventListener('DOMContentLoaded',"
                 "function(){setTimeout(function(){var t="
                 "document.getElementById(%r);if(t)t.click();},2500);});"
                 "</script>" % tab) if tab else ""
        at = html.index("</body>") if "</body>" in html else len(html)
        page = os.path.join(holding, "page.html")
        with open(page, "w", encoding="utf-8") as fh:
            fh.write(html[:at] + wait + click + html[at:])
        subprocess.run([firefox, "--headless", "--no-remote",
                        "--profile", profile, "--window-size", size,
                        "--screenshot", out, "file://" + page],
                       capture_output=True, timeout=180)
    finally:
        stop()
        shutil.rmtree(holding, ignore_errors=True)
    return os.path.isfile(out)


def main():
    if len(sys.argv) < 3:
        print(__doc__.strip())
        return 2
    tab = sys.argv[3] if len(sys.argv) > 3 else None
    if not shoot(sys.argv[1], sys.argv[2], tab):
        print("no firefox here, or nothing was written")
        return 1
    print("wrote %s (%.0f KB)"
          % (sys.argv[2], os.path.getsize(sys.argv[2]) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
