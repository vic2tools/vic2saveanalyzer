#!/usr/bin/env python3
"""Verify war-summary PNG download, included sections, and expanded lists."""
import sys
import boots

CHECKS = r"""
async function warExportChecks() {
  const check = (value, message) => { if (!value) throw new Error(message); };
  const originalClick = HTMLAnchorElement.prototype.click;
  const originalSerialize = XMLSerializer.prototype.serializeToString;
  let download, snapshot;
  HTMLAnchorElement.prototype.click = function() {
    if (this.download.endsWith('-summary.png')) download = this.href;
    else originalClick.call(this);
  };
  XMLSerializer.prototype.serializeToString = function(node) {
    if (node.querySelector?.('.ib')) snapshot = node.cloneNode(true);
    return originalSerialize.call(this, node);
  };
  try {
    document.getElementById('tab-wars').click();
    document.querySelector('#wartable tbody tr').click();
    const source = document.querySelector('#wardetail .ib');
    const name = source.querySelector('.ibtitle>span').textContent;
    const button = source.querySelector('.war-export');
    check(button.closest('.ibtitle'), 'Export icon must be beside the war name');
    button.click();
    for (let n = 0; button.disabled && n < 1200; n++) await new Promise(r => setTimeout(r, 50));
    check(download, source.querySelector('.war-export-status').textContent);
    check(snapshot, 'No styled infobox snapshot');
    check(snapshot.querySelector('.ibtitle').textContent === name, 'War title changed');
    check(snapshot.querySelector('.ibfacts').children.length === 2, 'Export must contain only the date and duration fact');
    check(!snapshot.querySelector('.wartheatre, .war-export, summary'), 'Unrequested content in PNG');
    check([...snapshot.querySelectorAll('details')].every(d => d.open), 'Nation lists are truncated');
    const bands = [...snapshot.querySelectorAll('.ibband')].map(b => b.textContent).join('|');
    check(bands === 'Belligerents|Casualties and losses', 'Wrong sections: ' + bands);
    check(snapshot.textContent.includes('Total casualties:'), 'Overall total missing');
    check(snapshot.querySelectorAll('.ibtotal').length === 2, 'Coalition totals missing');
    check([...snapshot.querySelectorAll('img')].every(img => img.src.startsWith('data:')), 'Flags must be embedded');
    const blob = await (await fetch(download)).blob();
    check(blob.type === 'image/png' && blob.size > 10000, 'Invalid PNG');
    const img = new Image();
    await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = reject; img.src = download; });
    check(img.width >= 600 && img.height > 400, 'Empty or undersized summary');
    say('war-export', 'passed');
  } catch (error) { bad.push('war-export: ' + error.message); }
  finally {
    HTMLAnchorElement.prototype.click = originalClick;
    XMLSerializer.prototype.serializeToString = originalSerialize;
  }
}
"""

if __name__ == '__main__':
    boots.WATCHER = boots.WATCHER.replace('  function verdict() {', CHECKS + '\n  function verdict() {')
    boots.WATCHER = boots.WATCHER.replace('tourWars(verdict);', 'warExportChecks().then(verdict);')
    result = boots.looked(sys.argv[1], seconds=150)
    print(result)
    if not result or result['error'] or result.get('war-export') != 'passed':
        sys.exit(1)
