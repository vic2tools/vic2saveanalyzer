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
