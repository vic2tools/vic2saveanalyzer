/* =============== WORLD: GREAT POWERS =============== */
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
    const flag = nationFlag(tag, flagKey); flag.className = 'gpflag';
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

registerTab('tab-nations', {init() { if (MAP) mapRender(); drawGreatPowers(); }});
exportNotes.mapcanvas = () => {
  mapStopPlay();
  return {subtitle: 'Current map view · ' + document.getElementById('mapzoom').textContent
    + ' · Occupation ' + (document.getElementById('mapocc').getAttribute('aria-pressed') === 'true' ? 'on' : 'off')
    + ' · Province borders ' + (document.getElementById('mapborders').getAttribute('aria-pressed') === 'true' ? 'on' : 'off')};
};
