#!/usr/bin/env python3
"""Exercise military ledgers and Compare navigation in Firefox.

Usage: python3 testkit/military_ui.py path/to/report.html
Uses a report with at least one nation and fielded forces.
"""
import sys
import boots

CHECKS = r"""
function militaryChecks() {
  const el = id => document.getElementById(id);
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const click = id => el(id).click();
  try {
    check(!el('tab-compare').hidden, 'Compare must stay in the main navigation');
    click('tab-military');
    check(!el('panel-military').querySelector('svg'), 'Military contains a chart');
    check(!el('techtable'), 'Duplicate technology table remains');
    const armyRows = () => [...el('miltable').querySelectorAll('.nation-toggle')];
    check(armyRows().length > 0, 'Fixture needs selected nations');
    check(el('miltable').querySelectorAll('th').length === 5, 'Army overview is not compact');
    const first = armyRows()[0];
    const nameOfButton = b => b.querySelector('span:last-child').textContent;
    const selectedName = nameOfButton(first);
    const names = armyRows().map(nameOfButton).sort().join('|');
    check(first.querySelector('.military-flag'), 'Nation flag missing');
    first.closest('tr').cells[1].click();
    check(el('military-browse').hidden && !el('military-country').hidden, 'Country did not open');
    const country = el('military-country');
    check(country.querySelector('h2').textContent === selectedName, 'Wrong country opened');
    check(el('military-composition').querySelector('rect'), 'Army composition history did not draw');
    check(country.querySelector('.military-forces-column .military-rivals'), 'Rivals are not beneath the inventory');
    check(country.querySelectorAll('.military-strength-strip>div').length === 5, 'Strength summary missing');
    check(country.querySelector('.military-inventory') && country.querySelector('.military-capacity'), 'Composition and capacity not visible together');
    check(!country.querySelector('.military-menu'), 'Old detail tabs remain');
    const scout = country.querySelector('.military-rivals select');
    scout.value = 'tech'; scout.dispatchEvent(new Event('change'));
    const rivalRows = [...country.querySelectorAll('.rival-table tbody tr')];
    check(rivalRows.length <= 3, 'Too many rivals');
    const techs = rivalRows.map(r => Number(r.cells[2]?.firstChild.textContent));
    check(techs.every((v,i) => !i || techs[i-1] >= v), 'Rivals not sorted by technology');
    check(country.querySelector('.military-delta'), 'Relative differences missing');
    const match = country.querySelector('.rival-table button');
    if (match) {
      match.click();
      check(!el('compare-head').hidden && !el('panel-compare').hidden, 'Rival comparison failed');
      click('tab-military');
    }
    click('overview-navy');
    check(country.querySelector('h2').textContent === selectedName, 'Branch switch lost country');
    check(el('military-composition').getAttribute('aria-label').includes('Fleet composition') && el('military-composition').querySelector('rect'), 'Navy composition history did not draw');
    check(country.querySelector('.military-inventory').textContent.includes('Current power'), 'Hull power missing');
    click('military-back');
    check(!el('military-browse').hidden && country.hidden, 'Back navigation failed');
    check([...el('fleettable').querySelectorAll('.nation-toggle')].map(nameOfButton).sort().join('|') === names, 'Branches use different filters');
    click('overview-army');
    el('miltable').querySelectorAll('th button')[1].click();
    const counts = [...el('miltable').querySelectorAll(':scope > tbody > tr.strength-row')].map(r => Number(r.cells[1].textContent.replaceAll(',', '')));
    check(counts.every((n,i) => !i || counts[i-1] <= n), 'Numeric sorting failed');
    armyRows()[0].click();
    click('overview-navy');
    el('fleetsave').selectedIndex = 0; el('fleetsave').dispatchEvent(new Event('change'));
    const date = el('fleetsave').value;
    click('mil-compare');
    check(!el('panel-compare').hidden && !el('compare-head').hidden, 'Shortcut did not open Head-to-head');
    check(el('milsave').value === date && el('mildate').textContent === date, 'Shortcut lost date');
    check(el('head-navy').getAttribute('aria-pressed') === 'true' && el('milmob').hidden, 'Shortcut lost Navy branch');
    click('head-army'); check(!el('milmob').hidden, 'Army potential control unavailable');
    click('milmob'); click('milview'); click('milswap');
    check(el('milpies').children.length > 0, 'Head-to-head stopped drawing');
    click('compare-trends-button');
    check(!el('compare-trends').hidden && el('compare-head').hidden && el('chart').closest('#compare-trends'), 'Trends navigation failed');
    check(!el('compare-composition-button') && !el('compare-composition'), 'Composition still appears in Compare');
    click('tab-military'); click('overview-army');
    if (!el('military-country').hidden) click('military-back');
    const none = [...el('miloverview').querySelectorAll('.picker-presets button')].find(b => b.textContent === 'None');
    check(none, 'No empty-selection preset'); none.click();
    check(el('miltable').textContent.includes('Select nations'), 'Army empty state missing');
    click('overview-navy'); check(el('fleettable').textContent.includes('Select nations'), 'Navy empty state missing');
    say('military', 'passed');
  } catch(e) { bad.push('military: ' + e.message); }
}
"""

if __name__ == '__main__':
    boots.WATCHER = boots.WATCHER.replace('  function verdict() {', CHECKS + '\n  function verdict() {')
    boots.WATCHER = boots.WATCHER.replace('tourWars(verdict);', 'militaryChecks(); verdict();')
    result = boots.looked(sys.argv[1])
    if not result or result['error'] or result.get('military') != 'passed':
        print(result or 'Firefox did not report back')
        sys.exit(1)
    print('Military country navigation, branch persistence, inventory, rival differences, sorting, dates, and Compare views passed.')
