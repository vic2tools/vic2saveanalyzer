/* =============== MAP: ARMIES AND FLEETS =============== */
/* Provinces the last mapStacks() could not place, so the readout can own up
   to an under-drawn map instead of quietly showing a fraction of the army.
   With the base-game fallback in the mod loader this should stay at zero. */
let mapUnplaced = 0, mapUnplacedBrigades = 0;

/* The dots do not move when the map does. Panning changes where each one is
   drawn, not which ones there are or what is in them, so the grouping is kept
   until the save or the nation picker changes it -- the two things that can. */
let mapStackCache = null;
/* Who was at war with whom on a given date.

   The first version of this marked provinces where a *battle* was recorded in
   the interval before the save, which was wrong in both directions: a battle
   fought last month leaves nobody on the tile today, so peaceful garrisons got
   crossed swords, and a siege that has been grinding for a year without a
   pitched battle in that particular fortnight got nothing.

   What the map can say honestly is who is standing where. Two nations on one
   tile who are on opposite sides of a war that is running are fighting -- that
   is what being on the same tile as an enemy means in this game. It needs no
   guess about timing, and it cannot mark an empty province.

   Built once, since the wars do not depend on the view. */
let mapWarBook = null;
function mapEnemiesAt(date) {
  if (!mapWarBook) {
    mapWarBook = [];
    for (const w of DATA.wars) {
      if (!w.attackers.length || !w.defenders.length) continue;
      mapWarBook.push({
        from: w.start ? dateYear(w.start) : 0,
        to: w.active || !w.end ? Infinity : dateYear(w.end),
        a: new Set(w.attackers), d: new Set(w.defenders),
      });
    }
  }
  const n = dateYear(date);
  return mapWarBook.filter(w => w.from <= n && n <= w.to);
}

/* The stacks on a contested tile, split into the two armies facing each other.

   Blending them was the thing that made a contested counter useless: "138k"
   over a province where 82k are besieging 56k says nothing anyone wants to
   know, and the band across the counter put the two sides' colours next to
   each other with no line between what they meant. Each side gets its own
   box and its own total; whoever is not in the war at all -- a neutral with
   troops parked in the middle -- keeps a box of their own on the end. */
function mapSides(stacks, fight) {
  if (!fight) return null;
  const bag = t => fight.a.includes(t) ? 0 : fight.d.includes(t) ? 1 : 2;
  const out = [[], [], []];
  for (const st of stacks) out[bag(st.tag)].push(st);
  return out.filter(g => g.length).map(g => ({
    stacks: g,
    men: g.reduce((n, a) => n + a.men, 0),
    n: g.reduce((n, a) => n + a.n, 0),
  }));
}

/* Are any two of these nations on opposite sides of a war running now? */
function mapContested(tags, wars) {
  if (tags.length < 2) return null;
  for (const w of wars) {
    const left = tags.filter(t => w.a.has(t));
    const right = tags.filter(t => w.d.has(t));
    if (left.length && right.length) return {a: left, d: right, war: w};
  }
  return null;
}

function mapStacks(date) {
  const stamp = date + '|' + (mapTags === null ? '*' : mapTags.join(','));
  if (mapStackCache && mapStackCache.stamp === stamp) {
    mapUnplaced = mapStackCache.unplaced;
    mapUnplacedBrigades = mapStackCache.unplacedBrigades;
    return mapStackCache.dots;
  }
  const armies = (MAP.armies || {})[date] || {};
  const wars = mapEnemiesAt(date);
  // `mapTags` is null until the picker is touched, which is what makes the
  // map open showing every nation. After that an empty list is a real
  // choice -- "None" -- and has to draw nothing rather than fall back to all.
  const wanted = mapTags === null ? null : new Set(mapTags);
  const dots = [];
  mapUnplaced = 0; mapUnplacedBrigades = 0;
  for (const pid in armies) {
    const spot = MAP.spots[pid];
    if (!spot) {
      mapUnplaced++;
      for (const a of armies[pid]) mapUnplacedBrigades += a[1];
      continue;
    }
    const stacks = armies[pid]
      .map(a => ({tag: MAP.tags[a[0]], n: a[1], mix: a[2],
                  // Reports written before strength was carried have three
                  // entries and no men in them; those fall back to regiments
                  // at full strength rather than reading as empty.
                  men: a.length > 3 ? a[3] : a[1] * 1000,
                  menMix: a.length > 4 ? a[4] : ''}))
      .filter(a => !wanted || wanted.has(a.tag));
    if (!stacks.length) continue;
    stacks.sort((a, b) => b.men - a.men);
    const fight = mapContested(stacks.map(a => a.tag), wars);
    dots.push({x: spot[0], y: spot[1], pid: +pid, stacks,
               total: stacks.reduce((s, a) => s + a.n, 0),
               men: stacks.reduce((s, a) => s + a.men, 0),
               fighting: fight,
               sides: mapSides(stacks, fight)});
  }
  dots.sort((a, b) => b.total - a.total);   // small stacks draw last, on top
  mapStackCache = {stamp, dots, unplaced: mapUnplaced,
                   unplacedBrigades: mapUnplacedBrigades};
  return dots;
}

/* A pointer or a wheel reports far more often than the screen redraws -- a
   120Hz trackpad or a high-rate mouse will fire several times between frames,
   and each one used to repaint. Every repaint past the first was thrown away
   unseen, and with occupation on each costs a second scaled blit of the raster
   plus a full-canvas mask, so the queue fell behind and the map dragged.

   Coalescing to one repaint per animation frame draws exactly what gets shown.
   The one-off callers -- picking a save, toggling a layer, clicking a marker --
   still call `mapRender` directly, since there is no storm to smooth there. */
let mapFrame = 0;
function mapRenderSoon() {
  if (mapFrame) return;
  mapFrame = requestAnimationFrame(() => { mapFrame = 0; mapRender(); });
}

/* Everyone alive at this save, land nobody owns included.

   Summing the nations would have been easier and would have been wrong: pops
   on land nobody has colonised yet belong to no nation, and they are 6.4% of
   the world in 1836 and none of it by 1908. A total built that way would climb
   as the map was carved up and read as people being born. */
function mapWorldPop(date) {
  const el = document.getElementById('mapworld');
  if (!el) return;
  const n = DATA.worldPop[date];
  if (!n) { el.textContent = ''; return; }
  const first = DATA.worldPop[DATA.dates[0]] || 0;
  const since = first && n !== first
    ? '  ' + (n > first ? '+' : '−')
      + Math.abs((n / first - 1) * 100).toFixed(1) + '% since ' + DATA.dates[0]
    : '';
  el.textContent = '·  world population ' + n.toLocaleString() + since;
}

// The map at the selected save: its tiles, its army counters, their numbers.
function mapRender() {
  if (!MAP) return;
  const date = document.getElementById('mapsave').value || DATA.lastDate;
  document.getElementById('mapdate').textContent = date;
  mapWorldPop(date);          // beside the date it was counted on
  mapTileState(date);
  const {ctx, s, cw, ch} = mapPaintGround(date);
  mapDrawCounts(ctx, mapDrawStacks(ctx, date, s, cw, ch));
  document.getElementById('mapzoom').textContent = mapZoom.toFixed(1) + '×';
  mapShow(mapPinned);
}

// The canvas sized to the page, the sea, and the tiles with occupation
// hatched over them: {ctx, s (the scale), cw, ch}.
function mapPaintGround(date) {
  const canvas = document.getElementById('mapcanvas');
  const dpr = window.devicePixelRatio || 1;
  const cw = canvas.clientWidth || MAP.w, ch = canvas.clientHeight || MAP.h;
  if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) {
    canvas.width = Math.round(cw * dpr);
    canvas.height = Math.round(ch * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  // Extend the ocean into the space around the fitted map in a tall atlas.
  ctx.fillStyle = `rgb(${MAP_WATER.join(',')})`;
  ctx.fillRect(0, 0, cw, ch);

  mapClamp(cw, ch);
  const s = mapFit(cw) * mapZoom;
  const scratch = mapHatchOccupied && mapOccAny ? mapScratch(canvas.width,canvas.height) : null;
  const sc = scratch ? scratch.getContext('2d') : null;
  if (sc) {
    sc.setTransform(dpr,0,0,dpr,0,0);
    sc.clearRect(0,0,cw,ch);
  }
  mapPaintTiles(ctx,sc,date,s,cw,ch,dpr);
  if (sc) {
    sc.globalCompositeOperation='destination-in';
    sc.fillStyle=mapHatchPattern(sc);
    sc.fillRect(0,0,cw,ch);
    sc.globalCompositeOperation='source-over';
    ctx.drawImage(scratch,0,0,cw,ch);
  }

  return {ctx, s, cw, ch};
}

// Every army and fleet counter at the save, biggest first, holding back one
// that would cover a counter already placed: the counters drawn, for their
// numbers.
function mapDrawStacks(ctx, date, s, cw, ch) {
  mapDots = mapStacks(date);
  // markers grow with zoom, but slower than the map, so a dense theatre thins
  // out as you go in instead of turning into one blob
  const grow = Math.pow(mapZoom, 0.45);
  const labelled = [];
  /* Province anchors in a dense theatre are closer together than a counter is
     wide, so two of them land on top of each other and neither number can be
     read -- which is what made the map look broken rather than busy. The
     stacks are drawn biggest first, and one that would cover a counter already
     placed is held back rather than drawn over it. Nothing is lost: the count
     of what is holding back is put on the readout, and zooming separates the
     anchors until they all fit, since counters grow slower than the map. */
  const placed = [];
  mapCrowded = 0;
  for (const dot of mapDots) {
    dot.sx = (dot.x - mapOX) * s;
    dot.sy = (dot.y - mapOY) * s;
    /* Every counter the same size -- sizing them by strength meant a big army
       drew a block several times the width of its neighbours, which buried
       them and made adjacent provinces collide. The number inside says how
       big the stack is, and says it exactly rather than by area.

       What the size does carry is how much detail there is room for. Zoomed
       out the counter is a small mark that answers "who has troops, and
       where"; zoomed in it grows into a block with the strength written in
       it. So it starts smaller than it used to and grows faster. */
    const half = Math.max(2.2, Math.min(14, 2.9 * Math.pow(mapZoom, 0.72)));
    dot.sr = half;                      // hit testing still works in radii
    const hw = half * 1.7, hh = half * 0.95;
    dot.hw = hw; dot.hh = hh;
    if (dot.sx < -30 || dot.sy < -30 || dot.sx > cw + 30 || dot.sy > ch + 30) continue;
    // Overlapping by more than half in both directions is the point at which
    // the number underneath stops being readable.
    // A contested tile draws a counter a side, so it needs the room of both
    // before anything else is allowed to sit next to it.
    const boxes = dot.sides ? dot.sides.length : 1;
    /* A contested tile draws a box a side, but not two full-width ones: at
       full width the pair was two and a half times a plain counter and buried
       whatever province sat next to it. Each side is drawn at four fifths,
       touching, so the pair comes to about 1.6 counters rather than 2.4. */
    const sideNarrow = boxes > 1 ? 0.8 : 1;
    const reach = half * 1.7 * boxes * sideNarrow;
    /* Two counters overlap when the distance between their centres is less
       than their half-widths added together. The first version halved that
       sum, which let them sit half on top of each other and still pass -- so
       the map still had counters with their numbers half buried. */
    /* A hair of overlap is allowed -- a counter clipping a neighbour's frame
       by a few per cent costs nothing, while demanding perfect separation hid
       four times as many. */
    let hidden = false;
    for (const p of placed) {
      if (Math.abs(p.x - dot.sx) < (reach + p.reach) * 0.72
          && Math.abs(p.y - dot.sy) < hh * 1.5) {
        hidden = true;
        break;
      }
    }
    /* A held-back counter still leaves a pip where it stands.

       Dropping it entirely was worse than the overlap it was avoiding: fifty
       brigades in Udine were simply not on the map, and the only way to find
       them was to hover apparently empty ground. A pip says "troops here, the
       number is a hover away", which is what the zoomed-out view is for. It
       reserves no space of its own, so it cannot push a third counter out in
       turn. */
    if (hidden) {
      mapCrowded++;
      const r = Math.max(1.6, half * 0.42);
      ctx.beginPath();
      ctx.arc(dot.sx, dot.sy, r, 0, Math.PI * 2);
      ctx.fillStyle = mapDim(MAP.colours[dot.stacks[0].tag] || '#ffffff');
      ctx.fill();
      ctx.lineWidth = Math.min(1.2, .5 * grow);
      ctx.strokeStyle = dot.fighting ? '#ff5c33' : 'rgba(255,240,214,.75)';
      ctx.stroke();
      continue;
    }
    placed.push({x: dot.sx, y: dot.sy, reach});
    const ink = t => mapDim(MAP.colours[t] || '#ffffff');
    const x0 = dot.sx - hw, y0 = dot.sy - hh, ww = hw * 2, hgt = hh * 2;

    /* Somewhere fought over since the last save gets a burst behind its
       counter -- spikes radiating past the corners, the way a fight is drawn
       on a map. Behind rather than over, so it never touches the number; a
       shape rather than a colour, because the map is already made of colour
       and an orange edge was lost against whichever nation owned the ground.
       The first go put small sabres above the counter, which collided with
       whatever was drawn north of it and vanished at anything but full zoom. */
    const inFight = dot.fighting;
    // Below this the diamond is smaller than the counter it sits behind
    // and only its tips show, so the counter's own edge carries it instead.
    const burstFits = half >= 4.5;

    /* One box, or one box a side where two armies are facing each other.
       Each is banded by the nations in it, in proportion to their men. */
    const groups = dot.sides || [{stacks: dot.stacks, men: dot.men, n: dot.total}];
    const gap = 0;               // the sides touch; a rule marks the join
    const bw = ww * sideNarrow;
    const boxW = bw * groups.length;
    let bx = dot.sx - boxW / 2;
    dot.boxes = [];
    /* The diamond goes behind the pair, which is where it read best -- but
       sized so it stays a diamond. The version that scaled its width with the
       box count and left its height alone came out a flattened lozenge with
       points jutting out either side; giving it height in proportion keeps it
       near 1.4:1, which reads as a shape rather than a smear. */
    if (inFight && burstFits) {
      const rx = boxW / 2 + half * 0.6, ry = hh + half * 1.35;
      ctx.beginPath();
      ctx.moveTo(dot.sx, dot.sy - ry);
      ctx.lineTo(dot.sx + rx, dot.sy);
      ctx.lineTo(dot.sx, dot.sy + ry);
      ctx.lineTo(dot.sx - rx, dot.sy);
      ctx.closePath();
      ctx.fillStyle = '#a82c14';
      ctx.fill();
      ctx.lineWidth = Math.min(1.3, .55 * grow);
      ctx.strokeStyle = 'rgba(255,196,150,.9)';
      ctx.stroke();
    }
    groups.forEach((g, gi) => {
      ctx.fillStyle = ink(g.stacks[0].tag);
      ctx.fillRect(bx, y0, bw, hgt);
      if (g.stacks.length > 1 && bw >= 8) {
        let at = bx;
        for (const part of g.stacks) {
          const seg = bw * (part.men / Math.max(1, g.men));
          ctx.fillStyle = ink(part.tag);
          ctx.fillRect(at, y0, seg, hgt);
          at += seg;
        }
        if (bw >= 16) {
          ctx.lineWidth = Math.min(1.1, .45 * grow);
          ctx.strokeStyle = 'rgba(0,0,0,.6)';
          at = bx;
          for (const part of g.stacks) {
            at += bw * (part.men / Math.max(1, g.men));
            ctx.beginPath();
            ctx.moveTo(at, y0); ctx.lineTo(at, y0 + hgt);
            ctx.stroke();
          }
        }
      }
      dot.boxes.push({x: bx + bw / 2, y: dot.sy, men: g.men, w: bw});
      bx += bw;
      // A bright rule where two sides meet, so the join is not read as one
      // nation's colour running into the next.
      if (gi < groups.length - 1) {
        ctx.lineWidth = Math.max(1, Math.min(2, .9 * grow));
        ctx.strokeStyle = 'rgba(255,232,200,.95)';
        ctx.beginPath();
        ctx.moveTo(bx, y0); ctx.lineTo(bx, y0 + hgt);
        ctx.stroke();
      }
    });
    /* A pale edge, which is what survives on a dark nation's land -- unless
       this province is being fought over and the counter is too small for the
       burst to show around it, in which case the edge itself carries it. At
       twelve pixels across there is no room for a symbol, but there is room
       for a colour. */
    ctx.lineWidth = inFight && !burstFits
      ? Math.max(1.4, Math.min(2.2, 1.1 * grow)) : Math.min(1.6, .7 * grow);
    ctx.strokeStyle = inFight && !burstFits
      ? '#ff5c33' : 'rgba(255,240,214,.7)';
    for (const b of dot.boxes) ctx.strokeRect(b.x - b.w / 2, y0, b.w, hgt);

    if (mapPinned && mapPinned.pid === dot.pid) {
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = '#ffffff';
      for (const b of dot.boxes) ctx.strokeRect(b.x - b.w / 2, y0, b.w, hgt);
    }
    labelled.push(dot);
  }
  return labelled;
}

function mapDrawCounts(ctx, labelled) {
  // Numerals last, so a small stack drawn over a big one cannot have its
  // count half-covered. Only where the circle can hold the digits: below
  // that the number would be a smudge, and the count is a hover away.
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const dot of labelled) {
    for (const box of dot.boxes) {
      // Men, not regiments: it is what the counter is sized on and what
      // changes when a stack takes casualties. Rounded to thousands past 10k,
      // where the exact figure is neither readable at this size nor what
      // anyone is asking of a glance. On a contested tile each side carries
      // its own, so the counter reads as the matchup it is.
      const text = box.men >= 10000
        ? Math.round(box.men / 1000).toLocaleString() + 'k'
        : box.men.toLocaleString();
      // Fitted to the box rather than a radius: monospace digits run about
      // 0.6em wide, so the width test is against the count of them.
      const size = Math.min(dot.hh * 1.6, box.w * 1.4 / text.length);
      if (size < 7) continue;
      ctx.font = `600 ${size.toFixed(1)}px "IBM Plex Mono", monospace`;
      ctx.lineWidth = Math.max(1.6, size / 5);
      ctx.strokeStyle = 'rgba(0,0,0,.55)';
      ctx.strokeText(text, box.x, box.y);
      ctx.fillStyle = '#F6ECD8';
      ctx.fillText(text, box.x, box.y);
    }
  }
}

