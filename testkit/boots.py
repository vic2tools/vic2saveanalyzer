#!/usr/bin/env python3
"""
Open a report in a real browser and see whether it comes up.

Everything else here checks the bytes of a report against the bytes of
another one. That catches a changed number and misses the only failure that
matters to a reader: a page that does not run. It has happened -- a helper
called from outside the function that defined it, which is a
`ReferenceError` at boot and a blank page, and no test noticed because the
file was byte-for-byte what it was supposed to be.

    python3 testkit/boots.py path/to/report.html

Loads it in headless Firefox with a handler on `window.onerror` and on
unhandled rejections -- the report is one big async function, so that is
where a failure inside it lands -- waits for it to settle, and asks the
page what it managed to build. Exits non-zero on any error, on a page that
put up its own "could not be unpacked" note, or on one that rendered
nothing.
"""

import os
import shutil
import subprocess
import sys
import tempfile

# Dumped by the page, read back off Firefox's stdout. `dump()` rather than
# `console.log` because console output is formatted and quoted and this is
# meant to be parsed.
MARK = "BOOTCHECK "

WATCHER = """<script>
(function () {
  var bad = [];
  window.onerror = function (m, src, line, col, err) {
    bad.push('onerror: ' + m + ' @' + line + ':' + col);
    return false;
  };
  window.addEventListener('unhandledrejection', function (e) {
    var r = e.reason;
    bad.push('rejected: ' + ((r && r.stack) ? r.stack.split('\\n')[0]
                             : (r && r.message) ? r.message : r));
  });
  function say(k, v) { dump('%(mark)s' + k + '=' + v + '\\n'); }

  // Every tab in turn. A tab draws when it is first shown, so seven of the
  // eight have never run a line at the point the page finishes loading --
  // which is where a chart that throws on a mod's thirteenth unit type, or
  // a table of a nation with no navy, would be sitting unnoticed.
  function visit(tabs, i, then) {
    if (i >= tabs.length) { then(); return; }
    var before = bad.length;
    try { tabs[i].click(); }
    catch (e) { bad.push('clicking ' + tabs[i].id + ': ' + e.message); }
    setTimeout(function () {
      if (bad.length > before) say('badtab', tabs[i].id);
      else {
        var panel = document.getElementById(
          tabs[i].getAttribute('aria-controls')) || {};
        // Chart geometry as well as element count: a plot that drew no
        // lines still fills its panel, and looks fine from out here.
        var drawn = panel.querySelectorAll
          ? panel.querySelectorAll('svg path, svg polyline, svg circle, svg rect').length
          : 0;
        say('oktab', tabs[i].id + ':' + (panel.childElementCount || 0)
            + ':' + drawn);
      }
      visit(tabs, i + 1, then);
    }, %(settle)d);
  }

  function verdict() {
    for (var i = 0; i < bad.length; i++) say('error', bad[i]);
    var note = document.getElementById('bootnote');
    say('bootnote', note ? note.textContent : '');
    say('tables', document.querySelectorAll('table').length);
    say('svgs', document.querySelectorAll('svg').length);
    say('rows', document.querySelectorAll('tbody tr').length);
    say('tabs', document.querySelectorAll('button.tab').length);
    say('title', document.title);
    say('done', 1);
    window.close();
  }

  // The report unpacks asynchronously and then draws. Long enough for a
  // campaign far bigger than any test uses, and it closes as soon as it has
  // looked, so the wait costs nothing when nothing is wrong.
  window.addEventListener('load', function () {
    setTimeout(function () {
      visit(document.querySelectorAll('button.tab'), 0, verdict);
    }, %(wait)d);
  });
}());
</script>
""" % {"mark": MARK, "wait": 5000, "settle": 700}


def looked(html_path, seconds=90, wait_ms=6000):
    """{what the page said}, or None if the browser never reported."""
    firefox = shutil.which("firefox")
    if firefox is None:
        return None
    holding = tempfile.mkdtemp(prefix="vic2boot")
    try:
        profile = os.path.join(holding, "profile")
        os.makedirs(profile)
        with open(os.path.join(profile, "user.js"), "w") as fh:
            fh.write('user_pref("browser.dom.window.dump.enabled", true);\n'
                     'user_pref("dom.allow_scripts_to_close_windows", true);\n'
                     'user_pref("browser.shell.checkDefaultBrowser", false);\n'
                     'user_pref("datareporting.policy.dataSubmissionEnabled",'
                     ' false);\n'
                     'user_pref("toolkit.telemetry.enabled", false);\n')

        with open(html_path, encoding="utf-8") as fh:
            html = fh.read()
        # Before the report's own script, so the handlers are installed
        # before anything can fail.
        at = html.index("</head>")
        watched = os.path.join(holding, "watched.html")
        with open(watched, "w", encoding="utf-8") as fh:
            fh.write(html[:at] + WATCHER + html[at:])

        try:
            done = subprocess.run(
                [firefox, "--headless", "--no-remote", "--profile", profile,
                 watched],
                capture_output=True, text=True, timeout=seconds)
            out = done.stdout + done.stderr
        except subprocess.TimeoutExpired as late:
            out = ((late.stdout or b"").decode("utf-8", "replace")
                   + (late.stderr or b"").decode("utf-8", "replace"))

        said = {"error": [], "badtab": [], "oktab": []}
        for line in out.splitlines():
            if not line.startswith(MARK):
                continue
            key, _, value = line[len(MARK):].partition("=")
            if key in said and isinstance(said[key], list):
                said[key].append(value)
            else:
                said[key] = value
        return said if said.get("done") else None
    finally:
        shutil.rmtree(holding, ignore_errors=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 2
    path = sys.argv[1]
    if not os.path.isfile(path):
        print("no such report: %s" % path)
        return 2
    size = os.path.getsize(path) / 1048576.0
    said = looked(path)
    if said is None:
        if shutil.which("firefox") is None:
            print("no firefox here, so nothing was opened")
            return 0
        print("the browser never reported back -- it may have failed to "
              "start, or the page never finished loading")
        return 1

    problems = list(said["error"])
    if said.get("bootnote"):
        problems.append("the page said: %s" % said["bootnote"])
    if int(said.get("tables", 0)) == 0 and int(said.get("svgs", 0)) == 0:
        problems.append("nothing was drawn: no tables and no charts")
    if int(said.get("tabs", 0)) == 0:
        problems.append("no tabs, so the page shell did not render either")
    for which in said["badtab"]:
        problems.append("the %s tab threw when it was opened" % which)
    for entry in said["oktab"]:
        which, _, rest = entry.partition(":")
        kids = (rest.split(":") + ["0"])[0]
        if kids == "0":
            problems.append("the %s tab opened but put nothing in its panel"
                            % which)

    print("%s, %.1f MB" % (os.path.basename(path), size))
    print("  title   %s" % said.get("title", ""))
    print("  drew    %s tables, %s charts, %s rows, %s tabs"
          % (said.get("tables"), said.get("svgs"), said.get("rows"),
             said.get("tabs")))
    print("  opened  %s" % ", ".join(
        "%s(%s)" % (t.replace("tab-", "").split(":")[0],
                    t.split(":")[2] if t.count(":") > 1 else "?")
        for t in said["oktab"]))
    print("          the bracket is how many shapes that tab's charts drew")
    if problems:
        print("\nPROBLEMS:")
        for one in problems:
            print("  %s" % one)
        return 1
    print("\nit opens, and it drew what it was supposed to")
    return 0


if __name__ == "__main__":
    sys.exit(main())
