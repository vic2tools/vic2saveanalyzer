<script>
/* The payload is JSON, gzipped, then base64'd, because the uncompressed shape
   of a long campaign is a hundred megabytes of repeated key names and columns
   of similar numbers -- a file nobody can send anybody. Compressed it is about
   a ninth of that, and the page opens faster for it: inflating a megabyte
   costs less than reading nine off a disk and parsing them.

   `DecompressionStream` is asynchronous and there is no synchronous gzip in a
   browser, which is why everything below runs inside one async function rather
   than at the top level. Nothing else about the page changes. */
const PACKED = "__DATA__";

/* Empty in an ordinary report, which carries its own payload. `--split` puts
   the payload in a file beside this one instead and names it here: the page
   then weighs a few hundred kilobytes, the data is fetched as raw gzip with no
   base64 third on top, and the browser inflates it as it arrives. The cost is
   that two files have to travel together and be served, which is why it is not
   the default -- a report is usually something somebody was sent. */
const PACKED_URL = "__DATAURL__";

/* The map's state snapshots, [date, base64 gzip] each, when the payload is in
   this page. Each is compressed already, so they sit beside the payload
   rather than being gzipped a second time inside it; `--split` keeps them in
   the payload file and leaves this empty. */
const STATE_CHUNKS = __STATES__;

async function unpackFrom(url) {
  let res;
  try {
    res = await fetch(url);
  } catch (err) {
    throw new Error('this report keeps its data in ' + url + ' beside it, and '
      + 'a browser will not read that from a plain file path. Put both files '
      + 'on a web server -- GitHub Pages will do -- and open the page from '
      + 'there');
  }
  if (!res.ok) throw new Error('could not read ' + url + ': ' + res.status);
  if (typeof DecompressionStream !== 'function')
    throw new Error('this browser has no DecompressionStream; Chrome 80, '
      + 'Firefox 113, Safari 16.4 or newer will open this file');
  const stream = res.body.pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(stream).text());
}

async function unpack(text) {
  if (typeof DecompressionStream !== 'function')
    throw new Error('this browser has no DecompressionStream; Chrome 80, '
      + 'Firefox 113, Safari 16.4 or newer will open this file');
  const bin = atob(text);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const stream = new Blob([bytes]).stream()
    .pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(stream).text());
}

/* A report is a file somebody was sent, so a failure has to say so on the page
   rather than only in a console the reader will never open. */
function bootNote(text) {
  let box = document.getElementById('bootnote');
  if (!box) {
    box = document.createElement('p');
    box.id = 'bootnote';
    box.className = 'note';
    box.style.cssText = 'margin:1.5rem 2rem;color:var(--ink)';
    document.body.prepend(box);
  }
  box.textContent = text;
  return box;
}

function bootFailed(err) {
  bootNote('This report could not be unpacked: '
    + (err && err.message ? err.message : err) + '.');
  throw err;
}

(async () => {
/* A campaign of a few dozen saves unpacks in well under a tenth of a second and
   should say nothing at all; one autosaved every month for a century takes long
   enough that a page of empty tables needs explaining. Hence the delay: the
   notice only ever appears when there is something to wait for. */
const slow = setTimeout(() => bootNote('Unpacking the campaign\u2026'), 200);
const DATA = PACKED_URL ? await unpackFrom(PACKED_URL) : await unpack(PACKED);
if (STATE_CHUNKS.length && DATA.map) DATA.map.populationStateChunks = STATE_CHUNKS;
// Workers pack self-contained state snapshots. Restore the same records the
// views have always read, with a bounded number of inflaters alive at once.
if (DATA.map && DATA.map.populationStateChunks) {
  const chunks = DATA.map.populationStateChunks;
  const states = DATA.map.populationStates || (DATA.map.populationStates = {});
  for (let at = 0; at < chunks.length; at += 8) {
    const batch = chunks.slice(at, at + 8);
    const decoded = await Promise.all(batch.map(([, text]) => unpack(text)));
    for (let i = 0; i < batch.length; i++) {
      const [words, layouts, nations] = decoded[i];
      const snapshot = Object.create(null);
      for (const [tag, rows] of Object.entries(nations)) {
        const regions = snapshot[tag] = Object.create(null);
        for (const [region, size, literacy, provinces, layout, counts] of rows) {
          const [types, cultures] = layouts[layout];
          regions[words[region]] = [size, literacy,
            Object.fromEntries(types.map((t, j) => [words[t], counts[j]])),
            cultures.map((c, j) => [words[Math.floor(c / 2)], counts[types.length + j], !!(c % 2)]),
            provinces];
        }
      }
      states[batch[i][0]] = snapshot;
    }
  }
  delete DATA.map.populationStateChunks;
}
clearTimeout(slow);
const said = document.getElementById('bootnote');
if (said) said.remove();

/* `facts` and `series` are the same numbers in two orientations: series is
   by nation then measure then date, facts is by date then nation then
   measure. Charts want the first, tables want the second, and shipping both
   whole meant saying everything twice -- two megabytes of an eleven megabyte
   payload, a seventh of the finished file. Only what series cannot supply
   travels now, and the rest is put back here, which takes a few milliseconds
   on a century of monthly saves.

   Only the measures `factKeys` names, which are the ones that were taken
   out. `series` holds a dozen more that facts never carried, and putting
   those in too would hand the tables values they have never had -- harmless
   today, because nothing reads them off a fact, and a silent change in what
   the page shows the first time something does.

   `thin_facts` and `rebuild_facts` in report.py are this same operation,
   kept there so a test can hold the two to being inverses. Change one and
   change the other. */
for (const tag in DATA.series) {
  const metrics = DATA.series[tag];
  for (const key of DATA.factKeys) {
    const column = metrics[key];
    if (!column) continue;
    for (let i = 0; i < column.length; i++) {
      const value = column[i];
      if (value === null) continue;
      const date = DATA.dates[i];
      const at = DATA.facts[date] || (DATA.facts[date] = {});
      (at[tag] || (at[tag] = {}))[key] = value;
    }
  }
}

