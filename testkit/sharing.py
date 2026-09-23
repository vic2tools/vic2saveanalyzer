#!/usr/bin/env python3
"""
Every way uploading a report can go wrong, and the one way it goes right.

`publish.upload` is the share button: it sends one file to a host and gets
a link back. It is aimed at somebody who wants to show a friend their
campaign and would not know what to do with a stack trace, so almost all of
it is error messages -- seven of them -- and none had ever been run.

    python3 testkit/sharing.py

Answers come from little servers started here on the loopback address, one
per behaviour: a host that is not listening, one that answers something
that is not JSON, one that takes the file and forgets to say where it put
it, one that says the report is too large, one that refuses it outright,
and one that does the right thing. Nothing leaves this machine and no real
report is used -- the file uploaded is a few bytes of made-up HTML.
"""

import http.server
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

import publish                                             # noqa: E402

A_REPORT = b"<!doctype html><title>Not a real report</title><p>hello"


def a_host(answer):
    """
    A server on the loopback address that answers however `answer` says.

    `answer` is (status, body bytes, content type). Returns (url, stop),
    and `stop` shuts it down. Threading, because a server that can only
    answer one request at a time deadlocks the moment anything retries.
    """
    class One(http.server.BaseHTTPRequestHandler):
        def do_POST(self):                               # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            status, body, kind = answer
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):                       # quiet
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), One)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return "http://127.0.0.1:%d" % port, server.shutdown


def a_closed_port():
    """An address with nothing listening on it."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return "http://127.0.0.1:%d" % port


def refuses(path, endpoint, expect, name=None):
    """[what went wrong] when the upload should fail saying `expect`."""
    try:
        url = publish.upload(path, endpoint, name=name)
    except publish.PublishError as said:
        if expect in str(said):
            return [], str(said)
        return (["said %r, which does not mention %r" % (str(said), expect)],
                str(said))
    except Exception as boom:                            # noqa: BLE001
        return (["raised %s instead of a PublishError: %s"
                 % (type(boom).__name__, boom)], "")
    return ["took it and answered %s, when it should have refused" % url], ""


def a_refused_token(holding, report):
    """
    [what went wrong] when GitHub turns the token down.

    The window keeps the token once it has been pasted, and hands it back
    on every press. A token GitHub will not take -- mistyped, or expired,
    which every fine-grained one does by default -- was handed back too,
    every time, with no way in the program to give it another; the only way
    out was editing the settings file by hand. So a refusal has to be told
    apart from the other failures, and the window has to forget the token
    when it hears one. The settings file is one of this check's own.
    """
    import queue
    import types

    class NoToken(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                # noqa: N802
            body = b'{"message": "Bad credentials"}'
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), NoToken)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    wrong = []
    try:
        try:
            publish.publish(report, "ghp_expired", base=base)
            wrong.append("a refused token was published with")
        except publish.TokenRefused:
            pass
        except Exception as boom:                        # noqa: BLE001
            wrong.append("a refused token raised %s, not TokenRefused"
                         % type(boom).__name__)

        try:
            import app
            import gui
        except Exception:                                # noqa: BLE001
            print("  a refused token is forgotten: no tkinter here, not tried")
            return wrong
        real, gui.SETTINGS = gui.SETTINGS, os.path.join(holding, "settings.json")
        real_publish = publish.publish
        try:
            gui.save_settings({"github_token": "ghp_expired", "saves": "x"})
            publish.publish = lambda *a, **k: real_publish(*a, base=base,
                                                           **{n: v for n, v in k.items()
                                                              if n != "base"})
            told = []
            window = types.SimpleNamespace(
                analyzer=types.SimpleNamespace(log_queue=queue.Queue()),
                root=types.SimpleNamespace(after=lambda _ms, fn, *a: told.append(a)),
                publish_failed=None, published=None)
            app.Tools._publish(window, report, "ghp_expired", "a campaign", [])
            after = gui.load_settings()
        finally:
            publish.publish = real_publish
            gui.SETTINGS = real
        if "github_token" in after:
            wrong.append("a token GitHub refused is still held, so the next "
                         "press hands it back again")
        if after.get("saves") != "x":
            wrong.append("forgetting the token took other settings with it")
        if not any("forgotten" in str(a) for a in told):
            wrong.append("the person was not told the token was forgotten")
        print("  %-32s %s" % ("a refused token is forgotten",
                              "FAIL" if wrong else "ok"))
    finally:
        server.shutdown()
    return wrong


def a_github_that_misbehaves(report):
    """
    [what went wrong] when the GitHub end of publishing misbehaves.

    Three ways, each of which used to go wrong. An API that redirects to
    another address was handed the token along with the redirect -- urllib
    copies every header onto a redirected request. A network that answers
    for GitHub with its own sign-in page, as hotels and trains do, raised
    a bare `JSONDecodeError`. And an answer that stalls part-way through
    raised a bare `TimeoutError`, which is not a `URLError` and so went
    past every handler; the upload to a report host did the same.
    """
    wrong = []
    heard = []

    class Elsewhere(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                # noqa: N802
            heard.append(self.headers.get("Authorization"))
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    def serve(handler):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return "http://127.0.0.1:%d" % server.server_address[1], server

    elsewhere, other = serve(Elsewhere)

    class Redirects(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                # noqa: N802
            self.send_response(301)
            self.send_header("Location", elsewhere + "/somewhere")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    class SignIn(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                # noqa: N802
            body = b"<html>Welcome aboard. Please sign in.</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    class Stalls(http.server.BaseHTTPRequestHandler):
        def answer(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b'{"lo')
            self.wfile.flush()
            time.sleep(3)

        do_GET = do_POST = answer                        # noqa: N815

        def log_message(self, *a):
            pass

    servers = [other]
    real_timeout = publish.TIMEOUT
    try:
        for name, handler, call in (
                ("an API that redirects elsewhere", Redirects,
                 lambda b: publish.publish(report, "ghp_secret", base=b)),
                ("a sign-in page answering for GitHub", SignIn,
                 lambda b: publish.publish(report, "ghp_secret", base=b)),
                ("GitHub stalling mid-answer", Stalls,
                 lambda b: publish.publish(report, "ghp_secret", base=b)),
                ("a report host stalling mid-answer", Stalls,
                 lambda b: publish.upload(report, b))):
            base, server = serve(handler)
            servers.append(server)
            publish.TIMEOUT = 1
            try:
                call(base)
                said = "published"
            except publish.PublishError as err:
                said = "refused in a sentence"
            except Exception as boom:                    # noqa: BLE001
                said = "raised %s" % type(boom).__name__
                wrong.append("%s: raised %s: %s" % (name, type(boom).__name__,
                                                    boom))
            print("  %-36s %s" % (name, said))
        if any(heard):
            wrong.append("the token was handed to the address a redirect "
                         "named: %s" % heard[0])
    finally:
        publish.TIMEOUT = real_timeout
        for server in servers:
            server.shutdown()
    return wrong


def main():
    holding = tempfile.mkdtemp(prefix="vic2share")
    report = os.path.join(holding, "report.html")
    with open(report, "wb") as fh:
        fh.write(A_REPORT)

    wrong = []
    cases = []

    # The ones that never reach a host.
    cases.append(("no host set", refuses(report, "", "no report host set")))
    cases.append(("no report there",
                  refuses(os.path.join(holding, "nope.html"),
                          "http://127.0.0.1:1", "there is no report at")))

    split = os.path.join(holding, "split.html")
    shutil.copy(report, split)
    with open(os.path.join(holding, "split.data.gz"), "wb") as fh:
        fh.write(b"\x1f\x8b")
    cases.append(("a --split report",
                  refuses(split, "http://127.0.0.1:1",
                          "keeps its data in a separate file")))

    # And the ones that do.
    answers = [
        ("nothing listening", None, "could not reach"),
        ("an answer that is not JSON", (200, b"<html>hello</html>",
                                        "text/html"),
         "not a report host"),
        ("a host that forgets the link", (200, b"{}", "application/json"),
         "did not say where it put it"),
        ("a host that says it is too large",
         (413, b'{"error":"8 MB is the limit"}', "application/json"),
         "too large"),
        ("a host that refuses it",
         (400, b'{"error":"that is not a report"}', "application/json"),
         "refused it (400)"),
    ]
    for name, answer, expect in answers:
        if answer is None:
            cases.append((name, refuses(report, a_closed_port(), expect)))
            continue
        url, stop = a_host(answer)
        try:
            cases.append((name, refuses(report, url, expect)))
        finally:
            stop()

    # The one that works.
    url, stop = a_host((200, json.dumps(
        {"url": "https://example.invalid/r/abc",
         "delete": "https://example.invalid/d/abc"}).encode(),
        "application/json"))
    said = []
    try:
        got = publish.upload(report, url, name="A campaign", say=said.append)
    except Exception as boom:                            # noqa: BLE001
        got = None
        wrong.append("the working host failed: %s" % boom)
    finally:
        stop()
    if got != "https://example.invalid/r/abc":
        wrong.append("the link came back as %r" % got)
    if not any("Uploading" in line for line in said):
        wrong.append("it never said it was uploading")
    if not any("take it down" in line for line in said):
        wrong.append("it never passed on how to take the report down")

    width = max(len(n) for n, _ in cases)
    for name, (bad, said) in cases:
        wrong += bad
        print("  %-*s %s  %s" % (width, name, "ok  " if not bad else "FAIL",
                                 said[:56]))
    print("  %-*s ok    %s" % (width, "a host that works", got))

    wrong += a_refused_token(holding, report)
    wrong += a_github_that_misbehaves(report)
    shutil.rmtree(holding, ignore_errors=True)
    print()
    if wrong:
        print("PROBLEMS:")
        for one in wrong:
            print("  %s" % one)
        return 1
    print("every way of failing says something a person could act on")
    return 0


if __name__ == "__main__":
    sys.exit(main())
