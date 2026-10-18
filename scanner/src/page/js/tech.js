/* =============== TECHNOLOGY =============== */
const TECH = DATA.technology && DATA.technology.tree ? DATA.technology : null;
let techCat = null;
let techPick = null;          // {category, area, index} of the opened tech

function techResearched(tag, date) {
  const have = new Set();
  const idx = ((DATA.techsBy[tag] || {})[date]) || [];
  for (const i of idx) have.add(DATA.techOrder[i]);
  return have;
}

// A tech matches a search if the term turns up in its own name or effects,
// or in the name or effects of anything it unlocks -- a mobilization search
// should surface both a tech that directly grants it and one that only does
// so through an invention gated behind it.
function techMatches(t, q) {
  const hit = (label, value) => label.toLowerCase().includes(q)
    || String(value).toLowerCase().includes(q);
  if (t.name.toLowerCase().includes(q)) return true;
  if (t.effects.some(([l, v]) => hit(l, v))) return true;
  return t.inventions.some(([, name, effs]) =>
    name.toLowerCase().includes(q) || effs.some(([l, v]) => hit(l, v)));
}
function techCatMatchCount(cat, q) {
  let n = 0;
  for (const col of TECH.tree[cat])
    for (const t of col.techs)
      if (techMatches(t, q)) n++;
  return n;
}

function drawTechTree() {
  if (!TECH) return;
  const tag = document.getElementById('techtag').value;
  const date = document.getElementById('techsave').value;
  document.getElementById('techwho').textContent =
    (nameOf(tag) === tag ? tag : nameOf(tag) + ' · ' + tag) + ' at ' + date;
  const have = techResearched(tag, date);
  const query = (document.getElementById('techfind').value || '').trim().toLowerCase();

  // category buttons, with a researched count each, plus a match count badge
  // when a search is active -- so a hit sitting in a category the reader
  // isn't currently looking at is visible without jumping them there.
  const bar = document.getElementById('techcats');
  bar.innerHTML = '';
  const cats = Object.keys(TECH.tree);
  if (!techCat || !TECH.tree[techCat]) techCat = cats[0];
  for (const cat of cats) {
    let total = 0, done = 0;
    for (const col of TECH.tree[cat])
      for (const t of col.techs) { total++; if (have.has(t.key)) done++; }
    const b = document.createElement('button');
    b.textContent = (TECH.categories[cat] || cat) + '  ' + done + '/' + total;
    if (query) {
      const n = techCatMatchCount(cat, query);
      if (n) {
        const badge = document.createElement('span');
        badge.className = 'techcatbadge';
        badge.textContent = n;
        badge.title = n + ' match' + (n === 1 ? '' : 'es') + ' in ' + (TECH.categories[cat] || cat);
        b.appendChild(badge);
      }
    }
    b.setAttribute('aria-pressed', cat === techCat);
    b.onclick = () => { techCat = cat; techPick = null; drawTechTree(); };
    bar.appendChild(b);
  }

  const grid = document.getElementById('techgrid');
  grid.innerHTML = '';
  grid.style.gridTemplateColumns =
    'repeat(' + TECH.tree[techCat].length + ',minmax(0,1fr))';
  TECH.tree[techCat].forEach((col, ci) => {
    const wrap = document.createElement('div');
    wrap.className = 'techcol';
    const head = document.createElement('div');
    head.className = 'techhead';
    head.textContent = col.label;
    wrap.appendChild(head);
    col.techs.forEach((t, ti) => {
      const box = document.createElement('button');
      const done = have.has(t.key);
      box.className = 'techbox' + (done ? ' done' : '');
      const open = techPick && techPick.category === techCat
                && techPick.area === ci && techPick.index === ti;
      if (open) box.classList.add('open');
      if (query) box.classList.add(techMatches(t, query) ? 'techmatch' : 'techdim');
      box.textContent = t.name;
      box.title = t.name + ' · ' + t.year + ' · ' + t.cost.toLocaleString() + ' research points';
      box.onclick = () => {
        techPick = open ? null : {category: techCat, area: ci, index: ti};
        drawTechTree();
      };
      wrap.appendChild(box);
    });
    grid.appendChild(wrap);
  });

  const panel = document.getElementById('techdetail');
  if (!techPick) {
    panel.innerHTML = '<span class="rk">Click a technology for its effects and '
                    + 'the inventions it unlocks.</span>';
    return;
  }
  const t = TECH.tree[techPick.category][techPick.area].techs[techPick.index];
  const done = have.has(t.key);
  const effects = t.effects.length
    ? t.effects.map(([label, value]) =>
        `<li><span class="rk">${label}</span> <b>${value}</b></li>`).join('')
    : '<li class="rk">No direct modifiers.</li>';
  const invs = t.inventions.length
    ? t.inventions.map(([, name, effs]) => `<li>${name}`
        + (effs.length
            ? `<div class="techinv"><span class="rk">${effs.map(([l, v]) =>
                `${l} <b>${v}</b>`).join(' &middot; ')}</span></div>`
            : '')
        + `</li>`).join('')
    : '<li class="rk">Nothing gated behind it.</li>';
  panel.innerHTML =
    `<div class="techtitle">${t.name}`
    + `<span class="rk"> ${t.year} · ${t.cost.toLocaleString()} rp · `
    + `${done ? 'researched' : 'not researched'}</span></div>`
    + `<div class="techcols2">`
    +   `<div><div class="techsub">Effects</div><ul>${effects}</ul></div>`
    +   `<div><div class="techsub">Inventions it makes available</div>`
    +     `<ul>${invs}</ul>`
    +     `<p class="note">These are the inventions the technology makes`
    +     ` available, not the ones this nation has rolled.</p></div>`
    + `</div>`;
}

if (TECH) {
  const tagSel = document.getElementById('techtag');
  fillSelect(tagSel, DATA.tags, t => nameOf(t) === t ? t : `${t} · ${nameOf(t)}`);
  tagSel.onchange = () => { techPick = null; drawTechTree(); };
  const saveSel = document.getElementById('techsave');
  fillSelect(saveSel, DATA.dates);
  saveSel.value = DATA.lastDate;
  const techLimit = () => limitSelect(tagSel, tagsAt(saveSel.value),
                                      biggestAt(saveSel.value, 'total_pop', 1)[0]);
  tagSel.value = largestBy('total_pop');
  techLimit();
  saveSel.onchange = () => { techPick = null; techLimit(); drawTechTree(); };
  document.getElementById('techfind').oninput = () => drawTechTree();
}

registerTab('tab-tech', {available: () => !!TECH, init() {
  drawTechTree();
  searchSelect(document.getElementById('techtag'), 'search nations');
}});
