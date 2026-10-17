/* =============== POPS =============== */
const popSave = document.getElementById('popsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  popSave.appendChild(o);
});
popSave.value = DATA.lastDate;
popSave.onchange = () => { drawPopTable(); refreshPopulation(); };

let popShare = false;
const popShareBtn = document.getElementById('popshare');
popShareBtn.onclick = () => {
  popShare = !popShare;
  popShareBtn.setAttribute('aria-pressed', popShare);
  popShareBtn.textContent = popShare ? 'Shares' : 'Counts';
  drawPopTable();
};

const popState = {key: 'total', dir: -1};
function drawPopTable() {
  const date = popSave.value;
  document.getElementById('popdate').textContent = date;
  const facts = DATA.facts[date] || {};
  const used = DATA.popTypes.filter(pt =>
    DATA.tags.some(t => ((DATA.pops[t] || {})[date] || {})[pt]));
  const cell = (v, row) => {
    if (!v) return popShare ? '—' : '0';
    return popShare ? (v / row.total * 100).toFixed(1) + '%' : v.toLocaleString();
  };
  const cols = [
    {key: 'tag', label: 'Tag', colour: r => colourFor(r.tag)},
    {key: 'name', label: 'Nation', render: r => nationIdentity(r.tag)},
    {key: 'total', label: 'Total pop', fmt: v => v.toLocaleString()},
    {key: 'accepted_pct', label: 'Accepted', fmt: v => v.toFixed(1) + '%'},
    /* The nation's own states, not its empire. A colony's pops are in the
       national average and drag it down without saying anything about the
       metropole -- Britain reads 52.5% with India in the figure and rather
       higher without. The column keeps the plain name because this is the
       reading somebody means by "how literate is this country"; the whole-
       empire figure is still on the chart above, as Average literacy. */
    {key: 'avg_literacy_stated', label: 'Literacy',
     fmt: v => (v * 100).toFixed(1) + '%',
     title: 'Literacy across the pops in this nation\u2019s own states, with '
          + 'its colonies left out. The same states the soldier counts use, so '
          + 'the two agree about what counts as our own. Average literacy on '
          + 'the chart above is the whole empire.'},
    {key: 'avg_militancy', label: 'Mil', fmt: v => v.toFixed(2)},
    {key: 'avg_consciousness', label: 'Con', fmt: v => v.toFixed(2)},
    ...used.map(pt => ({key: pt, label: gameName(pt), fmt: cell})),
  ];
  const rows = DATA.tags.map(tag => {
    const at = (DATA.pops[tag] || {})[date] || {};
    const f = facts[tag] || {};
    const row = {
      tag, name: nameOf(tag),
      total: f.total_pop || 0,
      accepted_pct: f.accepted_pct || 0,
      avg_literacy_stated: f.avg_literacy_stated || 0,
      avg_militancy: f.avg_militancy || 0,
      avg_consciousness: f.avg_consciousness || 0,
    };
    used.forEach(pt => row[pt] = at[pt] || 0);
    return row;
  }).filter(r => r.total > 0 && populationMatches(r.tag));
  renderTable(document.getElementById('poptable'), cols, rows, popState,
              row => openPopulationCountry(row.tag));
  filterPopulationTable();
}

// The nation the population history chart is drawn for.
let popChartTag = largestBy('total_pop');

const drawPopChart = () => populationHistory(
  DATA.pops[popChartTag] || {}, DATA.popTypes,
  nameOf(popChartTag) + ' has no pops in these saves.', popChartTag);

