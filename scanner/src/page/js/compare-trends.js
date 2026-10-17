/* =============== NATIONS =============== */
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

const scaleBtn = document.getElementById('scale');
scaleBtn.onclick = () => {
  logScale = !logScale;
  scaleBtn.setAttribute('aria-pressed', logScale);
  scaleBtn.textContent = logScale ? 'Logarithmic' : 'Linear';
  drawChart();
};

const worldBtn = document.getElementById('worldline');
worldBtn.onclick = () => {
  worldLine = !worldLine;
  worldBtn.setAttribute('aria-pressed', worldLine);
  drawChart();
};

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

