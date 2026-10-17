/* =============== WARS =============== */
const WARS = DATA.wars || [];
let warPick = null;
/* What to write in a war's "to" column.

   Victoria 2 wars do not always end. Two AIs that cannot reach each other
   never agree a peace, and the war sits in the save as an active_war until
   the campaign stops -- the German-French War in one campaign had its last
   battle in 1872 and was still open in 1881, nine years without a shot
   fired. The save is not wrong and neither was this column, but "ongoing"
   for a war nobody has fought since the last decade reads as a mistake in
   the report rather than a fact about the game. So a war still open at the
   last save says so, and one that has been open and quiet for over a year
   says that instead, with the date it went quiet. */
function warEnd(w) {
  if (!w.active) return w.end || '—';
  const quiet = warQuietSince(w);
  return quiet ? `<b>unresolved</b> <span class="rk">quiet since ${quiet}</span>`
               : '<b>ongoing</b>';
}
// The date an open war last saw a battle, if that was over a year before the
// last save; '' while it is still being fought.
function warQuietSince(w) {
  /* Years as a number, because these are `1872.9.1` strings and sorting them
     as text puts October before September. */
  const when = d => {
    const p = String(d).split('.');
    return (+p[0]) + ((+(p[1] || 1)) - 1) / 12;
  };
  let last = 0, shown = w.start;
  for (const b of w.battles) {
    if (b.date && when(b.date) > last) { last = when(b.date); shown = b.date; }
  }
  if (!last && w.start) last = when(w.start);
  let finish = 0;
  for (const d of (DATA.dates || [])) finish = Math.max(finish, when(d));
  return last && finish && finish - last > 1 ? shown : '';
}

let warSort = {key: 'losses', dir: -1};

function warLosses(w) { return w.losses[0] + w.losses[1]; }
function warSide(list) {
  return list.map(t => `<b style="color:${colourFor(t)}">${t}</b>`).join(' ');
}

function drawWarTable() {
  if (!WARS.length) return;
  const q = (document.getElementById('warfind').value || '').trim().toLowerCase();
  const rows = WARS.filter(w => !q
    || w.name.toLowerCase().includes(q)
    || w.attackers.concat(w.defenders).some(t =>
         t.toLowerCase() === q || nameOf(t).toLowerCase().includes(q)));
  const get = {
    name: w => w.name.toLowerCase(),
    start: w => w.start || '',
    losses: warLosses,
    battles: w => w.battles.length,
    land: w => w.transfers.length,
    outcome: w => w.outcome || 'zz',
  }[warSort.key] || warLosses;
  rows.sort((a, b) => {
    const x = get(a), y = get(b);
    return (x < y ? -1 : x > y ? 1 : 0) * warSort.dir;
  });

  const head = [['name', 'War'], ['start', 'From'], ['start', 'To'],
                ['losses', 'Casualties'], ['battles', 'Battles'],
                ['land', 'States'], ['outcome', 'Goals taken']];
  const wide = k => k === 'name' ? '' : ' class="num"';
  const body = rows.map((w, i) => {
    const idx = WARS.indexOf(w);
    return `<tr class="warrow${warPick === idx ? ' on' : ''}" data-war="${idx}">`
      + `<td class="warname">${w.name}`
      + `<div class="rk sides">${warSide(w.attackers)} <span class="rk">v</span> `
      + `${warSide(w.defenders)}</div></td>`
      + `<td class="num">${w.start || '—'}</td>`
      + `<td class="num">${warEnd(w)}</td>`
      + `<td class="num">${warLosses(w).toLocaleString()}</td>`
      + `<td class="num">${w.battles.length}${w.battles.length && w.dated < w.battles.length
            ? ` <span class="rk">(${w.dated} dated)</span>` : ''}</td>`
      + `<td class="num">${w.transfers.length || '—'}</td>`
      + `<td class="num">${w.outcome || '<span class="rk">—</span>'}</td></tr>`;
  }).join('');
  document.getElementById('wartable').innerHTML =
    `<thead><tr>${head.map(([k, label]) =>
      `<th data-k="${k}"${wide(k)}${warSort.key === k ? ' aria-sort="' +
        (warSort.dir < 0 ? 'descending' : 'ascending') + '"' : ''}>${label}</th>`)
      .join('')}</tr></thead><tbody>${body}</tbody>`;
  document.querySelectorAll('#wartable th').forEach(th => {
    th.onclick = () => {
      const k = th.dataset.k;
      if (warSort.key === k) warSort.dir *= -1;
      else warSort = {key: k, dir: k === 'name' || k === 'start' ? 1 : -1};
      drawWarTable();
    };
  });
  document.querySelectorAll('#wartable tbody tr').forEach(tr => {
    tr.onclick = () => {
      const idx = +tr.dataset.war;
      warPick = warPick === idx ? null : idx;
      drawWarTable();
      document.getElementById('warback').focus();
    };
  });
  document.getElementById('warcount').textContent =
    `${rows.length} of ${WARS.length} wars`;
  drawWarDetail();
}

let warBattleSort = {key: 'date', dir: 1};
// Which battles currently have their detail row open. Battle objects are
// parsed once and only ever reordered, never recreated, so the object itself
// is a stable key across re-sorts -- no need to invent a string id for it.
let expandedBattles = new Set();

function warFlag(tag) {
  const src = (DATA.flags || {})[tag + '|'];
  return src ? `<img class="tagflag" src="${src}" alt="">` : '';
}
function warTag(tag) {
  if (!tag) return '<span class="rk">&mdash;</span>';
  return `${warFlag(tag)}<b style="color:${colourFor(tag)}">${tag}</b>`;
}

// A war's own attackers/defenders lists are flat tags with no join info; the
// *_parties lists (when present) carry a join date and an original/later
// split per tag. Older data that predates that field falls back to treating
// everyone as original, so the layout still works either way.
function belParties(w, side) {
  const parties = w[side + '_parties'];
  if (parties) return parties;
  return (w[side + 's'] || []).map(tag => ({tag, joined: '', original: true}));
}
/* =============== THE WAR INFOBOX =============== */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
// `1845.12.23` the way a reader writes it: 23 December 1845.
function longDate(d) {
  const p = String(d || '').split('.');
  const month = MONTHS[+p[1] - 1];
  return p.length === 3 && month ? `${+p[2]} ${month} ${p[0]}` : (d || '—');
}
// How long from one date to another: years and months, and the days as well
// for anything under a year. The game's calendar has no leap years.
const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
function warSpan(from, to) {
  const a = String(from || '').split('.').map(Number);
  const b = String(to || '').split('.').map(Number);
  if (a.length !== 3 || b.length !== 3 || a.concat(b).some(isNaN)) return '';
  let y = b[0] - a[0], m = b[1] - a[1], d = b[2] - a[2];
  if (d < 0) { m -= 1; d += MONTH_DAYS[(b[1] + 10) % 12]; }
  if (m < 0) { y -= 1; m += 12; }
  if (y < 0) return '';
  const unit = (n, what) => `${n} ${what}${n === 1 ? '' : 's'}`;
  if (!y && !m) return unit(d, 'day');
  return [y ? unit(y, 'year') : '', m ? unit(m, 'month') : '',
          !y && d ? unit(d, 'day') : ''].filter(Boolean).join(', ');
}
const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th'
  : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');
// The same year axis as DATA.years, which Python's `year_fraction` fills.
const dateYear = d => {
  const p = String(d).split('.');
  return (+p[0]) + (+p[1] - 1) / 12 + (+p[2] - 1) / 365;
};

/* Which side of the war a nation fought on: 1 attacking, -1 defending, 0 when
   the two lists cannot say -- the same tag on both, as in a civil war. The two
   nations in a battle are on opposite sides, so an unclear one takes the
   opposite of its opponent. That is wars.py's `_side_losses` rule, which is
   what makes the casualties here add up to the coalition totals it ships. */
function warSides(w) {
  const att = new Set(w.attackers), dfd = new Set(w.defenders);
  const which = t => {
    const a = att.has(t), d = dfd.has(t);
    return a && !d ? 1 : d && !a ? -1 : 0;
  };
  const battle = b => {
    let x = which(b.a[0]), y = which(b.d[0]);
    if (!x && y) x = -y;
    if (!y && x) y = -x;
    return [x, y];
  };
  return {which, battle};
}

/* The save that shows a war going in: the last one taken before it began, if
   that was within a year, or else the first one taken while it was fought. A
   war of eight days between two monthly saves has none of its own, and the
   save three weeks before it says who was a great power as well as any would.
   None for a war over before the first save: then nothing here can say who
   was great at the time, or what anybody had. */
function warOpening(w) {
  if (!w.start || !DATA.dates.length) return null;
  const from = dateYear(w.start);
  const to = w.active ? Infinity : dateYear(w.end || w.start);
  let before = -1;
  DATA.years.forEach((y, i) => { if (y <= from) before = i; });
  if (before >= 0 && from - DATA.years[before] <= 1)
    return {date: DATA.dates[before], what: 'the last save before the war'};
  const during = DATA.years.findIndex(y => y > from && y <= to);
  return during < 0 ? null
    : {date: DATA.dates[during], what: 'the first save taken during the war'};
}
// {tag: rank} for the great powers at one save.
function warGreatPowers(opening) {
  const rank = {};
  if (!opening) return rank;
  ((DATA.greatPowers || {})[opening.date] || []).forEach((e, i) => {
    rank[Array.isArray(e) ? e[0] : e] = i + 1;
  });
  return rank;
}

/* A flag at one of three sizes: '' in a list, 'big' for a principal
   belligerent, 'hero' across the top. */
function ibFlag(tag, size) {
  const src = (DATA.flags || {})[tag + '|'];
  const cls = 'ibflag' + (size ? ' ' + size : '');
  if (src) return `<img class="${cls}" src="${src}" alt="">`;
  return `<span class="${cls} blank" style="background-color:${colourFor(tag)}">`
    + `${size ? tag : ''}</span>`;
}
const ibName = t => t
  ? `${warFlag(t)}<b style="color:${colourFor(t)}">${nameOf(t)}</b>`
  : '<span class="rk">unknown</span>';

/* One side's nations, the principal ones first: its war leader, then any
   great power, in rank order. A side the data marks no leader for -- a report
   built before leaders were marked -- lets its first nation stand in, so each
   side has a flag in the picture. */
function ibParties(w, side, gp) {
  const parties = belParties(w, side).map((p, i) => ({...p, i, gp: gp[p.tag] || 0}));
  const weight = p => p.leads ? 0 : p.gp ? 1 : 2;
  parties.sort((a, b) => weight(a) - weight(b)
    || (a.gp || 99) - (b.gp || 99) || a.i - b.i);
  parties.forEach(p => { p.major = !!(p.leads || p.gp); });
  if (parties.length && !parties.some(p => p.major)) parties[0].major = true;
  return parties;
}

function ibNation(p) {
  const ink = colourFor(p.tag);
  const late = !p.original && p.joined;
  if (p.major) {
    /* A nation can be knocked out years before the war ends -- a separate
       peace, or annexation -- and a join date on its own reads as though it
       fought to the finish. */
    const meta = [p.leads ? 'War leader' : '',
                  p.gp ? `Great power, ${ordinal(p.gp)}` : '',
                  late ? `joined ${p.joined}` : '',
                  p.left ? `left ${p.left}` : ''].filter(Boolean).join(' &middot; ');
    return `<div class="ibnat major">${ibFlag(p.tag, 'big')}<div class="ibwho">`
      + `<b style="color:${ink}">${nameOf(p.tag)}</b>`
      + (meta ? `<span class="ibmeta">${meta}</span>` : '') + `</div></div>`;
  }
  const aside = [late ? p.joined : '', p.left ? `left ${p.left}` : '']
    .filter(Boolean).join(' &middot; ');
  return `<div class="ibnat">${ibFlag(p.tag)}<div class="ibwho">`
    + `<b style="color:${ink}">${nameOf(p.tag)}</b></div>`
    + (aside ? `<span class="ibaside">${aside}</span>` : '') + `</div>`;
}
function ibBelligerents(label, parties) {
  const first = parties.filter(p => p.original);
  const later = parties.filter(p => !p.original);
  return `<div class="ibside">${label}</div>` + first.map(ibNation).join('')
    + (later.length ? `<div class="ibgroup">Joined later</div>`
        + later.map(ibNation).join('') : '');
}
// Province centres from the same raster as the deployment map. Army anchors
// cover only garrisoned provinces, so historical battles cannot rely on them.
let warCentres = null;
const warTheatreCache = new Map();
function warBattleSites(w) {
  if (!MAP) return [];
  mapDecoded();
  if (!warCentres) {
    warCentres = new Map();
    for (let y = 0; y < MAP.h; y++) for (let x = 0; x < MAP.w; x++) {
      const p = mapProv[y * MAP.w + x];
      if (!p) continue;
      let c = warCentres.get(p);
      if (!c) { c = [0, 0, 0]; warCentres.set(p, c); }
      c[0] += x; c[1] += y; c[2]++;
    }
    for (const c of warCentres.values()) { c[0] /= c[2]; c[1] /= c[2]; }
  }
  const sites = new Map();
  for (const b of w.battles) {
    const c = warCentres.get(+b.province);
    if (!c) continue;
    let site = sites.get(+b.province);
    if (!site) {
      site = {x:c[0], y:c[1], name:b.name, losses:0, count:0, date:''};
      sites.set(+b.province, site);
    }
    site.losses += Math.max(0, b.a[2]) + Math.max(0, b.d[2]);
    site.count++;
    if (b.date && (!site.date || dateYear(b.date) > dateYear(site.date))) site.date = b.date;
  }
  return [...sites.values()];
}

function warTheatre(w) {
  if (warTheatreCache.has(w)) return warTheatreCache.get(w);
  const sites = warBattleSites(w);
  if (!sites.length) { warTheatreCache.set(w, null); return null; }
  // Score neighbouring battles, not an average of distant fronts that could
  // put the camera in an empty ocean. Wrap longitude across the map seam.
  const dx = (a,b) => ((a-b + MAP.w * 1.5) % MAP.w) - MAP.w / 2;
  const radius = Math.min(MAP.w * .055, MAP.h * .18);
  const hasLosses = sites.some(p => p.losses > 0);
  let centre = sites[0], best = -1;
  for (const p of sites) {
    const score = sites.reduce((n,q) => n + (Math.hypot(dx(q.x,p.x),q.y-p.y) <= radius
      ? (hasLosses ? q.losses : q.count) : 0), 0);
    if (score > best || (score === best && p.losses > centre.losses)) { centre = p; best = score; }
  }
  const nearby = sites.filter(p => Math.hypot(dx(p.x,centre.x),p.y-centre.y) <= radius);
  const xs = nearby.map(p => centre.x + dx(p.x,centre.x)), ys = nearby.map(p => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  let width = Math.max(maxX-minX + radius*.65, (maxY-minY + radius*.65)*2, MAP.w*.075);
  width = Math.min(width, MAP.w, MAP.h*2);
  const height = width/2, x0 = (minX+maxX-width)/2;
  const y0 = Math.max(0, Math.min(MAP.h-height, (minY+maxY-height)/2));
  const target = centre.date || (w.active ? DATA.lastDate : w.end) || w.start;
  const dates = Object.keys(mapOwners);
  const date = dates.reduce((best,d) => !best || Math.abs(dateYear(d)-dateYear(target))
    < Math.abs(dateYear(best)-dateYear(target)) ? d : best, '');
  if (!date) { warTheatreCache.set(w,null); return null; }
  const own = mapOwners[date].own, palette = mapPalette(date);
  const fighters = new Set(w.attackers.concat(w.defenders));
  const canvas = document.createElement('canvas'); canvas.width = 720; canvas.height = 360;
  const ctx = canvas.getContext('2d'), img = ctx.createImageData(720,360);
  const wrap = x => ((Math.floor(x)%MAP.w)+MAP.w)%MAP.w;
  const province = (x,y) => mapProv[Math.min(MAP.h-1,Math.max(0,Math.floor(y)))*MAP.w+wrap(x)];
  const owner = p => own.has(p) ? own.get(p) : -1;
  const isBoundary = (p,q) => mapSea.has(p) !== mapSea.has(q) || owner(p) !== owner(q);
  for (let y=0; y<360; y++) for (let x=0; x<720; x++) {
    const mx=x0+x*width/720, my=y0+y*height/360, p=province(mx,my);
    let rgb = mapSea.has(p) ? [30,47,61] : [112,108,88];
    if (!mapSea.has(p) && fighters.has(MAP.tags[owner(p)])) {
      const colour=palette[p]; rgb=[(colour>>16)&255,(colour>>8)&255,colour&255];
      // mapPalette already applies the shared softer land colours.
    }
    if (isBoundary(p,province(mx+width/720,my)) || isBoundary(p,province(mx,my+height/360))) rgb=[35,32,28];
    const i=(y*720+x)*4; img.data.set([...rgb,255],i);
  }
  ctx.putImageData(img,0,0);
  const visible = sites.map(p=>({...p,px:(centre.x+dx(p.x,centre.x)-x0)*720/width,py:(p.y-y0)*360/height}))
    .filter(p=>p.px>=0 && p.px<=720 && p.py>=0 && p.py<=360).sort((a,b)=>a.losses-b.losses);
  const peak = Math.max(1,...visible.map(p=>p.losses));
  for (const p of visible) {
    ctx.beginPath(); ctx.arc(p.px,p.py,3+9*Math.sqrt(p.losses/peak),0,Math.PI*2);
    ctx.fillStyle='rgba(239,186,77,.75)'; ctx.fill(); ctx.strokeStyle='#2a1714'; ctx.lineWidth=1.5; ctx.stroke();
  }
  // Label only a few major sites; leave overlapping labels out.
  const labels=[]; ctx.font='bold 13px sans-serif';
  for (const p of [...visible].reverse()) {
    if (labels.length>=3) break;
    const label=p.name || 'Battle site', tw=ctx.measureText(label).width;
    const x=Math.max(6,Math.min(714-tw,p.px+12)), y=Math.max(18,Math.min(350,p.py-14));
    if (labels.some(q=>Math.abs(y-q.y)<22 && x<q.x+q.w+8 && x+tw+8>q.x)) continue;
    ctx.fillStyle='rgba(21,29,33,.85)'; ctx.fillRect(x-4,y-14,tw+8,20);
    ctx.fillStyle='#fff0cd'; ctx.fillText(label,x,y); labels.push({x,y,w:tw});
  }
  const n=visible.reduce((n,p)=>n+p.count,0), losses=visible.reduce((n,p)=>n+p.losses,0);
  const outside = dateYear(date)<dateYear(w.start) || (!w.active && w.end && dateYear(date)>dateYear(w.end));
  const caption=`Fighting around ${centre.name || 'the main battle sites'} · ${n} recorded battle${n===1?'':'s'}, ${losses.toLocaleString()} casualties in view. `
    + `Ownership: ${longDate(date)}${outside?' (outside the war’s dates)':''}. `
    + 'Gold circles show battle sites across the war, sized by casualties; borders show ownership, not a reconstructed frontline.';
  // Bound retained canvas memory when browsing a long campaign.
  if (warTheatreCache.size >= 8) warTheatreCache.delete(warTheatreCache.keys().next().value);
  const result={canvas,caption}; warTheatreCache.set(w,result); return result;
}

function drawWarTheatre(w) {
  const slot=document.getElementById('wartheatre');
  if (!slot) return;
  const view=warTheatre(w);
  if (!view) { slot.remove(); return; }
  const canvas=document.createElement('canvas'); canvas.width=720; canvas.height=360;
  canvas.setAttribute('role','img'); canvas.setAttribute('aria-label',view.caption);
  canvas.getContext('2d').drawImage(view.canvas,0,0);
  const caption=document.createElement('figcaption'); caption.textContent=view.caption;
  slot.append(canvas,caption);
}

// Past a handful, the rest of a list folds away behind a count.
function ibList(rows, keep) {
  if (rows.length <= keep + 1) return rows.join('');
  return rows.slice(0, keep).join('')
    + `<details><summary>and ${rows.length - keep} more</summary>`
    + rows.slice(keep).join('') + `</details>`;
}

/* What each side of the war lost, land and sea apart: {land: {1, -1, 0},
   sea: {...}}, 0 for the losses neither side's list could place.

   Only by side, never by nation. A save keeps one loss figure for each side of
   a battle, under the one nation leading it, and the men an ally had in that
   army are counted in it too -- so a nation's "losses" summed from battles are
   really the losses of every army it led. Which side of the war a battle's
   side was on is sound, though: every army in it was on the same side. */
function warSideLosses(w, sides) {
  const lost = {land: {1: 0, '-1': 0, 0: 0}, sea: {1: 0, '-1': 0, 0: 0}};
  for (const b of w.battles) {
    const marks = sides.battle(b), into = lost[b.sea ? 'sea' : 'land'];
    into[marks[0]] += b.a[2];
    into[marks[1]] += b.d[2];
  }
  return lost;
}

// Each side's casualties, as one total: the war table's figure, split in two.
function ibLosses(w, sides) {
  const {land, sea} = warSideLosses(w, sides);
  const column = side => `<div class="ibtotal"><div class="ibwho">Total</div>`
    + `<span class="ibnum">${(land[side] + sea[side]).toLocaleString()}</span></div>`;
  return {cols: [column(-1), column(1)], unplaced: land[0] + sea[0]};
}

/* Brigades and ships at the first save taken during the war. Only the nations
   the report charts have figures; the rest are counted, not guessed at. */
function ibStrength(parties, date) {
  const at = DATA.facts[date] || {};
  const rows = parties.filter(p => at[p.tag])
    .map(p => [p.tag, at[p.tag].brigades || 0, at[p.tag].ships || 0])
    .sort((x, y) => y[1] - x[1] || y[2] - x[2]);
  const pair = (b, s) => `<span class="ibnum pair"><span>${b.toLocaleString()}</span>`
    + `<span>${s.toLocaleString()}</span></span>`;
  const missing = parties.length - rows.length;
  if (!rows.length)
    return `<span class="rk">No figures for ${missing === 1 ? 'this nation' : `these ${missing} nations`}</span>`;
  return `<div class="ibhead"><span>brigades</span><span>ships</span></div>`
    + ibList(rows.map(([t, b, s]) => `<div class="ibnat">${ibFlag(t)}<div class="ibwho">`
        + `<b style="color:${colourFor(t)}">${nameOf(t)}</b></div>${pair(b, s)}</div>`), 8)
    + `<div class="ibtotal"><div class="ibwho">Total</div>`
    + pair(rows.reduce((n, r) => n + r[1], 0), rows.reduce((n, r) => n + r[2], 0))
    + `</div>`
    + (missing ? `<div class="ibmeta" style="margin-top:4px">and ${missing} with no `
        + `figures at that save</div>` : '');
}

/* What the peace did, in as many words as the saves can back. A war goal is
   judged by who held its state either side of the war (see the goals table),
   so a war nothing saw going in, or one still open, is not given a verdict. */
function ibResult(w, sides) {
  if (w.active) {
    const quiet = warQuietSince(w);
    return quiet ? `Unresolved: still open at the last save, with no battle since ${quiet}`
                 : 'Still being fought at the last save';
  }
  if (!w.goals.length) return '<span class="rk">No war goal was recorded</span>';
  const judged = w.goals.filter(g => g.checkable);
  if (!judged.length) {
    const first = DATA.dates.length ? DATA.years[0] : 0;
    return '<span class="rk">Not known: '
      + (w.end && first && dateYear(w.end) <= first
          ? 'the war was over before the first save'
          : 'no war goal could be checked against who held what') + '</span>';
  }
  const lines = [];
  for (const [side, who] of [[-1, 'Defenders'], [1, 'Attackers'], [0, 'Others']]) {
    const mine = judged.filter(g => sides.which(g.actor) === side);
    if (!mine.length) continue;
    const full = mine.filter(g => g.met).length;
    const part = mine.filter(g => g.part).length;
    const cls = full === mine.length ? 'up' : full + part ? '' : 'down';
    const text = mine.length === 1
      ? `${who}' war goal ${full ? 'taken' : part ? 'taken in part' : 'not taken'}`
      : `${who} took ${full + part} of ${mine.length} war goals`
        + (part ? `, ${part} in part` : '');
    lines.push(`<span class="${cls}">${text}</span>`);
  }
  return lines.join('<br>');
}

function warInfobox(w) {
  const sides = warSides(w);
  const opening = warOpening(w);
  const gp = warGreatPowers(opening);
  const dfd = ibParties(w, 'defender', gp);
  const att = ibParties(w, 'attacker', gp);
  const cols = (left, right, named) => {
    const side = label => named ? '' : `<div class="ibside stacked">${label}</div>`;
    return `<div class="ibcols"><div class="ibcol">${side('Defenders')}${left}</div>`
      + `<div class="ibcol">${side('Attackers')}${right}</div></div>`;
  };
  const band = title => `<div class="ibband" data-war-section="${title}">${title}</div>`;

  const facts = [];
  const fact = (label, html) => facts.push(`<dt>${label}</dt><dd>${html}</dd>`);
  const span = warSpan(w.start, w.active ? DATA.lastDate : w.end);
  fact('Date', `${longDate(w.start)} &ndash; ${w.active ? 'ongoing' : longDate(w.end)}`
    + (span ? `<br><span class="rk">${span}${w.active ? ' by the last save' : ''}</span>` : ''));
  fact('Result', ibResult(w, sides));
  if (w.transfers.length) {
    fact('Territorial changes', `<ul>${w.transfers.map(t =>
      `<li>${ibName(t[2])} ceded ${t[1] || t[0] || 'a state'} to ${ibName(t[3])}`
      + (t[4] < t[5] ? ` <span class="rk">(${t[4]} of ${t[5]} provinces)</span>`
         : !(t[1] || t[0]) ? ` <span class="rk">(${t[4]} province${t[4] === 1 ? '' : 's'})</span>`
         : '')
      + `</li>`).join('')}</ul>`);
  }
  if (w.battles.length) {
    const naval = w.battles.filter(b => b.sea).length;
    const land = w.battles.length - naval;
    const won = {1: 0, '-1': 0};
    for (const b of w.battles) {
      const side = sides.battle(b)[b.won ? 0 : 1];
      if (side) won[side]++;
    }
    fact('Battles', [land ? `${land} on land` : '', naval ? `${naval} at sea` : '']
      .filter(Boolean).join(', ')
      + `<br><span class="rk">defenders won ${won[-1]}, attackers ${won[1]}</span>`);
  } else {
    fact('Battles', '<span class="rk">None recorded</span>');
  }

  const notes = [];
  let body = band('Belligerents')
    + cols(ibBelligerents('Defenders', dfd), ibBelligerents('Attackers', att), true);
  if (opening && DATA.facts[opening.date]) {
    body += band('Strength')
      + `<div class="ibcaption">At ${opening.date}, ${opening.what}</div>`
      + cols(ibStrength(dfd, opening.date), ibStrength(att, opening.date));
  }
  if (w.battles.length) {
    const lost = ibLosses(w, sides);
    body += band('Casualties and losses') + cols(lost.cols[0], lost.cols[1])
      + `<div class="ibcaption" style="padding:10px 14px;border-top:1px solid var(--grid)">Total casualties: <b>${w.battles.reduce((n, b) => n + b.a[2] + b.d[2], 0).toLocaleString()}</b></div>`;
    notes.push('Casualties are each side&rsquo;s losses in its battles, men and ships '
      + 'together. They are not split by nation: a save records one loss figure for '
      + 'each side of a battle, under the nation leading it, whoever&rsquo;s troops died.');
    if (lost.unplaced)
      notes.push(`${lost.unplaced.toLocaleString()} more were lost by armies `
        + `neither side&rsquo;s list could place.`);
  }
  if (!w.battles.length) body += band('Casualties and losses') + '<div class="ibcaption" style="padding-bottom:10px">No battle casualties recorded.</div>';
  if (Object.keys(DATA.greatPowers || {}).length) {
    notes.push(opening
      ? `Great-power ranks as of ${opening.date}, ${opening.what}.`
      : 'No save shows this war going in, so great powers are not marked: '
        + 'the saves cannot say who was one then.');
  }

  return `<div class="ib"><div class="ibtitle"><span>${w.name}</span><button type="button" class="war-export" title="Export war summary as PNG" aria-label="Export war summary as PNG"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M14 3H4v18h16V11M15 3h6v6M21 3l-9 9M4 17l5-5 5 5 3-3 3 3"/><circle cx="8" cy="7" r="1"/></svg></button><span class="war-export-status" role="status"></span></div>`
    + (MAP && w.battles.length ? '<figure id="wartheatre" class="wartheatre"></figure>' : '')
    + `<dl class="ibfacts">${facts.join('')}</dl>`
    + body
    + (notes.length ? `<div class="ibnote">${notes.map(n => `<p>${n}</p>`).join('')}</div>` : '')
    + `</div>`;
}

// A side's unit string is "kind:n;kind:n", largest first. Parsed once here for
// both the (unused in the row) army total and the expanded composition list.
function sideUnits(s) {
  const units = s[3] ? s[3].split(';').map(p => {
    const [kind, n] = p.split(':');
    return [gameName(kind), +n];
  }) : [];
  return {units, army: units.reduce((sum, [, n]) => sum + n, 0)};
}

function battleDetail(b) {
  const side = (label, s) => {
    const {units, army} = sideUnits(s);
    return `<div class="battleside"><div class="sidehead">${label}</div>`
      + `<div class="side">${warTag(s[0])}`
      + `<span class="who">${s[1] || '—'}</span>`
      + units.map(([kind, n]) =>
          `<span class="unit">${kind} ${n.toLocaleString()}</span>`).join('')
      + `</div>`
      + `<div class="sidetotal">army <b>${army.toLocaleString()}</b>`
      +   ` &nbsp; lost <b>${s[2].toLocaleString()}</b></div>`
      + `</div>`;
  };
  return `<tr class="battledetail"><td colspan="8"><div class="battlesides">`
    + side('Defender', b.d) + side('Attacker', b.a)
    + `</div></td></tr>`;
}

function warBattleTable(list, title, kind) {
  if (!list.length) return '';
  const get = {
    date: b => b.date || '9999',
    name: b => b.name.toLowerCase(),
    alost: b => b.a[2],
    dlost: b => b.d[2],
    total: b => b.a[2] + b.d[2],
  }[warBattleSort.key] || (b => b.date || '9999');
  const rows = list.slice().sort((x, y) => {
    const a = get(x), b = get(y);
    return (a < b ? -1 : a > b ? 1 : 0) * warBattleSort.dir;
  });
  // Defender before Attacker, matching how a reader asks "who held, who came
  // for it" -- the Winner column already carries whichever side actually won.
  const head = [['date', 'Date'], ['name', 'Battle'], ['', 'Winner'],
                ['', 'Defender'], ['dlost', 'Lost'],
                ['', 'Attacker'], ['alost', 'Lost'], ['total', 'Total losses']];
  // Column widths sum to 100%. Fixed rather than content-driven -- see
  // .battletable -- so this table can never push the page wider than the
  // screen no matter how long a battle or nation name gets.
  const widths = [12, 20, 9, 11, 10, 11, 10, 17];
  const numCol = [true, false, false, false, true, false, true, true];
  return `<div class="techsub" style="margin-top:12px">${title} `
    + `<span class="rk">${list.length}</span></div>`
    + `<div class="tablewrap fit"><table class="mini battletable">`
    + `<colgroup>${widths.map(w => `<col style="width:${w}%">`).join('')}</colgroup>`
    + `<thead><tr>`
    + head.map(([k, label], i) => {
        const cls = numCol[i] ? ' class="num"' : '';
        return k
          ? `<th data-bk="${k}"${cls}${warBattleSort.key === k ? ' aria-sort="' +
              (warBattleSort.dir < 0 ? 'descending' : 'ascending') + '"' : ''}>${label}</th>`
          : `<th${cls}>${label}</th>`;
      }).join('')
    + `</tr></thead><tbody>`
    + rows.map((b, i) => {
        const win = b.won ? b.a[0] : b.d[0];
        const open = expandedBattles.has(b);
        return `<tr class="battlerow${open ? ' on' : ''}" `
            + `data-bkind="${kind}" data-bi="${list.indexOf(b)}">`
          + `<td class="num">${b.date || '<span class="rk">unknown</span>'}</td>`
          + `<td>${b.name}</td><td>${warTag(win)}</td>`
          + `<td>${warTag(b.d[0])}</td>`
          + `<td class="num">${b.d[2].toLocaleString()}</td>`
          + `<td>${warTag(b.a[0])}</td>`
          + `<td class="num">${b.a[2].toLocaleString()}</td>`
          + `<td class="num">${(b.a[2] + b.d[2]).toLocaleString()}</td></tr>`
          + (open ? battleDetail(b) : '');
      }).join('')
    + `</tbody></table></div>`;
}

// Render a styled copy of the infobox, rather than redraw its flags and text.
async function warSummaryPNG(source) {
  await document.fonts.ready;
  const clone = source.cloneNode(true);
  const originals = [source, ...source.querySelectorAll('*')];
  const copies = [clone, ...clone.querySelectorAll('*')];
  originals.forEach((node, index) => {
    const style = getComputedStyle(node);
    copies[index].style.cssText = Array.from(style).map(key => key + ':' + style.getPropertyValue(key) + ';').join('');
  });
  let section = '';
  for (const child of [...clone.children]) {
    if (child.classList.contains('ibband')) section = child.dataset.warSection;
    if (child.classList.contains('ibtitle') || child.classList.contains('ibnote')) continue;
    if (child.classList.contains('ibfacts')) {
      [...child.children].slice(2).forEach(node => node.remove());
      child.style.height = 'auto';
      continue;
    }
    if (section === 'Belligerents' || section === 'Casualties and losses') continue;
    child.remove();
  }
  clone.querySelectorAll('.war-export, .war-export-status').forEach(node => node.remove());
  clone.querySelectorAll('details').forEach(node => {
    node.open = true; node.style.height = 'auto';
    node.querySelector('summary')?.remove();
  });
  // Computed pixel heights describe the original collapsed layout. Let the
  // selected sections reflow at the same width after removing other content.
  clone.querySelectorAll('div,dl,dd').forEach(node => {
    node.style.height = 'auto';
    if (node.style.display === 'grid') node.style.gridTemplateRows = 'none';
  });
  const width = Math.ceil(source.getBoundingClientRect().width);
  clone.style.width = width + 'px'; clone.style.maxWidth = 'none'; clone.style.height = 'auto';
  clone.style.margin = '0';
  const stage = document.createElement('div');
  stage.style.cssText = 'position:fixed;left:-100000px;top:0;pointer-events:none;';
  stage.appendChild(clone); document.body.appendChild(stage);
  try {
    await Promise.all([...clone.querySelectorAll('img')].map(img => img.decode()));
    const height = Math.ceil(clone.getBoundingClientRect().height);
    // SVG images have their own font context. Embed the report's webfonts so
    // the exported text keeps the same metrics and appearance.
    const fontRules = [];
    const loadedFonts = [...document.fonts].filter(font => font.status === 'loaded');
    for (const sheet of loadedFonts.length ? document.styleSheets : []) {
      let css;
      try { css = [...sheet.cssRules].map(rule => rule.cssText).join('\n'); }
      catch { if (!sheet.href) continue; const response = await fetch(sheet.href); if (!response.ok) throw new Error('Could not load report fonts.'); css = await response.text(); }
      for (const rule of css.match(/@font-face\s*\{[^}]*\}/g) || []) {
        if (!loadedFonts.some(font => rule.includes(font.family.replace(/[\"']/g, '')))) continue;
        let embedded = rule;
        for (const match of rule.matchAll(/url\(["']?([^"')]+)["']?\)/g)) {
          const response = await fetch(new URL(match[1], sheet.href || location.href));
          if (!response.ok) throw new Error('Could not load report fonts.');
          const data = await new Promise((resolve, reject) => {
            const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject;
            response.blob().then(blob => reader.readAsDataURL(blob), reject);
          });
          embedded = embedded.replace(match[0], 'url("' + data + '")');
        }
        fontRules.push(embedded);
      }
    }
    const root = document.createElementNS('http://www.w3.org/1999/xhtml', 'div');
    const sheet = source.closest('.sheet');
    const sheetStyle = getComputedStyle(sheet);
    const sheetBox = sheet.getBoundingClientRect(), sourceBox = source.getBoundingClientRect();
    root.style.cssText = 'width:' + width + 'px;background-color:' + getComputedStyle(document.body).backgroundColor + ';';
    root.style.backgroundImage = sheetStyle.backgroundImage;
    root.style.backgroundSize = sheetBox.width + 'px ' + sheetBox.height + 'px';
    root.style.backgroundPosition = (sheetBox.left - sourceBox.left) + 'px ' + (sheetBox.top - sourceBox.top) + 'px';
    const style = document.createElement('style'); style.textContent = fontRules.join('\n'); root.append(style, clone);
    const xml = new XMLSerializer().serializeToString(root);
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '"><foreignObject width="100%" height="100%">' + xml + '</foreignObject></svg>';
    const img = new Image();
    await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = () => reject(new Error('Could not render the war summary.')); img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg); });
    const canvas = document.createElement('canvas'); canvas.width = width * 2; canvas.height = height * 2;
    const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Could not encode the war summary.')), 'image/png'));
  } finally { stage.remove(); }
}

function attachWarExport(box, war) {
  const button = box.querySelector('.war-export');
  button.onclick = async () => {
    const status = box.querySelector('.war-export-status');
    button.disabled = true; status.textContent = 'Preparing image…';
    try {
      const blob = await warSummaryPNG(box.querySelector('.ib'));
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url;
      link.download = (war.name.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'war') + '-summary.png';
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      status.textContent = 'PNG ready.';
    } catch (error) { status.textContent = 'Export failed: ' + error.message; }
    finally { button.disabled = false; }
  };
}

