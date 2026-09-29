#!/usr/bin/env python3
"""Check pop-type isolation, reset, state scope, and unchanged percentage denominator."""
import sys
import boots

CHECKS = r"""
function populationHistoryChecks() {
  const el = id => document.getElementById(id);
  const check = (ok, msg) => { if (!ok) throw new Error(msg); };
  try {
    el('tab-pops').click();
    el('popcountry').value = 'ENG'; el('popcountry').dispatchEvent(new Event('change'));
    function exercise() {
      const chart = el('popchart');
      check(!el('poplegend').querySelector('button'), 'Legend must not add buttons');
      const bars = () => [...chart.querySelectorAll('rect[data-pop-type]')];
      const chosen = bars().find(b => b.dataset.popType === 'craftsmen') || bars()[0];
      check(chosen && new Set(bars().map(b => b.dataset.popType)).size > 1, 'Fixture needs several pop types');
      const key = chosen.dataset.popType;
      const original = [...chart.querySelectorAll('rect title')].map(t => t.textContent);
      chosen.dispatchEvent(new MouseEvent('click', {bubbles:true}));
      const isolated = [...chart.querySelectorAll('rect title')].map(t => t.textContent);
      check(isolated.length > 0 && isolated.length < original.length, 'Isolation did not reduce bars');
      check(bars().every(b => b.dataset.popType === key), 'Other pop types remain');
      check(isolated.every(t => original.includes(t)), 'Values or population shares changed');
      bars()[0].dispatchEvent(new MouseEvent('click', {bubbles:true}));
      check(bars().length === original.length, 'Click again did not reset');
      bars()[0].dispatchEvent(new KeyboardEvent('keydown', {key:'Enter',bubbles:true}));
      check(bars().length < original.length, 'Keyboard isolation failed');
      bars()[0].dispatchEvent(new KeyboardEvent('keydown', {key:' ',bubbles:true}));
      check(bars().length === original.length, 'Keyboard reset failed');
    }
    exercise();
    el('popregion').selectedIndex = 1; el('popregion').dispatchEvent(new Event('change'));
    exercise();
    say('pop-history', 'passed');
  } catch(e) { bad.push('pop-history: ' + e.message); }
}
"""
if __name__ == '__main__':
    boots.WATCHER = boots.WATCHER.replace('  function verdict() {', CHECKS + '\n  function verdict() {')
    boots.WATCHER = boots.WATCHER.replace('tourWars(verdict);', 'populationHistoryChecks(); verdict();')
    result = boots.looked(sys.argv[1])
    print(result)
    if not result or result['error'] or result.get('pop-history') != 'passed':
        sys.exit(1)
