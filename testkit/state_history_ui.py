#!/usr/bin/env python3
"""Check every decoded state value and its ordering in a real browser.

    python3 testkit/state_history_ui.py /path/to/report.html

Python and JavaScript independently restore the wire format. A hash of all
rows checks names, population, literacy, composition order, acceptance and
province counts without printing millions of values. Literacy is formatted
to its stored precision so JSON's 0 versus 0.0 spelling cannot hide a failure.
"""

import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

import boots
from outcome import SKIPPED



def unpack(chunk):
    """
    One state snapshot as it travels -- gzipped JSON of the words, the
    layouts and each nation's rows -- restored here independently of the
    page's own decoder, which is what this holds to it.
    """
    words, layouts, nations = json.loads(gzip.decompress(base64.b64decode(chunk)))
    restored = {}
    for tag, rows in nations.items():
        states = restored[tag] = {}
        for region, size, literacy, provinces, layout, counts in rows:
            types, cultures = layouts[layout]
            n = len(types)
            states[words[region]] = [size, literacy,
                {words[t]: count for t, count in zip(types, counts)},
                [[words[c // 2], count, bool(c % 2)]
                 for c, count in zip(cultures, counts[n:])], provinces]
    return restored


def expand_map(data):
    """The map's snapshots, every one restored, under `populationStates`."""
    if data and "populationStateChunks" in data:
        states = data.setdefault("populationStates", {})
        for date, chunk in data.pop("populationStateChunks"):
            states[date] = unpack(chunk)
    return data


def check(path):
    if shutil.which('firefox') is None:
        print('No Firefox available to check the state decoder')
        raise SystemExit(SKIPPED)
    html = Path(path).read_text()
    packed = re.search(r'const PACKED = "([^"]+)"', html)[1]
    data = json.loads(gzip.decompress(base64.b64decode(packed)))
    # The snapshots travel beside the payload, not inside it , and the page puts them back as this does.
    beside = re.search(r'const STATE_CHUNKS = (\[.*?\]);\n', html, re.S)
    if beside and data.get('map'):
        chunks = json.loads(beside[1])
        if chunks:
            data['map']['populationStateChunks'] = chunks
    if not data.get('map'):
        print('No map/state history in this report')
        raise SystemExit(SKIPPED)
    states = expand_map(data['map'])['populationStates']
    rows = [[date, tag, region, row[0],
             None if row[1] is None else format(row[1], '.6f'),
             list(row[2].items()), row[3], row[4]]
            for date, nations in states.items()
            for tag, regions in nations.items() for region, row in regions.items()]
    raw = json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()
    expected = hashlib.sha256(raw).hexdigest()
    probe = r'''
const checkedStates = [];
for (const [date, nations] of Object.entries(DATA.map.populationStates))
  for (const [tag, regions] of Object.entries(nations))
    for (const [region, row] of Object.entries(regions))
      checkedStates.push([date, tag, region, row[0],
        row[1] === null ? null : row[1].toFixed(6),
        Object.entries(row[2]), row[3], row[4]]);
const checkedBytes = new TextEncoder().encode(JSON.stringify(checkedStates));
const checkedHash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', checkedBytes)))
  .map(b => b.toString(16).padStart(2, '0')).join('');
if (checkedHash !== EXPECTED) throw new Error('State history differs from the Python decoder');
document.documentElement.dataset.stateHistoryChecked = String(checkedStates.length);
'''.replace('EXPECTED', json.dumps(expected))
    html = html.replace('clearTimeout(slow);', probe + '\nclearTimeout(slow);', 1)
    original = boots.WATCHER
    boots.WATCHER = original.replace('  function verdict() {',
        "  function verdict() {\n    say('states', document.documentElement.dataset.stateHistoryChecked);")
    try:
        with tempfile.TemporaryDirectory(prefix='vic2states-') as tmp:
            watched = Path(tmp) / 'report.html'
            watched.write_text(html)
            result = boots.looked(str(watched))
    finally:
        boots.WATCHER = original
    assert result and not result['error'], result
    assert result.get('states') == str(len(rows)), result
    print('Browser and Python agree on all %d state records' % len(rows))


if __name__ == '__main__':
    check(sys.argv[1])
