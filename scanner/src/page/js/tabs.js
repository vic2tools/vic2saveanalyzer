/* =============== TABS =============== */
const tabs = [...document.querySelectorAll('.tab')];
function selectTab(id) {
  if (id !== 'tab-nations') mapStopPlay();
  tabs.forEach(t => {
    const on = t.id === id;
    t.setAttribute('aria-selected', on);
    document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
  });
}
tabs.forEach((t, i) => {
  t.onclick = () => selectTab(t.id);
  t.onkeydown = e => {
    const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    // Past the ones that have taken themselves off the row. Arrowing onto a
    // tab that is not there selects a panel nobody can see their way back
    // from.
    let at = i;
    for (let n = 0; n < tabs.length; n++) {
      at = (at + d + tabs.length) % tabs.length;
      if (!tabs[at].hidden) break;
    }
    const next = tabs[at];
    next.focus(); selectTab(next.id);
  };
});

goodsPicker.set(topMovers(6));
drawChart();
drawMilPies(); drawMilTable();
drawFleetTable();
drawPopTable(); drawPopChart();
refreshPopulation();
drawMarketTable();
drawSupply();
searchSelect(document.getElementById('prodgood'), 'search goods');
if (TECH) drawTechTree();
if (WARS.length) drawWarTable();
searchSelect(document.getElementById('techtag'), 'search nations');
if (MAP) mapRender();
drawGreatPowers();

/* A tab with nothing behind it is worse than no tab. Technology and Wars
   already take themselves off the row when the campaign has none; the map
   and the great power ranking hide their own sections without a mod and
   left Nations on the row, selected, with an empty panel under it -- so a
   report built without a mod opened on a blank page and looked broken.
   Done here rather than beside the map because it has to run after
   everything that hides a section, and it is the same rule for all of
   them: a panel whose sections are all hidden is a tab not worth showing. */
tabs.forEach(t => {
  if (t.hidden) return;
  const panel = document.getElementById(t.getAttribute('aria-controls'));
  const sections = panel ? [...panel.querySelectorAll(':scope > section')] : [];
  if (sections.length && sections.every(s => s.hidden)) t.hidden = true;
});
const firstShown = tabs.find(t => !t.hidden);
if (firstShown) selectTab(firstShown.id);

