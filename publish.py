# Victoria 2 campaign analyzer
# Copyright (C) 2026 vic2tools
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# <https://www.gnu.org/licenses/> for the full text, or the LICENSE file beside
# this one.
"""
Turning a finished report into a link somebody else can open.

A report is a web page, so sharing one is a hosting problem, and hosting is
where the easy answers run out. The free file hosts that take a 20 MB upload
without an account nearly all serve an HTML file as plain text or as a
download, deliberately -- a host that renders strangers' HTML is a phishing
site with extra steps. What is left is somewhere the reader owns, and the one
almost everybody can have for nothing is GitHub Pages.

So this puts the report in a repository of the user's own and turns Pages on:
the link is theirs, it keeps working, they can delete it, and nobody else's
server holds their campaign. The cost is a token, pasted once.

Everything here speaks the GitHub REST API over `urllib`, and `base` exists so
the whole path can be run against a mock rather than only ever being tried for
the first time against the real thing.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.request

API = "https://api.github.com"
TIMEOUT = 300


class PublishError(Exception):
    """Something the user needs to read, not a stack trace."""


def _call(base, token, method, path, body=None):
    """One REST call. Returns (status, parsed body)."""
    request = urllib.request.Request(
        base.rstrip("/") + path, method=method,
        data=json.dumps(body).encode("utf-8") if body is not None else None)
    request.add_header("Authorization", "Bearer " + token)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "vic2saveanalyzer")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            raw = answer.read()
            return answer.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as err:
        raw = err.read()
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = {"message": raw[:200].decode("utf-8", "replace")}
        return err.code, parsed
    except urllib.error.URLError as err:
        raise PublishError("could not reach %s: %s" % (base, err.reason))


def slug(text):
    """A campaign name as a URL path: `SWE-SCA 1836` -> `swe-sca-1836`."""
    out = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    return out or "report"


def publish(path, token, repo="vic2-reports", name=None, base=API,
            say=None, extra=()):
    """
    Put a report on the user's own GitHub Pages, and give back its URL.

    `path` is the report, `extra` any files that have to travel beside it --
    a `--split` report's data, say. `name` is the folder inside the repository,
    so one repository holds every campaign rather than one each.

    Raises PublishError with something worth reading if any step fails.
    """
    say = say or (lambda line: None)
    if not token:
        raise PublishError("no GitHub token set")
    if not os.path.isfile(path):
        raise PublishError("there is no report at %s" % path)

    status, who = _call(base, token, "GET", "/user")
    if status == 401:
        raise PublishError("GitHub would not accept that token. It needs to "
                           "be a token with permission to create "
                           "repositories and write to them.")
    if status != 200 or not who.get("login"):
        raise PublishError("GitHub said %s when asked who the token belongs "
                           "to: %s" % (status, who.get("message", "")))
    login = who["login"]
    say("Signed in to GitHub as %s." % login)

    status, _ = _call(base, token, "GET", "/repos/%s/%s" % (login, repo))
    if status == 404:
        say("Making the repository %s/%s." % (login, repo))
        # Public, because Pages on a private repository is a paid feature and
        # a link nobody can open is not a link.
        status, made = _call(base, token, "POST", "/user/repos", {
            "name": repo, "private": False, "auto_init": True,
            "description": "Victoria 2 campaign reports."})
        if status not in (200, 201):
            raise PublishError("could not create %s: %s"
                               % (repo, made.get("message", status)))
    elif status != 200:
        raise PublishError("could not look at %s/%s: %s"
                           % (login, repo, status))

    folder = slug(name or os.path.splitext(os.path.basename(path))[0])
    for source, target in [(path, "index.html")] + [
            (p, os.path.basename(p)) for p in extra]:
        _put(base, token, login, repo, "%s/%s" % (folder, target), source, say)

    status, pages = _call(base, token, "POST", "/repos/%s/%s/pages"
                          % (login, repo),
                          {"source": {"branch": "main", "path": "/"}})
    if status in (200, 201):
        say("Turned GitHub Pages on for %s." % repo)
    elif status == 409:
        pass                          # already on, which is the usual case
    elif status == 403:
        raise PublishError("that token is not allowed to turn Pages on. Give "
                           "it the Pages permission, or turn Pages on once by "
                           "hand in the repository's settings.")
    else:
        say("GitHub said %s about turning Pages on; if the link 404s, turn it "
            "on in the repository's settings." % status)

    site = (pages or {}).get("html_url") or "https://%s.github.io/%s/" % (
        login, repo)
    return site.rstrip("/") + "/" + folder + "/"


def _put(base, token, login, repo, where, source, say):
    """Write one file into the repository, replacing what is there."""
    with open(source, "rb") as fh:
        blob = base64.b64encode(fh.read()).decode("ascii")
    path = "/repos/%s/%s/contents/%s" % (login, repo, where)
    status, there = _call(base, token, "GET", path)
    body = {"message": "Add " + where, "content": blob}
    if status == 200 and there.get("sha"):
        body["sha"] = there["sha"]    # replacing a report published before
        body["message"] = "Update " + where
    say("Uploading %s (%.1f MB)."
        % (where, os.path.getsize(source) / 1048576.0))
    status, answer = _call(base, token, "PUT", path, body)
    if status not in (200, 201):
        message = answer.get("message", "")
        if status == 413 or "too large" in message.lower():
            raise PublishError(
                "GitHub refused %s as too large. Build the report with fewer "
                "saves, or with --split so the page and its data go up "
                "separately." % os.path.basename(source))
        raise PublishError("could not upload %s: %s"
                           % (where, message or status))
