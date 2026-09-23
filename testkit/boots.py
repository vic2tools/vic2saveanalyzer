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
  // The tab the reader lands on, looked at before anything is clicked --
  // afterwards the selected tab is whichever this tour left it on. A
  // report built without a mod used to open on the map tab with no map in
  // it: every section hidden, the page blank, and nothing about it
  // visible in the element counts, because the panel still had children.
  function landing() {
    var on = document.querySelector('.tab[aria-selected="true"]');
    if (!on) { say('landed', 'nothing:0:0:none'); return; }
    var p = document.getElementById(on.getAttribute('aria-controls'));
    var secs = p ? p.querySelectorAll(':scope > section') : [];
    var shown = 0;
    for (var j = 0; j < secs.length; j++) if (!secs[j].hidden) shown++;
    say('landed', on.id + ':' + secs.length + ':' + shown + ':'
        + (on.hidden ? 'hidden' : 'shown'));
  }

  window.addEventListener('load', function () {
    setTimeout(function () {
      landing();
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


def hostile_names():
    """
    [what went wrong] with a report built from names that are markup.

    Names reach the page out of save files and mods: war and battle names,
    leaders, provinces, nations. The page writes them into its HTML, and a
    war named `<img src=x onerror=...>` ran its script the moment the Wars
    tab drew -- in a report that may be published to a public site, or
    built from a multiplayer save somebody else wrote. The campaign here
    carries two such probes, one in a war's name and one in a nation
    joining it, each of which reports back if it ever runs.
    """
    import subprocess
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    import savefmt
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def probe(n):
        text = "%sinjected=%d\n" % (MARK, n)
        return "<img src=x onerror=dump(String.fromCharCode(%s))>" % ",".join(
            str(ord(c)) for c in text)

    holding = tempfile.mkdtemp(prefix="vic2hostile")
    try:
        saves = os.path.join(holding, "saves")
        os.makedirs(saves)
        for n, date in enumerate(("1870.1.1", "1871.1.1")):
            savefmt.write(
                os.path.join(saves, "s%d.v2" % n), savefmt.head(date),
                savefmt.province(1, "ENG", [savefmt.pop("farmers", 1, 9000)]),
                savefmt.province(2, "FRA", [savefmt.pop("farmers", 2, 9000,
                                                        culture="french")]),
                savefmt.country("ENG"),
                savefmt.country("FRA", culture="french", capital=2),
                ["active_war=", "{", '\tname="%s"' % probe(1), "\thistory=", "\t{",
                 "\t\t1869.5.1=", "\t\t{", '\t\t\tadd_attacker="ENG"', "\t\t}",
                 "\t\t1869.5.1=", "\t\t{", '\t\t\tadd_attacker="%s"' % probe(2),
                 "\t\t}",
                 "\t\t1869.5.1=", "\t\t{", '\t\t\tadd_defender="FRA"', "\t\t}",
                 "\t}", '\tattacker="ENG"', '\tdefender="FRA"',
                 '\toriginal_attacker="ENG"', '\toriginal_defender="FRA"',
                 '\taction="1869.5.1"', "}"])
        out = os.path.join(holding, "out")
        built = subprocess.run(
            [sys.executable, os.path.join(here, "vic2_analyzer.py"), saves,
             "--out", out, "--no-cache", "-q"], capture_output=True,
            text=True, env=dict(os.environ, TMPDIR=holding))
        report = os.path.join(out, "report.html")
        if built.returncode or not os.path.isfile(report):
            return ["the hostile campaign did not build: %s"
                    % (built.stdout + built.stderr).strip()[-200:]]
        said = looked(report)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    if said is None:
        return ([] if shutil.which("firefox") is None else
                ["the browser never reported back on the hostile campaign"])
    ran = said.get("injected")
    if ran:
        return ["a name from a save ran as script in the report (probe %s)"
                % ran]
    if not said.get("done"):
        return ["the hostile campaign's report never finished loading"]
    print("  names that are markup stay text: ok")
    return []


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--hostile":
        if shutil.which("firefox") is None:
            print("no firefox here, so nothing was opened")
            return 0
        wrong = hostile_names()
        for one in wrong:
            print("PROBLEMS:\n  %s" % one)
        return 1 if wrong else 0
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
    landed = said.get("landed")
    if landed:
        which, total, shown, state = landed.split(":")
        if state == "hidden":
            problems.append("the report opens on %s, which is hidden" % which)
        elif int(total) and not int(shown):
            problems.append("the report opens on %s and every section of it "
                            "is hidden -- a blank page" % which)
        print("  opens on %s (%s of %s sections showing)"
              % (which.replace("tab-", ""), shown, total))
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
    problems += hostile_names()
    if problems:
        print("\nPROBLEMS:")
        for one in problems:
            print("  %s" % one)
        return 1
    print("\nit opens, and it drew what it was supposed to")
    return 0


if __name__ == "__main__":
    sys.exit(main())
