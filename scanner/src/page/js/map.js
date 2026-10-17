/* =============== MAP =============== */
const MAP = DATA.map;
let mapTags = null;          // null means every nation
let mapHatchOccupied = true;
let mapShowProvinceBorders = false;
/* Contested tiles are always marked: "enemies are standing here" is a fact
   of the save, not a guess worth switching off. */
let mapProv = null;          // province id for every pixel
let mapOwners = null;        // date -> {own: Map, occ: Map}
let mapDots = [];            // what is currently drawn, for hit testing
let mapCrowded = 0;          // counters held back because one was already there
let mapOccAny = false;
let mapStopPlay = () => {};  // set once the controls exist
let mapZoom = 1;             // 1 fits the whole world to the panel width
let mapOX = 0, mapOY = 0;    // map coordinate sitting at the panel's top left
let mapPinned = null;        // a marker clicked, so the readout stays put

function mapDecoded() {
  if (!mapProv) { mapProv = mapDecode(); mapOwners = mapOwnerTables(); }
}

/* A colour in the byte order `putImageData` actually reads.

   The canvas buffer is bytes R,G,B,A, so on a little-endian machine one 32-bit
   store must carry them reversed. Every machine this runs on is little-endian,
   but the order is derived rather than assumed: a single pixel is written
   through the byte view and read back through the word view, once. */
let mapEndian = 0;
function mapWord(rgb) {
  if (!mapEndian) {
    const probe = new Uint8ClampedArray(4);
    probe[0] = 1;
    mapEndian = new Uint32Array(probe.buffer)[0] === 1 ? 1 : 2;
  }
  return mapEndian === 1
    ? (0xFF000000 | ((rgb & 255) << 16) | (rgb & 0xFF00) | ((rgb >> 16) & 255))
    : (((rgb & 0xFFFFFF) << 8) | 0xFF);
}

/* A palette converted once, with the unclaimed-land colour on the end. */
function mapWords(table, wild) {
  const out = new Uint32Array(table.length + 1);
  for (let i = 0; i < table.length; i++) out[i] = mapWord(table[i]);
  out[table.length] = mapWord(wild);
  return out;
}

function mapDecode() {
  const grid = new Int32Array(MAP.w * MAP.h);
  let at = 0;
  for (const token of MAP.runs.split(' ')) {
    if (!token) continue;
    const dot = token.indexOf('.');
    const pid = parseInt(dot < 0 ? token : token.slice(0, dot), 36);
    const run = dot < 0 ? 1 : parseInt(token.slice(dot + 1), 36);
    grid.fill(pid, at, at + run);
    at += run;
  }
  return grid;
}

/* Ownership ships as a delta per save, so replay them in order. */
function mapOwnerTables() {
  const out = {};
  let cur = new Map();
  for (const step of MAP.owners) {
    if (step.base) cur = new Map();
    if (step.clear) for (const p of step.clear.split(',')) cur.delete(+p);
    if (step.set) for (const pair of step.set.split(',')) {
      const c = pair.indexOf(':');
      cur.set(+pair.slice(0, c), +pair.slice(c + 1));
    }
    const occ = new Map();
    if (step.occ) for (const pair of step.occ.split(',')) {
      const c = pair.indexOf(':');
      occ.set(+pair.slice(0, c), +pair.slice(c + 1));
    }
    out[step.date] = {own: new Map(cur), occ};
  }
  return out;
}

const mapSea = new Set((MAP && MAP.sea) || []);
const MAP_WATER = [30, 47, 61], MAP_WILD = [112, 108, 88], MAP_EDGE = [35, 32, 28];
/* Land is painted in a nation's own colour and so are the army counters
   standing on it, which left a nation's brigades all but invisible inside its
   own borders -- an orange stack on orange ground, separated by half a pixel
   of outline. The counter is what gives way: it keeps the nation's hue but
   drops toward MAP_SHADE, so the political map reads at full strength and a
   stack still reads against the country it is standing in. Going the other
   way -- dimming the land -- worked too, but it dulled the whole map to fix
   a few hundred circles. Dark counters also carry a pale numeral, which a
   full-strength one could not. */
const MAP_SHADE = [16, 14, 20], MAP_SHADE_MIX = 0.48;
/** A #rrggbb string in the same hue, dropped toward MAP_SHADE. */
const mapDim = hex => {
  const rgb = parseInt((hex || '#ffffff').slice(1), 16);
  const keep = 1 - MAP_SHADE_MIX;
  const mix = (v, i) => Math.round(v * keep + MAP_SHADE[i] * MAP_SHADE_MIX);
  return `rgb(${mix((rgb >> 16) & 255, 0)} ${mix((rgb >> 8) & 255, 1)} `
       + `${mix(rgb & 255, 2)})`;
};

// Match the theatre map's softer land colours without changing marker colours.
function mapLandColour(hex) {
  const rgb = parseInt(hex.slice(1), 16);
  const soften = v => Math.round(v * .65 + 45);
  return (soften((rgb >> 16) & 255) << 16)
    | (soften((rgb >> 8) & 255) << 8) | soften(rgb & 255);
}

function mapPalette(date) {
  const book = mapOwners[date] || {own: new Map(), occ: new Map()};
  const owners = new Map(book.own);
  let top = 0;
  mapSea.forEach(p => { if (p > top) top = p; });
  owners.forEach((_i, p) => { if (p > top) top = p; });
  const table = new Int32Array(top + 1);
  const wild = (MAP_WILD[0] << 16) | (MAP_WILD[1] << 8) | MAP_WILD[2];
  const water = (MAP_WATER[0] << 16) | (MAP_WATER[1] << 8) | MAP_WATER[2];
  for (let p = 0; p <= top; p++) table[p] = mapSea.has(p) ? water : wild;
  owners.forEach((idx, pid) => {
    const hex = MAP.colours[MAP.tags[idx]];
    if (hex) table[pid] = mapLandColour(hex);
  });
  return table;
}

/* Who is holding land that belongs to somebody else, as a colour per province
   and -1 for everywhere nobody is. Kept apart from the owner table because
   occupation is drawn over the top rather than instead: shading occupied ground
   in the occupier's colour made a siege and an annexation look identical. */
function mapOccPalette(date) {
  const book = mapOwners[date] || {own: new Map(), occ: new Map()};
  let top = 0;
  book.occ.forEach((_i, p) => { if (p > top) top = p; });
  const table = new Int32Array(top + 1).fill(-1);
  book.occ.forEach((idx, pid) => {
    const hex = MAP.colours[MAP.tags[idx]];
    if (hex) table[pid] = parseInt(hex.slice(1), 16);
  });
  return table;
}

/* Fixed province-index levels never depend on the date or the camera. Each
   level halves both dimensions; a 2x2 majority keeps coastlines and small
   provinces steadier than sampling one pixel. Odd raster edges are retained. */
const mapLevels = [];
let mapMaxProvince = 0;
function mapLevel(level) {
  if (!mapLevels.length) {
    mapDecoded();
    for (const p of mapProv) if (p > mapMaxProvince) mapMaxProvince = p;
    mapLevels.push({w:MAP.w, h:MAP.h, prov:mapProv, step:1});
  }
  while (mapLevels.length <= level) {
    const prev = mapLevels[mapLevels.length - 1];
    const w = Math.ceil(prev.w / 2), h = Math.ceil(prev.h / 2);
    const prov = new Int32Array(w * h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = y * 2 * prev.w + x * 2;
      const right = x * 2 + 1 < prev.w, down = y * 2 + 1 < prev.h;
      const a = prev.prov[i], b = right ? prev.prov[i+1] : a;
      const c = down ? prev.prov[i+prev.w] : a;
      const d = down ? (right ? prev.prov[i+prev.w+1] : c) : b;
      prov[y*w+x] = b === c || b === d ? b : c === d ? c : a;
    }
    mapLevels.push({w,h,prov,step:prev.step*2});
  }
  return mapLevels[level];
}

/* Only visible tiles are coloured. A bounded LRU holds both layers across
   pans and zoom steps; ownership changes discard coloured tiles, not geometry.
   Borders read neighbouring province owners directly, including across tile
   seams: playback never scans the full world to find political boundaries. */
const MAP_TILE_SIZE = 256, MAP_TILE_LIMIT = 128;
const mapTiles = new Map();
let mapTileDate = null, mapTilePalette = null;
function mapSameValues(a,b) {
  if (!a || a.length!==b.length) return false;
  for (let i=0;i<a.length;i++) if (a[i]!==b[i]) return false;
  return true;
}
function mapTileState(date) {
  if (mapTileDate === date) return mapTilePalette;
  mapLevel(0);
  const colours = mapPalette(date), occupation = mapOccPalette(date);
  const owners = (mapOwners[date] || {own:new Map()}).own;
  const identity = new Int32Array(mapMaxProvince + 1).fill(-1);
  for (const p of mapSea) identity[p] = -2;
  for (const [p, owner] of owners) if (!mapSea.has(p)) identity[p] = owner;
  // Most saves move armies without changing the political raster. Retain the
  // tiles when ownership and occupation are identical, using exact comparison
  // rather than a hash that could leave a stale border after a collision.
  if (!mapTilePalette || !mapSameValues(mapTilePalette.identity,identity)
      || !mapSameValues(mapTilePalette.occupation,occupation)) mapTiles.clear();
  mapTilePalette = {
    colours:mapWords(colours, (MAP_WILD[0]<<16)|(MAP_WILD[1]<<8)|MAP_WILD[2]),
    colourCount:colours.length, occupation,
    occupied:mapWords(occupation,0), identity,
    edge:mapWord((MAP_EDGE[0]<<16)|(MAP_EDGE[1]<<8)|MAP_EDGE[2]),
  };
  mapOccAny = occupation.some(c => c >= 0);
  mapTileDate = date;
  return mapTilePalette;
}

function mapTile(level, tx, ty, palette, occupied) {
  const key = `${level}|${tx}|${ty}|${mapShowProvinceBorders}|${occupied}`;
  let tile = mapTiles.get(key);
  if (tile) { mapTiles.delete(key); mapTiles.set(key,tile); return tile; }
  const idx = mapLevel(level), x0 = tx*MAP_TILE_SIZE, y0 = ty*MAP_TILE_SIZE;
  const w = Math.min(MAP_TILE_SIZE,idx.w-x0), h = Math.min(MAP_TILE_SIZE,idx.h-y0);
  const base = document.createElement('canvas'); base.width=w; base.height=h;
  const ctx = base.getContext('2d'), img = ctx.createImageData(w,h);
  const pixels = new Uint32Array(img.data.buffer);
  const occImg = occupied ? ctx.createImageData(w,h) : null;
  const occPixels = occImg ? new Uint32Array(occImg.data.buffer) : null;
  const {identity,colours,colourCount,occupation} = palette;
  for (let y=0; y<h; y++) for (let x=0; x<w; x++) {
    const i=(y0+y)*idx.w+x0+x, dst=y*w+x, p=idx.prov[i];
    const right=x0+x+1<idx.w ? idx.prov[i+1] : p;
    const down=y0+y+1<idx.h ? idx.prov[i+idx.w] : p;
    const boundary=p!==right || p!==down;
    const edge=boundary && (mapShowProvinceBorders
      || identity[p]!==identity[right] || identity[p]!==identity[down]);
    pixels[dst]=edge ? palette.edge : colours[p<colourCount ? p : colourCount];
    if (occPixels && !edge && p<occupation.length && occupation[p]>=0) occPixels[dst]=palette.occupied[p];
  }
  ctx.putImageData(img,0,0);
  let occ=null;
  if (occImg) {
    occ=document.createElement('canvas'); occ.width=w; occ.height=h;
    occ.getContext('2d').putImageData(occImg,0,0);
  }
  tile={base,occ}; mapTiles.set(key,tile);
  if (mapTiles.size>MAP_TILE_LIMIT) mapTiles.delete(mapTiles.keys().next().value);
  return tile;
}

function mapPaintTiles(ctx, sc, date, s, cw, ch, dpr) {
  // Choose a stable resolution near physical screen pixels, not an arbitrary
  // zoom=1 special case. Cap density at 2 for bounded work on high-DPI screens.
  let level=Math.max(0,Math.floor(Math.log2(1/(s*Math.min(dpr,2)))));
  const maxLevel=Math.ceil(Math.log2(Math.max(MAP.w,MAP.h)));
  level=Math.min(level,maxLevel);
  const x0=Math.max(0,mapOX), y0=Math.max(0,mapOY);
  const x1=Math.min(MAP.w,mapOX+cw/s), y1=Math.min(MAP.h,mapOY+ch/s);
  if (x1<=x0 || y1<=y0) return;
  // Keep the visible working set below the cache limit even on huge displays.
  while (level<maxLevel) {
    const span=MAP_TILE_SIZE*2**level;
    const count=(Math.ceil(x1/span)-Math.floor(x0/span))*(Math.ceil(y1/span)-Math.floor(y0/span));
    if (count<=MAP_TILE_LIMIT/2) break;
    level++;
  }
  const idx=mapLevel(level), step=idx.step;
  const palette=mapTileState(date);
  const firstX=Math.floor(x0/step/MAP_TILE_SIZE), firstY=Math.floor(y0/step/MAP_TILE_SIZE);
  const endX=Math.ceil(x1/step/MAP_TILE_SIZE), endY=Math.ceil(y1/step/MAP_TILE_SIZE);
  // Align shared edges to device pixels and use nearest sampling. This avoids
  // translucent hairlines between tiles and keeps boundaries crisp at any zoom.
  ctx.imageSmoothingEnabled=false;
  if(sc) sc.imageSmoothingEnabled=false;
  for(let ty=firstY;ty<endY;ty++) for(let tx=firstX;tx<endX;tx++) {
    const tile=mapTile(level,tx,ty,palette,!!sc);
    const lx=tx*MAP_TILE_SIZE, ly=ty*MAP_TILE_SIZE;
    const sx=Math.max(0,x0/step-lx), sy=Math.max(0,y0/step-ly);
    const ex=Math.min(tile.base.width,x1/step-lx), ey=Math.min(tile.base.height,y1/step-ly);
    const dx=Math.round(((lx+sx)*step-mapOX)*s*dpr)/dpr;
    const dy=Math.round(((ly+sy)*step-mapOY)*s*dpr)/dpr;
    const dw=Math.round(((lx+ex)*step-mapOX)*s*dpr)/dpr-dx;
    const dh=Math.round(((ly+ey)*step-mapOY)*s*dpr)/dpr-dy;
    ctx.drawImage(tile.base,sx,sy,ex-sx,ey-sy,dx,dy,dw,dh);
    if(sc) sc.drawImage(tile.occ,sx,sy,ex-sx,ey-sy,dx,dy,dw,dh);
  }
}

/* One tile of diagonal stripes, built once and used as a mask on the screen
   rather than painted into the map. On the screen the hatching keeps the same
   width however far the map is zoomed; baked into a 5,616-pixel raster, one
   stripe would be a hair at zoom 1 and half a province at zoom 24. */
let mapHatchTile = null;
let mapHatchFill = null;     // the CanvasPattern, which outlives the frame
function mapHatchPattern(ctx) {
  if (mapHatchFill) return mapHatchFill;
  if (!mapHatchTile) {
    const p = 9, ink = 3;
    mapHatchTile = document.createElement('canvas');
    mapHatchTile.width = mapHatchTile.height = p;
    const t = mapHatchTile.getContext('2d');
    const img = t.createImageData(p, p);
    for (let y = 0; y < p; y++) {
      for (let x = 0; x < p; x++) {
        const o = (y * p + x) * 4;
        img.data[o] = img.data[o + 1] = img.data[o + 2] = 255;
        // x + y wraps cleanly at the tile edge, so the stripes join up.
        // Three pixels on and six off, rather than the five and four it began
        // as: the occupier has to be legible, but it is the owner's province
        // and the owner's colour should still be the one the eye lands on.
        img.data[o + 3] = ((x + y) % p) < ink ? 255 : 0;
      }
    }
    t.putImageData(img, 0, 0);
  }
  // Held rather than remade each frame. A pattern is bound to the canvas that
  // created it, and the scratch canvas is kept, so one lasts as long as it.
  mapHatchFill = ctx.createPattern(mapHatchTile, 'repeat');
  return mapHatchFill;
}

/* A screen-sized canvas to build the hatched layer in, since masking with
   `destination-in` eats whatever else is on the canvas it runs on. */
let mapScratchCanvas = null;
function mapScratch(w, h) {
  if (!mapScratchCanvas) mapScratchCanvas = document.createElement('canvas');
  if (mapScratchCanvas.width !== w || mapScratchCanvas.height !== h) {
    mapScratchCanvas.width = w;
    mapScratchCanvas.height = h;
    // Resizing a canvas resets its context, so the pattern made from the old
    // one is no longer usable and has to be made again.
    mapHatchFill = null;
  }
  return mapScratchCanvas;
}

function mapFit(cw) {        // screen pixels per map pixel at zoom 1
  if (cw === undefined) {
    const canvas = document.getElementById('mapcanvas');
    cw = canvas.clientWidth || MAP.w;
  }
  return cw / MAP.w;
}

function mapClamp(cw, ch) {
  const canvas = document.getElementById('mapcanvas');
  // Reading `clientWidth` makes the browser settle the layout before it can
  // answer. The render already knows the size, so it passes it in rather than
  // asking again twice.
  if (cw === undefined) cw = canvas.clientWidth || MAP.w;
  if (ch === undefined) ch = canvas.clientHeight || MAP.h;
  const s = mapFit(cw) * mapZoom;
  const viewW = cw / s;
  const viewH = ch / s;
  mapOX = viewW >= MAP.w ? (MAP.w - viewW) / 2
                         : Math.min(Math.max(mapOX, 0), MAP.w - viewW);
  mapOY = viewH >= MAP.h ? (MAP.h - viewH) / 2
                         : Math.min(Math.max(mapOY, 0), MAP.h - viewH);
}

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
    const num = d => {
      const p = String(d).split('.');
      return (+p[0]) * 10000 + (+(p[1] || 1)) * 100 + (+(p[2] || 1));
    };
    mapWarBook = [];
    for (const w of DATA.wars) {
      if (!w.attackers.length || !w.defenders.length) continue;
      mapWarBook.push({
        from: w.start ? num(w.start) : 0,
        to: w.active || !w.end ? Infinity : num(w.end),
        a: new Set(w.attackers), d: new Set(w.defenders),
      });
    }
    mapWarBook.num = num;
  }
  const n = mapWarBook.num(date);
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

function mapRender() {
  if (!MAP) return;
  const canvas = document.getElementById('mapcanvas');
  const date = document.getElementById('mapsave').value || DATA.lastDate;
  document.getElementById('mapdate').textContent = date;
  mapWorldPop(date);          // beside the date it was counted on
  mapTileState(date);

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
  document.getElementById('mapzoom').textContent = mapZoom.toFixed(1) + '×';
  mapShow(mapPinned);
}

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
  DATA.dates.forEach(d => {
    const o = document.createElement('option'); o.value = d; o.textContent = d;
    mapSave.appendChild(o);
  });
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

  const borderBtn = document.getElementById('mapborders');
  borderBtn.onclick = () => {
    mapShowProvinceBorders = !mapShowProvinceBorders;
    borderBtn.setAttribute('aria-pressed', mapShowProvinceBorders);
    mapRender();
  };

  const occBtn = document.getElementById('mapocc');
  occBtn.onclick = () => {
    mapHatchOccupied = !mapHatchOccupied;
    occBtn.setAttribute('aria-pressed', mapHatchOccupied);
    occBtn.textContent = mapHatchOccupied ? 'Occupation' : 'Ownership';
    mapRender();
  };
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


