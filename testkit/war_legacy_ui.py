#!/usr/bin/env python3
"""
The war view's two layouts, and that neither credits casualties to a nation.

    python3 testkit/war_legacy_ui.py [path/to/report.html]

A save keeps one loss figure for each side of a battle, under the nation
leading that side, and the men its allies had in the army are counted in
it. Summed by nation, that put an ally's dead on whoever led them: the
infobox listed what each nation "lost", and the old War Analyzer's window,
the legacy layout, had a Losses column for every country. Both are gone;
what is left is per battle, per side of the war, and per war.

This builds a small campaign whose answers are known -- an ally leading one
battle, a defender's ally another, and a naval one -- opens its report in
headless Firefox, and checks the numbers in both layouts, the legacy one's
panels, columns and sort, and that the chosen layout is kept from one war to
the next. Given a report as well, it opens every war in it in both layouts
and checks that each side's totals add up to the war's and its battles'.
"""
import os
import shutil
import subprocess
import sys
import tempfile

import boots                                                # noqa: E402
import browser                                              # noqa: E402
import fixtures                                             # noqa: E402
import savefmt                                              # noqa: E402
import kit                                                  # noqa: E402
from outcome import SKIPPED                                 # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Shared by both: the casualties section of an open infobox, and the legacy
# layout's numbers read back off the page.
COMMON = r"""
  const num = el => +((el && el.textContent) || '').replace(/[^0-9]/g, '');
  function casualtiesSection() {
    const kids = [...document.querySelectorAll('#wardetail .ib > *')];
    const at = kids.findIndex(k => k.classList.contains('ibband')
                                   && k.textContent.startsWith('Casualties'));
    if (at < 0) return null;
    const out = [];
    for (const k of kids.slice(at + 1)) {
      if (k.classList.contains('ibband') || k.classList.contains('ibnote')) break;
      out.push(k);
    }
    return out;
  }
  function noNationLosses(where) {
    const section = casualtiesSection();
    if (!section) return;
    for (const part of section) {
      if (part.querySelector('.ibnat, img, .ibflag'))
        throw new Error(where + ': the casualties section names a nation');
    }
  }
  function legacyRead() {
    const lg = document.querySelector('#wardetail .lgwar');
    if (!lg) throw new Error('no legacy layout');
    const panels = [...lg.children];
    if (panels.length !== 3) throw new Error('legacy layout has ' + panels.length + ' panels');
    const dl = el => {
      const out = {};
      const dts = el.querySelectorAll('dt');
      dts.forEach(dt => { out[dt.textContent.replace(/:$/, '')] = dt.nextElementSibling; });
      return out;
    };
    const side = el => {
      const facts = dl(el.querySelector('dl'));
      const table = el.querySelector('table');
      return {el, facts, land: num(facts['Total losses']), sea: num(facts['Total ships lost']),
              head: [...table.querySelectorAll('thead th')].map(th => th.textContent),
              rows: [...table.querySelectorAll('tbody tr')].map(tr =>
                [...tr.children].map(td => td.textContent))};
    };
    const [general, goal] = [...panels[1].querySelectorAll('.lggrid')].map(dl);
    const battles = [...panels[1].querySelectorAll('.lgbattles tbody tr')].map(tr =>
      [...tr.children].map(td => td.textContent));
    const note = [...panels[1].querySelectorAll('.note')].map(p => p.textContent)
      .find(t => t.includes('could place')) || '';
    const lost = note.match(/([\d,]+) men and ([\d,]+) ships/);
    return {lg, attacker: side(panels[0]), defender: side(panels[2]), general, goal,
            title: panels[1].querySelector('.lgtitle').textContent, battles,
            head: [...panels[1].querySelectorAll('.lgbattles thead th')].map(th => th.textContent),
            unplaced: lost ? [+lost[1].replace(/,/g, ''), +lost[2].replace(/,/g, '')] : [0, 0]};
  }
  const SIDE_HEAD = 'Flag|Country|Joined|Ended';
  const BATTLE_HEAD = 'Battle|Date|Attacker|Defender|Type|Result|Total losses';
  function legacyAddsUp(v, where) {
    const check = (ok, what) => { if (!ok) throw new Error(where + ': ' + what); };
    check(v.attacker.head.join('|') === SIDE_HEAD, 'attacker columns ' + v.attacker.head.join('|'));
    check(v.defender.head.join('|') === SIDE_HEAD, 'defender columns ' + v.defender.head.join('|'));
    for (const s of [v.attacker, v.defender])
      check(s.rows.every(r => r.length === 4), 'a country row with other than four cells');
    const land = num(v.general['Total losses']), sea = num(v.general['Total ships lost']);
    check(v.attacker.land + v.defender.land + v.unplaced[0] === land,
          `side losses ${v.attacker.land} + ${v.defender.land} + ${v.unplaced[0]} != ${land}`);
    check(v.attacker.sea + v.defender.sea + v.unplaced[1] === sea,
          `side ships ${v.attacker.sea} + ${v.defender.sea} + ${v.unplaced[1]} != ${sea}`);
    if (!v.battles.length) return;
    check(v.head.join('|') === BATTLE_HEAD, 'battle columns ' + v.head.join('|'));
    const totals = v.battles.map(r => num({textContent: r[6]}));
    check(totals.every((n, i) => !i || totals[i - 1] >= n), 'battles not by total losses, most first');
    const by = kind => v.battles.filter(r => r[4] === kind)
      .reduce((n, r) => n + num({textContent: r[6]}), 0);
    check(by('Land') === land, `land battles add to ${by('Land')}, not ${land}`);
    check(by('Naval') === sea, `naval battles add to ${by('Naval')}, not ${sea}`);
  }
  const openWar = i => document.querySelectorAll('#wartable tbody tr')[i].click();
  const back = () => document.getElementById('warback').click();
  const layout = which => document.getElementById('warview-' + which).click();
"""

# The fixture's war, whose every figure is known.
FIXTURE = r"""
function warLegacyChecks() {
""" + COMMON + r"""
  const check = (ok, what) => { if (!ok) throw new Error(what); };
  try {
    document.getElementById('tab-wars').click();
    check(document.getElementById('warbar').hidden, 'layout switch shown with no war open');
    openWar(0);
    check(!document.getElementById('warbar').hidden, 'no layout switch on an open war');
    check(document.getElementById('warview-infobox').getAttribute('aria-pressed') === 'true',
          'the infobox is not the default');
    check(document.querySelector('#wardetail .ib'), 'the infobox did not open');
    noNationLosses('infobox');
    const totals = casualtiesSection().map(k => [...k.querySelectorAll('.ibtotal .ibnum')])
      .flat().map(num);
    // Defenders on the left: FRA's 3,000 and 3 ships, PRU's 700 (which led
    // the attack on ENG). Attackers: SPA's 1,200, ENG's 400 and 1 ship.
    check(totals.join(',') === '3703,1601', 'side totals ' + totals.join(','));

    layout('legacy');
    let v = legacyRead();
    check(v.title === 'The Test War', 'title ' + v.title);
    check(v.attacker.facts['Original attacker'].textContent.includes('ENG'), 'attacker leader');
    check(v.defender.facts['Original defender'].textContent.includes('FRA'), 'defender leader');
    check(v.attacker.land === 1600 && v.attacker.sea === 1,
          `attacker totals ${v.attacker.land}/${v.attacker.sea}`);
    check(v.defender.land === 3700 && v.defender.sea === 3,
          `defender totals ${v.defender.land}/${v.defender.sea}`);
    check(v.attacker.rows.map(r => r[1]).join() === 'ENG,SPA', 'attackers ' + v.attacker.rows.map(r => r[1]));
    check(v.defender.rows.map(r => r[1]).join() === 'FRA,PRU', 'defenders ' + v.defender.rows.map(r => r[1]));
    check(v.attacker.rows[0][2] === '1870.1.1' && v.attacker.rows[1][2] === '1870.2.1',
          'joined ' + v.attacker.rows.map(r => r[2]));
    check(v.attacker.rows.every(r => r[3] === 'ongoing'), 'ended ' + v.attacker.rows.map(r => r[3]));
    // Not one figure a nation could be credited with, anywhere in a side.
    for (const s of [v.attacker, v.defender])
      for (const n of ['1,200', '1,201', '400', '401', '3,000', '3,003', '700'])
        check(!s.el.querySelector('table').textContent.includes(n), 'a side table shows ' + n);
    check(v.general['Start date'].textContent === '1870.1.1', 'start');
    check(v.general['Has ended'].textContent === 'No', 'has ended');
    check(num(v.general['Total losses']) === 5300, 'total losses');
    check(num(v.general['Total ships lost']) === 4, 'ships lost');
    check(v.goal['Casus belli'].querySelector('span').title === 'acquire_state', 'casus belli');
    check(v.goal['State ID'].textContent === '2', 'state id');
    check(v.goal['Is fulfilled'].textContent === 'No', 'fulfilled');
    check(v.goal['Date'].textContent === '1870.1.1', 'goal date');
    check(v.battles.map(r => r[0]).join() === 'Alpha,Beta,Gamma', 'battle order ' + v.battles.map(r => r[0]));
    check(v.battles[0].slice(2, 6).join('|') === 'SPA|FRA|Land|Yes', 'Alpha row ' + v.battles[0]);
    check(v.battles[2][4] === 'Naval', 'Gamma at sea');
    legacyAddsUp(v, 'The Test War');

    document.querySelector('#wardetail th[data-lk="date"]').click();
    v = legacyRead();
    check(v.battles.map(r => r[1]).join() === '1870.3.1,1870.4.1,1870.5.1', 'date sort');

    back();
    openWar(0);
    check(document.querySelector('#wardetail .lgwar'), 'the next war did not keep the legacy layout');
    check(document.getElementById('warview-legacy').getAttribute('aria-pressed') === 'true',
          'legacy is not shown pressed');
    layout('infobox');
    check(document.querySelector('#wardetail .ib') && !document.querySelector('#wardetail .lgwar'),
          'back to the infobox');
    say('war-legacy', 'passed');
  } catch (error) { bad.push('war-legacy: ' + error.message); }
}
"""

# Any report: every war, both layouts.
TOUR = r"""
function warLegacyChecks() {
""" + COMMON + r"""
  let n = 0;
  try {
    const tab = document.getElementById('tab-wars');
    if (!tab || tab.hidden) { say('war-legacy', 'passed:0'); return; }
    tab.click();
    const count = document.querySelectorAll('#wartable tbody tr').length;
    for (let i = 0; i < count; i++) {
      layout('infobox');
      openWar(i);
      const name = document.querySelector('#wardetail .ibtitle > span').textContent;
      noNationLosses(name);
      layout('legacy');
      legacyAddsUp(legacyRead(), name);
      back();
      n++;
    }
    layout('infobox');
    say('war-legacy', 'passed:' + n);
  } catch (error) { bad.push('war-legacy, war ' + n + ': ' + error.message); }
}
"""


def battle(name, where, won, attacker, defender):
    def side(tag, leader, units, lost):
        return (["\t\t\t\t\t%s=" % ("attacker" if tag == attacker[0] else "defender"), "\t\t\t\t\t{",
                 '\t\t\t\t\t\tcountry="%s"' % tag, '\t\t\t\t\t\tleader="%s"' % leader]
                + ["\t\t\t\t\t\t%s=%d" % kv for kv in units]
                + ["\t\t\t\t\t\tlosses=%d" % lost, "\t\t\t\t\t}"])
    return (["\t\t\t\tbattle=", "\t\t\t\t{", '\t\t\t\t\tname="%s"' % name,
             "\t\t\t\t\tlocation=%d" % where, "\t\t\t\t\tresult=%s" % ("yes" if won else "no")]
            + side(*attacker) + side(*defender) + ["\t\t\t\t}"])


def war_block():
    def dated(date, lines):
        return ["\t\t%s=" % date, "\t\t{"] + lines + ["\t\t}"]

    def goal(key, extra):
        return (["\t%s=" % key, "\t{", '\t\tcasus_belli="acquire_state"', '\t\tactor="ENG"',
                 '\t\treceiver="FRA"', "\t\tstate_province_id=2"] + extra + ["\t}"])
    history = (dated("1870.1.1", ['\t\t\tadd_attacker="ENG"'])
               + dated("1870.1.1", ['\t\t\tadd_defender="FRA"'])
               + dated("1870.2.1", ['\t\t\tadd_attacker="SPA"'])
               + dated("1870.2.1", ['\t\t\tadd_defender="PRU"'])
               # An ally leads the attack: its 1,200 are the attackers' loss.
               + dated("1870.3.1", battle("Alpha", 1, True,
                                          ("SPA", "Ana", [("infantry", 9000)], 1200),
                                          ("FRA", "Rene", [("infantry", 6000)], 3000)))
               # A defender's ally attacks; ENG, an attacker in the war, holds.
               + dated("1870.4.1", battle("Beta", 2, False,
                                          ("PRU", "Kurt", [("infantry", 5000)], 700),
                                          ("ENG", "Tom", [("infantry", 7000)], 400)))
               + dated("1870.5.1", battle("Gamma", 3, True,
                                          ("ENG", "Nel", [("frigate", 5)], 1),
                                          ("FRA", "Jean", [("frigate", 4)], 3))))
    return (["active_war=", "{", '\tname="The Test War"', "\thistory=", "\t{"] + history
            + ["\t}", '\tattacker="ENG"', '\tattacker="SPA"', '\tdefender="FRA"',
               '\tdefender="PRU"', '\toriginal_attacker="ENG"', '\toriginal_defender="FRA"',
               '\taction="1870.5.1"']
            + goal("war_goal", ['\t\tdate="1870.1.1"', "\t\tis_fulfilled=no"])
            + goal("original_wargoal", []) + ["}"])


def fixture_report(holding):
    """The report of a two-save campaign carrying The Test War, or None."""
    saves = os.path.join(holding, "saves")
    os.makedirs(saves)
    for n, date in enumerate(("1870.6.1", "1870.7.1")):
        savefmt.write(
            os.path.join(saves, "s%d.v2" % n), savefmt.head(date),
            savefmt.province(1, "ENG", [savefmt.pop("farmers", 1, 9000)]),
            savefmt.province(2, "FRA", [savefmt.pop("farmers", 2, 9000, culture="french")]),
            savefmt.country("ENG"),
            savefmt.country("FRA", culture="french", capital=2),
            war_block())
    game = fixtures.a_vanilla(os.path.join(holding, "Victoria 2"))
    os.makedirs(os.path.join(game, "units"), exist_ok=True)
    for unit, kind in (("infantry", "land"), ("frigate", "naval")):
        with open(os.path.join(game, "units", unit + ".txt"), "w") as fh:
            fh.write("%s = {\n\ttype = %s\n}\n" % (unit, kind))
    out = os.path.join(holding, "out")
    built = kit.analyze(*[saves,
         "--out", out, "--game-root", game, "--no-cache", "-q"], env=dict(os.environ, TMPDIR=holding))
    report = os.path.join(out, "report.html")
    if built.returncode or not os.path.isfile(report):
        print("the test campaign did not build: %s" % (built.stdout + built.stderr).strip()[-400:])
        return None
    return report


def look(report, checks):
    return boots.looked(report, seconds=300, tour=False,
                        probes=[('checks', checks + 'await warLegacyChecks();')])


def verdict(what, said):
    if said is None:
        print("%s: the browser never reported back" % what)
        return False
    if said["error"] or not (said.get("war-legacy") or "").startswith("passed"):
        print("%s:\n  %s" % (what, "\n  ".join(said["error"]) or "no verdict"))
        return False
    print("%s: %s" % (what, said["war-legacy"]))
    return True


def main():
    if browser.firefox() is None:
        print("no firefox here, so nothing was opened")
        return SKIPPED
    holding = tempfile.mkdtemp(prefix="vic2legacy")
    try:
        report = fixture_report(holding)
        ok = report is not None and verdict("the test war", look(report, FIXTURE))
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    if len(sys.argv) > 1:
        ok = verdict(os.path.basename(os.path.dirname(os.path.abspath(sys.argv[1])))
                     or sys.argv[1], look(sys.argv[1], TOUR)) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
