/* =============== GREAT POWERS =============== */
function drawGreatPowers() {
  const grid = document.getElementById('gpgrid');
  const date = document.getElementById('mapsave').value || DATA.lastDate;
  const list = DATA.greatPowers[date] || [];
  document.getElementById('gpstrip').hidden = !list.length;
  grid.replaceChildren();
  list.forEach((entry, i) => {
    const [tag, flagKey] = entry;
    const card = document.createElement('div'); card.className = 'gpcard';
    card.setAttribute('role', 'listitem');
    card.style.setProperty('--nation-colour', (DATA.map?.colours || {})[tag] || colourFor(tag));
    const identity = document.createElement('div'); identity.className = 'gpidentity';
    const rank = document.createElement('span'); rank.className = 'gprank'; rank.textContent = i + 1;
    let flag = nationFlag(tag); flag.className = 'gpflag';
    if (DATA.flags[flagKey]) {
      flag = document.createElement('img'); flag.src = DATA.flags[flagKey]; flag.alt = ''; flag.className = 'gpflag';
    }
    const name = document.createElement('button'); name.className = 'gpname'; name.textContent = nameOf(tag);
    name.title = 'View trends for ' + nameOf(tag);
    name.onclick = () => {
      nationsPicker.set([tag]); selectTab('tab-compare'); showCompareView('trends');
      document.getElementById('metric-category').focus();
    };
    identity.append(rank, flag, name);
    const stats = document.createElement('div'); stats.className = 'gpstats';
    const f = (DATA.facts[date] || {})[tag] || {};
    for (const [label, value] of [['Prestige', f.prestige == null ? null : Math.round(f.prestige)],
      ['Factory levels', f.factory_levels], ['Brigades', f.brigades], ['Ships', f.ships]]) {
      const stat = document.createElement('span'); stat.textContent = label;
      const amount = document.createElement('b'); amount.textContent = value == null ? '—' : value.toLocaleString();
      stat.append(amount); stats.append(stat);
    }
    card.append(identity, stats); grid.append(card);
  });
}


/* A long <select> of nations is unusable without one. Filters the options in
   place and jumps to the first match, so the select stays the source of truth
   and every existing onchange keeps working. */
function searchSelect(select, placeholder) {
  if (!select) return;
  const box = document.createElement('input');
  box.type = 'search';
  box.className = 'selsearch';
  box.placeholder = placeholder || 'search';
  box.setAttribute('aria-label', placeholder || 'search');
  select.parentNode.insertBefore(box, select);
  box.oninput = () => {
    const q = box.value.trim().toLowerCase();
    let first = null;
    for (const o of select.options) {
      // `off` is set by limitSelect for nations this save does not have; the
      // search must not bring them back.
      const hit = o.dataset.off !== '1'
        && (!q || o.textContent.toLowerCase().includes(q));
      o.hidden = !hit;
      if (hit && !first) first = o;
    }
    if (q && first && select.value !== first.value) {
      select.value = first.value;
      if (select.onchange) select.onchange();
    }
  };
}

