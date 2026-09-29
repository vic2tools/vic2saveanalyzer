#!/usr/bin/env python3
"""Check real PNG downloads from trend, fleet, head-to-head and map views."""
import sys
import boots

CHECKS = r"""
async function exportChecks() {
  const el = id => document.getElementById(id);
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const choose = (id, value) => { el(id).value = value; el(id).dispatchEvent(new Event('change')); };
  const originalClick = HTMLAnchorElement.prototype.click;
  let downloads = [];
  HTMLAnchorElement.prototype.click = function() {
    if (this.download.endsWith('.png')) downloads.push({url:this.href, name:this.download});
    else originalClick.call(this);
  };
  async function capture(id) {
    const source = el(id);
    const button = document.querySelector('[data-export-target="' + id + '"]');
    const controls = button.parentElement;
    const before = downloads.length;
    button.click();
    for (let i = 0; button.disabled && i < 200; i++) await new Promise(r => setTimeout(r, 50));
    check(!button.disabled && downloads.length === before + 1, id + ': ' + controls.textContent);
    const file = downloads.at(-1);
    const blob = await (await fetch(file.url)).blob();
    check(blob.type === 'image/png' && blob.size > 10000, id + ': empty PNG');
    const image = new Image();
    await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = file.url; });
    check(image.width === 2400 && image.height > 500, id + ': wrong dimensions');
    const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
    const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0);
    check(ctx.getImageData(0,0,1,1).data[3] === 255, id + ': transparent background');
    say('png', id + ':' + blob.size);
  }
  try {
    el('tab-compare').click();
    await capture('chart');
    choose('metric-category','Navy'); choose('metric-family','Ships');
    await capture('chart');
    el('compare-head-button').click();
    await capture('milpies');
    el('milview').click();
    await capture('milpies');
    el('tab-nations').click();
    check(!el('mapcanvas').closest('section').hidden, 'Fixture needs a world map');
    await capture('mapcanvas');
    say('exports','passed');
  } catch(e) { bad.push('exports: ' + e.message); }
  finally { HTMLAnchorElement.prototype.click = originalClick; }
}
"""

if __name__ == '__main__':
    boots.WATCHER = boots.WATCHER.replace('  function verdict() {', CHECKS + '\n  function verdict() {')
    boots.WATCHER = boots.WATCHER.replace('tourWars(verdict);', 'exportChecks().then(verdict);')
    result = boots.looked(sys.argv[1])
    print(result)
    if not result or result['error'] or result.get('exports') != 'passed':
        sys.exit(1)
