/* =============== MAP: READOUT AND CONTROLS =============== */
function mapIdle() {
  const shown = mapDots.reduce((s, d) => s + d.total, 0);
  document.getElementById('mapreadout').innerHTML =
    `<span class="rk">stacks</span> <b>${mapDots.length.toLocaleString()}</b>`
    + (mapCrowded
        ? `<span><span class="rk">drawn as pips, too close to label</span> `
          + `<b>${mapCrowded.toLocaleString()}</b> <span class="rk">\u2014 zoom in`
          + `</span></span>` : '')
    + `<span><span class="rk">brigades shown</span> <b>${shown.toLocaleString()}</b></span>`
    + `<span><span class="rk">shading</span> <b>owner</b>`
    + `<span class="rk">${mapHatchOccupied
        ? (mapOccAny ? ', occupied land hatched' : ', nothing occupied') : ''}</span></span>`
    + (mapUnplaced
        ? `<span><span class="rk">no map position</span> `
          + `<b>${mapUnplaced.toLocaleString()}</b>`
          + `<span class="rk"> provinces, ${mapUnplacedBrigades.toLocaleString()} brigades</span></span>`
        : '')
    + `<span class="rk">hover the land for its owner, a marker for its armies</span>`;
}

/* The province under the cursor, which is the painting's own lookup run
   backwards: `mapProv` holds a province id per raster pixel. */
function mapProvinceAt(p) {
  if (!mapProv) return -1;
  const s = mapFit() * mapZoom;
  const x = Math.floor(mapOX + p.x / s), y = Math.floor(mapOY + p.y / s);
  if (x < 0 || y < 0 || x >= MAP.w || y >= MAP.h) return -1;
  return mapProv[y * MAP.w + x];
}

/* Who owns a province and who is standing on it, as readout spans. Hatching
   says a province is held by somebody else, but no pattern can say *which*
   nation owns the ground under it once a stripe is across it -- so the readout
   names both outright, which is the one answer that is never ambiguous. */
function landBits(pid) {
  const date = document.getElementById('mapsave').value || DATA.lastDate;
  const book = (mapOwners || {})[date] || {own: new Map(), occ: new Map()};
  const tagOf = idx => (idx === undefined ? null : MAP.tags[idx]);
  const own = tagOf(book.own.get(pid)), occ = tagOf(book.occ.get(pid));
  const chip = (label, tag) => `<span><span class="rk">${label}</span> `
    + `<b style="color:${MAP.colours[tag] || '#fff'}">${tag}</b>`
    + (nameOf(tag) === tag ? '' : ` <span class="rk">${nameOf(tag)}</span>`)
    + `</span>`;
  if (!own) return [`<span class="rk">unclaimed</span>`];
  return occ ? [chip('owned by', own), chip('held by', occ)]
             : [chip('owned by', own)];
}

/* Land with no army on it still has an owner worth naming. */
function mapShowLand(pid) {
  if (pid < 0 || mapSea.has(pid)) return mapIdle();
  const name = (MAP.names && MAP.names[pid]) || ('province ' + pid);
  document.getElementById('mapreadout').innerHTML =
    `<span class="rk">${name}</span>` + landBits(pid).join('');
}

function mapShow(dot) {
  if (!dot) return mapIdle();
  const name = (MAP.names && MAP.names[dot.pid]) || ('province ' + dot.pid);
  const row = s => {
    const mix = s.mix.split(';').map(part => {
      const c = part.lastIndexOf(':');
      return `${part.slice(0, c)} ${part.slice(c + 1)}`;
    }).join(', ');
    // A brigade at less than full strength is the whole point of showing men,
    // so the share is quoted where it is not a round hundred per cent.
    const full = s.n * (MAP.regimentSize || 3000);
    const pct = full ? Math.round(s.men / full * 100) : 100;
    return `<b style="color:${MAP.colours[s.tag] || '#fff'}">${s.tag}</b>`
         + `<b class="num">${s.men.toLocaleString()}</b>`
         + `<span class="rk num">${s.n.toLocaleString()} `
         + `${s.n === 1 ? 'bde' : 'bdes'}</span>`
         + `<span class="rk num">${pct}%</span>`
         + `<span class="mix">${mix}</span>`;
  };
  /* Contested tiles are listed side by side rather than as one run of
     nations, with each side's total above its members -- which is the
     comparison the province is actually posing. */
  const bits = [];
  if (dot.sides && dot.sides.length > 1) {
    const label = ['attacking', 'defending', 'neither side'];
    dot.sides.forEach((g, i) => {
      const who = g.stacks.map(a => a.tag).join(' + ');
      bits.push(`<div class="sidehead"><b>${who}</b> `
        + `<span class="rk">${label[dot.fighting.a.includes(g.stacks[0].tag) ? 0
             : dot.fighting.d.includes(g.stacks[0].tag) ? 1 : 2]}</span> `
        + `<b>${g.men.toLocaleString()}</b> <span class="rk">men in `
        + `${g.n.toLocaleString()} ${g.n === 1 ? 'brigade' : 'brigades'}</span>`
        + `</div>`);
      bits.push(`<div class="natgrid">${g.stacks.map(row).join('')}</div>`);
    });
  } else {
    bits.push(`<div class="natgrid">${dot.stacks.map(row).join('')}</div>`);
  }
  const fight = dot.fighting
    ? `<span><b style="color:#ff7043">contested</b> <span class="rk">`
      + `${dot.fighting.a.join(' + ')} against ${dot.fighting.d.join(' + ')}`
      + `</span></span>`
    : '';

  document.getElementById('mapreadout').innerHTML =
    `<span class="rk">${name}</span>`
    + landBits(dot.pid).join('')
    + `<span><b>${dot.men.toLocaleString()}</b> <span class="rk">men, `
    + `${dot.total.toLocaleString()} ${dot.total === 1 ? 'brigade' : 'brigades'}`
    + `</span></span>`
    + fight
    + bits.join('');
}

function mapAt(e) {
  const canvas = document.getElementById('mapcanvas');
  const box = canvas.getBoundingClientRect();
  return {x: e.clientX - box.left, y: e.clientY - box.top};
}

function mapPick(p) {
  let best = null, bestD = 1e9;
  for (const dot of mapDots) {
    if (dot.sx === undefined) continue;
    const dx = dot.sx - p.x, dy = dot.sy - p.y;
    const d = dx * dx + dy * dy;
    const reach = Math.max(dot.sr, 5) + 2;
    if (d < reach * reach && d < bestD) { best = dot; bestD = d; }
  }
  return best;
}

if (MAP) {
  const wrap = document.querySelector('.mapwrap');
  wrap.style.aspectRatio = MAP.w + ' / ' + MAP.h;

  const mapSave = document.getElementById('mapsave');
  fillSelect(mapSave, DATA.dates);
  mapSave.value = DATA.lastDate;
  mapSave.onchange = () => {
    mapStep.value = DATA.dates.indexOf(mapSave.value);
    mapPinned = null; mapPicker.refresh(); mapRender(); drawGreatPowers();
  };

  /* A run of saves is a campaign in the order it happened, and until now the
     only way to see it move was to pick each date in turn. The slider is the
     same choice as the dropdown -- both set the save -- and Play walks it. */
  const mapStep = document.getElementById('mapstep');
  const playBtn = document.getElementById('mapplay');
  mapStep.max = Math.max(0, DATA.dates.length - 1);
  mapStep.value = DATA.dates.length - 1;
  mapStep.disabled = DATA.dates.length < 2;
  playBtn.disabled = DATA.dates.length < 2;

  const goToSave = i => {
    mapStep.value = i;
    mapSave.value = DATA.dates[i];
    mapSave.onchange();
  };
  mapStep.oninput = () => { mapStopPlay(); goToSave(+mapStep.value); };

  /* How long a frame is held. A quarter of a second is about as slow as
     anyone wants to watch a campaign that has thirty saves in it, and the
     multipliers are there for the one that has nine hundred. */
  /* How long Play holds each save, in milliseconds.

     One number cannot suit every campaign: a folder of monthly autosaves runs
     to about a thousand saves and a folder of yearly ones to about a hundred,
     and a pace that reads well at one is unwatchable at the other. The button
     this replaced started at 250ms -- four saves a second, faster than anything
     can actually be read -- and could only go up from there. */
  const HOLD = [4000, 3000, 2000, 1500, 1000, 750, 500, 350, 250, 125,
                50, 25];
  const holdText = ms => ms >= 1000
    ? (ms / 1000) + 's a save' : ms + 'ms a save';
  const speedBtn = document.getElementById('mapspeed');
  const speedOut = document.getElementById('mapspeedout');
  speedBtn.disabled = DATA.dates.length < 2;
  speedBtn.max = HOLD.length - 1;
  /* Longer campaigns open faster, so the run is watchable rather than starting
     at the same pace whether there are twenty saves or a thousand. The reader
     can move it either way from there. */
  const wantHold = DATA.dates.length > 400 ? 125
                 : DATA.dates.length > 150 ? 250
                 : DATA.dates.length > 60 ? 500
                 : DATA.dates.length > 25 ? 750 : 1000;
  speedBtn.value = HOLD.indexOf(wantHold);
  const showSpeed = () => { speedOut.textContent = holdText(HOLD[+speedBtn.value]); };
  speedBtn.oninput = showSpeed;
  showSpeed();
  const frameDelay = () => HOLD[+speedBtn.value];

  let mapTimer = null;
  mapStopPlay = () => {
    if (!mapTimer) return;
    clearTimeout(mapTimer);
    mapTimer = null;
    playBtn.setAttribute('aria-pressed', 'false');
    playBtn.textContent = 'Play';
  };
  playBtn.onclick = () => {
    if (mapTimer) return mapStopPlay();
    // Pressing Play while sitting on the last save means "again from the top",
    // which is what anyone who has just watched it to the end wants next.
    if (+mapStep.value >= DATA.dates.length - 1) goToSave(0);
    playBtn.setAttribute('aria-pressed', 'true');
    playBtn.textContent = 'Pause';
    /* Each frame schedules the next one after it has finished drawing, rather
       than every frame being booked in advance on an interval. A repaint is
       about a tenth of a second of work and the picker refresh doubles it, so
       an interval would keep firing while the last frame was still drawing
       and the queue would run away with itself; this way a slow machine plays
       back slower instead of falling behind.
       What is waited is the rest of the frame's slot, not the whole slot on
       top of the work, so 1x really is a quarter of a second a frame rather
       than a quarter of a second plus however long the drawing took. */
    const tick = () => {
      const next = +mapStep.value + 1;
      if (next > DATA.dates.length - 1) return mapStopPlay();
      const started = performance.now();
      goToSave(next);
      const left = frameDelay() - (performance.now() - started);
      mapTimer = setTimeout(tick, Math.max(16, left));
    };
    mapTimer = setTimeout(tick, frameDelay());
  };

  toggleButton(document.getElementById('mapborders'),
               () => (mapShowProvinceBorders = !mapShowProvinceBorders), () => mapRender());

  toggleButton(document.getElementById('mapocc'), () => (mapHatchOccupied = !mapHatchOccupied),
               () => mapRender(), ['Ownership', 'Occupation']);
  document.getElementById('mapreset').onclick = () => {
    mapZoom = 1; mapOX = 0; mapOY = 0; mapPinned = null; mapRender();
  };

  const mapPicker = makePicker(document.getElementById('pick-map'),
    tagPickerCfg(DATA.tags.slice(), sel => { mapTags = sel; mapRender(); },
                 () => mapSave.value));

  const canvas = document.getElementById('mapcanvas');

  function mapZoomTo(factor, at) {
    const before = mapFit() * mapZoom;
    const mx = mapOX + at.x / before, my = mapOY + at.y / before;
    /* 24x used to be the ceiling, which is where a dense theatre still had
       counters shouldering each other: they stop growing at their cap while
       the map keeps magnifying, so every further doubling of zoom pulls the
       province anchors twice as far apart and crowding halves. 48x shows
       about 117 map pixels across a panel -- blocky, since that is the
       resolution the raster has, but it is the view where a front with a
       dozen stacks on it can be read one counter at a time. */
    mapZoom = Math.min(48, Math.max(1, mapZoom * factor));
    const after = mapFit() * mapZoom;
    mapOX = mx - at.x / after;
    mapOY = my - at.y / after;
    mapRenderSoon();
  }

  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    mapZoomTo(Math.exp(-e.deltaY * 0.0016), mapAt(e));
  }, {passive: false});

  canvas.addEventListener('dblclick', e => mapZoomTo(2, mapAt(e)));

  let drag = null;
  canvas.addEventListener('pointerdown', e => {
    drag = {...mapAt(e), ox: mapOX, oy: mapOY, moved: false};
    canvas.setPointerCapture(e.pointerId);
    canvas.style.cursor = 'grabbing';
  });
  canvas.addEventListener('pointermove', e => {
    const p = mapAt(e);
    if (drag) {
      const s = mapFit() * mapZoom;
      if (Math.abs(p.x - drag.x) + Math.abs(p.y - drag.y) > 3) drag.moved = true;
      mapOX = drag.ox - (p.x - drag.x) / s;
      mapOY = drag.oy - (p.y - drag.y) / s;
      mapRenderSoon();
      return;
    }
    if (mapPinned) return;
    const hit = mapPick(p);
    if (hit) mapShow(hit); else mapShowLand(mapProvinceAt(p));
  });
  canvas.addEventListener('pointerup', e => {
    const moved = drag && drag.moved;
    drag = null;
    canvas.style.cursor = 'grab';
    if (moved) return;
    const hit = mapPick(mapAt(e));
    mapPinned = (mapPinned && hit && mapPinned.pid === hit.pid) ? null : hit;
    mapRender();
  });
  canvas.addEventListener('pointerleave', () => { if (!mapPinned) mapIdle(); });
  window.addEventListener('resize', () => { if (MAP) mapRenderSoon(); });
} else {
  // No --mod-path, so there is no province bitmap and no country order: hide the
  // map and the great power ranking rather than showing empty frames.
  document.getElementById('mapcanvas').closest('section').hidden = true;
}


