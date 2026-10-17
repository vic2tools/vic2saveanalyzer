const C = DATA.colours;
/**
 * A stable colour for the nth series in a set.
 *
 * `C` is a hand-picked palette sized for a vanilla campaign. Mods run past
 * it -- Ferrum Mare fields a 13th regiment type and a 13th pop type, and the
 * market runs to about 48 goods -- and plain `C[i % C.length]` then hands two
 * different series the *identical* colour: `tank` came out the same gold as
 * `artillery`, one indistinguishable wedge in the composition pie.
 *
 * The first `C.length` series keep their hand-picked colours exactly, so
 * every chart that fitted before is unchanged. Past that, hues are placed at
 * the golden angle -- which spreads any number of them about as evenly as a
 * circle allows -- at the palette's own saturation, so the overflow still
 * reads as part of the same set.
 *
 * Lightness steps every `C.length` on top of that, because the golden angle
 * only guarantees a wide gap between *consecutive* series: the pair that
 * ends up closest in hue is always about 21 or 34 apart, which is far enough
 * to land on a different step. The goods list, the worst case here, comes
 * out with no two colours nearer than a tone apart.
 */
const seriesColour = i => {
  if (i < 0) return C[0];
  if (i < C.length) return C[i];
  const over = i - C.length;
  const hue = ((over * 137.508) + 21) % 360;
  const light = [63, 52, 74][Math.floor(over / C.length) % 3];
  return `hsl(${hue.toFixed(1)} 38% ${light}%)`;
};
const SVGNS = 'http://www.w3.org/2000/svg';
const el = (n, a) => { const e = document.createElementNS(SVGNS, n);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
// The right margin is wide because the end-of-line tags live in it: a tag
// laid over the plot has to fight the gridlines and the lines it names,
// and a stack of them has nowhere to go but on top of each other.
const W = 1000, H = 460, M = {t: 20, r: 58, b: 40, l: 80};

const nameOf = t => DATA.tagNames[t] || t;
/* A nation is drawn in its own colour out of the mod, so the report reads like
   the game. Half of them are unusable as ink on a burgundy page, though --
   Prussia is nearly black, Russia a deep green -- so each is lifted until it
   clears a contrast ratio against the ground, keeping its hue and saturation
   and moving only its lightness. A nation with no colour, or no mod to read one
   from, falls back to the report's own palette. */
const GROUND_RGB = [0x4A, 0x1C, 0x28];

function _chan(v) {
  const s = v / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}
function _luminance([r, g, b]) {
  return 0.2126 * _chan(r) + 0.7152 * _chan(g) + 0.0722 * _chan(b);
}
function _contrast(rgb) {
  const a = _luminance(rgb), b = _luminance(GROUND_RGB);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
function _toHsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const hi = Math.max(r, g, b), lo = Math.min(r, g, b), d = hi - lo;
  let h = 0;
  if (d) {
    if (hi === r) h = ((g - b) / d) % 6;
    else if (hi === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  const l = (hi + lo) / 2;
  const s = d ? d / (1 - Math.abs(2 * l - 1)) : 0;
  return [h, s, l];
}
function _fromHsl([h, s, l]) {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return [r, g, b].map(v => Math.round((v + m) * 255));
}

const READABLE = 3.4;          // enough for a bold tag and a 2px chart line
function _readable(hex) {
  const m = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(hex || '');
  if (!m) return null;
  let rgb = [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
  if (_contrast(rgb) >= READABLE) return '#' + m[1] + m[2] + m[3];
  const [h, s] = _toHsl(rgb);
  // Saturation gets a floor so near-greys do not lift into flat white, and a
  // ceiling so a fully saturated dark -- Prussia's navy, Russia's bottle green
  // -- comes up as ink rather than as neon. Lightness climbs from low, and the
  // first value that clears the threshold wins, so nothing is lifted further
  // than it has to be.
  const sat = Math.min(Math.max(s, 0.22), 0.58);
  for (let l = 0.38; l <= 0.9; l += 0.03) {
    const lifted = _fromHsl([h, sat, l]);
    if (_contrast(lifted) >= READABLE) {
      return '#' + lifted.map(v => v.toString(16).padStart(2, '0')).join('');
    }
  }
  return null;
}

const NATION_INK = {};
(() => {
  const own = (DATA.map && DATA.map.colours) || {};
  DATA.tags.forEach(t => {
    const ink = _readable(own[t]);
    NATION_INK[t] = ink || seriesColour(DATA.tags.indexOf(t));
  });
})();

/* A nation the report does not chart has no place in DATA.tags, and every one
   of them used to fall back to the palette's first colour: Austria, Baden and
   Sweden came out the same gold in one war's list. Most nations in a
   campaign's wars are like that -- gone before its first save -- so the tag
   picks a slot past the palette instead, the same one on every report. */
function tagSlot(t) {
  let h = 0;
  for (const ch of String(t)) h = (h * 31 + ch.charCodeAt(0)) % 9973;
  return C.length + h % 360;
}
const colourFor = t => NATION_INK[t] || seriesColour(tagSlot(t));
/* A save names a culture by its key. The mod's localisation has the name the
   game shows; without a mod folder there is none, so the key stands in, tidied
   the way every other raw key here is. */
const cultureName = c => DATA.cultureNames[c] || (c || '').replace(/_/g, ' ');
/* Same again for the other bare keys a save writes down -- goods, unit types,
   pop types, technologies, casus belli. The mod's localisation holds the name
   the game shows, so `cattle` reads Livestock in IGoR and Cattle in vanilla;
   with no mod folder there is nothing to look it up in and the key stands in,
   tidied. */
const gameName = k => DATA.names[k] || (k || '').replace(/_/g, ' ');
// Any list a reader scans for a name has to be in the order of the names it
// shows, not of the keys behind them: IGoR calls `barrels` Tanks and `cattle`
// Livestock, and sorted by key those land under B and C.
const byGameName = (a, b) => gameName(a).localeCompare(gameName(b));
const goodColour = g => seriesColour(DATA.goods.indexOf(g));

const fmtCount = v => {
  const a = Math.abs(v);
  if (a >= 1e9) return (v/1e9).toFixed(2)+'bn';
  if (a >= 1e6) return (v/1e6).toFixed(2)+'m';
  if (a >= 1e4) return Math.round(v/1e3)+'k';
  if (a >= 1e3) return v.toLocaleString();
  return (Math.round(v*100)/100).toString();
};
const formatters = {
  count: fmtCount,
  percent: v => v.toFixed(1)+'%',
  fraction: v => (v*100).toFixed(1)+'%',
  decimal: v => v.toFixed(2),
};

function niceTicks(lo, hi, count) {
  if (hi <= lo) return [lo];
  const raw = (hi - lo) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].find(s => s * mag >= raw) * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(v);
  return out;
}
function logTicks(lo, hi) {
  const out = [];
  for (let e = Math.floor(lo); e <= Math.ceil(hi); e++)
    for (const m of [1, 3]) {
      const v = e + Math.log10(m);
      if (v >= lo - 1e-9 && v <= hi + 1e-9) out.push(v);
    }
  return out.length >= 3 ? out : niceTicks(lo, hi, 5);
}
/* Stack one column of labels, moving each as little as it can be moved.

   The obvious way -- walk down the list and push anything too close to its
   neighbour further down -- drags a whole run downhill from whichever label
   happened to come first, so labels with room to spare still end up moved and
   the run as a whole finishes low. Here labels that already clear each other
   are left exactly where their line ended, and only a run that genuinely
   collides is evened out, centred on where its own members wanted to be. */
function packColumn(items, gap, top, bottom) {
  items.sort((a, b) => a.want - b.want);
  // A run's `sum / n` is the first position it would like: every member
  // contributes the start it implies, which is its own wanted position less
  // the gaps that would sit above it inside the run.
  const runs = [];
  for (const item of items) {
    let run = {n: 1, sum: item.want, items: [item]};
    while (runs.length) {
      const prev = runs[runs.length - 1];
      if (prev.sum / prev.n + prev.n * gap <= run.sum / run.n) break;
      runs.pop();
      run = {n: prev.n + run.n,
             sum: prev.sum + run.sum - prev.n * run.n * gap,
             items: prev.items.concat(run.items)};
    }
    runs.push(run);
  }
  const out = [];
  for (const run of runs) {
    const start = Math.max(top, Math.min(run.sum / run.n,
                                         bottom - (run.n - 1) * gap));
    run.items.forEach((it, i) => { it.y = start + i * gap; out.push(it); });
  }
  if (!out.length) return out;
  // Holding a run inside the band can push it into the run below, so the stack
  // is settled downhill, slid back up by however far that overran the bottom,
  // then settled uphill and slid back down the same way. Settling one way only
  // walks the last labels out of the chart and onto the axis.
  for (let i = 1; i < out.length; i++)
    if (out[i].y - out[i-1].y < gap) out[i].y = out[i-1].y + gap;
  const over = out[out.length - 1].y - bottom;
  if (over > 0) out.forEach(it => { it.y -= over; });
  for (let i = out.length - 2; i >= 0; i--)
    if (out[i+1].y - out[i].y < gap) out[i].y = out[i+1].y - gap;
  const under = top - out[0].y;
  if (under > 0) out.forEach(it => { it.y += under; });
  // Sliding only works while the stack fits. If it does not -- more labels than
  // even the extra columns could absorb -- spread what is there evenly and take
  // the tighter spacing: crowded inside the frame beats legible outside it.
  if (out.length > 1 && out[out.length - 1].y - out[0].y > bottom - top) {
    const even = (bottom - top) / (out.length - 1);
    out.forEach((it, i) => { it.y = top + i * even; });
  }
  return out;
}

/* Place every end-of-line label: in, its wanted y, which is where its own line
   ended; out, the y to draw it at, plus the anchor and column to draw it from. */
function placeLabels(labels, gap, top, bottom) {
  const fits = Math.max(1, Math.floor((bottom - top) / gap) + 1);
  labels.forEach(l => { l.col = 0; l.lo = l.bx0; l.hi = l.bx1; });
  // A label only contends with the ones it would actually collide with. Nearly
  // all of them sit at the last save, but a nation that stopped existing partway
  // leaves its tag out in the middle of the chart, where it is nowhere near the
  // right-hand stack and has no business being shoved about by it. So they are
  // grouped by whether the space they take overlaps at all, merging as it goes:
  // two tags that each clear a third but not each other still have to end up in
  // one group, which a fixed distance test gets wrong.
  //
  // Grouping and column count feed each other, though -- a group that needs a
  // second column takes more width, which can reach the group beside it, which
  // then belongs in the same group -- so the two are settled together, grouping
  // and sizing in turn until nothing more moves. The space a group claims only
  // ever grows, so groups only ever combine and this always comes to a stop.
  let columns = [];
  for (let pass = 0; pass < 8; pass++) {
    const next = [];
    let open = null;
    labels.slice().sort((a, b) => a.lo - b.lo).forEach(l => {
      if (open && l.lo < open.edge) {
        open.list.push(l);
        open.wide = Math.max(open.wide, l.wide);
        open.edge = Math.max(open.edge, l.hi);
      } else {
        open = {list: [l], wide: l.wide, edge: l.hi};
        next.push(open);
      }
    });
    let settled = next.length === columns.length;
    next.forEach(col => {
      // More labels than the height holds at a legible gap. Squeezing them in
      // regardless only trades one unreadable pile for another, so the stack
      // steps sideways into a second column, a third, as many as it takes. The
      // one limit is width -- labels may eat into the plot, but not swallow
      // it -- and past that the packer falls back to crowding.
      const room = Math.max(1, Math.floor((W - M.l) * 0.5 / col.wide));
      col.k = Math.min(room, Math.max(1, Math.ceil(col.list.length / fits)));
      // Every tag in a group hangs off one shared anchor rather than off its
      // own line's end. Stepping each label sideways from wherever its own line
      // stopped would put one group's second column straight through the next
      // group's first, which is the collision the grouping just went to the
      // trouble of ruling out.
      col.end = col.list.some(l => l.atEnd);
      const left = Math.min(...col.list.map(l => l.bx0));
      col.anchor = col.end ? W - 4 : Math.max(...col.list.map(l => l.bx0));
      const span = col.k * col.wide;
      // The claim runs from the leftmost line end to the far side of the last
      // column: leaders cross that ground too, and it is what the next group
      // has to clear.
      const lo = col.end ? Math.min(left, col.anchor - span) : left;
      const hi = col.end ? col.anchor : col.anchor + span;
      col.list.forEach(l => {
        if (lo !== l.lo || hi !== l.hi) settled = false;
        l.lo = lo;
        l.hi = hi;
        l.anchor = col.anchor;
        l.end = col.end;
      });
    });
    columns = next;
    if (settled) break;
  }
  columns.forEach(col => {
    col.list.forEach(l => { l.step = col.wide; });
    col.list.sort((a, b) => a.want - b.want);
    // Every k-th label goes to the same column, which leaves each column's
    // labels about k times further apart than they started; handing each column
    // a contiguous block would put the whole crowded run back into one column
    // and fix nothing.
    for (let c = 0; c < col.k; c++) {
      const part = col.list.filter((_, i) => i % col.k === c);
      part.forEach(l => { l.col = c; });
      packColumn(part, gap, top, bottom);
    }
  });
  return labels;
}

