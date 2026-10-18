/* One bar per save is one bar per year while a campaign is saved by hand, and
   a thicket the moment it is saved every month: nine hundred columns four
   pixels wide with their totals printed over each other. A year is the unit
   anyone reads a population by, so these charts keep the last save in each
   year and drop the rest. The run has the same shape and the bars have room
   to be labelled. */
const YEAR_DATES = (() => {
  const last = new Map();
  DATA.dates.forEach(d => last.set(d.split('.')[0], d));
  return [...last.values()];
})();

/* Which bars can carry a label without colliding with the one before: greedy
   from the left, and the final bar always gets one, since a chart whose last
   column is unlabelled asks the reader to count. Anything the greedy pass put
   too close to that final label gives way to it. */
function labelSlots(xs, gap) {
  const keep = [];
  for (let i = 0; i < xs.length - 1; i++)
    if (!keep.length || xs[i] - xs[keep[keep.length - 1]] >= gap) keep.push(i);
  if (xs.length) {
    while (keep.length && xs[xs.length - 1] - xs[keep[keep.length - 1]] < gap) keep.pop();
    keep.push(xs.length - 1);
  }
  return new Set(keep);
}

function stackedBars(svgId, legendId, byDate, keys, emptyMsg, populationTag = null, scopeTotals = null, filter = null) {
  const svg = document.getElementById(svgId);
  svg.textContent = '';
  const legend = document.getElementById(legendId);
  legend.textContent = '';
  const NW = 1000, NH = 360, NM = {t: 16, r: 20, b: 38, l: 70};
  const dates = YEAR_DATES;
  const available = keys.filter(k => dates.some(d => (byDate[d] || {})[k]));
  const used = filter?.key ? available.filter(k => k === filter.key) : available;
  const fullTotals = dates.map(d => available.reduce((sum, k) => sum + (byDate[d]?.[k] || 0), 0));
  const totals = dates.map(d =>
    used.reduce((s, k) => s + ((byDate[d] || {})[k] || 0), 0));
  const peak = Math.max(1, ...totals);

  if (!used.length) {
    svgMessage(svg, NW/2, NH/2, emptyMsg);
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

  const slot = (NW - NM.l - NM.r) / dates.length;
  const barW = Math.min(56, slot * 0.62);
  const mids = dates.map((d, i) => NM.l + slot * (i + 0.5));
  const yearSlots = labelSlots(mids, 30);
  const totalSlots = labelSlots(mids, 42);
  dates.forEach((d, i) => {
    const x = mids[i] - barW / 2;
    let y = NH - NM.b;
    used.forEach((k, si) => {
      const count = (byDate[d] || {})[k] || 0;
      if (!count) return;
      const h = count / peak * (NH - NM.t - NM.b);
      y -= h;
      const rect = el('rect', {x, y, width: barW, height: h,
        fill: seriesColour(populationTag ? DATA.popTypes.indexOf(k) : si), 'fill-opacity': .82,
        stroke: 'var(--ground)', 'stroke-width': .5});
      const title = document.createElementNS(SVGNS, 'title');
      title.textContent = `${d} · ${gameName(k)}: ${count.toLocaleString()}`;
      if (populationTag) {
        const total = scopeTotals ? scopeTotals[d] : DATA.facts[d]?.[populationTag]?.total_pop ?? fullTotals[i];
        title.textContent += total > 0 ? ` · ${(100 * count / total).toFixed(1)}% of ${scopeTotals ? "state" : "country"} population` : '';
      }
      rect.appendChild(title);
      if (filter) {
        rect.dataset.popType = k; rect.dataset.date = d;
        rect.setAttribute('tabindex', '0'); rect.setAttribute('role', 'button');
        rect.setAttribute('aria-pressed', filter.key === k);
        rect.setAttribute('aria-label', title.textContent + (filter.key === k ? '. Show all pop types.' : '. Show only this pop type.'));
        const select = () => filter.onSelect(filter.key === k ? null : k, k, d);
        rect.onclick = select;
        rect.onkeydown = event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); }
        };
      }
      svg.appendChild(rect);
    });
    const mk = (txt, yy, size, fill) => {
      const t = el('text', {x: mids[i], y: yy, 'text-anchor': 'middle'});
      t.setAttribute('font-family', 'IBM Plex Mono, monospace');
      t.setAttribute('font-size', size); t.setAttribute('fill', fill);
      t.textContent = txt; svg.appendChild(t);
    };
    if (yearSlots.has(i)) mk(d.split('.')[0], NH - NM.b + 17, 10, '#C9AC80');
    if (totals[i] && totalSlots.has(i)) mk(fmtCount(totals[i]), y - 6, 10.5, '#F4E7CC');
  });

  available.forEach((k, si) => {
    const item = document.createElement('span');
    item.className = 'slegend';
    item.innerHTML = `<i style="background:${seriesColour(populationTag ? DATA.popTypes.indexOf(k) : si)}"></i>${gameName(k)}`;
    legend.appendChild(item);
  });
}

let focusedPopType = null;
function populationHistory(byDate, keys, emptyMsg, tag, totals = null) {
  if (focusedPopType && !YEAR_DATES.some(d => byDate[d]?.[focusedPopType])) focusedPopType = null;
  const svg = document.getElementById('popchart');
  svg.setAttribute('aria-label', focusedPopType ? gameName(focusedPopType) + ' population over time' : 'Pop sizes by type over time');
  stackedBars('popchart', 'poplegend', byDate, keys, emptyMsg, tag, totals, {
    key: focusedPopType,
    onSelect: (key, clicked, date) => {
      focusedPopType = key;
      populationHistory(byDate, keys, emptyMsg, tag, totals);
      const bars = [...svg.querySelectorAll('rect[data-pop-type]')];
      bars.find(bar => bar.dataset.popType === clicked && bar.dataset.date === date)?.focus({preventScroll:true});
    },
  });
}

