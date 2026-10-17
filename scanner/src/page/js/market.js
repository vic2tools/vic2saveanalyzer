/* =============== MARKET =============== */
const PD = DATA.priceDates, PY = DATA.priceYears;
let goodsOn = [];
let priceLog = false, priceIndex = false;

const pxMin = PY.length ? Math.min(...PY) : 0, pxMax = PY.length ? Math.max(...PY) : 1;
const pxOf = y => M.l + (pxMax === pxMin ? 0 : (y - pxMin) / (pxMax - pxMin)) * (W - M.l - M.r);

const topMovers = n => [...DATA.goods]
  .filter(g => DATA.movement[g] > 0)
  .sort((a, b) => DATA.movement[b] - DATA.movement[a])
  .slice(0, n);

const goodsPicker = makePicker(document.getElementById('pick-goods'), {
  items: [...DATA.goods].sort(byGameName),
  labelFor: g => gameName(g),
  subLabelFor: g => DATA.categoryLabels[DATA.goodCategory[g]] || DATA.goodCategory[g] || '',
  colourFor: goodColour,
  selected: [],
  noun: 'goods',
  presets: [
    ['Military', () => DATA.goods.filter(g => DATA.goodCategory[g] === 'military')],
    ['Industrial', () => DATA.goods.filter(g => DATA.goodCategory[g] === 'industrial')],
    ['Raw', () => DATA.goods.filter(g => DATA.goodCategory[g] === 'raw')],
    ['Consumer', () => DATA.goods.filter(g => DATA.goodCategory[g] === 'consumer')],
    ['None', () => []],
  ],
  onChange: sel => { goodsOn = sel; drawPrices(); },
});
document.getElementById('topmovers').onclick = () => goodsPicker.set(topMovers(6));

const pscale = document.getElementById('pscale');
pscale.onclick = () => {
  priceLog = !priceLog;
  pscale.setAttribute('aria-pressed', priceLog);
  pscale.textContent = priceLog ? 'Logarithmic' : 'Linear';
  drawPrices();
};
const pindex = document.getElementById('pindex');
pindex.onclick = () => {
  priceIndex = !priceIndex;
  pindex.setAttribute('aria-pressed', priceIndex);
  pindex.textContent = priceIndex ? 'Indexed (=100)' : 'Absolute';
  drawPrices();
};

function priceSeries(good) {
  const by = DATA.prices[good] || [];
  const pts = [];
  let base = null;
  for (let i = 0; i < PD.length; i++) {
    let v = by[i];
    if (v == null) continue;
    if (priceIndex) {
      if (base === null) { base = v; if (!base) continue; }
      v = v / base * 100;
    }
    pts.push([PY[i], v]);
  }
  return pts;
}

function drawPrices() {
  const note = document.getElementById('pricenote');
  const shown = DATA.goods.filter(g => goodsOn.includes(g));
  plot(document.getElementById('pricechart'), {
    series: shown.map(g => ({name: gameName(g), colour: goodColour(g),
                             pts: priceSeries(g)})),
    xOf: pxOf, xTicks: yearTicks(pxMin, pxMax),
    hoverXs: PD.map((d, i) => ({v: PY[i], label: d})),
    fmt: v => priceIndex ? Math.round(v).toString() : (v >= 10 ? v.toFixed(0) : v.toFixed(2)),
    log: priceLog, thin: true, baseline: priceIndex ? 100 : null,
    zeroFloor: !priceIndex,
    readout: document.getElementById('pricereadout'),
    idle: 'Hover the plot to read prices at a date.',
    emptyMsg: PD.length ? 'Select a good, or press Top movers.' : 'No price data in these saves.',
  });

  const flat = DATA.goods.filter(g => DATA.movement[g] === 0).length;
  note.textContent = PD.length
    ? `${PD.length} dated readings across ${DATA.goods.length} goods.`
      + (flat ? ` ${flat} never moved in this span, so they are undiscovered or untraded.` : '')
    : '';
}

/* A good that records no sale in any save is not traded on the market at all.
   Precious metal is the standing example: the engine turns it straight into
   money at the mint rather than putting it up for sale, so its supply is real
   and its sales are always nil. Reading that as "100% unsold, for ever" would
   put it at the top of every glut list and say nothing. */
const NEVER_SOLD = new Set(DATA.goods.filter(g =>
  DATA.snapshotDates.every(d => !(((DATA.snapshot[d] || {})[g]) || {}).actual_sold)));
const unsoldShare = (good, snap) =>
  (!snap || !snap.supply || NEVER_SOLD.has(good)) ? null
    : Math.max(0, (snap.supply - snap.actual_sold) / snap.supply * 100);

const snapSel = document.getElementById('snapsel');
DATA.snapshotDates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  snapSel.appendChild(o);
});
if (DATA.snapshotDates.length)
  snapSel.value = DATA.snapshotDates[DATA.snapshotDates.length - 1];
snapSel.onchange = drawMarketTable;

const MARKET_COLS = [
  {key: 'good', label: 'Good', fmt: gameName, sortBy: r => gameName(r.good),
   colour: r => goodColour(r.good)},
  {key: 'category', label: 'Category'},
  {key: 'price', label: 'Price', fmt: v => v.toFixed(2)},
  {key: 'base', label: 'Base', fmt: v => v == null ? '—' : v.toFixed(2),
   title: "The good's base cost from the mod's common/goods.txt"},
  {key: 'vsBase', label: 'vs base',
   fmt: v => v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(0) + '%',
   title: 'How far the world price sits above or below that base cost',
   cls: r => r.vsBase == null ? '' : r.vsBase > 1 ? 'up' : r.vsBase < -1 ? 'down' : ''},
  {key: 'change', label: 'Change',
   fmt: v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%',
   cls: r => r.change > 0.05 ? 'up' : r.change < -0.05 ? 'down' : ''},
  {key: 'supply', label: 'Supply', fmt: fmtCount},
  {key: 'demand', label: 'Demand', fmt: fmtCount},
  {key: 'actual_sold', label: 'Sold', fmt: fmtCount},
  {key: 'unsold', label: 'Unsold', fmt: v => v == null ? '—' : v.toFixed(0) + '%',
   title: "The share of the day's supply nobody bought. A good left on the "
        + 'quayside is being overproduced whatever its demand figure says, '
        + 'which matters in a mod where one nation stands ready to buy the '
        + "world's surplus.",
   cls: r => r.unsold == null ? '' : r.unsold > 25 ? 'down' : r.unsold < 2 ? 'up' : ''},
  {key: 'pegged', label: 'Pegged', fmt: v => v ? 'yes' : '—',
   title: 'A buyer with no limit is standing in this good\'s market: demand is '
        + 'recorded as something on the order of a billion, which no economy '
        + 'produces. Every pegged reading in these saves sits at exactly five '
        + "times the good's base cost, the engine's price ceiling -- so the price "
        + 'says nothing about whether the good is scarce or drowning.',
   cls: r => r.pegged ? 'down' : ''},
];
const marketState = {key: 'change', dir: -1};
function drawMarketTable() {
  const date = snapSel.value;
  document.getElementById('snapdate').textContent = date || '—';
  const snap = DATA.snapshot[date] || {};
  const rows = Object.keys(snap).map(good => {
    const by = DATA.prices[good] || [];
    const seen = [];
    for (let i = 0; i < PD.length; i++) if (by[i] != null) seen.push(i);
    const first = seen.length ? by[seen[0]] : 0;
    const last = seen.length ? by[seen[seen.length - 1]] : 0;
    const base = DATA.basePrices[good];
    return {
      good, category: DATA.goodCategory[good] || 'other',
      price: snap[good].price,
      base: base == null ? null : base,
      vsBase: base ? (snap[good].price - base) / base * 100 : null,
      change: first ? (last - first) / first * 100 : 0,
      supply: snap[good].supply,
      demand: snap[good].demand,
      actual_sold: snap[good].actual_sold,
      unsold: unsoldShare(good, snap[good]),
      pegged: snap[good].pegged,
      discovered: snap[good].discovered,
    };
  }).filter(r => r.discovered);
  renderTable(document.getElementById('market'), MARKET_COLS, rows, marketState,
              row => { goodsPicker.set([row.good]); showProducers(row.good, date); });
}

/* =============== WHO PRODUCES IT ===============
   Each country block carries `saved_country_supply`: what that nation put on
   the world market. Added up over every nation it comes back to the market's
   own supply pool, which is what makes it production as the market sees it
   rather than a stockpile or an income.

   Overproduction is the thing worth finding here, and demand is a poor guide
   to it. A mod with a nation that stands ready to buy any surplus -- IGoR's
   world bank -- keeps demand permanently above supply for goods that are
   plainly drowning, so the honest signals are elsewhere: how much of the day's
   supply went unsold, and how far the price has sunk below the good's own base
   cost. Both are in the table above; this names who is doing it. */
const SUPPLY = DATA.supply || {};

const prodSave = document.getElementById('prodsave');
const prodGood = document.getElementById('prodgood');
const prodDates = DATA.dates.filter(d => Object.values(SUPPLY).some(by => by[d]));
prodDates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  prodSave.appendChild(o);
});
if (prodDates.length) prodSave.value = prodDates[prodDates.length - 1];
prodSave.onchange = drawSupply;

const prodGoods = DATA.goods.filter(g => SUPPLY[g]).sort(byGameName);
prodGoods.forEach(g => {
  const o = document.createElement('option'); o.value = g;
  o.textContent = gameName(g);
  prodGood.appendChild(o);
});
prodGood.onchange = drawSupply;
// Open on whatever the world makes most of, which is a good with enough
// suppliers to be worth a chart rather than whatever sorts first.
if (prodGoods.length) {
  const at = prodDates[prodDates.length - 1];
  prodGood.value = prodGoods.slice().sort((a, b) =>
    ((SUPPLY[b][at] || {}).t || 0) - ((SUPPLY[a][at] || {}).t || 0))[0];
}

/* Jump the panel to one good -- a click in the market table means that good. */
function showProducers(good, date) {
  if (!SUPPLY[good]) return;
  prodGood.value = good;
  if (date && prodDates.includes(date)) prodSave.value = date;
  drawSupply();
}

function drawSupply() {
  const svg = document.getElementById('prodchart');
  svg.textContent = '';
  const note = document.getElementById('prodnote');
  const readout = document.getElementById('prodreadout');
  const date = prodSave.value, good = prodGood.value;
  document.getElementById('proddate').textContent = date || '\u2014';
  const rec = (SUPPLY[good] || {})[date];
  const PW = 1000, PH = 430;
  if (!rec || !rec.t) {
    const t = el('text', {x: PW / 2, y: PH / 2, 'text-anchor': 'middle', fill: '#C9AC80',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = prodDates.length
      ? `Nobody supplied ${good ? gameName(good) : 'this good'} at ${date}.`
      : 'These saves carry no per-nation supply.';
    svg.appendChild(t);
    readout.textContent = '';
    note.textContent = '';
    return;
  }

  const named = rec.n.reduce((sum, pair) => sum + pair[1], 0);
  const rest = rec.t - named;
  const bars = rec.n.map(pair => ({tag: pair[0], value: pair[1], colour: colourFor(pair[0])}));
  // Everyone the payload did not name, kept as one bar so the shares still add
  // up to the world's supply instead of quietly to less than it.
  if (rest > rec.t * 0.005)
    bars.push({tag: '', value: rest, colour: 'var(--grid)', rest: true});

  const snap = (DATA.snapshot[date] || {})[good] || {};
  const base = DATA.basePrices[good];
  const unsold = unsoldShare(good, snap);

  const left = 132, right = 156, top = 58, bottom = 14;
  const rowH = Math.min(26, (PH - top - bottom) / Math.max(1, bars.length));
  const barH = Math.max(6, rowH - 7);
  const peak = Math.max(...bars.map(b => b.value));
  const spanX = PW - left - right;
  const at = v => v / (peak || 1) * spanX;

  const head = el('text', {x: left, y: 28, fill: 'var(--ink)',
    'font-family': 'Barlow Condensed, sans-serif', 'font-size': 22, 'font-weight': 600});
  head.textContent = gameName(good);
  svg.appendChild(head);
  const sub = el('text', {x: left, y: 47, fill: 'var(--ink-dim)',
    'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
  sub.textContent = `world supply ${fmtCount(rec.t)}`
    + (snap.actual_sold !== undefined ? ` \u00b7 sold ${fmtCount(snap.actual_sold)}` : '')
    + (unsold !== null ? ` \u00b7 ${unsold.toFixed(0)}% unsold` : '')
    + (snap.price !== undefined ? ` \u00b7 price ${snap.price.toFixed(2)}` : '')
    + (base ? ` \u00b7 ${((snap.price - base) / base * 100).toFixed(0)}% vs base` : '')
    + (snap.pegged ? ' \u00b7 price pegged at its ceiling' : '');
  svg.appendChild(sub);

  const tell = bar => {
    const share = bar.value / rec.t * 100;
    readout.innerHTML =
      `<span class="rk">${bar.rest ? 'everyone else' : nameOf(bar.tag)}</span>`
      + `<span><b style="color:${bar.rest ? 'var(--ink)' : colourFor(bar.tag)}">`
      + `${fmtCount(bar.value)}</b> <span class="rk">of ${fmtCount(rec.t)}</span></span>`
      + `<span><span class="rk">share</span> <b>${share.toFixed(1)}%</b></span>`
      + (bar.rest ? '<span class="rk">every supplier outside the top '
                    + `${rec.n.length}</span>` : '');
  };

  bars.forEach((bar, i) => {
    const y = top + i * rowH;
    const w = Math.max(1, at(bar.value));
    const label = el('text', {x: left - 10, y: y + barH * 0.5 + 4, 'text-anchor': 'end',
      fill: bar.rest ? 'var(--ink-dim)' : colourFor(bar.tag),
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
    label.textContent = bar.rest ? 'everyone else' : bar.tag;
    svg.appendChild(label);

    const rect = el('rect', {x: left, y, width: w, height: barH,
      fill: bar.colour, 'fill-opacity': bar.rest ? .35 : .82,
      stroke: 'var(--ground)', 'stroke-width': .5});
    rect.style.cursor = 'pointer';
    rect.onpointerenter = () => { rect.setAttribute('fill-opacity', 1); tell(bar); };
    rect.onpointerleave = () => rect.setAttribute('fill-opacity', bar.rest ? .35 : .82);
    const title = document.createElementNS(SVGNS, 'title');
    title.textContent = `${bar.rest ? 'everyone else' : nameOf(bar.tag)}: `
      + `${fmtCount(bar.value)} (${(bar.value / rec.t * 100).toFixed(1)}%)`;
    rect.appendChild(title);
    svg.appendChild(rect);

    const value = el('text', {x: left + w + 8, y: y + barH * 0.5 + 4,
      fill: 'var(--ink)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
    value.textContent =
      `${fmtCount(bar.value)}   ${(bar.value / rec.t * 100).toFixed(1)}%`;
    svg.appendChild(value);
  });

  const three = rec.n.slice(0, 3).reduce((sum, pair) => sum + pair[1], 0);
  const idle = `<span class="rk">${bars.length} bars</span>`
    + `<span><span class="rk">largest</span> <b style="color:${colourFor(rec.n[0][0])}">`
    + `${rec.n[0][0]}</b> <span class="rk">`
    + `${(rec.n[0][1] / rec.t * 100).toFixed(1)}%</span></span>`
    + `<span><span class="rk">top three</span> <b>${(three / rec.t * 100).toFixed(1)}%</b></span>`
    + (unsold !== null ? `<span><span class="rk">unsold</span> <b>${unsold.toFixed(0)}%</b></span>` : '');
  svg.onpointerleave = () => readout.innerHTML = idle;
  readout.innerHTML = idle;

  note.textContent = 'Choose a good and save; hover a bar to see a nation’s contribution to world supply.';
}

