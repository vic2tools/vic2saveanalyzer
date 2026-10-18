/* =============== COMPARE: TRENDS =============== */
let natTags = defaultTags.slice();
let logScale = false;

const metricSel = document.getElementById('metric');
// Families keep related readings together without changing the underlying data.
const metricGroups = [
  ['Population', [
    ['Population', ['total_pop','accepted_pop','primary_culture_pop'], 'People living in the nation, with culture-specific views.'],
    ['Accepted share', ['accepted_pct'], 'Percentage of the population belonging to an accepted culture.'],
    ['Literacy', ['avg_literacy','avg_literacy_stated'], 'Average literacy, across the nation or its own states.'],
    ['Population growth', ['pop_growth','accepted_growth'], 'Annualized percentage change between saves.'],
    ['Population gain', ['pop_gain','accepted_gain'], 'People added or lost between saves, including border changes.'],
    ['Social strata', ['pop_poor','pop_middle','pop_rich'], 'Population by social stratum.']]],
  ['Living conditions', [
    ['Life needs unmet', ['life_unmet','life_unmet_pct'], 'People whose life needs are not fully met.'],
    ['Starvation', ['starving','starving_pct'], 'Starving population, shown as a count or population share.']]],
  ['Army', [
    ['Brigades', ['brigades','regular_brigades','mobilized_brigades','mobilizing'], 'Fielded brigades or units queued for mobilization.'],
    ['Recruitment capacity', ['brigade_cap'], 'Professional brigade capacity supported by soldier populations.'],
    ['Mobilizable population', ['mobilization_pool'], 'Population eligible to support mobilization.'],
    ['Mobilization ceiling', ['mobilization_brigades'], 'Total population-based mobilization capacity, including already mobilized brigades.']]],
  ['Navy', [
    ['Ships', ['ships'], 'Ship counts over time. Choose a hull to inspect a specific ship type.'],
    ['Naval bases', ['naval_base_levels','ports','max_naval_base'], 'Total base levels, provinces with bases, or the largest individual base.']]],
  ['Economy', [
    ['Treasury', ['treasury'], 'National treasury balance.'],
    ['Tax base', ['tax_base'], 'The nation’s tax base.'],
    ['Factories', ['factory_count','factory_levels'], 'Number of factories or their combined levels.'],
    ['Railroads', ['railroad_levels'], 'Combined railroad levels.']]],
  ['Society', [
    ['Consciousness', ['avg_consciousness'], 'Average political consciousness.'],
    ['Militancy', ['avg_militancy'], 'Average population militancy.']]],
  ['Nation', [
    ['Prestige', ['prestige'], 'National prestige over time.'],
    ['Infamy', ['infamy'], 'National infamy over time.'],
    ['Technologies', ['techs'], 'Number of researched technologies.'],
    ['Territory', ['provinces','states'], 'Territory measured in provinces or states.']]],
];
const availableMetrics = new Map(DATA.metrics.map(m => [m.key, m]));
const groupedKeys = new Set(metricGroups.flatMap(([, families]) => families.flatMap(([, keys]) => keys)));
const extraMetrics = DATA.metrics.filter(m => !groupedKeys.has(m.key));
if (extraMetrics.length) metricGroups.push(['Other', extraMetrics.map(m => [m.label, [m.key], m.label])]);
const categories = metricGroups.map(([name, families]) => [name,
  families.map(([label, keys, description]) => [label, keys.filter(k => availableMetrics.has(k)), description])
    .filter(([, keys]) => keys.length)]).filter(([, families]) => families.length);
const categorySel = document.getElementById('metric-category');
const familySel = document.getElementById('metric-family');
const metricMemory = new Map();
const familyMemory = new Map();
const variantLabels = {
  total_pop:'Total', accepted_pop:'Accepted culture', primary_culture_pop:'Primary culture',
  avg_literacy:'All population', avg_literacy_stated:'Own states',
  brigades:'All fielded', regular_brigades:'Standing', mobilized_brigades:'Mobilized', mobilizing:'Queued',
  life_unmet:'People', life_unmet_pct:'% of population', starving:'People', starving_pct:'% of population',
  pop_growth:'Total population', accepted_growth:'Accepted culture', pop_gain:'Total population', accepted_gain:'Accepted culture',
  pop_poor:'Poor', pop_middle:'Middle', pop_rich:'Rich', factory_count:'Count', factory_levels:'Total levels',
  naval_base_levels:'Total levels', ports:'Provinces with bases', max_naval_base:'Largest base',
};
function selectMetricFamily() {
  const family = categories.find(([name]) => name === categorySel.value)[1].find(([name]) => name === familySel.value);
  const [label, keys, description] = family;
  familyMemory.set(categorySel.value, label);
  metricSel.replaceChildren(...keys.map(key => new Option(variantLabels[key] || availableMetrics.get(key).label, key)));
  metricSel.value = metricMemory.get(label) || keys[0];
  document.getElementById('metric-variant').hidden = keys.length < 2;
  document.getElementById('ship-variant').hidden = metricSel.value !== 'ships';
  document.getElementById('metric-description').textContent = description;
  familySel.title = description;
}
function selectMetricCategory() {
  const families = categories.find(([name]) => name === categorySel.value)[1];
  familySel.replaceChildren(...families.map(([name]) => new Option(name, name)));
  familySel.value = familyMemory.get(categorySel.value) || families[0][0];
  selectMetricFamily();
}
categories.forEach(([name]) => categorySel.add(new Option(name, name)));
selectMetricCategory();
categorySel.onchange = () => { selectMetricCategory(); drawChart(); };
familySel.onchange = () => { selectMetricFamily(); drawChart(); };
const fmtFor = key => {
  const m = DATA.metrics.find(m => m.key === key);
  return formatters[m ? m.fmt : 'count'] || fmtCount;
};
metricSel.onchange = () => { metricMemory.set(familySel.value, metricSel.value); drawChart(); };

const nationsPicker = makePicker(document.getElementById('pick-nations'),
  tagPickerCfg(natTags, sel => { natTags = sel; drawChart(); }));

const scaleBtn = toggleButton(document.getElementById('scale'), () => (logScale = !logScale),
                              () => drawChart(), ['Linear', 'Logarithmic']);

const worldBtn = toggleButton(document.getElementById('worldline'), () => (worldLine = !worldLine),
                              () => drawChart());

/* [predecessor, successor] for every nation that turned into another one. */
const SUCCESSIONS = Object.entries(DATA.succession).flatMap(
  ([to, info]) => (info.from || []).map(([from]) => [from, to]));

(() => {
  const note = document.getElementById('succnote');
  if (!note) return;
  const lines = Object.entries(DATA.succession).map(([to, info]) =>
    `${(info.from || []).map(([f, , decided]) =>
        nameOf(f) + (decided ? '' : '*')).join(' and ')} became `
    + `<b>${nameOf(to)}</b> by ${info.date}`);
  const guessed = Object.values(DATA.succession)
    .some(i => (i.from || []).some(([, , d]) => !d));
  note.innerHTML = lines.length
    ? 'A dashed line joins a nation to the one it became. A save records none '
      + 'of this: a nation that formed another leaves a block holding only its '
      + 'diplomatic relations, and the decision that does the forming changes '
      + 'the tag without leaving a flag behind. So these come from the '
      + 'decisions the mod itself ships, which declare who may form what, '
      + 'matched against the '
      + 'province ledger, which says who did: the newcomer appears holding land '
      + 'the old nation held one save earlier, and the old nation holds none. A '
      + 'nation that merely releases a puppet keeps its own line. In this '
      + 'campaign: ' + lines.join('; ') + '.'
      + (guessed ? ' Starred nations are not named by any decision -- they are '
                 + 'released or event-formed, and are matched by their people '
                 + 'being people the new nation accepts.' : '')
    : 'No nation in this campaign turned into another one.';
})();

/* Growth is not a quantity a save holds; it is the difference between two of
   them. That makes it read differently from every other measure here, so the
   chart says so, and draws the line that separates growing from shrinking. */
const isRate = key => (DATA.metrics.find(m => m.key === key) || {}).rate === 1;

/* Everyone alive, as a series the chart can draw beside the nations.

   It is not a nation and cannot be one: it counts pops on land nobody owns,
   which belong to no tag at all -- 6.4% of the world in 1836 and none of it by
   1908 -- so it comes from its own total rather than from adding the nations
   up. Offered only against population, since nothing else on the measure list
   has a world figure behind it. */
let worldLine = false;
function worldSeries(key) {
  if (!worldLine || key !== 'total_pop' || !DATA.worldPop) return [];
  const pts = DATA.dates
    .map((d, i) => [years[i], DATA.worldPop[d]])
    .filter(p => p[1] !== undefined);
  return pts.length ? [{name: 'World', colour: 'var(--ink-dim)', pts}] : [];
}

function drawChart() {
  const key = metricSel.value;
  document.getElementById('chart-title').textContent = availableMetrics.get(key).label + ' over time';
  document.getElementById('chart').setAttribute('aria-label', availableMetrics.get(key).label + ' over time by nation');
  document.getElementById('fleetspan').hidden = true;
  const shown = DATA.tags.filter(t => natTags.includes(t));
  const rate = isRate(key);
  const worldBtn = document.getElementById('worldline');
  // Nothing else on the list has a world total behind it, so the button says
  // so by going quiet rather than drawing a line that would be a guess. Being
  // switched on does not survive that: a measure with no world figure cannot
  // be showing one, so the button gives up the state as well as the colour.
  worldBtn.disabled = key !== 'total_pop' || !DATA.worldPop;
  if (worldBtn.disabled && worldLine) {
    worldLine = false;
    worldBtn.setAttribute('aria-pressed', 'false');
  }
  if (key === 'ships') {
    document.getElementById('ratenote').hidden = true;
    drawFleetChart();
    return;
  }
  plot(document.getElementById('chart'), {
    series: shown.map(tag => ({
      name: tag, colour: colourFor(tag),
      // `!= null` rather than `!== undefined`: a measure a nation has no
      // reading for in a save is a null in its column, not a gap.
      pts: DATA.dates.map((d, i) => [years[i], DATA.series[tag][key][i]])
                     .filter(p => p[1] != null),
    })).concat(worldSeries(key)),
    xOf: xOfSave, xTicks: saveTicks, hoverXs: saveHovers,
    fmt: fmtFor(key), log: logScale, markers: true,
    links: SUCCESSIONS,
    baseline: rate ? 0 : null,
    readout: document.getElementById('readout'),
    idle: 'Hover the plot to read values at a date.',
    emptyMsg: shown.length || worldSeries(key).length
      ? 'No data for this measure.' : 'Select a nation.',
  });
  const note = document.getElementById('ratenote');
  note.hidden = !rate;
  if (rate) note.innerHTML = 'Compounded yearly, between one save and the one '
    + 'before it: a nation that grew 3% over six months plots at about 6%. '
    + `Two saves less than ${(DATA.growthSpan * 12).toFixed(0)} months apart are `
    + 'measured across the gap to the next one far enough away instead &mdash; a '
    + 'fortnight of ordinary growth annualises into hundreds of percent and would '
    + 'bury everything else on the chart. Conquest, annexation and independence '
    + 'move population as surely as births do, so the sharp spikes and drops are '
    + 'usually a border moving rather than a demographic event.';
}


/* =============== COMPARE: HEAD TO HEAD =============== */
let milMode = 'army';       // army | navy
let milView = 'totals';     // totals | composition
let milPotential = false;    // true = standing + mobilization ceiling, false = brigades right now
// Horizon blue against field grey: the two uniforms the period ended in, and
// far enough apart on a burgundy ground to read at a glance. Mobilization is
// the same blue and grey held back to a khaki, so an added ceiling reads as
// part of the same army rather than a third force.
const MOB_COLOUR = '#B79B6E';
// Brigades the cap allows that nobody has raised. Kept clearly apart from the
// mobilization brass, since the two are different kinds of "not yet".
const CAP_COLOUR = '#6B7C8C';
const SIDE_COLOUR = ['#5E8CB8', '#9DA08D'];

const milSave = document.getElementById('milsave');
fillSelect(milSave, DATA.dates);
milSave.value = DATA.lastDate;




const byBrigades = [...DATA.tags].sort((a, b) =>
  (((DATA.facts[DATA.lastDate] || {})[b] || {}).brigades || 0) -
  (((DATA.facts[DATA.lastDate] || {})[a] || {}).brigades || 0));
let sideA = [byBrigades[0]].filter(Boolean);
let sideB = [byBrigades[1]].filter(Boolean);

const pickerA = makePicker(document.getElementById('pick-milA'),
  tagPickerCfg(sideA, sel => { sideA = sel; drawMilPies(); }, () => milSave.value));
const pickerB = makePicker(document.getElementById('pick-milB'),
  tagPickerCfg(sideB, sel => { sideB = sel; drawMilPies(); }, () => milSave.value));

function setHeadBranch(branch) {
  milMode = branch;
  for (const kind of ['army', 'navy']) document.getElementById('head-' + kind).setAttribute('aria-pressed', kind === branch);
  document.getElementById('milmob').hidden = branch === 'navy';
  drawMilPies();
}
for (const branch of ['army', 'navy']) document.getElementById('head-' + branch).onclick = () => setHeadBranch(branch);
function showCompareView(view) {
  for (const kind of ['trends', 'head']) {
    document.getElementById('compare-' + kind).hidden = kind !== view;
    document.getElementById('compare-' + kind + '-button').setAttribute('aria-pressed', kind === view);
  }
}
for (const view of ['trends', 'head']) document.getElementById('compare-' + view + '-button').onclick = () => showCompareView(view);
toggleButton(document.getElementById('milview'),
             () => (milView = milView === 'totals' ? 'composition' : 'totals') === 'composition',
             () => drawMilPies(), ['Totals', 'Composition']);
toggleButton(document.getElementById('milmob'), () => (milPotential = !milPotential),
             () => drawMilPies(), ['Current', 'Potential']);
document.getElementById('milswap').onclick = () => {
  const a = sideA.slice();
  pickerA.set(sideB.slice());
  pickerB.set(a);
};
milSave.onchange = () => {
  pickerA.refresh(); pickerB.refresh();
  drawMilPies();
};


const milTypes = () => milMode === 'army' ? DATA.regimentTypes : DATA.shipTypes;
const milColour = t => seriesColour(milTypes().indexOf(t));
const milSource = tag => (milMode === 'army' ? DATA.brigades : DATA.ships)[tag] || {};

/** Sum a side's unit counts by type across every nation in the group. */
function groupCounts(tags, date) {
  const out = {};
  tags.forEach(tag => {
    const at = milSource(tag)[date] || {};
    for (const key in at) out[key] = (out[key] || 0) + at[key];
  });
  return out;
}
const groupTotal = (tags, date) => {
  const at = groupCounts(tags, date);
  let n = 0;
  for (const key in at) n += at[key];
  return n;
};
/**
 * Standing (non-mobilized) brigades for a side. Kept separate from
 * `groupTotal` -- which is every brigade a side currently has, mobilized or
 * not -- specifically so it can be added to the mobilization ceiling below
 * without double-counting: `mobilization_brigades` is the *total* a side
 * could ever raise through mobilizing, already inclusive of whatever it's
 * mobilized so far, so adding it to `groupTotal` (which also already
 * includes those same mobilized brigades) counted them twice.
 */
// One fact summed over a side's nations at one save; a nation without it adds 0.
function sumFact(tags, date, key) {
  const at = DATA.facts[date] || {};
  return tags.reduce((sum, t) => sum + ((at[t] || {})[key] || 0), 0);
}
function groupStanding(tags, date) {
  if (milMode !== 'army') return groupTotal(tags, date);
  return sumFact(tags, date, 'regular_brigades');
}
/**
 * The standing brigades a side's soldier pops could support.
 *
 * Potential used to mean the brigades already standing plus the mobilization
 * ceiling, which understated a nation that had not recruited its soldier pops
 * out -- and nations differ enormously there. This is the other half: what
 * could be raised without mobilizing at all.
 */
function groupCap(tags, date) {
  if (milMode !== 'army') return groupTotal(tags, date);
  return sumFact(tags, date, 'brigade_cap');
}
/** Mobilization ceiling for a side. Naval hulls cannot be mobilized. */
function groupMob(tags, date) {
  if (milMode !== 'army') return 0;
  return sumFact(tags, date, 'mobilization_brigades');
}
/** How many of a side's current brigades came from mobilizing already,
    rather than standing recruitment -- regular_brigades + this always sums
    to groupTotal, since a brigade is one or the other, never both. */
function groupMobilized(tags, date) {
  if (milMode !== 'army') return 0;
  return sumFact(tags, date, 'mobilized_brigades');
}
/**
 * A side's headline total: its brigades right now, or -- with "Potential"
 * selected -- its standing brigades plus everything its mobilization
 * ceiling could still add. See `groupStanding` for why that's the ceiling
 * added to *standing*, not to the current brigade count.
 */
function sideTotal(tags, date) {
  return milPotential
    ? groupCap(tags, date) + groupMob(tags, date)
    : groupTotal(tags, date);
}
const sideLabel = tags => !tags.length ? 'nobody'
  : tags.length <= 3 ? tags.join(' + ')
  : `${tags.slice(0, 2).join(' + ')} +${tags.length - 2} more`;

function arcPath(cx, cy, r0, r1, a0, a1) {
  const at = (r, a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const large = (a1 - a0) > Math.PI ? 1 : 0;
  const [x0, y0] = at(r1, a0), [x1, y1] = at(r1, a1);
  const [x2, y2] = at(r0, a1), [x3, y3] = at(r0, a0);
  return `M${x0} ${y0}A${r1} ${r1} 0 ${large} 1 ${x1} ${y1}`
       + `L${x2} ${y2}A${r0} ${r0} 0 ${large} 0 ${x3} ${y3}Z`;
}

/**
 * Draw a donut. A single slice covering the ring needs two arcs.
 *
 * With opts.split and exactly two slices the ring is drawn as a head-to-head:
 * both slices start at the top, the first sweeping anticlockwise so it fills the
 * left half and the second clockwise so it fills the right. That puts each
 * side's colour on the side of the chart its label is on, which the plain
 * clockwise-from-top order gets backwards.
 */
function donut(svg, cx, cy, r0, r1, slices, onHover, opts) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (!total) {
    svg.appendChild(el('circle', {cx, cy, r: r1, fill: 'none',
      stroke: 'var(--grid)', 'stroke-width': 1}));
    return;
  }
  const top = -Math.PI / 2;
  const split = !!(opts && opts.split) && slices.length === 2;
  let angle = top;
  slices.forEach((slice, i) => {
    if (!slice.value) return;
    const sweep = slice.value / total * Math.PI * 2;
    const full = sweep >= Math.PI * 2 - 1e-6;
    const a0 = split ? (i === 0 ? top - sweep : top) : angle;
    const a1 = split ? (i === 0 ? top : top + sweep) : angle + sweep;
    const path = el('path', {
      d: full
        ? arcPath(cx, cy, r0, r1, a0, a0 + Math.PI)
          + arcPath(cx, cy, r0, r1, a0 + Math.PI, a0 + Math.PI * 2)
        : arcPath(cx, cy, r0, r1, a0, a1),
      fill: slice.colour, 'fill-opacity': .85,
      stroke: 'var(--ground)', 'stroke-width': 1,
    });
    const title = document.createElementNS(SVGNS, 'title');
    title.textContent = `${slice.label}: ${slice.value.toLocaleString()} `
      + `(${(slice.value / total * 100).toFixed(1)}%)`;
    path.appendChild(title);
    path.style.cursor = 'pointer';
    path.onpointerenter = () => { path.setAttribute('fill-opacity', 1); onHover(slice); };
    path.onpointerleave = () => path.setAttribute('fill-opacity', .85);
    svg.appendChild(path);
    angle += sweep;
  });
}

function centreText(svg, cx, cy, big, small) {
  const a = el('text', {x: cx, y: cy - 2, 'text-anchor': 'middle', fill: 'var(--ink)',
    'font-family': 'Barlow Condensed, sans-serif', 'font-size': 34, 'font-weight': 600});
  a.textContent = big;
  svg.appendChild(a);
  const b = el('text', {x: cx, y: cy + 20, 'text-anchor': 'middle', fill: 'var(--ink-dim)',
    'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
  b.textContent = small;
  svg.appendChild(b);
}

function drawMilPies() {
  const svg = document.getElementById('milpies');
  svg.textContent = '';
  const legend = document.getElementById('millegend');
  legend.textContent = '';
  const readout = document.getElementById('milreadout');
  const date = milSave.value;
  document.getElementById('mildate').textContent = date;
  const noun = milMode === 'army' ? 'brigades' : 'ships';

  const raised = [groupTotal(sideA, date), groupTotal(sideB, date)];
  const standing = [groupStanding(sideA, date), groupStanding(sideB, date)];
  const mobs = [groupMob(sideA, date), groupMob(sideB, date)];
  const caps = [groupCap(sideA, date), groupCap(sideB, date)];
  // The cap counts brigades that do not exist yet, so they have no unit type to
  // be drawn as; they get a slice of their own, and the slices then still add
  // up to the headline -- standing + mobilized + unbuilt + remaining ceiling is
  // the cap plus the ceiling. Declared here with the other side arrays because
  // the labels under each donut read it well before the slices are built.
  const unbuilt = milPotential
    ? [0, 1].map(i => Math.max(0, caps[i] - standing[i])) : [0, 0];
  const mobilized = [groupMobilized(sideA, date), groupMobilized(sideB, date)];
  const totals = [sideTotal(sideA, date), sideTotal(sideB, date)];
  if (!sideA.length && !sideB.length) {
    svgMessage(svg, 500, 200, 'Pick at least one nation for a side.');
    readout.textContent = '';
    return;
  }

  const ratioText = totals[1] ? (totals[0] / totals[1]).toFixed(2) + '×' : '—';
  // Hulls are not interchangeable: five frigates are not a cruiser. Fleet power
  // is what a side's ships are worth in a fight, so it sits beside the count
  // rather than replacing it -- the two disagreeing is the interesting part.
  const powers = NAVAL && milMode === 'navy'
    ? [fleetPower(sideA, date, false), fleetPower(sideB, date, false)] : null;
  const heavyPowers = powers && torpedoesAbout(sideA.concat(sideB), date)
    ? [fleetPower(sideA, date, true), fleetPower(sideB, date, true)] : null;
  // The same fleets at the strength and experience the save records. Shown
  // under the design figure rather than instead of it, so a fleet somebody has
  // stopped paying for still appears at what it could be worth again.
  const nowPowers = powers
    ? [fleetPower(sideA, date, false, true), fleetPower(sideB, date, false, true)]
    : null;
  const powersDiffer = nowPowers && [0, 1].some(i =>
    Math.abs(nowPowers[i] - powers[i]) > Math.max(0.5, powers[i] * 0.005));
  const powerRatio = powers && powers[1]
    ? (powers[0] / powers[1]).toFixed(2) + '×' : '—';
  const powerBits = !powers ? ''
    : `<span><span class="rk">fleet power</span> `
      + `<b style="color:${SIDE_COLOUR[0]}">${fmtPower(powers[0])}</b>`
      + ` <span class="rk">v</span> `
      + `<b style="color:${SIDE_COLOUR[1]}">${fmtPower(powers[1])}</b></span>`
      + `<span><span class="rk">power ratio</span> <b>${powerRatio}</b></span>`
      + (powersDiffer ? `<span><span class="rk">at current strength</span> `
        + `<b>${fmtPower(nowPowers[0])}</b> <span class="rk">v</span> `
        + `<b>${fmtPower(nowPowers[1])}</b></span>` : '')
      + (heavyPowers ? `<span><span class="rk">vs heavy</span> `
        + `<b>${fmtPower(heavyPowers[0])}</b> <span class="rk">v</span> `
        + `<b>${fmtPower(heavyPowers[1])}</b></span>` : '');
  const mobBits = milMode === 'army'
    ? [sideA, sideB].map(mobilizedSide).filter(Boolean).join('') : '';
  function mobilizedSide(tags) {
    const n = sumFact(tags, date, 'mobilized_brigades');
    if (!n) return '';
    return `<span><span class="rk">${sideLabel(tags)} mobilized</span> <b>${n.toLocaleString()}</b></span>`;
  }
  const split = milMode === 'army' && (milPotential ? (mobs[0] || mobs[1]) : (mobilized[0] || mobilized[1]))
    ? `<span><span class="rk">standing</span> <b>${standing[0].toLocaleString()}</b>`
      + ` <span class="rk">v</span> <b>${standing[1].toLocaleString()}</b></span>`
      + (milPotential && (caps[0] || caps[1])
          ? `<span title="The standing brigades each side's soldier pops can `
            + `support, never read below what it already has."><span `
            + `class="rk">brigade cap</span> `
            + `<b>${caps[0].toLocaleString()}</b> <span class="rk">v</span> `
            + `<b>${caps[1].toLocaleString()}</b></span>` : '')
      + `<span><span class="rk">${milPotential ? 'mob ceiling' : 'mobilized'}</span> `
      + `<b>${(milPotential ? mobs[0] : mobilized[0]).toLocaleString()}</b>`
      + ` <span class="rk">v</span> <b>${(milPotential ? mobs[1] : mobilized[1]).toLocaleString()}</b></span>`
    : '';
  const idle = `<span class="rk">left</span> <b style="color:${SIDE_COLOUR[0]}">`
    + `${totals[0].toLocaleString()}</b>`
    + `<span><span class="rk">right</span> <b style="color:${SIDE_COLOUR[1]}">`
    + `${totals[1].toLocaleString()}</b></span>`
    + `<span><span class="rk">ratio</span> <b>${ratioText}</b></span>` + split
    + powerBits
    + mobBits
    + `<span class="rk">${totals[0] + totals[1] ? '' : 'no ' + noun + ' at this save'}</span>`;
  const setIdle = () => readout.innerHTML = idle;

  if (milView === 'totals') {
    // One pie, one slice per side: the broad "who has more" view.
    const slices = [
      {label: sideLabel(sideA), value: totals[0], colour: SIDE_COLOUR[0], tags: sideA, side: 0},
      {label: sideLabel(sideB), value: totals[1], colour: SIDE_COLOUR[1], tags: sideB, side: 1},
    ];
    donut(svg, 500, 196, 84, 138, slices, slice => {
      const share = (totals[0] + totals[1])
        ? (slice.value / (totals[0] + totals[1]) * 100).toFixed(1) : '0.0';
      const parts = slice.tags.map(tag => {
        const n = sideTotal([tag], date);
        return `<span><span class="rk">${tag}</span> <b style="color:${colourFor(tag)}">`
             + `${n.toLocaleString()}</b></span>`;
      });
      readout.innerHTML = `<span class="rk">${slice.label}</span>`
        + `<span><b style="color:${slice.colour}">${slice.value.toLocaleString()}</b> `
        + `<span class="rk">${noun} (${share}% of both)</span></span>`
        + (slice.tags.length > 1 ? parts.join('') : '');
    }, {split: true});
    // The donut hole is only ~2x its inner radius wide, so the centre label
    // has to stay short -- "both sides" fits; tacking the noun and a
    // mobilization note on (as this used to) ran past the ring itself. That
    // detail moves to sit under each side's own number instead, where there
    // is room for it and it reads as "how this side's total breaks down"
    // rather than a caption on the aggregate.
    centreText(svg, 500, 196, (totals[0] + totals[1]).toLocaleString(), 'both sides');

    [[sideA, 0, 232], [sideB, 1, 768]].forEach(([tags, side, x]) => {
      const head = el('text', {x, y: 34, 'text-anchor': 'middle', fill: SIDE_COLOUR[side],
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 13});
      head.textContent = sideLabel(tags);
      svg.appendChild(head);
      const val = el('text', {x, y: 82, 'text-anchor': 'middle', fill: 'var(--ink)',
        'font-family': 'Barlow Condensed, sans-serif', 'font-size': 40, 'font-weight': 600});
      val.textContent = totals[side].toLocaleString();
      svg.appendChild(val);
      const sub = el('text', {x, y: 104, 'text-anchor': 'middle', fill: 'var(--ink-dim)',
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
      sub.textContent = noun;
      svg.appendChild(sub);
      // A second line under each side's number only when there is something
      // to split it into -- a side with no mobilization ceiling (navy, or a
      // nation that can't mobilize) has nothing worth breaking out.
      if (milMode === 'army'
          && (milPotential ? (mobs[side] || unbuilt[side]) : mobilized[side])) {
        const breakdown = el('text', {x, y: 122, 'text-anchor': 'middle',
          fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
        breakdown.textContent = milPotential
          ? `${standing[side].toLocaleString()} standing `
            + (unbuilt[side] ? `+ ${unbuilt[side].toLocaleString()} unbuilt ` : '')
            + `+ ${mobs[side].toLocaleString()} mob ceiling`
          : `${standing[side].toLocaleString()} standing `
            + `+ ${mobilized[side].toLocaleString()} mobilized`;
        svg.appendChild(breakdown);
      }
      // The same slot under the navy's count carries what those hulls are
      // worth, which is the number that actually decides a battle.
      if (powers) {
        const worth = el('text', {x, y: 122, 'text-anchor': 'middle',
          fill: 'var(--brass)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
        worth.textContent = `${fmtPower(powers[side])} fleet power`;
        svg.appendChild(worth);
        let line = 138;
        if (powersDiffer) {
          const now = el('text', {x, y: line, 'text-anchor': 'middle',
            fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
          const pct = powers[side]
            ? Math.round(100 * nowPowers[side] / powers[side]) : 100;
          now.textContent = `${fmtPower(nowPowers[side])} at current strength `
            + `(${pct}%)`;
          svg.appendChild(now);
          line += 15;
        }
        if (heavyPowers && heavyPowers[side] > powers[side] + 0.5) {
          const vs = el('text', {x, y: line, 'text-anchor': 'middle',
            fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
          vs.textContent = `${fmtPower(heavyPowers[side])} against heavy ships`;
          svg.appendChild(vs);
        }
      }
    });
    const ratio = el('text', {x: 500, y: 362, 'text-anchor': 'middle', fill: 'var(--brass)',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 16, 'font-weight': 600});
    ratio.textContent = ratioText;
    svg.appendChild(ratio);
    const ratioLabel = el('text', {x: 500, y: 380, 'text-anchor': 'middle',
      fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
    ratioLabel.textContent = 'ratio';
    svg.appendChild(ratioLabel);

    slices.forEach(slice => {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${slice.colour}"></i>${slice.label} `
        + `(${slice.value.toLocaleString()})`;
      legend.appendChild(item);
    });
  } else {
    // Two pies broken down by unit type, shared colour scale. The unit-type
    // counts already include every brigade a side has raised so far,
    // mobilized ones among them -- so the ceiling can only be added on top
    // as *remaining* headroom (ceiling minus what's mobilized already), and
    // only in Potential mode. Adding the full ceiling regardless of mode, as
    // this used to, double-counted a nation's already-mobilized brigades:
    // once inside its unit-type slices, again as part of "the ceiling".
    const counts = [groupCounts(sideA, date), groupCounts(sideB, date)];
    const remainingMob = milPotential
      ? [0, 1].map(i => Math.max(0, mobs[i] - mobilized[i])) : [0, 0];
    const present = milTypes().filter(t => counts.some(c => c[t]));
    const setType = type => {
      const parts = [0, 1].map(i => {
        const n = type === '__mob' ? remainingMob[i]
              : type === '__unbuilt' ? unbuilt[i] : (counts[i][type] || 0);
        const pct = totals[i] ? (n / totals[i] * 100).toFixed(1) : '0.0';
        return `<span><span class="rk">${i ? 'right' : 'left'}</span> `
             + `<b style="color:${SIDE_COLOUR[i]}">${n.toLocaleString()}</b> `
             + `<span class="rk">(${pct}%)</span></span>`;
      });
      const [x, y] = type === '__mob' ? remainingMob
                   : type === '__unbuilt' ? unbuilt
                   : [counts[0][type] || 0, counts[1][type] || 0];
      const r = y ? (x / y).toFixed(2) + '×' : (x ? '—' : '');
      const label = type === '__mob' ? 'still mobilizable'
                  : type === '__unbuilt' ? 'cap not yet raised' : gameName(type);
      // What one of these hulls is worth, side by side. The two sides can
      // differ on the same hull type: inventions upgrade guns and armour, so
      // one nation's cruiser is not another's.
      let worth = '';
      if (powers && type !== '__mob' && type !== '__unbuilt') {
        const each = [0, 1].map(i => {
          const per = sideCount[i] ? shipPowerOf(sideCount[i], date, type, false) : 0;
          return `<span><span class="rk">${i ? 'right' : 'left'} each</span> `
               + `<b style="color:${SIDE_COLOUR[i]}">${fmtPower(per)}</b> `
               + `<span class="rk">x${(counts[i][type] || 0).toLocaleString()} `
               + `= ${fmtPower(per * (counts[i][type] || 0))}</span></span>`;
        });
        worth = `<span class="rk">power</span>` + each.join('');
      }
      readout.innerHTML = `<span class="rk">${label}</span>` + parts.join('')
        + (r ? `<span><span class="rk">ratio</span> <b>${r}</b></span>` : '')
        + worth;
    };
    // A side is one nation or several. Power per hull belongs to a nation, so
    // the readout quotes the side's largest fleet rather than pretending a
    // coalition of nations on different technology shares one cruiser.
    const shipsOf = t => ((DATA.facts[date] || {})[t] || {}).ships || 0;
    const sideCount = [sideA, sideB].map(
      tags => tags.slice().sort((a, b) => shipsOf(b) - shipsOf(a))[0]);

    [[sideA, 0, 268], [sideB, 1, 732]].forEach(([tags, side, cx]) => {
      const head = el('text', {x: cx, y: 34, 'text-anchor': 'middle', fill: SIDE_COLOUR[side],
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 13});
      head.textContent = sideLabel(tags);
      svg.appendChild(head);
      const slices = present.map(type => ({
        label: `${sideLabel(tags)} · ${gameName(type)}`, value: counts[side][type] || 0,
        colour: milColour(type), type,
      }));
      if (unbuilt[side]) slices.push({
        label: `${sideLabel(tags)} · cap not yet raised`, value: unbuilt[side],
        colour: CAP_COLOUR, type: '__unbuilt',
      });
      if (remainingMob[side]) slices.push({
        label: `${sideLabel(tags)} · still mobilizable`, value: remainingMob[side],
        colour: MOB_COLOUR, type: '__mob',
      });
      donut(svg, cx, 196, 74, 122, slices, slice => setType(slice.type));
      centreText(svg, cx, 196, totals[side].toLocaleString(), noun);
      if (powers) {
        const worth = el('text', {x: cx, y: 348, 'text-anchor': 'middle',
          fill: 'var(--brass)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 13});
        worth.textContent = fmtPower(powers[side]);
        svg.appendChild(worth);
        const cap = el('text', {x: cx, y: 364, 'text-anchor': 'middle',
          fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
        cap.textContent = 'fleet power';
        svg.appendChild(cap);
      }
    });

    const ratio = el('text', {x: 500, y: 190, 'text-anchor': 'middle', fill: 'var(--brass)',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 15});
    ratio.textContent = ratioText;
    svg.appendChild(ratio);
    const ratioLabel = el('text', {x: 500, y: 208, 'text-anchor': 'middle',
      fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
    ratioLabel.textContent = 'ratio';
    svg.appendChild(ratioLabel);

    present.forEach(type => {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${milColour(type)}"></i>${gameName(type)}`;
      item.style.cursor = 'pointer';
      item.onmouseenter = () => setType(type);
      legend.appendChild(item);
    });
    if (unbuilt[0] || unbuilt[1]) {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${CAP_COLOUR}"></i>cap not yet raised`;
      item.style.cursor = 'pointer';
      item.onmouseenter = () => setType('__unbuilt');
      legend.appendChild(item);
    }
    if (remainingMob[0] || remainingMob[1]) {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${MOB_COLOUR}"></i>still mobilizable`;
      item.style.cursor = 'pointer';
      item.onmouseenter = () => setType('__mob');
      legend.appendChild(item);
    }
  }

  svg.onpointerleave = setIdle;
  setIdle();
}


/* =============== COMPARE: HULLS OVER TIME =============== */

const shipSel = document.getElementById('shiptype');
fillSelect(shipSel, ['__all', ...[...DATA.shipTypes].sort(byGameName)],
           s => s === '__all' ? 'All ships' : gameName(s));
shipSel.onchange = drawChart;


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

registerTab('tab-compare', {init() { drawChart(); drawMilPies(); }});
exportNotes.chart = base => ({
  subtitle: base + ' · ' + scaleBtn.textContent + (worldLine ? ' · World total included' : '')});
exportNotes.milpies = () => ({
  subtitle: (milMode === 'army' ? 'Army' : 'Navy') + ' · ' + milView
    + (milMode === 'army' ? (milPotential ? ' · Potential' : ' · Current') : '')
    + ' · ' + sideLabel(sideA) + ' versus ' + sideLabel(sideB),
  legend: [...document.querySelectorAll('#millegend .slegend')].map(item => ({
    text: item.textContent.trim(), colour: getComputedStyle(item.querySelector('i')).backgroundColor})),
  suffix: '-' + milMode + '-' + milView,
});
