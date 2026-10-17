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

  // A picker tied to a save only offers what that save has. `available`
  // returns the current list; everything else is built once and hidden, so
  // switching saves costs nothing and a nation that comes back is still there.
  let allowed = null;
  const permitted = item => allowed === null || allowed.has(item);

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
      selected.clear(); fn().filter(permitted).forEach(i => selected.add(i));
      sync(); cfg.onChange(ordered());
    };
    presets.appendChild(b);
  });

  // Always report in the item list's own order so table columns stay put.
  const ordered = () => cfg.items.filter(i => selected.has(i) && permitted(i));

  // One place decides whether an option shows: the search box and the save
  // filter both feed it, so neither can undo the other.
  function applyFilter() {
    const q = search.value.trim().toLowerCase();
    let visible = 0;
    cfg.items.forEach(i => {
      const hay = (cfg.labelFor(i) + ' ' + (cfg.subLabelFor ? cfg.subLabelFor(i) : '')).toLowerCase();
      const on = permitted(i) && (!q || hay.includes(q));
      optFor[i].style.display = on ? '' : 'none';
      if (on) visible++;
    });
    empty.hidden = visible > 0;
  }

  function sync() {
    cfg.items.forEach(i => optFor[i].setAttribute('aria-pressed', selected.has(i)));
    applyFilter();
    const n = ordered().length;
    const word = n === 1 ? cfg.noun.replace(/s$/, '') : cfg.noun;
    toggle.innerHTML = `<span>${n} ${word} selected</span><span class="caret">▾</span>`;
  }
  search.oninput = applyFilter;
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

  if (cfg.available) allowed = new Set(cfg.available());
  sync();
  return {
    get: ordered,
    set: list => { selected.clear(); list.forEach(i => selected.add(i)); sync(); cfg.onChange(ordered()); },
    // Called when the save changes. Anything selected that the new save does
    // not have drops out of the report without being forgotten, so stepping
    // back to an earlier save brings it straight back.
    refresh: () => {
      if (!cfg.available) return;
      allowed = new Set(cfg.available());
      if (!ordered().length) {
        (cfg.fallback ? cfg.fallback() : []).forEach(i => selected.add(i));
      }
      sync();
      cfg.onChange(ordered());
    },
  };
}

/* =============== generic line plot =============== */
function plot(svg, cfg) {
  svg.textContent = '';
  const readout = cfg.readout;
  const idle = cfg.idle || 'Hover the plot to read values.';
  if (!cfg.series.length || !cfg.series.some(s => s.pts.length)) {
    svgMessage(svg, W/2, H/2, cfg.emptyMsg || 'Nothing to plot.');
    if (readout) readout.textContent = '';
    return;
  }

  const log = cfg.log;
  let vals = [];
  cfg.series.forEach(s => s.pts.forEach(([, v]) => { if (!log || v > 0) vals.push(v); }));
  if (!vals.length) {
    svgMessage(svg, W/2, H/2, 'No positive values to show on a log scale.');
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
  // Every tick the caller gave, gridline and label together. The callers hand
  // over round years spaced far enough apart to read, so there is nothing left
  // here to thin out.
  cfg.xTicks.forEach(({v, label: txt}) => {
    const x = xOf(v);
    axis.appendChild(el('line', {x1: x, x2: x, y1: M.t, y2: H - M.b, class: 'gridline'}));
    const label = el('text', {x, y: H - M.b + 17, 'text-anchor': 'middle'});
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

  // Sits before the series so a join is drawn under the lines it connects.
  const joins = el('g', {});
  svg.appendChild(joins);

  const endLabels = [];
  const span = {};
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
    // A marker on every reading is a row of boxes with a line threaded
    // through it once the saves come monthly, and it says nothing the line has
    // not already said. Only the two ends carry one, which is the one thing
    // the line cannot show on its own: where this nation's run of data starts
    // and where it stops.
    // A series with a single reading has no line, so its one marker is the
    // whole of it; drawing the same box twice would only thicken its edge.
    if (cfg.markers)
      (xy.length > 1 ? [xy[0], xy[xy.length - 1]] : [xy[0]]).forEach(p => svg.appendChild(el('rect', {
        x: p[0] - 2.5, y: p[1] - 2.5, width: 5, height: 5,
        fill: 'var(--ground)', stroke: s.colour, 'stroke-width': 1.5})));
    const last = xy[xy.length - 1];
    span[s.name] = {first: xy[0], last, colour: s.colour};
    endLabels.push({name: s.name, colour: s.colour, x: last[0], y: last[1]});
  });

  // One nation became another: join where the old line stops to where the new
  // one starts. Only drawn when both are on the chart, since a join to nothing
  // would be a line to nowhere.
  (cfg.links || []).forEach(([from, to]) => {
    const a = span[from], b = span[to];
    if (!a || !b) return;
    joins.appendChild(el('line', {
      x1: a.last[0], y1: a.last[1], x2: b.first[0], y2: b.first[1],
      stroke: b.colour, 'stroke-width': 1.3, 'stroke-dasharray': '3 4',
      opacity: 0.8}));
  });
  /* The tags on the ends of the lines. Eight nations whose values run close
     together finish the chart within a few pixels of one another, and eight
     tags crammed into those few pixels are worth less than the room they cost.
     The gap is the type size plus real leading rather than the bare clearance
     it used to be, the stack is packed by least displacement so a tag only
     moves as far as it must, and a leader joins each tag back to the point it
     names, so buying the separation never costs the reader the one thing the
     tag was for. A flat leader says the tag sits at its line's own height; a
     sloped one says it had to be nudged to make room. */
  const fs = cfg.thin ? 10.5 : 11;
  const charW = fs * 0.6;              // IBM Plex Mono runs 0.6em to the glyph
  const gutter = W - M.r;
  endLabels.forEach(l => {
    l.want = l.y;
    l.atEnd = l.x > gutter - 24;
    // The box the tag would take if nothing were in its way, padded, which is
    // both what decides who it collides with and how far a second column steps.
    l.wide = l.name.length * charW + 10;
    l.bx0 = l.atEnd ? W - 4 - l.wide : l.x + 6;
    l.bx1 = l.bx0 + l.wide;
  });
  placeLabels(endLabels, fs + 3.5, M.t + 4, H - M.b - 2);
  endLabels.forEach(l => {
    const tx = l.end ? l.anchor - l.col * l.step : l.anchor + l.col * l.step;
    const width = l.name.length * charW;
    // A tag still sitting on its line's last point says so by being there and
    // needs no leader. One that had to move, in either direction, gets a line
    // back to the point it belongs to.
    const near = l.end ? tx - width : tx;
    if (Math.abs(l.y - l.want) > 1.2 || near - l.x > 9) {
      const from = l.x + 3, to = near - 4;
      const stub = (to - from) * 0.3;
      svg.appendChild(el('path', {class: 'leader', stroke: l.colour,
        d: `M${from.toFixed(1)} ${l.want.toFixed(1)}`
         + `L${(from + stub).toFixed(1)} ${l.want.toFixed(1)}`
         + `L${(to - stub).toFixed(1)} ${l.y.toFixed(1)}`
         + `L${to.toFixed(1)} ${l.y.toFixed(1)}`}));
    }
    const label = el('text', {x: tx, y: l.y + fs * 0.34, fill: l.colour,
      class: 'endlab', 'font-size': fs,
      'text-anchor': l.end ? 'end' : 'start'});
    label.textContent = l.name;
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
      if (hit) return [s, hit[1], false];
      // Series that share their dates -- every chart but the cross-campaign
      // one -- want an exact hit and nothing else, so this stays off by
      // default. Two campaigns saved on different days never share an x, and
      // an exact match would show whichever one happens to own the line and
      // hide the other, which is the opposite of a comparison. With `carry`
      // the last reading at or before the line stands in.
      if (!cfg.carry) return null;
      let prev = null;
      for (const p of s.pts) { if (p[0] > at.v) break; prev = p; }
      return prev ? [s, prev[1], true] : null;
    }).filter(Boolean).sort((a, b) => b[1] - a[1])
      .map(([s, v, carried]) => `<span><span class="rk">${s.name}</span> `
        + `<b style="color:${s.colour}"${carried
            ? ' title="its last reading at or before this date"' : ''}>`
        + `${cfg.fmt(v)}${carried ? ' ·' : ''}</b></span>`);
    readout.innerHTML = `<span class="rk">${at.label}</span>` + parts.join('');
  };
}

/* =============== generic sortable table =============== */
// A sentence in the middle of an empty chart, in the page's dim ink
// (--ink-dim; an SVG fill attribute cannot read a CSS variable).
function svgMessage(svg, x, y, text) {
  const t = el('text', {x, y, 'text-anchor': 'middle', fill: '#C9AC80',
    'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
  t.textContent = text;
  svg.appendChild(t);
}

// A button that turns something on and off: `flip` changes the state and
// returns whether it is now on; the button's pressed state and, given
// `labels` [off, on], its text follow it; then `redraw`.
function toggleButton(button, flip, redraw, labels) {
  button.onclick = () => {
    const on = flip();
    button.setAttribute('aria-pressed', on);
    if (labels) button.textContent = labels[on ? 1 : 0];
    redraw();
  };
  return button;
}

// Hand the reader a file: a link to `blob`, clicked, and let go a minute later.
function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = name;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// A <select>'s options, one per value, each shown as `label` says.
function fillSelect(select, values, label = v => v) {
  values.forEach(v => {
    const o = document.createElement('option'); o.value = v; o.textContent = label(v);
    select.appendChild(o);
  });
}

/* =============== sorting, shared by every sortable table ===============
   A table's sort is {key, dir}: dir 1 ascending, -1 descending. */
// Rows in the order `state` asks for. A blank -- null or undefined -- sorts
// last whichever way the column runs; text sorts as a reader would.
function sortRows(rows, get, state) {
  return [...rows].sort((a, b) => {
    const x = get(a), y = get(b);
    if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
    return state.dir * (typeof x === 'string' ? x.localeCompare(y) : x - y);
  });
}
// A header clicked: the same column turns round; another starts at `first`.
function nextSort(state, key, first = -1) {
  if (state.key === key) state.dir *= -1; else { state.key = key; state.dir = first; }
}
// The aria-sort a column's header carries, or null when it is not the key.
function ariaSort(state, key) {
  return state.key === key ? (state.dir < 0 ? 'descending' : 'ascending') : null;
}

function renderTable(table, cols, rows, state, onRow) {
  const head = table.querySelector('thead tr');
  head.textContent = '';
  cols.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col.label; th.tabIndex = 0;
    if (col.title) th.title = col.title;
    if (ariaSort(state, col.key)) th.setAttribute('aria-sort', ariaSort(state, col.key));
    const go = () => { nextSort(state, col.key); renderTable(table, cols, rows, state, onRow); };
    th.onclick = go;
    th.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
    head.appendChild(th);
  });
  const body = table.querySelector('tbody');
  body.textContent = '';
  // A column whose text is a localised name still sorts on the key underneath
  // unless it says otherwise, which would put Livestock under C for cattle.
  const sortCol = cols.find(c => c.key === state.key);
  const readSort = sortCol && sortCol.sortBy ? sortCol.sortBy : r => r[state.key];
  sortRows(rows, readSort, state).forEach(row => {
    const tr = document.createElement('tr');
    cols.forEach(col => {
      const td = document.createElement('td');
      const v = row[col.key];
      if (col.render) td.appendChild(col.render(row));
      else td.textContent = col.fmt ? col.fmt(v, row) : (v === undefined ? '—' : v);
      if (col.colour) td.style.color = col.colour(row);
      if (col.cls) td.className = col.cls(row);
      tr.appendChild(td);
    });
    if (onRow) { tr.style.cursor = 'pointer'; tr.onclick = () => onRow(row); }
    body.appendChild(tr);
  });
}

