let militaryCountry = null;
const militaryLedgers = {};
const strengthValue = value => value == null ? '—'
  : typeof value === 'number' ? value.toLocaleString() : value;

function strengthDetails(sections, note) {
  const grid = document.createElement('div');
  grid.className = 'return-grid';
  sections.forEach(([title, entries]) => {
    const section = document.createElement('div');
    const heading = document.createElement('h3');
    const list = document.createElement('dl');
    heading.textContent = title;
    const shown = entries.length ? entries : [['No units recorded', '—']];
    shown.forEach(([label, value]) => {
      const line = document.createElement('div');
      const term = document.createElement('dt');
      const definition = document.createElement('dd');
      term.textContent = label;
      definition.textContent = strengthValue(value);
      line.append(term, definition);
      list.appendChild(line);
    });
    section.append(heading, list);
    grid.appendChild(section);
  });
  const help = document.createElement('p');
  help.className = 'note';
  help.textContent = note;
  return [grid, help];
}

// Use the report's embedded flags; a nation-colour swatch is the honest fallback.
// A nation's flag as the payload carries it: the one `key` names (the great
// powers' cards name the flag of their government), else its usual one,
// else ''.
function flagSrc(tag, key) {
  return (key && DATA.flags[key]) || DATA.flags[tag + '|'] || '';
}

function nationFlag(tag, key) {
  const src = flagSrc(tag, key);
  const flag = document.createElement(src ? 'img' : 'span');
  flag.className = 'military-flag' + (src ? '' : ' blank');
  if (src) { flag.src = src; flag.alt = ''; }
  else { flag.style.backgroundColor = colourFor(tag); flag.setAttribute('aria-hidden', 'true'); }
  return flag;
}

function nationIdentity(tag) {
  const identity = document.createElement('span'); identity.className = 'nation-identity';
  const name = document.createElement('span'); name.textContent = nameOf(tag);
  name.style.color = colourFor(tag);
  identity.append(nationFlag(tag),name);
  return identity;
}

function compareMilitaryNations(tag, rival, branch) {
  milSave.value = fleetSave.value;
  pickerA.set([tag]); pickerB.set([rival]);
  pickerA.refresh(); pickerB.refresh();
  setHeadBranch(branch);
  selectTab('tab-compare'); showCompareView('head');
  document.getElementById('compare-head-button').focus();
}

// Keep this a transparent shortlist, not an invented battle or diplomacy score.
// Candidates come from all nations present in this save, independent of filters.
function militaryRivalRows(tag, branch, metric, date) {
  const facts = DATA.facts[date] || {};
  const value = (t, key) => {
    const f = facts[t] || {};
    if (key === 'size') return branch === 'army' ? f.brigades || 0 : shipCount(t, date, '__all') || 0;
    if (key === 'tech') return f[branch + '_techs'] ?? null;
    if (key === 'power') {
      const stats = navalStats(t,date), counts = (DATA.ships[t] || {})[date] || {};
      return stats && Object.keys(counts).every(type => stats[type]) ? fleetPower([t],date,false,true) : null;
    }
    return f.mobilization_brigades ?? null;
  };
  const own = value(tag, 'size');
  const rows = Object.keys(facts).filter(t => t !== tag && value(t, 'size') > 0)
    .map(t => ({tag:t, size:value(t, 'size'), tech:value(t, 'tech'), mob:value(t, 'mob'), power:metric === 'power' ? value(t,'power') : null}));
  const key = metric === 'closest' ? 'size' : metric;
  return rows.filter(r => r[key] != null).sort((a,b) => {
    const order = metric === 'closest' ? Math.abs(a.size-own) - Math.abs(b.size-own) : b[key]-a[key];
    return order || b.size-a.size || a.tag.localeCompare(b.tag);
  }).slice(0,3);
}

function militaryRivals(tag, branch, date) {
  const box = document.createElement('div'); box.className = 'ib military-rivals';
  const title = document.createElement('div'); title.className = 'ibtitle';
  title.textContent = 'Who challenges ' + nameOf(tag) + '’s might?';
  const controls = document.createElement('div'); controls.className = 'controls';
  const label = document.createElement('label'); label.textContent = 'Scout rivals by ';
  const select = document.createElement('select'); select.setAttribute('aria-label', 'Rank potential rivals');
  [['closest','Closest in force size'], ['size',branch === 'army' ? 'Largest armies' : 'Largest navies'],
   ['tech',branch === 'army' ? 'Highest army technology' : 'Highest naval technology'],
   ...(branch === 'army' ? [['mob','Largest mobilization ceiling']] : [['power','Highest fleet power']])]
    .forEach(([value,text]) => select.add(new Option(text,value)));
  label.appendChild(select); controls.appendChild(label);
  const wrap = document.createElement('div'); wrap.className = 'tablewrap';
  const table = document.createElement('table'); table.className = 'rival-table'; wrap.appendChild(table);
  const note = document.createElement('p'); note.className = 'note';
  note.textContent = 'Three other nations at this save, ranked by the selected measure. Force size means '
    + (branch === 'army' ? 'fielded brigades' : 'ship count, not fighting power')
    + '. These are global strength comparisons, not geographic neighbours or confirmed enemies. Tech is researched technology count.';
  const draw = () => {
    table.replaceChildren();
    const head = table.createTHead().insertRow();
    ['Nation',branch === 'army' ? 'Brigades' : 'Ships','Tech',branch === 'army' ? 'Mob ceiling' : 'Power · est.',''].forEach(text => {
      const th = document.createElement('th'); th.scope = 'col'; th.textContent = text; head.appendChild(th);
    });
    const body = table.createTBody();
    const rows = militaryRivalRows(tag,branch,select.value,date);
    rows.forEach(r => {
      const tr = body.insertRow();
      const name = document.createElement('span'); name.className = 'rival-name'; name.style.color = colourFor(r.tag);
      name.append(nationFlag(r.tag), document.createTextNode(nameOf(r.tag))); tr.insertCell().appendChild(name);
      const own = (DATA.facts[date] || {})[tag] || {};
      const difference = (cell,value,baseline) => {
        cell.textContent = strengthValue(value);
        if (value == null || baseline == null) return;
        const delta = document.createElement('small'); delta.className = 'military-delta';
        const n = value-baseline;
        delta.textContent = n === 0 ? 'Equal to yours' : strengthValue(Math.abs(n))+(n > 0 ? ' more than yours' : ' fewer than yours');
        cell.appendChild(delta);
      };
      difference(tr.insertCell(),r.size,branch === 'army' ? own.brigades : shipCount(tag,date,'__all'));
      difference(tr.insertCell(),r.tech,own[branch+'_techs']);
      const stats = navalStats(r.tag,date), counts = (DATA.ships[r.tag] || {})[date] || {};
      const known = stats && Object.keys(counts).every(type => stats[type]);
      const measure = tr.insertCell();
      if (branch === 'army') difference(measure,r.mob,own.mobilization_brigades);
      else {
        measure.textContent = known ? fmtPower(fleetPower([r.tag],date,false,true)) : '—';
        const ownStats = navalStats(tag,date), ownCounts = (DATA.ships[tag] || {})[date] || {};
        if (known && ownStats && Object.keys(ownCounts).every(type => ownStats[type])) {
          const delta = document.createElement('small'); delta.className = 'military-delta';
          const n = fleetPower([r.tag],date,false,true)-fleetPower([tag],date,false,true);
          delta.textContent = n === 0 ? 'Equal to yours' : fmtPower(Math.abs(n))+(n > 0 ? ' above yours' : ' below yours');
          measure.appendChild(delta);
        }
      }
      const compare = document.createElement('button'); compare.textContent = 'Compare →';
      compare.setAttribute('aria-label', 'Compare ' + nameOf(tag) + ' with ' + nameOf(r.tag));
      compare.onclick = () => compareMilitaryNations(tag,r.tag,branch);
      tr.insertCell().appendChild(compare);
    });
    if (!rows.length) { const td = body.insertRow().insertCell(); td.colSpan = 5; td.textContent = 'No other nations with recorded forces for this measure.'; }
  };
  select.onchange = draw; draw();
  const help = militaryHelp(note.textContent);
  box.append(title,controls,wrap,help);
  return box;
}

function militaryHelp(text) {
  const help = document.createElement('details'); help.className = 'military-help';
  const summary = document.createElement('summary'); summary.textContent = 'How these figures are calculated';
  const body = document.createElement('p'); body.textContent = text;
  help.append(summary,body); return help;
}

function militaryInventory(row, branch, date) {
  const box = document.createElement('div'); box.className = 'ib military-inventory';
  const title = document.createElement('div'); title.className = 'ibtitle';
  title.textContent = branch === 'army' ? 'Fielded composition' : 'Hull inventory';
  const wrap = document.createElement('div'); wrap.className = 'tablewrap fit';
  const table = document.createElement('table');
  const head = table.createTHead().insertRow();
  const labels = ['Unit type','Count','Share', ...(branch === 'navy' ? ['Current power'] : [])];
  labels.forEach(label => { const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; head.appendChild(th); });
  const counts = branch === 'army' ? (DATA.brigades[row.tag] || {})[date] || {} : row.counts;
  const total = Object.values(counts).reduce((sum,n) => sum+n,0);
  const stats = navalStats(row.tag,date), crew = (DATA.crews[row.tag] || {})[date] || {};
  const body = table.createTBody();
  Object.entries(counts).filter(([,count]) => count > 0).sort((a,b) => b[1]-a[1]).forEach(([type,count]) => {
    const tr = body.insertRow(); tr.insertCell().textContent = gameName(type);
    tr.insertCell().textContent = strengthValue(count);
    tr.insertCell().textContent = total ? (100*count/total).toFixed(1)+'%' : '—';
    if (branch === 'navy') tr.insertCell().textContent = stats?.[type]
      ? fmtPower(shipPower(stats[type],false)*(crew[type] ?? count)) : '—';
  });
  if (!body.rows.length) { const td = body.insertRow().insertCell(); td.colSpan = labels.length; td.textContent = 'No units recorded at this save.'; }
  wrap.appendChild(table); box.append(title,wrap); return box;
}

function militaryDossier(row, branch, sections, note) {
  const date = fleetSave.value, facts = (DATA.facts[date] || {})[row.tag] || {};
  const page = document.createElement('div'); page.className = 'military-country-page';
  const header = document.createElement('div'); header.className = 'military-country-header';
  const back = document.createElement('button'); back.id = 'military-back'; back.textContent = '← All countries';
  back.onclick = () => {
    const tag = militaryCountry; militaryCountry = null; refreshMilitaryCountry();
    const id = overviewBranch === 'army' ? 'miltable' : 'fleettable';
    [...document.querySelectorAll('#'+id+' .strength-row')].find(tr => tr.dataset.tag === tag)?.querySelector('button').focus();
  };
  const name = document.createElement('h2'); name.textContent = row.name; name.style.color = colourFor(row.tag);
  const stamp = document.createElement('span'); stamp.className = 'note'; stamp.textContent = date;
  header.append(back,nationFlag(row.tag),name,stamp);
  const strip = document.createElement('div'); strip.className = 'military-strength-strip';
  const metrics = branch === 'army'
    ? [['Fielded brigades',row.brigades],['Professional',row.regular_brigades],['Mobilized',row.mobilized_brigades],['Unbuilt capacity',row.cap_headroom],['Total potential · est.',row.total_military_potential]]
    : [['Ships',row.total],['Heavy hulls',row.heavy],['Other hulls',row.other],['Current power · est.',row.power == null ? null : fmtPower(row.power)],['Full-strength power',row.design == null ? null : fmtPower(row.design)]];
  metrics.forEach(([label,value]) => {
    const tile = document.createElement('div'), caption = document.createElement('div'), number = document.createElement('div');
    caption.className = 'tb-label'; caption.textContent = label;
    number.className = 'military-stat'; number.textContent = strengthValue(value); tile.append(caption,number); strip.appendChild(tile);
  });
  const main = document.createElement('div'); main.className = 'military-country-body';
  const capacity = document.createElement('div'); capacity.className = 'ib military-capacity';
  const title = document.createElement('div'); title.className = 'ibtitle';
  title.textContent = branch === 'army' ? 'Recruitment & mobilization' : 'Fleet capability';
  const content = document.createElement('div'); content.className = 'military-capacity-content';
  const entries = branch === 'army' ? [[sections[0][0],sections[0][1].filter(([label]) => !['Unbuilt capacity','Total potential (estimate)'].includes(label))],sections[1]]
    : [['Naval establishment',[['Naval technologies',facts.navy_techs ?? null],['Current power',row.power == null ? null : fmtPower(row.power)],['Full-strength power',row.design == null ? null : fmtPower(row.design)]]]];
  content.append(...strengthDetails(entries,''));
  if (branch === 'army') {
    const tech = document.createElement('p'); tech.className = 'note'; tech.textContent = 'Army technologies researched: '+strengthValue(facts.army_techs);
    content.appendChild(tech);
  }
  content.appendChild(militaryHelp(note)); capacity.append(title,content);
  const forces = document.createElement('div'); forces.className = 'military-forces-column';
  forces.append(militaryInventory(row,branch,date),militaryRivals(row.tag,branch,date));
  main.append(forces,capacity);
  const history = document.createElement('section'); history.className = 'military-composition-history';
  const heading = document.createElement('h2');
  heading.textContent = branch === 'army' ? 'Army composition over time' : 'Fleet composition over time';
  const figure = document.createElement('figure');
  const svg = document.createElementNS(SVGNS,'svg'); svg.id = 'military-composition';
  svg.setAttribute('viewBox','0 0 1000 360'); svg.setAttribute('role','img');
  svg.setAttribute('aria-label',nameOf(row.tag)+' · '+heading.textContent);
  figure.appendChild(svg);
  const legend = document.createElement('div'); legend.id = 'military-composition-legend'; legend.className = 'stackwrap';
  const hint = document.createElement('p'); hint.className = 'note';
  hint.textContent = 'Full campaign history for this country. Each bar uses the last save of that year. Hover a band for its '+(branch === 'army' ? 'brigade' : 'ship')+' count.';
  history.append(heading,figure,legend,hint);
  page.append(header,strip,main,history);
  return page;
}

function refreshMilitaryCountry() {
  const host = document.getElementById('military-country');
  const ledger = militaryLedgers[overviewBranch];
  const row = ledger?.rows.find(row => row.tag === militaryCountry);
  if (militaryCountry && !row) militaryCountry = null;
  document.getElementById('military-browse').hidden = !!militaryCountry;
  document.getElementById('miloverview').classList.toggle('country-open',!!militaryCountry);
  host.hidden = !militaryCountry;
  host.replaceChildren();
  if (row) {
    host.appendChild(militaryDossier(row,overviewBranch,ledger.sections(row),ledger.note));
    const army = overviewBranch === 'army';
    stackedBars('military-composition','military-composition-legend',
      (army ? DATA.brigades : DATA.ships)[row.tag] || {},
      army ? DATA.regimentTypes : DATA.shipTypes,
      row.name+' has no '+(army ? 'brigades' : 'ships')+' in these saves.');
  }
}

// Preserve the selected country while rebuilding either branch at a new save.
// Native buttons provide keyboard activation without making every cell focusable.
function renderStrengthLedger(id, cols, rows, state, sections, note) {
  const branch = id === 'miltable' ? 'army' : 'navy';
  militaryLedgers[branch] = {rows, sections, note};
  if (branch === overviewBranch) refreshMilitaryCountry();
  const table = document.getElementById(id);
  const head = table.querySelector('thead tr'), body = table.querySelector('tbody');
  head.replaceChildren(); body.replaceChildren();
  cols.forEach((col, index) => {
    const th = document.createElement('th');
    th.scope = 'col';
    th.setAttribute('aria-sort', ariaSort(state, col.key) || 'none');
    const button = document.createElement('button');
    button.textContent = col.label;
    button.onclick = () => {
      nextSort(state, col.key);
      renderStrengthLedger(id, cols, rows, state, sections, note);
      head.children[index].querySelector('button').focus();
    };
    th.appendChild(button); head.appendChild(th);
  });
  const ordered = sortRows(rows, r => r[state.key], state);
  ordered.forEach(row => {
    const tr = document.createElement('tr');
    tr.className = 'strength-row'; tr.dataset.tag = row.tag;
    cols.forEach((col, index) => {
      const td = document.createElement('td');
      if (index === 0) {
        const button = document.createElement('button');
        button.className = 'nation-toggle';
        const arrow = document.createElement('span'); arrow.setAttribute('aria-hidden','true');
        const name = document.createElement('span'); name.textContent = row.name; name.style.color = colourFor(row.tag);
        button.append(arrow,nationFlag(row.tag),name);
        arrow.textContent = '▸';
        button.setAttribute('aria-controls','military-country');
        tr.onclick = () => {
          militaryCountry = row.tag; refreshMilitaryCountry();
          document.getElementById('military-back').focus();
        };
        td.appendChild(button);
      } else {
        const value = row[col.key];
        td.textContent = col.fmt ? col.fmt(value) : strengthValue(value);
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  if (!rows.length) {
    const tr = document.createElement('tr'), td = document.createElement('td');
    td.colSpan = cols.length;
    td.textContent = 'Select nations to view their strength returns.';
    tr.appendChild(td); body.appendChild(tr);
  }
}

const milState = {key: 'brigades', dir: -1};
function drawMilTable() {
  const date = fleetSave.value;
  const facts = DATA.facts[date] || {};
  const usedReg = DATA.regimentTypes;
  const cols = [
    {key:'name', label:'Nation'},
    {key:'brigades', label:'Fielded brigades'},
    {key:'regular_brigades', label:'Professional'},
    {key:'mobilized_brigades', label:'Mobilized'},
    {key:'cap_headroom', label:'Unbuilt capacity'},
  ];
  const rows = milTags.map(tag => {
    const f = facts[tag] || {};
    const at = (DATA.brigades[tag] || {})[date] || {};
    const soldiers = ((DATA.pops[tag] || {})[date] || {}).soldiers || 0;
    const row = {
      tag, name: nameOf(tag),
      brigades: f.brigades || 0,
      regular_brigades: f.regular_brigades || 0,
      mobilized_brigades: f.mobilized_brigades || 0,
      mobilizing: f.mobilizing || 0,
      mobilization_brigades: f.mobilization_brigades || 0,
      brigade_cap: f.brigade_cap || 0,
      cap_headroom: Math.max(0, (f.brigade_cap || 0) - (f.regular_brigades || 0)),
      total_military_potential: (f.brigade_cap || 0)
                              + (f.mobilization_brigades || 0),
      mobilisation_size: f.mobilisation_size || 0,
      mobilization_pool: f.mobilization_pool || 0,
      ships: f.ships || 0,
      soldiers,
      soldier_pct: f.total_pop ? soldiers / f.total_pop * 100 : 0,
      noncol_soldier_pct: f.total_pop
        ? (f.soldiers_noncolonial || 0) / f.total_pop * 100 : 0,
    };
    usedReg.forEach(rt => row[rt] = at[rt] || 0);
    return row;
  });
  renderStrengthLedger('miltable', cols, rows, milState, row => [
    ['Recruitment potential', [
      ['Professional brigade cap', row.brigade_cap], ['Unbuilt capacity', row.cap_headroom],
      ['Mobilization ceiling (estimate)', row.mobilization_brigades], ['Mobilization queued', row.mobilizing],
      ['Total potential (estimate)', row.total_military_potential]]],
    ['Recruitment base', [['Soldier population', row.soldiers], ['Soldier share', row.soldier_pct.toFixed(2) + '%'],
      ['Non-colonial soldier share', row.noncol_soldier_pct.toFixed(2) + '%'],
      ['Mobilizable population', row.mobilization_pool], ['Mobilization rate', (row.mobilisation_size * 100).toFixed(2) + '%']]],
    ['Fielded composition', usedReg.filter(type => row[type]).map(type => [gameName(type), row[type]])],
  ], 'Potential combines the professional brigade cap and population-based mobilization ceiling. Mobilized brigades are already included in that ceiling; it is not the remaining in-game mobilization count.');
}

/* =============== FLEETS =============== */

const shipSel = document.getElementById('shiptype');
fillSelect(shipSel, ['__all', ...[...DATA.shipTypes].sort(byGameName)],
           s => s === '__all' ? 'All ships' : gameName(s));
shipSel.onchange = drawChart;

const shipCount = (tag, date, type) => {
  const at = (DATA.ships[tag] || {})[date];
  if (!at) return undefined;
  if (type === '__all') return Object.values(at).reduce((a, b) => a + b, 0);
  return at[type];
};

function drawFleetChart() {
  const type = shipSel.value;
  document.getElementById('chart-title').textContent = (type === '__all' ? 'Ships' : gameName(type)) + ' over time';
  document.getElementById('chart').setAttribute('aria-label', document.getElementById('chart-title').textContent + ' by nation');
  const shown = DATA.tags.filter(t => natTags.includes(t));
  const series = shown.map(tag => ({
    name: tag, colour: colourFor(tag),
    pts: DATA.dates.map((d, i) => [years[i], shipCount(tag, d, type)])
                   .filter(p => p[1] !== undefined),
  }));
  /* A hull nobody had before 1882 spent two thirds of this chart as empty
     floor, with the years that actually had ships crushed into the last
     third. The axis starts where the first one was launched and stops where
     the last one was still afloat, so the span the hull existed for is the
     span the chart draws. Doing it off the plotted points rather than off a
     date in the tech tree also covers the other end: a hull every navy has
     since scrapped stops the axis there instead of trailing off flat. */
  const seen = [].concat(...series.map(x => x.pts.map(pt => pt[0])));
  const lo = seen.length ? Math.min(...seen) : xMin;
  const hi = seen.length ? Math.max(...seen) : xMax;
  // No padding either side: the first reading sits on the vertical axis and
  // the last on the right edge, the way it does on every other chart here.
  const a = lo, b = hi;
  const xOf = y => M.l + (b === a ? 0.5 : (y - a) / (b - a)) * (W - M.l - M.r);
  plot(document.getElementById('chart'), {
    series,
    xOf, xTicks: yearTicks(a, b),
    hoverXs: saveHovers.filter(h => h.v >= a && h.v <= b),
    fmt: fmtCount, log: logScale, markers: true,
    readout: document.getElementById('readout'),
    idle: 'Hover the plot to read fleet sizes at a date.',
    emptyMsg: shown.length ? 'No ships of this type in these saves.' : 'Select a nation.',
  });
  const note = document.getElementById('fleetspan');
  const whole = !seen.length || (lo <= years[0] && hi >= years[years.length - 1]);
  note.hidden = whole;
  if (!whole) {
    const at = v => DATA.dates[years.indexOf(v)] || '';
    // Mods name hulls, so the article cannot be baked into the sentence.
    const name = type === '__all' ? 'ship' : gameName(type);
    const one = (/^[aeiou]/i.test(name) ? 'an ' : 'a ') + name;
    note.textContent = lo === hi
      ? `The ${at(lo)} save is the only one with ${one} in it.`
      : `Nobody in these saves held ${one} outside `
        + `${at(lo)} – ${at(hi)}, so the chart stops there.`;
  }
}

const fleetState = {key: 'total', dir: -1};
function drawFleetTable() {
  const date = fleetSave.value;
  const cols = [{key:'name', label:'Nation'}, {key:'total', label:'Ships'},
    {key:'heavy', label:'Heavy hulls'}, {key:'other', label:'Other hulls'},
    {key:'power', label:'Current power · est.', fmt: v => v == null ? '—' : fmtPower(v)}];
  const rows = milTags.map(tag => {
    const counts = (DATA.ships[tag] || {})[date] || {};
    const stats = navalStats(tag, date);
    const known = stats && Object.keys(counts).every(type => stats[type]);
    const total = shipCount(tag, date, '__all') || 0;
    const heavy = known ? Object.entries(counts).reduce((n, [type, count]) => n + (stats[type].heavy ? count : 0), 0) : null;
    return {tag, name:nameOf(tag), total, heavy, other:known ? total - heavy : null,
      power:known ? fleetPower([tag], date, false, true) : null,
      design:known ? fleetPower([tag], date, false, false) : null, counts};
  });
  renderStrengthLedger('fleettable', cols, rows, fleetState, row => [
    ['Fleet estimates', [['Current power', row.power == null ? 'Unavailable' : fmtPower(row.power)],
      ['Full-strength power', row.design == null ? 'Unavailable' : fmtPower(row.design)]]],
    ['Hull inventory', Object.entries(row.counts).filter(([,n]) => n).map(([type,n]) => [gameName(type),n])],
  ], 'Power estimates use hull and gun statistics. Current power incorporates recorded strength and experience where available, otherwise full-strength hull counts. These are comparative estimates, not predicted battle outcomes.');
}

