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

/* Every province's place on the map, measured in one pass over the bitmap
   and kept: its box, its area in pixels, its centre (the mean of its
   pixels), and for land the land provinces it touches. In the order the map
   first meets each province. */
let mapGeometry = null;
function provinceGeometry() {
  mapDecoded();
  if (mapGeometry) return mapGeometry;
  const geometry = new Map();
  for (let y = 0; y < MAP.h; y++) for (let x = 0; x < MAP.w; x++) {
    const p = mapProv[y * MAP.w + x];
    if (!p) continue;
    let g = geometry.get(p);
    if (!g) {
      g = {x0: x, x1: x, y0: y, y1: y, area: 0, sx: 0, sy: 0, neighbours: new Set()};
      geometry.set(p, g);
    }
    g.x0 = Math.min(g.x0, x); g.x1 = Math.max(g.x1, x); g.y1 = y;
    g.area++; g.sx += x; g.sy += y;
    if (mapSea.has(p)) continue;
    for (const q of [x ? mapProv[y * MAP.w + x - 1] : p, y ? mapProv[(y - 1) * MAP.w + x] : p]) {
      if (q === p || mapSea.has(q)) continue;
      g.neighbours.add(q); geometry.get(q)?.neighbours.add(p);
    }
  }
  for (const g of geometry.values()) { g.cx = g.sx / g.area; g.cy = g.sy / g.area; }
  return mapGeometry = geometry;
}

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

