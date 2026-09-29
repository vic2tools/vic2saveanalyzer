#!/usr/bin/env python3
"""Exercise metric discovery and the shared fleet chart in a built report."""
import sys
import boots

CHECKS = r"""
function compareChecks() {
  const el = id => document.getElementById(id);
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const choose = (id, value) => { el(id).value = value; el(id).dispatchEvent(new Event('change')); };
  try {
    el('tab-compare').click();
    const keys = new Set();
    for (const category of [...el('metric-category').options]) {
      choose('metric-category', category.value);
      for (const family of [...el('metric-family').options]) {
        choose('metric-family', family.value);
        for (const metric of [...el('metric').options]) {
          choose('metric', metric.value);
          keys.add(metric.value);
          check(el('chart').children.length > 0, 'Chart missing: ' + metric.value);
          check(el('ship-variant').hidden === (metric.value !== 'ships'), 'Hull control visibility');
        }
      }
    }
    check(keys.size >= 20, 'Fixture must exercise a broad set of metrics');
    choose('metric-category', 'Army'); choose('metric-family', 'Brigades');
    choose('metric', 'regular_brigades');
    const nations = el('compare-trends').querySelector('.picker').textContent;
    choose('metric-category', 'Navy'); choose('metric-family', 'Ships');
    for (const hull of [...el('shiptype').options]) {
      choose('shiptype', hull.value);
      check(el('chart').children.length > 0, 'Hull chart missing');
    }
    el('scale').click();
    check(el('scale').getAttribute('aria-pressed') === 'true', 'Shared scale failed');
    choose('metric-category', 'Army');
    check(el('metric-family').value === 'Brigades' && el('metric').value === 'regular_brigades', 'Selection memory failed');
    check(el('compare-trends').querySelector('.picker').textContent === nations, 'Nation selection changed');
    check(!el('fleetchart') && !el('pick-fleet'), 'Separate fleet visualizer remains');
    say('compare', 'passed');
  } catch(e) { bad.push('compare: ' + e.message); }
}
"""

if __name__ == '__main__':
    boots.WATCHER = boots.WATCHER.replace('  function verdict() {', CHECKS + '\n  function verdict() {')
    boots.WATCHER = boots.WATCHER.replace('tourWars(verdict);', 'compareChecks(); verdict();')
    result = boots.looked(sys.argv[1])
    print(result)
    if not result or result['error'] or result.get('compare') != 'passed':
        sys.exit(1)
