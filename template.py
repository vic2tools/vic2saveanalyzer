"""HTML template for the report. Kept apart so report.py stays readable."""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campaign returns</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --ground:#0C2440; --ground-deep:#08192C; --panel:#10314F;
  --rule:#3E6E96; --grid:#1B4266;
  --ink:#E4EFF7; --ink-dim:#8FB4CE;
  --brass:#F2B441; --minium:#E0644F;
  --sheet-pad:clamp(16px,4vw,44px);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--ground-deep);color:var(--ink);
  font-family:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased;
}
.sheet{
  max-width:1180px;margin:0 auto;padding:var(--sheet-pad);
  background:var(--ground);
  background-image:
    linear-gradient(var(--grid) 1px,transparent 1px),
    linear-gradient(90deg,var(--grid) 1px,transparent 1px);
  background-size:28px 28px;min-height:100vh;
  border-left:1px solid var(--rule);border-right:1px solid var(--rule);
}
.titleblock{
  border:1px solid var(--rule);background:rgba(8,25,44,.86);
  display:grid;grid-template-columns:1.6fr 1fr 1fr 1fr;
}
.titleblock>div{padding:12px 16px;border-right:1px solid var(--rule)}
.titleblock>div:last-child{border-right:0}
.tb-label{
  font-family:'Barlow Condensed','Arial Narrow',sans-serif;
  text-transform:uppercase;letter-spacing:.18em;font-size:11px;
  color:var(--ink-dim);margin-bottom:3px;
}
.tb-value{
  font-family:'Barlow Condensed','Arial Narrow',sans-serif;
  font-size:clamp(19px,2.4vw,27px);font-weight:500;letter-spacing:.02em;line-height:1.1;
}
h1.tb-value{margin:0;font-weight:600;letter-spacing:.04em}
.tb-value.mono{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:19px}
@media(max-width:760px){.titleblock{grid-template-columns:1fr 1fr}
  .titleblock>div{border-bottom:1px solid var(--rule)}}

.tabs{display:flex;flex-wrap:wrap;margin:0 0 26px;border-bottom:1px solid var(--rule)}
.tab{
  font-family:'Barlow Condensed','Arial Narrow',sans-serif;
  text-transform:uppercase;letter-spacing:.19em;font-size:13px;font-weight:600;
  background:transparent;border:1px solid var(--rule);border-bottom:0;
  color:var(--ink-dim);padding:11px 20px;cursor:pointer;
  margin-right:-1px;margin-bottom:-1px;
}
.tab[aria-selected="true"]{
  background:var(--ground);color:var(--brass);box-shadow:inset 0 3px 0 var(--brass)}
.tab:focus-visible{outline:2px solid var(--brass);outline-offset:-4px}
[role="tabpanel"][hidden]{display:none}

section{margin-bottom:34px}
h2{
  font-family:'Barlow Condensed','Arial Narrow',sans-serif;
  text-transform:uppercase;letter-spacing:.2em;font-size:13px;font-weight:600;
  color:var(--ink-dim);margin:0 0 12px;padding-bottom:7px;
  border-bottom:1px solid var(--rule);
}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
select,button,input[type=search]{
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;
  background:var(--panel);color:var(--ink);
  border:1px solid var(--rule);border-radius:0;padding:7px 11px;
}
select,button{cursor:pointer}
select:focus-visible,button:focus-visible,input:focus-visible{
  outline:2px solid var(--brass);outline-offset:2px}
.controls > button[aria-pressed="true"]{
  background:var(--brass);color:var(--ground-deep);border-color:var(--brass)}

/* ---- searchable picker ---- */
.picker{position:relative;display:inline-block}
.picker-toggle{display:flex;align-items:center;gap:9px;min-width:210px;text-align:left}
.picker-toggle .caret{margin-left:auto;color:var(--ink-dim)}
.picker-panel{
  position:absolute;z-index:20;top:calc(100% + 3px);left:0;width:330px;max-width:88vw;
  background:#0A2138;border:1px solid var(--rule);padding:10px;
  box-shadow:0 10px 28px rgba(0,0,0,.5);
}
.picker-panel[hidden]{display:none}
.picker-search{width:100%;margin-bottom:8px}
.picker-presets{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap}
.picker-presets button{padding:5px 9px;font-size:12px}
.picker-list{max-height:260px;overflow-y:auto;border-top:1px solid var(--grid)}
.picker-opt{
  display:flex;align-items:center;gap:9px;width:100%;text-align:left;
  background:transparent;border:0;border-bottom:1px solid var(--grid);
  color:var(--ink-dim);padding:7px 6px;cursor:pointer;
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px;
}
.picker-opt:hover{background:rgba(63,110,150,.24)}
.picker-opt[aria-pressed="true"]{color:var(--ink);background:rgba(242,180,65,.10)}
.picker-opt[aria-pressed="true"] .tag{color:var(--brass)}
.picker-opt .swatch{width:10px;height:10px;flex:0 0 10px;opacity:.25}
.picker-opt[aria-pressed="true"] .swatch{opacity:1}
.picker-opt .tag{width:42px;flex:0 0 42px;color:var(--ink)}
.picker-opt .nm{color:var(--ink-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.picker-empty{padding:12px 6px;color:var(--ink-dim);font-size:12.5px}

figure{margin:0;border:1px solid var(--rule);background:rgba(8,25,44,.72)}
svg{display:block;width:100%;height:auto}
@media(max-width:640px){
  figure{overflow-x:auto}
  figure svg{min-width:640px}
  .readout{position:sticky;left:0}
}
.axis text{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;fill:var(--ink-dim)}
.gridline{stroke:var(--grid);stroke-width:1}
.axisline{stroke:var(--rule);stroke-width:1}
.plotline{fill:none;stroke-width:1.75;stroke-linejoin:round;stroke-linecap:round}
.plotline.thin{stroke-width:1.35}
@media(prefers-reduced-motion:no-preference){
  .plotline{stroke-dasharray:var(--len);stroke-dashoffset:var(--len);
    animation:draw .9s cubic-bezier(.3,.7,.3,1) forwards}
  @keyframes draw{to{stroke-dashoffset:0}}
}
.readout{
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px;
  border-top:1px solid var(--rule);padding:11px 14px;
  display:flex;flex-wrap:wrap;gap:5px 22px;min-height:42px;align-items:center;
}
.readout .rk{color:var(--ink-dim)}
.readout b{font-weight:500}
table{width:100%;border-collapse:collapse;
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px}
th,td{padding:7px 9px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{
  font-family:'Barlow Condensed','Arial Narrow',sans-serif;font-size:12px;
  text-transform:uppercase;letter-spacing:.13em;color:var(--ink-dim);
  cursor:pointer;user-select:none;border-bottom:1px solid var(--rule);
}
th:hover{color:var(--ink)}
th[aria-sort]{color:var(--brass)}
tbody tr:hover{background:rgba(63,110,150,.16)}
.tablewrap{overflow:auto;max-height:560px;
  border:1px solid var(--rule);background:rgba(8,25,44,.72)}
/* Without this the table shrinks to the wrapper instead of overflowing, so
   wide tables clip their right-hand columns with nothing to scroll to. */
.tablewrap table{min-width:max-content}
.tablewrap thead th{position:sticky;top:0;background:#0A2138;z-index:2}
/* Pin the label column so nation columns stay identifiable when scrolled. */
.tablewrap.pinned td:first-child,
.tablewrap.pinned th:first-child{position:sticky;left:0;background:#0A2138}
.tablewrap.pinned td:first-child{z-index:1}
.tablewrap.pinned thead th:first-child{z-index:3}
.tablewrap.pinned tbody tr:hover td:first-child{background:#123048}
.groupcell{color:var(--brass);background:#132C46 !important;position:static !important}
/* A full-width colspan cell cannot stick, so pin the label inside it. */
.groupcell span{position:sticky;left:9px;display:inline-block}
.up{color:#9BD65E}.down{color:var(--minium)}
/* Centre labels sit over the donut hole; they must never eat hover events. */
#milpies text{pointer-events:none}
.note{color:var(--ink-dim);font-size:13px;margin:10px 2px 0}
.stackwrap{display:flex;flex-wrap:wrap;gap:7px;margin-top:11px}
.slegend{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:11.5px;
  color:var(--ink-dim);display:flex;align-items:center;gap:6px}
.slegend i{width:9px;height:9px;display:block}
footer{color:var(--ink-dim);font-size:12.5px;border-top:1px solid var(--rule);
  padding-top:14px;margin-top:8px}
</style>
</head>
<body>
<main class="sheet">

  <div class="titleblock">
    <div><div class="tb-label">Sheet</div><h1 class="tb-value">Campaign returns</h1></div>
    <div><div class="tb-label">Span</div><div class="tb-value mono">__SPAN__</div></div>
    <div><div class="tb-label">Saves</div><div class="tb-value mono">__SAVECOUNT__</div></div>
    <div><div class="tb-label">Nations</div><div class="tb-value mono">__NATIONCOUNT__</div></div>
  </div>

  <div class="tabs" role="tablist" aria-label="Views">
    <button class="tab" role="tab" id="tab-nations" aria-controls="panel-nations" aria-selected="true">Nations</button>
    <button class="tab" role="tab" id="tab-military" aria-controls="panel-military" aria-selected="false">Military</button>
    <button class="tab" role="tab" id="tab-fleets" aria-controls="panel-fleets" aria-selected="false">Fleets</button>
    <button class="tab" role="tab" id="tab-pops" aria-controls="panel-pops" aria-selected="false">Pops</button>
    <button class="tab" role="tab" id="tab-market" aria-controls="panel-market" aria-selected="false">Market</button>
  </div>

  <!-- ============ NATIONS ============ -->
  <div role="tabpanel" id="panel-nations" aria-labelledby="tab-nations">
    <section>
      <h2>Series</h2>
      <div class="controls">
        <label class="tb-label" for="metric" style="margin:0">Measure</label>
        <select id="metric"></select>
        <span id="pick-nations"></span>
        <button id="scale" aria-pressed="false" title="Switch between linear and logarithmic vertical scale">Linear</button>
      </div>
      <figure>
        <svg id="chart" viewBox="0 0 1000 460" role="img" aria-label="Metric plotted over time by nation"></svg>
        <div class="readout" id="readout"></div>
      </figure>
    </section>

    <section>
      <h2>Standing at <span id="lastdate"></span></h2>
      <div class="tablewrap"><table id="ledger"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Click a column heading to sort. Only the nations selected above are listed.</p>
    </section>
  </div>

  <!-- ============ MILITARY ============ -->
  <div role="tabpanel" id="panel-military" aria-labelledby="tab-military" hidden>
    <section>
      <h2>Head to head at <span id="mildate"></span></h2>
      <div class="controls">
        <label class="tb-label" for="milsave" style="margin:0">Save</label>
        <select id="milsave"></select>
        <button id="milmode" aria-pressed="false" title="Switch the pies between land regiments and naval hulls">Army</button>
        <button id="milmob" aria-pressed="true" title="Add each nation's mobilization ceiling to its brigade count. Army only.">With mobilization</button>
      </div>
      <div class="controls">
        <label class="tb-label" style="margin:0">Left</label>
        <span id="pick-milA"></span>
        <label class="tb-label" style="margin:0">Right</label>
        <span id="pick-milB"></span>
        <button id="milswap" title="Swap the two sides">Swap</button>
        <button id="milview" aria-pressed="false" title="Totals compares the two sides as one pie; composition breaks each side down by unit type">Totals</button>
      </div>
      <figure>
        <svg id="milpies" viewBox="0 0 1000 400" role="img" aria-label="Force composition compared between two nations"></svg>
        <div class="readout" id="milreadout"></div>
      </figure>
      <div class="stackwrap" id="millegend"></div>
      <p class="note">Hover a slice on either pie and both nations' counts for that type are shown together.</p>
    </section>

    <section>
      <h2>Overview</h2>
      <div class="controls">
        <span id="pick-military"></span>
      </div>
      <div class="tablewrap pinned"><table id="miltable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Click a heading to sort. Scroll sideways for the remaining unit-type columns.
        <strong>Brigades</strong> counts every raised regiment, professionals plus any currently
        mobilized. <strong>Professionals</strong> are the ones raised from soldier pops, which
        stand whether or not the nation is mobilized. <strong>Mob ceiling</strong> is every brigade
        the mobilizable population could raise at the nation's mobilisation size &mdash; the whole
        pool, including any brigades already mobilized out of it. <strong>Total military
        potential</strong> is professionals plus that ceiling: the largest army the nation could
        field. With <code>--mod-path</code> the mobilisation size is read from the mod; without it,
        it comes from <code>--mobilisation-size</code>.</p>
    </section>

    <section>
      <h2>Military technology</h2>
      <div class="tablewrap pinned"><table id="techtable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note" id="technote">Rows follow research order within each line, so progress reads top to
        bottom. Columns are ordered by military tech, so scroll sideways for the nations with least.</p>
    </section>
  </div>

  <!-- ============ FLEETS ============ -->
  <div role="tabpanel" id="panel-fleets" aria-labelledby="tab-fleets" hidden>
    <section>
      <h2>Compare navies</h2>
      <div class="controls">
        <label class="tb-label" for="shiptype" style="margin:0">Hull</label>
        <select id="shiptype"></select>
        <span id="pick-fleet"></span>
        <button id="fscale" aria-pressed="false">Linear</button>
      </div>
      <figure>
        <svg id="fleetchart" viewBox="0 0 1000 460" role="img" aria-label="Ship counts over time by nation"></svg>
        <div class="readout" id="fleetreadout"></div>
      </figure>
    </section>

    <section>
      <h2>Fleets at <span id="fleetdate"></span></h2>
      <div class="controls">
        <label class="tb-label" for="fleetsave" style="margin:0">Save</label>
        <select id="fleetsave"></select>
      </div>
      <div class="tablewrap"><table id="fleettable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Every hull type present in the save gets a column. Click a heading to sort.</p>
    </section>

    <section>
      <h2>Fleet composition</h2>
      <div class="controls">
        <label class="tb-label" for="navtag" style="margin:0">Nation</label>
        <select id="navtag"></select>
      </div>
      <figure>
        <svg id="navy" viewBox="0 0 1000 360" role="img" aria-label="Ship counts by type over time"></svg>
      </figure>
      <div class="stackwrap" id="navlegend"></div>
      <p class="note">Hull types are read straight from the save, so mod-added ships appear under their own names.</p>
    </section>
  </div>

  <!-- ============ POPS ============ -->
  <div role="tabpanel" id="panel-pops" aria-labelledby="tab-pops" hidden>
    <section>
      <h2>Pops at <span id="popdate"></span></h2>
      <div class="controls">
        <label class="tb-label" for="popsave" style="margin:0">Save</label>
        <select id="popsave"></select>
        <button id="popshare" aria-pressed="false" title="Show each pop type as a share of the nation's population">Counts</button>
      </div>
      <div class="tablewrap"><table id="poptable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Click a heading to sort, or a row to see that nation's cultures below.</p>
    </section>

    <section>
      <h2>Cultures &middot; <span id="cultag"></span></h2>
      <div class="controls">
        <label class="tb-label" for="cultagsel" style="margin:0">Nation</label>
        <select id="cultagsel"></select>
      </div>
      <div class="tablewrap"><table id="cultable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Accepted cultures are the primary culture plus anything in the nation's accepted list at that save.</p>
    </section>

    <section>
      <h2>Population composition</h2>
      <div class="controls">
        <label class="tb-label" for="poptag" style="margin:0">Nation</label>
        <select id="poptag"></select>
      </div>
      <figure>
        <svg id="popchart" viewBox="0 0 1000 360" role="img" aria-label="Pop sizes by type over time"></svg>
      </figure>
      <div class="stackwrap" id="poplegend"></div>
    </section>
  </div>

  <!-- ============ MARKET ============ -->
  <div role="tabpanel" id="panel-market" aria-labelledby="tab-market" hidden>
    <section>
      <h2>World prices &middot; <span>__PRICESPAN__</span></h2>
      <div class="controls">
        <span id="pick-goods"></span>
        <button id="topmovers">Top movers</button>
        <button id="pscale" aria-pressed="false">Linear</button>
        <button id="pindex" aria-pressed="false" title="Rebase every good to 100 at its first reading so goods at different price levels can be compared">Absolute</button>
      </div>
      <figure>
        <svg id="pricechart" viewBox="0 0 1000 460" role="img" aria-label="Goods prices over time"></svg>
        <div class="readout" id="pricereadout"></div>
      </figure>
      <p class="note" id="pricenote"></p>
    </section>

    <section>
      <h2>Market at <span id="snapdate"></span></h2>
      <div class="controls">
        <label class="tb-label" for="snapsel" style="margin:0">Save</label>
        <select id="snapsel"></select>
      </div>
      <div class="tablewrap"><table id="market"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Supply, demand and quantity sold are stored only for the save's own date, so this
        is a snapshot rather than a series. Demand is the real figure: Victoria&nbsp;II inflates the
        stored value by about two billion to hold a good at its price floor, and those goods are
        marked. Change is measured across the whole price span. Click a row to plot that good.</p>
    </section>
  </div>

  <footer>
    Generated from Victoria&nbsp;II save files. Population counts are the sum of
    pop sizes in owned provinces; literacy, consciousness and militancy are
    weighted by pop size. Prices come from the rolling monthly buffer each save
    carries, stitched together across saves.
  </footer>
</main>

<script>
const DATA = __DATA__;
const C = DATA.colours;
const SVGNS = 'http://www.w3.org/2000/svg';
const el = (n, a) => { const e = document.createElementNS(SVGNS, n);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
const W = 1000, H = 460, M = {t: 20, r: 20, b: 40, l: 80};

const nameOf = t => DATA.tagNames[t] || t;
const colourFor = t => C[DATA.tags.indexOf(t) % C.length];
const goodColour = g => C[DATA.goods.indexOf(g) % C.length];

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
// Keep end-of-line labels from stacking on top of one another.
function spread(labels, gap, top, bottom) {
  labels.sort((a, b) => a.y - b.y);
  for (let i = 1; i < labels.length; i++)
    if (labels[i].y - labels[i-1].y < gap) labels[i].y = labels[i-1].y + gap;
  const over = labels.length ? labels[labels.length-1].y - bottom : 0;
  if (over > 0) labels.forEach(l => l.y -= over);
  if (labels.length && labels[0].y < top)
    labels.forEach(l => l.y += top - labels[0].y);
  return labels;
}

/* =============== searchable picker =============== */
function makePicker(mount, cfg) {
  // cfg: {items, labelFor, subLabelFor, colourFor, selected, presets, noun, onChange}
  const selected = new Set(cfg.selected || []);
  const wrap = document.createElement('span');
  wrap.className = 'picker';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'picker-toggle';
  toggle.setAttribute('aria-expanded', 'false');
  const panel = document.createElement('div');
  panel.className = 'picker-panel';
  panel.hidden = true;

  const search = document.createElement('input');
  search.type = 'search';
  search.className = 'picker-search';
  search.placeholder = 'Search ' + cfg.noun + '…';
  search.setAttribute('aria-label', 'Search ' + cfg.noun);

  const presets = document.createElement('div');
  presets.className = 'picker-presets';
  const list = document.createElement('div');
  list.className = 'picker-list';

  panel.append(search, presets, list);
  wrap.append(toggle, panel);
  mount.replaceWith(wrap);

  const optFor = {};
  cfg.items.forEach(item => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'picker-opt';
    const sub = cfg.subLabelFor ? cfg.subLabelFor(item) : '';
    b.innerHTML = `<span class="swatch" style="background:${cfg.colourFor(item)}"></span>`
      + `<span class="tag">${cfg.labelFor(item)}</span>`
      + (sub ? `<span class="nm">${sub}</span>` : '');
    b.onclick = () => {
      selected.has(item) ? selected.delete(item) : selected.add(item);
      sync(); cfg.onChange(ordered());
    };
    optFor[item] = b;
    list.appendChild(b);
  });
  const empty = document.createElement('div');
  empty.className = 'picker-empty';
  empty.textContent = 'Nothing matches.';
  empty.hidden = true;
  list.appendChild(empty);

  (cfg.presets || []).forEach(([label, fn]) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = label;
    b.onclick = () => {
      selected.clear(); fn().forEach(i => selected.add(i));
      sync(); cfg.onChange(ordered());
    };
    presets.appendChild(b);
  });

  // Always report in the item list's own order so table columns stay put.
  const ordered = () => cfg.items.filter(i => selected.has(i));

  function sync() {
    cfg.items.forEach(i => optFor[i].setAttribute('aria-pressed', selected.has(i)));
    const n = selected.size;
    const word = n === 1 ? cfg.noun.replace(/s$/, '') : cfg.noun;
    toggle.innerHTML = `<span>${n} ${word} selected</span><span class="caret">▾</span>`;
  }
  search.oninput = () => {
    const q = search.value.trim().toLowerCase();
    let visible = 0;
    cfg.items.forEach(i => {
      const hay = (cfg.labelFor(i) + ' ' + (cfg.subLabelFor ? cfg.subLabelFor(i) : '')).toLowerCase();
      const on = !q || hay.includes(q);
      optFor[i].style.display = on ? '' : 'none';
      if (on) visible++;
    });
    empty.hidden = visible > 0;
  };
  toggle.onclick = () => {
    const open = panel.hidden;
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', open);
    if (open) search.focus();
  };
  document.addEventListener('click', ev => {
    if (!wrap.contains(ev.target)) { panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); }
  });
  panel.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') { panel.hidden = true; toggle.setAttribute('aria-expanded','false'); toggle.focus(); }
  });

  sync();
  return {
    get: () => cfg.items.filter(i => selected.has(i)),
    set: list => { selected.clear(); list.forEach(i => selected.add(i)); sync(); cfg.onChange(ordered()); },
  };
}

/* =============== generic line plot =============== */
function plot(svg, cfg) {
  svg.textContent = '';
  const readout = cfg.readout;
  const idle = cfg.idle || 'Hover the plot to read values.';
  if (!cfg.series.length || !cfg.series.some(s => s.pts.length)) {
    const t = el('text', {x: W/2, y: H/2, 'text-anchor': 'middle', fill: '#8FB4CE',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = cfg.emptyMsg || 'Nothing to plot.';
    svg.appendChild(t);
    if (readout) readout.textContent = '';
    return;
  }

  const log = cfg.log;
  let vals = [];
  cfg.series.forEach(s => s.pts.forEach(([, v]) => { if (!log || v > 0) vals.push(v); }));
  if (!vals.length) {
    const t = el('text', {x: W/2, y: H/2, 'text-anchor': 'middle', fill: '#8FB4CE',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = 'No positive values to show on a log scale.';
    svg.appendChild(t);
    if (readout) readout.textContent = '';
    return;
  }

  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (log) { lo = Math.log10(lo); hi = Math.log10(hi); }
  else { lo = Math.min(lo, cfg.zeroFloor === false ? lo : 0); }
  if (hi === lo) hi = lo + 1;
  hi += (hi - lo) * 0.06;
  const yOf = v => {
    const s = log ? Math.log10(Math.max(v, 1e-9)) : v;
    return M.t + (1 - (s - lo) / (hi - lo)) * (H - M.t - M.b);
  };
  const xOf = cfg.xOf;

  const axis = el('g', {class: 'axis'});
  (log ? logTicks(lo, hi) : niceTicks(lo, hi, 6)).forEach(tick => {
    const y = M.t + (1 - (tick - lo) / (hi - lo)) * (H - M.t - M.b);
    if (y < M.t - 1 || y > H - M.b + 1) return;
    axis.appendChild(el('line', {x1: M.l, x2: W - M.r, y1: y, y2: y, class: 'gridline'}));
    const label = el('text', {x: M.l - 9, y: y + 3.5, 'text-anchor': 'end'});
    label.textContent = cfg.fmt(log ? Math.pow(10, tick) : tick);
    axis.appendChild(label);
  });
  cfg.xTicks.forEach(({v, label: txt}) => {
    const x = xOf(v);
    axis.appendChild(el('line', {x1: x, x2: x, y1: M.t, y2: H - M.b, class: 'gridline'}));
    const label = el('text', {x: x, y: H - M.b + 17, 'text-anchor': 'middle'});
    label.textContent = txt;
    axis.appendChild(label);
  });
  if (cfg.baseline != null) {
    const y = yOf(cfg.baseline);
    if (y > M.t && y < H - M.b)
      axis.appendChild(el('line', {x1: M.l, x2: W - M.r, y1: y, y2: y,
        stroke: 'var(--rule)', 'stroke-width': 1, 'stroke-dasharray': '3 3'}));
  }
  axis.appendChild(el('line', {x1: M.l, x2: M.l, y1: M.t, y2: H - M.b, class: 'axisline'}));
  axis.appendChild(el('line', {x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b, class: 'axisline'}));
  svg.appendChild(axis);

  const endLabels = [];
  cfg.series.forEach(s => {
    const pts = s.pts.filter(([, v]) => !log || v > 0);
    if (!pts.length) return;
    const xy = pts.map(([x, v]) => [xOf(x), yOf(v)]);
    if (xy.length > 1) {
      const path = el('path', {
        d: xy.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' '),
        stroke: s.colour, class: 'plotline' + (cfg.thin ? ' thin' : ''),
      });
      let len = 0;
      for (let i = 1; i < xy.length; i++)
        len += Math.hypot(xy[i][0] - xy[i-1][0], xy[i][1] - xy[i-1][1]);
      path.style.setProperty('--len', len.toFixed(0));
      svg.appendChild(path);
    }
    if (cfg.markers)
      xy.forEach(p => svg.appendChild(el('rect', {
        x: p[0] - 2.5, y: p[1] - 2.5, width: 5, height: 5,
        fill: 'var(--ground)', stroke: s.colour, 'stroke-width': 1.5})));
    const last = xy[xy.length - 1];
    endLabels.push({name: s.name, colour: s.colour, x: last[0], y: last[1]});
  });
  const gap = cfg.thin ? 11.5 : 12;
  spread(endLabels, gap, M.t + 4, H - M.b).forEach(({name, colour, x, y}) => {
    const atEnd = x > W - M.r - (cfg.thin ? 70 : 46);
    const label = el('text', {x: atEnd ? x - 6 : x + 6, y: y + 3.5, fill: colour,
      'font-family': 'IBM Plex Mono, monospace', 'font-size': cfg.thin ? 10.5 : 11,
      'text-anchor': atEnd ? 'end' : 'start'});
    label.textContent = name;
    svg.appendChild(label);
  });

  if (!readout || !cfg.hoverXs) return;
  const hover = el('line', {x1: 0, x2: 0, y1: M.t, y2: H - M.b,
    stroke: 'var(--brass)', 'stroke-width': 1, opacity: 0});
  svg.appendChild(hover);
  readout.textContent = idle;
  svg.onpointerleave = () => { hover.setAttribute('opacity', 0); readout.textContent = idle; };
  svg.onpointermove = ev => {
    const box = svg.getBoundingClientRect();
    const px = (ev.clientX - box.left) / box.width * W;
    let best = 0, bestD = Infinity;
    cfg.hoverXs.forEach((h, i) => {
      const d = Math.abs(xOf(h.v) - px);
      if (d < bestD) { bestD = d; best = i; }
    });
    const at = cfg.hoverXs[best];
    hover.setAttribute('x1', xOf(at.v));
    hover.setAttribute('x2', xOf(at.v));
    hover.setAttribute('opacity', .65);
    const parts = cfg.series.map(s => {
      const hit = s.pts.find(p => p[0] === at.v);
      return hit ? [s, hit[1]] : null;
    }).filter(Boolean).sort((a, b) => b[1] - a[1])
      .map(([s, v]) => `<span><span class="rk">${s.name}</span> <b style="color:${s.colour}">${cfg.fmt(v)}</b></span>`);
    readout.innerHTML = `<span class="rk">${at.label}</span>` + parts.join('');
  };
}

/* =============== generic sortable table =============== */
function renderTable(table, cols, rows, state, onRow) {
  const head = table.querySelector('thead tr');
  head.textContent = '';
  cols.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col.label; th.tabIndex = 0;
    if (col.title) th.title = col.title;
    if (col.key === state.key) th.setAttribute('aria-sort', state.dir < 0 ? 'descending' : 'ascending');
    const go = () => {
      if (state.key === col.key) state.dir *= -1; else { state.key = col.key; state.dir = -1; }
      renderTable(table, cols, rows, state, onRow);
    };
    th.onclick = go;
    th.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
    head.appendChild(th);
  });
  const body = table.querySelector('tbody');
  body.textContent = '';
  [...rows].sort((a, b) => {
    const x = a[state.key], y = b[state.key];
    if (x === undefined) return 1;
    if (y === undefined) return -1;
    return state.dir * (typeof x === 'string' ? x.localeCompare(y) : x - y);
  }).forEach(row => {
    const tr = document.createElement('tr');
    cols.forEach(col => {
      const td = document.createElement('td');
      const v = row[col.key];
      td.textContent = col.fmt ? col.fmt(v, row) : (v === undefined ? '—' : v);
      if (col.colour) td.style.color = col.colour(row);
      if (col.cls) td.className = col.cls(row);
      tr.appendChild(td);
    });
    if (onRow) { tr.style.cursor = 'pointer'; tr.onclick = () => onRow(row); }
    body.appendChild(tr);
  });
}

/* =============== shared bits =============== */
const years = DATA.years;
const xMin = Math.min(...years), xMax = Math.max(...years);
const xOfSave = y => M.l + (xMax === xMin ? 0 : (y - xMin) / (xMax - xMin)) * (W - M.l - M.r);
const saveTicks = DATA.dates.map((d, i) => ({v: years[i], label: d.split('.')[0]}));
const saveHovers = DATA.dates.map((d, i) => ({v: years[i], label: d}));

const defaultTags = (DATA.playerTags.length ? DATA.playerTags : DATA.tags).slice(0, 8);
// For single-nation dropdowns, opening on the largest example is more useful
// than opening on whatever sorts first.
function largestBy(key) {
  const at = DATA.facts[DATA.dates[DATA.dates.length - 1]] || {};
  return [...DATA.tags].sort((a, b) =>
    ((at[b] || {})[key] || 0) - ((at[a] || {})[key] || 0))[0] || DATA.tags[0];
}

function tagPickerCfg(selected, onChange) {
  return {
    items: DATA.tags,
    labelFor: t => t,
    subLabelFor: t => nameOf(t) === t ? '' : nameOf(t),
    colourFor,
    selected,
    noun: 'nations',
    presets: [
      ['Players', () => DATA.playerTags.length ? DATA.playerTags : DATA.tags.slice(0, 8)],
      ['Top 8 by pop', () => [...DATA.tags].sort((a, b) =>
        (DATA.series[b].total_pop[DATA.lastDate] || 0) - (DATA.series[a].total_pop[DATA.lastDate] || 0)
      ).slice(0, 8)],
      ['All', () => DATA.tags],
      ['None', () => []],
    ],
    onChange,
  };
}
DATA.lastDate = DATA.dates[DATA.dates.length - 1];

/* =============== NATIONS =============== */
let natTags = defaultTags.slice();
let logScale = false;

const metricSel = document.getElementById('metric');
DATA.metrics.forEach(m => {
  const o = document.createElement('option');
  o.value = m.key; o.textContent = m.label; metricSel.appendChild(o);
});
const fmtFor = key => {
  const m = DATA.metrics.find(m => m.key === key);
  return formatters[m ? m.fmt : 'count'] || fmtCount;
};
metricSel.onchange = drawChart;

makePicker(document.getElementById('pick-nations'),
  tagPickerCfg(natTags, sel => { natTags = sel; drawChart(); drawLedger(); }));

const scaleBtn = document.getElementById('scale');
scaleBtn.onclick = () => {
  logScale = !logScale;
  scaleBtn.setAttribute('aria-pressed', logScale);
  scaleBtn.textContent = logScale ? 'Logarithmic' : 'Linear';
  drawChart();
};

function drawChart() {
  const key = metricSel.value;
  const shown = DATA.tags.filter(t => natTags.includes(t));
  plot(document.getElementById('chart'), {
    series: shown.map(tag => ({
      name: tag, colour: colourFor(tag),
      pts: DATA.dates.map((d, i) => [years[i], DATA.series[tag][key][d]])
                     .filter(p => p[1] !== undefined),
    })),
    xOf: xOfSave, xTicks: saveTicks, hoverXs: saveHovers,
    fmt: fmtFor(key), log: logScale, markers: true,
    readout: document.getElementById('readout'),
    idle: 'Hover the plot to read values at a date.',
    emptyMsg: shown.length ? 'No data for this measure.' : 'Select a nation.',
  });
}

const LEDGER_COLS = [
  {key: 'tag', label: 'Tag', colour: r => colourFor(r.tag)},
  {key: 'name', label: 'Nation'},
  {key: 'primary_culture', label: 'Primary culture', fmt: v => v || '—'},
  {key: 'provinces', label: 'Prov', fmt: v => v.toLocaleString()},
  {key: 'total_pop', label: 'Population', fmt: v => v.toLocaleString()},
  {key: 'accepted_pct', label: 'Accepted', fmt: v => v.toFixed(1) + '%'},
  {key: 'avg_literacy', label: 'Literacy', fmt: v => (v * 100).toFixed(1) + '%'},
  {key: 'brigades', label: 'Brigades', fmt: v => v.toLocaleString()},
  {key: 'ships', label: 'Ships', fmt: v => v.toLocaleString()},
  {key: 'factory_levels', label: 'Fct lvl', fmt: v => v.toLocaleString()},
  {key: 'prestige', label: 'Prestige', fmt: v => Math.round(v).toLocaleString()},
];
const ledgerState = {key: 'total_pop', dir: -1};
function drawLedger() {
  const at = DATA.facts[DATA.lastDate] || {};
  const rows = natTags.filter(t => at[t]).map(t => ({tag: t, name: nameOf(t), ...at[t]}));
  renderTable(document.getElementById('ledger'), LEDGER_COLS, rows, ledgerState);
}

/* =============== MILITARY =============== */
let milTags = defaultTags.slice(0, 6);
let milMode = 'army';       // army | navy
let milView = 'totals';     // totals | composition
let milWithMob = true;      // add the mobilization ceiling to army totals
const MOB_COLOUR = '#8FB4CE';
const SIDE_COLOUR = ['#F2B441', '#5FCBB4'];

const milSave = document.getElementById('milsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  milSave.appendChild(o);
});
milSave.value = DATA.lastDate;

const byBrigades = [...DATA.tags].sort((a, b) =>
  (((DATA.facts[DATA.lastDate] || {})[b] || {}).brigades || 0) -
  (((DATA.facts[DATA.lastDate] || {})[a] || {}).brigades || 0));
let sideA = [byBrigades[0]].filter(Boolean);
let sideB = [byBrigades[1]].filter(Boolean);

const pickerA = makePicker(document.getElementById('pick-milA'),
  tagPickerCfg(sideA, sel => { sideA = sel; drawMilPies(); }));
const pickerB = makePicker(document.getElementById('pick-milB'),
  tagPickerCfg(sideB, sel => { sideB = sel; drawMilPies(); }));

const milModeBtn = document.getElementById('milmode');
milModeBtn.onclick = () => {
  milMode = milMode === 'army' ? 'navy' : 'army';
  milModeBtn.setAttribute('aria-pressed', milMode === 'navy');
  milModeBtn.textContent = milMode === 'army' ? 'Army' : 'Navy';
  drawMilPies();
};
const milViewBtn = document.getElementById('milview');
milViewBtn.onclick = () => {
  milView = milView === 'totals' ? 'composition' : 'totals';
  milViewBtn.setAttribute('aria-pressed', milView === 'composition');
  milViewBtn.textContent = milView === 'totals' ? 'Totals' : 'Composition';
  drawMilPies();
};
const milMobBtn = document.getElementById('milmob');
milMobBtn.onclick = () => {
  milWithMob = !milWithMob;
  milMobBtn.setAttribute('aria-pressed', milWithMob);
  milMobBtn.textContent = milWithMob ? 'With mobilization' : 'Standing only';
  drawMilPies();
};
document.getElementById('milswap').onclick = () => {
  const a = sideA.slice();
  pickerA.set(sideB.slice());
  pickerB.set(a);
};
milSave.onchange = () => { drawMilPies(); drawMilTable(); drawTechTable(); };

makePicker(document.getElementById('pick-military'),
  tagPickerCfg(milTags, sel => { milTags = sel; drawMilTable(); drawTechTable(); }));

const milTypes = () => milMode === 'army' ? DATA.regimentTypes : DATA.shipTypes;
const milColour = t => C[milTypes().indexOf(t) % C.length];
const milSource = tag => (milMode === 'army' ? DATA.brigades : DATA.ships)[tag] || {};

/** Sum a side's unit counts by type across every nation in the group. */
function groupCounts(tags, date) {
  const out = {};
  tags.forEach(tag => {
    const at = milSource(tag)[date] || {};
    for (const key in at) out[key] = (out[key] || 0) + at[key];
  });
  return out;
}
const groupTotal = (tags, date) => {
  const at = groupCounts(tags, date);
  let n = 0;
  for (const key in at) n += at[key];
  return n;
};
/** Mobilization ceiling for a side. Naval hulls cannot be mobilized. */
function groupMob(tags, date) {
  if (milMode !== 'army' || !milWithMob) return 0;
  const at = DATA.facts[date] || {};
  return tags.reduce((sum, t) => sum + ((at[t] || {}).mobilization_brigades || 0), 0);
}
const sideLabel = tags => !tags.length ? 'nobody'
  : tags.length <= 3 ? tags.join(' + ')
  : `${tags.slice(0, 2).join(' + ')} +${tags.length - 2} more`;

function arcPath(cx, cy, r0, r1, a0, a1) {
  const at = (r, a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const large = (a1 - a0) > Math.PI ? 1 : 0;
  const [x0, y0] = at(r1, a0), [x1, y1] = at(r1, a1);
  const [x2, y2] = at(r0, a1), [x3, y3] = at(r0, a0);
  return `M${x0} ${y0}A${r1} ${r1} 0 ${large} 1 ${x1} ${y1}`
       + `L${x2} ${y2}A${r0} ${r0} 0 ${large} 0 ${x3} ${y3}Z`;
}

/**
 * Draw a donut. A single slice covering the ring needs two arcs.
 *
 * With opts.split and exactly two slices the ring is drawn as a head-to-head:
 * both slices start at the top, the first sweeping anticlockwise so it fills the
 * left half and the second clockwise so it fills the right. That puts each
 * side's colour on the side of the chart its label is on, which the plain
 * clockwise-from-top order gets backwards.
 */
function donut(svg, cx, cy, r0, r1, slices, onHover, opts) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (!total) {
    svg.appendChild(el('circle', {cx, cy, r: r1, fill: 'none',
      stroke: 'var(--grid)', 'stroke-width': 1}));
    return;
  }
  const top = -Math.PI / 2;
  const split = !!(opts && opts.split) && slices.length === 2;
  let angle = top;
  slices.forEach((slice, i) => {
    if (!slice.value) return;
    const sweep = slice.value / total * Math.PI * 2;
    const full = sweep >= Math.PI * 2 - 1e-6;
    const a0 = split ? (i === 0 ? top - sweep : top) : angle;
    const a1 = split ? (i === 0 ? top : top + sweep) : angle + sweep;
    const path = el('path', {
      d: full
        ? arcPath(cx, cy, r0, r1, a0, a0 + Math.PI)
          + arcPath(cx, cy, r0, r1, a0 + Math.PI, a0 + Math.PI * 2)
        : arcPath(cx, cy, r0, r1, a0, a1),
      fill: slice.colour, 'fill-opacity': .85,
      stroke: 'var(--ground)', 'stroke-width': 1,
    });
    const title = document.createElementNS(SVGNS, 'title');
    title.textContent = `${slice.label}: ${slice.value.toLocaleString()} `
      + `(${(slice.value / total * 100).toFixed(1)}%)`;
    path.appendChild(title);
    path.style.cursor = 'pointer';
    path.onpointerenter = () => { path.setAttribute('fill-opacity', 1); onHover(slice); };
    path.onpointerleave = () => path.setAttribute('fill-opacity', .85);
    svg.appendChild(path);
    angle += sweep;
  });
}

function centreText(svg, cx, cy, big, small) {
  const a = el('text', {x: cx, y: cy - 2, 'text-anchor': 'middle', fill: 'var(--ink)',
    'font-family': 'Barlow Condensed, sans-serif', 'font-size': 34, 'font-weight': 600});
  a.textContent = big;
  svg.appendChild(a);
  const b = el('text', {x: cx, y: cy + 20, 'text-anchor': 'middle', fill: 'var(--ink-dim)',
    'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
  b.textContent = small;
  svg.appendChild(b);
}

function drawMilPies() {
  const svg = document.getElementById('milpies');
  svg.textContent = '';
  const legend = document.getElementById('millegend');
  legend.textContent = '';
  const readout = document.getElementById('milreadout');
  const date = milSave.value;
  document.getElementById('mildate').textContent = date;
  const noun = milMode === 'army' ? 'brigades' : 'ships';

  const raised = [groupTotal(sideA, date), groupTotal(sideB, date)];
  const mobs = [groupMob(sideA, date), groupMob(sideB, date)];
  const totals = [raised[0] + mobs[0], raised[1] + mobs[1]];
  if (!sideA.length && !sideB.length) {
    const t = el('text', {x: 500, y: 200, 'text-anchor': 'middle', fill: '#8FB4CE',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = 'Pick at least one nation for a side.';
    svg.appendChild(t);
    readout.textContent = '';
    return;
  }

  const ratioText = totals[1] ? (totals[0] / totals[1]).toFixed(2) + '×' : '—';
  const mobOf = tags => tags.reduce((sum, t) =>
    sum + (((DATA.facts[date] || {})[t] || {}).mobilized_brigades || 0), 0);
  const mobBits = milMode === 'army'
    ? [sideA, sideB].map(mobilizedSide).filter(Boolean).join('') : '';
  function mobilizedSide(tags) {
    const n = mobOf(tags);
    if (!n) return '';
    return `<span><span class="rk">${sideLabel(tags)} mobilized</span> <b>${n.toLocaleString()}</b></span>`;
  }
  const split = milMode === 'army' && (mobs[0] || mobs[1])
    ? `<span><span class="rk">raised</span> <b>${raised[0].toLocaleString()}</b>`
      + ` <span class="rk">v</span> <b>${raised[1].toLocaleString()}</b></span>`
      + `<span><span class="rk">mobilization</span> <b>${mobs[0].toLocaleString()}</b>`
      + ` <span class="rk">v</span> <b>${mobs[1].toLocaleString()}</b></span>`
    : '';
  const idle = `<span class="rk">left</span> <b style="color:${SIDE_COLOUR[0]}">`
    + `${totals[0].toLocaleString()}</b>`
    + `<span><span class="rk">right</span> <b style="color:${SIDE_COLOUR[1]}">`
    + `${totals[1].toLocaleString()}</b></span>`
    + `<span><span class="rk">ratio</span> <b>${ratioText}</b></span>` + split
    + mobBits
    + `<span class="rk">${totals[0] + totals[1] ? '' : 'no ' + noun + ' at this save'}</span>`;
  const setIdle = () => readout.innerHTML = idle;

  if (milView === 'totals') {
    // One pie, one slice per side: the broad "who has more" view.
    const slices = [
      {label: sideLabel(sideA), value: totals[0], colour: SIDE_COLOUR[0], tags: sideA, side: 0},
      {label: sideLabel(sideB), value: totals[1], colour: SIDE_COLOUR[1], tags: sideB, side: 1},
    ];
    donut(svg, 500, 196, 84, 138, slices, slice => {
      const share = (totals[0] + totals[1])
        ? (slice.value / (totals[0] + totals[1]) * 100).toFixed(1) : '0.0';
      const parts = slice.tags.map(tag => {
        const n = groupTotal([tag], date);
        return `<span><span class="rk">${tag}</span> <b style="color:${colourFor(tag)}">`
             + `${n.toLocaleString()}</b></span>`;
      });
      readout.innerHTML = `<span class="rk">${slice.label}</span>`
        + `<span><b style="color:${slice.colour}">${slice.value.toLocaleString()}</b> `
        + `<span class="rk">${noun} (${share}% of both)</span></span>`
        + (slice.tags.length > 1 ? parts.join('') : '');
    }, {split: true});
    centreText(svg, 500, 196, (totals[0] + totals[1]).toLocaleString(),
               'both sides · ' + noun + (mobs[0] || mobs[1] ? ' + mobilization' : ''));

    [[sideA, 0, 232], [sideB, 1, 768]].forEach(([tags, side, x]) => {
      const head = el('text', {x, y: 34, 'text-anchor': 'middle', fill: SIDE_COLOUR[side],
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 13});
      head.textContent = sideLabel(tags);
      svg.appendChild(head);
      const val = el('text', {x, y: 82, 'text-anchor': 'middle', fill: 'var(--ink)',
        'font-family': 'Barlow Condensed, sans-serif', 'font-size': 40, 'font-weight': 600});
      val.textContent = totals[side].toLocaleString();
      svg.appendChild(val);
      const sub = el('text', {x, y: 104, 'text-anchor': 'middle', fill: 'var(--ink-dim)',
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
      sub.textContent = noun;
      svg.appendChild(sub);
    });
    const ratio = el('text', {x: 500, y: 372, 'text-anchor': 'middle', fill: 'var(--brass)',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    ratio.textContent = 'left / right  ' + ratioText;
    svg.appendChild(ratio);

    slices.forEach(slice => {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${slice.colour}"></i>${slice.label} `
        + `(${slice.value.toLocaleString()})`;
      legend.appendChild(item);
    });
  } else {
    // Two pies broken down by unit type, shared colour scale.
    const counts = [groupCounts(sideA, date), groupCounts(sideB, date)];
    const present = milTypes().filter(t => counts.some(c => c[t]));
    const setType = type => {
      const parts = [0, 1].map(i => {
        const n = type === '__mob' ? mobs[i] : (counts[i][type] || 0);
        const pct = totals[i] ? (n / totals[i] * 100).toFixed(1) : '0.0';
        return `<span><span class="rk">${i ? 'right' : 'left'}</span> `
             + `<b style="color:${SIDE_COLOUR[i]}">${n.toLocaleString()}</b> `
             + `<span class="rk">(${pct}%)</span></span>`;
      });
      const [x, y] = type === '__mob' ? mobs
                   : [counts[0][type] || 0, counts[1][type] || 0];
      const r = y ? (x / y).toFixed(2) + '×' : (x ? '—' : '');
      const label = type === '__mob' ? 'mobilization ceiling' : type.replace(/_/g, ' ');
      readout.innerHTML = `<span class="rk">${label}</span>` + parts.join('')
        + (r ? `<span><span class="rk">ratio</span> <b>${r}</b></span>` : '');
    };

    [[sideA, 0, 268], [sideB, 1, 732]].forEach(([tags, side, cx]) => {
      const head = el('text', {x: cx, y: 34, 'text-anchor': 'middle', fill: SIDE_COLOUR[side],
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 13});
      head.textContent = sideLabel(tags);
      svg.appendChild(head);
      const slices = present.map(type => ({
        label: `${sideLabel(tags)} · ${type}`, value: counts[side][type] || 0,
        colour: milColour(type), type,
      }));
      if (mobs[side]) slices.push({
        label: `${sideLabel(tags)} · mobilization`, value: mobs[side],
        colour: MOB_COLOUR, type: '__mob',
      });
      donut(svg, cx, 196, 74, 122, slices, slice => setType(slice.type));
      centreText(svg, cx, 196, totals[side].toLocaleString(), noun);
    });

    const ratio = el('text', {x: 500, y: 190, 'text-anchor': 'middle', fill: 'var(--brass)',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 15});
    ratio.textContent = ratioText;
    svg.appendChild(ratio);
    const ratioLabel = el('text', {x: 500, y: 208, 'text-anchor': 'middle',
      fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
    ratioLabel.textContent = 'left / right';
    svg.appendChild(ratioLabel);

    present.forEach(type => {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${milColour(type)}"></i>${type.replace(/_/g, ' ')}`;
      item.style.cursor = 'pointer';
      item.onmouseenter = () => setType(type);
      legend.appendChild(item);
    });
    if (mobs[0] || mobs[1]) {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${MOB_COLOUR}"></i>mobilization ceiling`;
      item.style.cursor = 'pointer';
      item.onmouseenter = () => setType('__mob');
      legend.appendChild(item);
    }
  }

  svg.onpointerleave = setIdle;
  setIdle();
}

const milState = {key: 'brigades', dir: -1};
function drawMilTable() {
  const date = milSave.value;
  const facts = DATA.facts[date] || {};
  const usedReg = DATA.regimentTypes.filter(rt =>
    milTags.some(t => ((DATA.brigades[t] || {})[date] || {})[rt]));
  const cols = [
    {key: 'tag', label: 'Tag', colour: r => colourFor(r.tag)},
    {key: 'name', label: 'Nation'},
    {key: 'brigades', label: 'Brigades', fmt: v => v.toLocaleString()},
    {key: 'regular_brigades', label: 'Professionals', fmt: v => v.toLocaleString(),
     title: 'Brigades raised from soldier pops, which stand whether or not the '
          + 'nation is mobilized'},
    {key: 'mobilized_brigades', label: 'Mobilized', fmt: v => v.toLocaleString(),
     title: 'Brigades raised from non-soldier pops, which only exist while mobilized',
     cls: r => r.mobilized_brigades ? 'up' : ''},
    {key: 'mobilizing', label: 'Queued', fmt: v => v.toLocaleString(),
     title: 'Mobilization orders that have not spawned a brigade yet'},
    {key: 'mobilization_brigades', label: 'Mob ceiling', fmt: v => v.toLocaleString(),
     title: 'Brigades the mobilizable population could raise at the mobilisation '
          + 'size the report was built with. A ceiling, not the in-game number.'},
    {key: 'total_military_potential', label: 'Total military potential',
     fmt: v => v.toLocaleString(),
     title: 'Professionals plus the mobilization ceiling: the largest army this '
          + 'nation could field. Mobilized brigades are already inside the '
          + 'ceiling, so they are not added again.'},
    {key: 'mobilisation_size', label: 'Mob size', fmt: v => (v * 100).toFixed(2) + '%',
     title: "Share of the poor strata this nation can mobilize"},
    {key: 'mobilization_pool', label: 'Mobilizable pop', fmt: v => v.toLocaleString(),
     title: 'Accepted-culture farmers, labourers and craftsmen'},
    {key: 'ships', label: 'Ships', fmt: v => v.toLocaleString()},
    {key: 'army_techs', label: 'Army tech', fmt: v => v.toLocaleString()},
    {key: 'navy_techs', label: 'Navy tech', fmt: v => v.toLocaleString()},
    {key: 'soldiers', label: 'Soldier pops', fmt: v => v.toLocaleString()},
    {key: 'soldier_pct', label: 'Soldier %', fmt: v => v.toFixed(2) + '%',
     title: "Soldier pops as a share of the nation's population"},
    ...usedReg.map(rt => ({key: rt, label: rt.replace(/_/g, ' '),
                           fmt: v => (v || 0).toLocaleString()})),
  ];
  const rows = milTags.map(tag => {
    const f = facts[tag] || {};
    const at = (DATA.brigades[tag] || {})[date] || {};
    const soldiers = ((DATA.pops[tag] || {})[date] || {}).soldiers || 0;
    const row = {
      tag, name: nameOf(tag),
      brigades: f.brigades || 0,
      regular_brigades: f.regular_brigades || 0,
      mobilized_brigades: f.mobilized_brigades || 0,
      mobilizing: f.mobilizing || 0,
      mobilization_brigades: f.mobilization_brigades || 0,
      total_military_potential: (f.regular_brigades || 0) + (f.mobilization_brigades || 0),
      mobilisation_size: f.mobilisation_size || 0,
      mobilization_pool: f.mobilization_pool || 0,
      ships: f.ships || 0,
      army_techs: f.army_techs || 0,
      navy_techs: f.navy_techs || 0,
      soldiers,
      soldier_pct: f.total_pop ? soldiers / f.total_pop * 100 : 0,
    };
    usedReg.forEach(rt => row[rt] = at[rt] || 0);
    return row;
  }).filter(r => r.brigades || r.ships);
  renderTable(document.getElementById('miltable'), cols, rows, milState);
}

function drawTechTable() {
  const table = document.getElementById('techtable');
  const date = milSave.value;
  const facts = DATA.facts[date] || {};
  const milScore = t => ((facts[t] || {}).army_techs || 0) + ((facts[t] || {}).navy_techs || 0);
  // Order by military tech so the nations worth reading sit nearest the label
  // column; the rest are still there, just further right.
  const tags = milTags.slice().sort((a, b) => milScore(b) - milScore(a)).slice(0, 24);

  const head = table.querySelector('thead tr');
  head.textContent = '';
  ['Technology'].concat(tags).forEach((label, i) => {
    const th = document.createElement('th');
    th.textContent = label;
    if (i) th.style.color = colourFor(label);
    th.style.cursor = 'default';
    head.appendChild(th);
  });

  const has = {};
  tags.forEach(t => has[t] = new Set(((DATA.techsBy[t] || {})[date]) || []));

  const body = table.querySelector('tbody');
  body.textContent = '';
  const totals = document.createElement('tr');
  const totalsLabel = document.createElement('td');
  totalsLabel.textContent = 'Army + navy techs';
  totals.appendChild(totalsLabel);
  tags.forEach(t => {
    const td = document.createElement('td');
    const f = facts[t] || {};
    td.textContent = `${f.army_techs || 0} + ${f.navy_techs || 0}`;
    td.style.color = 'var(--brass)';
    totals.appendChild(td);
  });
  body.appendChild(totals);

  let lastLine = null;
  DATA.techOrder.forEach((tech, idx) => {
    const [branch, line] = DATA.techMeta[idx];
    if (branch === 'other') return;
    // Skip techs no nation in the save has -- mods leave gaps in the lines.
    if (!DATA.tags.some(t => (((DATA.techsBy[t] || {})[date]) || []).includes(idx))) return;
    if (line !== lastLine) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 1 + tags.length;
      td.className = 'groupcell';
      const label = document.createElement('span');
      label.textContent = (branch === 'army' ? 'Army · ' : 'Navy · ') + line;
      td.appendChild(label);
      tr.appendChild(td);
      body.appendChild(tr);
      lastLine = line;
    }
    const tr = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = tech.replace(/_/g, ' ');
    tr.appendChild(name);
    tags.forEach(t => {
      const td = document.createElement('td');
      const got = has[t].has(idx);
      td.textContent = got ? 'yes' : '—';
      td.className = got ? 'up' : 'down';
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });

  const note = document.getElementById('technote');
  const extra = milTags.length > tags.length
    ? ` Showing the ${tags.length} with most military tech of ${milTags.length} selected.` : '';
  note.textContent = 'Rows follow research order within each line, so progress reads top to '
    + 'bottom. Columns are ordered by military tech, so scroll sideways for the nations with '
    + 'least.' + extra;
}

/* =============== FLEETS =============== */
let fleetTags = defaultTags.slice();
let fleetLog = false;

const shipSel = document.getElementById('shiptype');
[['__all', 'All ships'], ...DATA.shipTypes.map(s => [s, s])].forEach(([v, label]) => {
  const o = document.createElement('option'); o.value = v; o.textContent = label;
  shipSel.appendChild(o);
});
shipSel.onchange = drawFleetChart;

makePicker(document.getElementById('pick-fleet'),
  tagPickerCfg(fleetTags, sel => { fleetTags = sel; drawFleetChart(); }));

const fscale = document.getElementById('fscale');
fscale.onclick = () => {
  fleetLog = !fleetLog;
  fscale.setAttribute('aria-pressed', fleetLog);
  fscale.textContent = fleetLog ? 'Logarithmic' : 'Linear';
  drawFleetChart();
};

const shipCount = (tag, date, type) => {
  const at = (DATA.ships[tag] || {})[date];
  if (!at) return undefined;
  if (type === '__all') return Object.values(at).reduce((a, b) => a + b, 0);
  return at[type];
};

function drawFleetChart() {
  const type = shipSel.value;
  const shown = DATA.tags.filter(t => fleetTags.includes(t));
  plot(document.getElementById('fleetchart'), {
    series: shown.map(tag => ({
      name: tag, colour: colourFor(tag),
      pts: DATA.dates.map((d, i) => [years[i], shipCount(tag, d, type)])
                     .filter(p => p[1] !== undefined),
    })),
    xOf: xOfSave, xTicks: saveTicks, hoverXs: saveHovers,
    fmt: fmtCount, log: fleetLog, markers: true,
    readout: document.getElementById('fleetreadout'),
    idle: 'Hover the plot to read fleet sizes at a date.',
    emptyMsg: shown.length ? 'No ships of this type in these saves.' : 'Select a nation.',
  });
}

const fleetSave = document.getElementById('fleetsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  fleetSave.appendChild(o);
});
fleetSave.value = DATA.lastDate;
fleetSave.onchange = drawFleetTable;

const fleetState = {key: 'total', dir: -1};
function drawFleetTable() {
  const date = fleetSave.value;
  document.getElementById('fleetdate').textContent = date;
  const used = DATA.shipTypes.filter(st => DATA.tags.some(t => shipCount(t, date, st)));
  const cols = [
    {key: 'tag', label: 'Tag', colour: r => colourFor(r.tag)},
    {key: 'name', label: 'Nation'},
    {key: 'total', label: 'Total', fmt: v => v.toLocaleString()},
    ...used.map(st => ({key: st, label: st.replace(/_/g, ' '),
                        fmt: v => (v || 0).toLocaleString()})),
  ];
  const rows = DATA.tags.map(tag => {
    const row = {tag, name: nameOf(tag), total: shipCount(tag, date, '__all') || 0};
    used.forEach(st => row[st] = shipCount(tag, date, st) || 0);
    return row;
  }).filter(r => r.total > 0);
  renderTable(document.getElementById('fleettable'), cols, rows, fleetState,
              row => { shipSel.value = '__all'; drawFleetChart(); navSel.value = row.tag; drawNavy(); });
}

const navSel = document.getElementById('navtag');
DATA.tags.forEach(t => {
  const o = document.createElement('option'); o.value = t;
  o.textContent = nameOf(t) === t ? t : `${t} · ${nameOf(t)}`;
  navSel.appendChild(o);
});
navSel.value = largestBy('ships');
navSel.onchange = () => drawNavy();

function stackedBars(svgId, legendId, byDate, keys, emptyMsg) {
  const svg = document.getElementById(svgId);
  svg.textContent = '';
  const legend = document.getElementById(legendId);
  legend.textContent = '';
  const NW = 1000, NH = 360, NM = {t: 16, r: 20, b: 38, l: 70};
  const used = keys.filter(k => DATA.dates.some(d => (byDate[d] || {})[k]));
  const totals = DATA.dates.map(d =>
    used.reduce((s, k) => s + ((byDate[d] || {})[k] || 0), 0));
  const peak = Math.max(1, ...totals);

  if (!used.length) {
    const t = el('text', {x: NW/2, y: NH/2, 'text-anchor': 'middle', fill: '#8FB4CE',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = emptyMsg;
    svg.appendChild(t);
    return;
  }

  const axis = el('g', {class: 'axis'});
  niceTicks(0, peak, 5).forEach(tick => {
    const y = NM.t + (1 - tick / peak) * (NH - NM.t - NM.b);
    axis.appendChild(el('line', {x1: NM.l, x2: NW - NM.r, y1: y, y2: y, class: 'gridline'}));
    const label = el('text', {x: NM.l - 9, y: y + 3.5, 'text-anchor': 'end'});
    label.textContent = fmtCount(tick);
    axis.appendChild(label);
  });
  axis.appendChild(el('line', {x1: NM.l, x2: NW - NM.r, y1: NH - NM.b, y2: NH - NM.b, class: 'axisline'}));
  svg.appendChild(axis);

  const slot = (NW - NM.l - NM.r) / DATA.dates.length;
  const barW = Math.min(56, slot * 0.62);
  DATA.dates.forEach((d, i) => {
    const x = NM.l + slot * (i + 0.5) - barW / 2;
    let y = NH - NM.b;
    used.forEach((k, si) => {
      const count = (byDate[d] || {})[k] || 0;
      if (!count) return;
      const h = count / peak * (NH - NM.t - NM.b);
      y -= h;
      const rect = el('rect', {x, y, width: barW, height: h,
        fill: C[si % C.length], 'fill-opacity': .82,
        stroke: 'var(--ground)', 'stroke-width': .5});
      const title = document.createElementNS(SVGNS, 'title');
      title.textContent = `${d} · ${k}: ${count.toLocaleString()}`;
      rect.appendChild(title);
      svg.appendChild(rect);
    });
    const mk = (txt, yy, size, fill) => {
      const t = el('text', {x: x + barW/2, y: yy, 'text-anchor': 'middle'});
      t.setAttribute('font-family', 'IBM Plex Mono, monospace');
      t.setAttribute('font-size', size); t.setAttribute('fill', fill);
      t.textContent = txt; svg.appendChild(t);
    };
    mk(d.split('.')[0], NH - NM.b + 17, 10, '#8FB4CE');
    if (totals[i]) mk(fmtCount(totals[i]), y - 6, 10.5, '#E4EFF7');
  });

  used.forEach((k, si) => {
    const item = document.createElement('span');
    item.className = 'slegend';
    item.innerHTML = `<i style="background:${C[si % C.length]}"></i>${k.replace(/_/g, ' ')}`;
    legend.appendChild(item);
  });
}

const drawNavy = () => stackedBars('navy', 'navlegend',
  DATA.ships[navSel.value] || {}, DATA.shipTypes,
  nameOf(navSel.value) + ' has no ships in these saves.');

/* =============== POPS =============== */
const popSave = document.getElementById('popsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  popSave.appendChild(o);
});
popSave.value = DATA.lastDate;
popSave.onchange = () => { drawPopTable(); drawCultureTable(); };

let popShare = false;
const popShareBtn = document.getElementById('popshare');
popShareBtn.onclick = () => {
  popShare = !popShare;
  popShareBtn.setAttribute('aria-pressed', popShare);
  popShareBtn.textContent = popShare ? 'Shares' : 'Counts';
  drawPopTable();
};

const popState = {key: 'total', dir: -1};
function drawPopTable() {
  const date = popSave.value;
  document.getElementById('popdate').textContent = date;
  const facts = DATA.facts[date] || {};
  const used = DATA.popTypes.filter(pt =>
    DATA.tags.some(t => ((DATA.pops[t] || {})[date] || {})[pt]));
  const cell = (v, row) => {
    if (!v) return popShare ? '—' : '0';
    return popShare ? (v / row.total * 100).toFixed(1) + '%' : v.toLocaleString();
  };
  const cols = [
    {key: 'tag', label: 'Tag', colour: r => colourFor(r.tag)},
    {key: 'name', label: 'Nation'},
    {key: 'total', label: 'Total pop', fmt: v => v.toLocaleString()},
    {key: 'accepted_pct', label: 'Accepted', fmt: v => v.toFixed(1) + '%'},
    {key: 'avg_literacy', label: 'Literacy', fmt: v => (v * 100).toFixed(1) + '%'},
    {key: 'avg_militancy', label: 'Mil', fmt: v => v.toFixed(2)},
    {key: 'avg_consciousness', label: 'Con', fmt: v => v.toFixed(2)},
    ...used.map(pt => ({key: pt, label: pt, fmt: cell})),
  ];
  const rows = DATA.tags.map(tag => {
    const at = (DATA.pops[tag] || {})[date] || {};
    const f = facts[tag] || {};
    const row = {
      tag, name: nameOf(tag),
      total: f.total_pop || 0,
      accepted_pct: f.accepted_pct || 0,
      avg_literacy: f.avg_literacy || 0,
      avg_militancy: f.avg_militancy || 0,
      avg_consciousness: f.avg_consciousness || 0,
    };
    used.forEach(pt => row[pt] = at[pt] || 0);
    return row;
  }).filter(r => r.total > 0);
  renderTable(document.getElementById('poptable'), cols, rows, popState,
              row => { culSel.value = row.tag; drawCultureTable(); popTag.value = row.tag; drawPopChart(); });
}

const culSel = document.getElementById('cultagsel');
DATA.tags.forEach(t => {
  const o = document.createElement('option'); o.value = t;
  o.textContent = nameOf(t) === t ? t : `${t} · ${nameOf(t)}`;
  culSel.appendChild(o);
});
culSel.value = largestBy('total_pop');
culSel.onchange = drawCultureTable;

const culState = {key: 'size', dir: -1};
function drawCultureTable() {
  const tag = culSel.value, date = popSave.value;
  document.getElementById('cultag').textContent =
    (nameOf(tag) === tag ? tag : `${tag} · ${nameOf(tag)}`) + ' at ' + date;
  const list = ((DATA.cultures[tag] || {})[date]) || [];
  const total = list.reduce((s, c) => s + c[1], 0);
  const rows = list.map(([culture, size, accepted]) => ({
    culture, size, accepted,
    share: total ? size / total * 100 : 0,
  }));
  const cols = [
    {key: 'culture', label: 'Culture'},
    {key: 'size', label: 'Pops', fmt: v => v.toLocaleString()},
    {key: 'share', label: 'Share', fmt: v => v.toFixed(1) + '%'},
    {key: 'accepted', label: 'Accepted', fmt: v => v ? 'yes' : '—',
     cls: r => r.accepted ? 'up' : 'down'},
  ];
  renderTable(document.getElementById('cultable'), cols, rows, culState);
}

const popTag = document.getElementById('poptag');
DATA.tags.forEach(t => {
  const o = document.createElement('option'); o.value = t;
  o.textContent = nameOf(t) === t ? t : `${t} · ${nameOf(t)}`;
  popTag.appendChild(o);
});
popTag.value = largestBy('total_pop');
popTag.onchange = () => drawPopChart();

const drawPopChart = () => stackedBars('popchart', 'poplegend',
  DATA.pops[popTag.value] || {}, DATA.popTypes,
  nameOf(popTag.value) + ' has no pops in these saves.');

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
  items: DATA.goods,
  labelFor: g => g,
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
  const by = DATA.prices[good] || {};
  const pts = [];
  let base = null;
  for (let i = 0; i < PD.length; i++) {
    let v = by[PD[i]];
    if (v === undefined) continue;
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
  const firstYear = Math.ceil(pxMin), lastYear = Math.floor(pxMax);
  const step = Math.max(1, Math.ceil((lastYear - firstYear + 1) / 12));
  const xTicks = [];
  for (let yr = firstYear; yr <= lastYear; yr += step) xTicks.push({v: yr, label: yr});

  plot(document.getElementById('pricechart'), {
    series: shown.map(g => ({name: g, colour: goodColour(g), pts: priceSeries(g)})),
    xOf: pxOf, xTicks,
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

const snapSel = document.getElementById('snapsel');
DATA.snapshotDates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  snapSel.appendChild(o);
});
if (DATA.snapshotDates.length)
  snapSel.value = DATA.snapshotDates[DATA.snapshotDates.length - 1];
snapSel.onchange = drawMarketTable;

const MARKET_COLS = [
  {key: 'good', label: 'Good', colour: r => goodColour(r.good)},
  {key: 'category', label: 'Category'},
  {key: 'price', label: 'Price', fmt: v => v.toFixed(2)},
  {key: 'change', label: 'Change',
   fmt: v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%',
   cls: r => r.change > 0.05 ? 'up' : r.change < -0.05 ? 'down' : ''},
  {key: 'supply', label: 'Supply', fmt: fmtCount},
  {key: 'demand', label: 'Demand', fmt: fmtCount},
  {key: 'actual_sold', label: 'Sold', fmt: fmtCount},
  {key: 'floored', label: 'At floor', fmt: v => v ? 'yes' : '—'},
];
const marketState = {key: 'change', dir: -1};
function drawMarketTable() {
  const date = snapSel.value;
  document.getElementById('snapdate').textContent = date || '—';
  const snap = DATA.snapshot[date] || {};
  const rows = Object.keys(snap).map(good => {
    const by = DATA.prices[good] || {};
    const seen = PD.filter(d => by[d] !== undefined);
    const first = seen.length ? by[seen[0]] : 0;
    const last = seen.length ? by[seen[seen.length - 1]] : 0;
    return {
      good, category: DATA.goodCategory[good] || 'other',
      price: snap[good].price,
      change: first ? (last - first) / first * 100 : 0,
      supply: snap[good].supply,
      demand: snap[good].demand,
      actual_sold: snap[good].actual_sold,
      floored: snap[good].floored,
      discovered: snap[good].discovered,
    };
  }).filter(r => r.discovered);
  renderTable(document.getElementById('market'), MARKET_COLS, rows, marketState,
              row => goodsPicker.set([row.good]));
}

/* =============== TABS =============== */
const tabs = [...document.querySelectorAll('.tab')];
function selectTab(id) {
  tabs.forEach(t => {
    const on = t.id === id;
    t.setAttribute('aria-selected', on);
    document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
  });
}
tabs.forEach((t, i) => {
  t.onclick = () => selectTab(t.id);
  t.onkeydown = e => {
    const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const next = tabs[(i + d + tabs.length) % tabs.length];
    next.focus(); selectTab(next.id);
  };
});

document.getElementById('lastdate').textContent = DATA.lastDate;
goodsPicker.set(topMovers(6));
drawChart(); drawLedger();
drawMilPies(); drawMilTable(); drawTechTable();
drawFleetChart(); drawFleetTable(); drawNavy();
drawPopTable(); drawCultureTable(); drawPopChart();
drawMarketTable();
</script>
</body>
</html>
"""
