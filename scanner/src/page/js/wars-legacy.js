/* =============== THE LEGACY LAYOUT =============== */

// Which layout a war opens in, 'infobox' or 'legacy': kept while the report
// is open, like the sorts, so the next war opens in the one last chosen.
let warView = 'infobox';
let legacyBattleSort = {key: 'total', dir: -1};

/* One side's panel: its leader's flag, its totals, its nations. No losses by
   nation, for the reason warSideLosses gives. */
function legacySide(w, side, lost, mark) {
  const parties = belParties(w, side);
  const leader = (parties.find(p => p.leads) || parties[0] || {}).tag || '';
  const ended = p => p.left || (w.active ? '<span class="rk">ongoing</span>' : w.end || '—');
  const label = side === 'attacker' ? 'Original attacker' : 'Original defender';
  return `<div class="lgpanel lgside" data-side="${side}">`
    + (leader ? ibFlag(leader, 'hero') : '')
    + `<dl><dt>${label}:</dt><dd>${leader ? warTag(leader) : '—'}</dd>`
    + `<dt>Total losses:</dt><dd>${lost.land[mark].toLocaleString()}</dd>`
    + `<dt>Total ships lost:</dt><dd>${lost.sea[mark].toLocaleString()}</dd></dl>`
    + `<div class="tablewrap fit"><table class="mini"><thead><tr>`
    + `<th>Flag</th><th>Country</th><th class="num">Joined</th>`
    + `<th class="num">Ended</th></tr></thead><tbody>`
    + parties.map(p => `<tr><td>${warFlag(p.tag)}</td>`
        + `<td><b style="color:${colourFor(p.tag)}">${p.tag}</b></td>`
        + `<td class="num">${p.joined || '—'}</td><td class="num">${ended(p)}</td></tr>`)
      .join('')
    + `</tbody></table></div></div>`;
}

/* The war's first goal, as the save's original_wargoal has it. Whether it was
   fulfilled and when it was added are only in the war_goal records, so they
   are shown when exactly one of those is the same demand, and not otherwise. */
function legacyGoal(w) {
  const g = w.goal || {};
  const same = w.goals.filter(x => x.cb === g.casus_belli && x.actor === g.actor
                                   && x.receiver === g.receiver);
  const one = same.length === 1 ? same[0] : null;
  const fulfilled = !one || one.sieged === null ? '—' : one.sieged ? 'Yes' : 'No';
  return [['Actor', warTag(g.actor)], ['Receiver', warTag(g.receiver)],
          ['Casus belli', g.casus_belli
            ? `<span title="${g.casus_belli}">${gameName(g.casus_belli)}</span>` : '—'],
          ['State ID', g.province || '—'], ['Is fulfilled', fulfilled],
          ['Date', one && one.added || '—']];
}

function legacyBattles(w) {
  const total = b => b.a[2] + b.d[2];
  const get = {
    name: b => b.name.toLowerCase(), date: b => b.date ? dateYear(b.date) : 9999,
    attacker: b => b.a[0], defender: b => b.d[0], type: b => b.sea ? 1 : 0,
    result: b => b.won ? 1 : 0, total,
  }[legacyBattleSort.key] || total;
  const rows = w.battles.slice().sort((x, y) => {
    const a = get(x), b = get(y);
    return (a < b ? -1 : a > b ? 1 : 0) * legacyBattleSort.dir;
  });
  const head = [['name', 'Battle'], ['date', 'Date'], ['attacker', 'Attacker'],
                ['defender', 'Defender'], ['type', 'Type'], ['result', 'Result'],
                ['total', 'Total losses']];
  const num = k => k === 'date' || k === 'total' ? ' class="num"' : '';
  return `<div class="tablewrap fit"><table class="mini lgbattles"><thead><tr>`
    + head.map(([k, label]) => `<th data-lk="${k}"${num(k)}`
        + (k === 'result' ? ' title="Whether the attacker won"' : '')
        + (legacyBattleSort.key === k ? ` aria-sort="${legacyBattleSort.dir < 0
            ? 'descending' : 'ascending'}"` : '') + `>${label}</th>`).join('')
    + `</tr></thead><tbody>`
    + rows.map(b => `<tr><td>${b.name}</td>`
        + `<td class="num">${b.date || '<span class="rk">unknown</span>'}</td>`
        + `<td>${warTag(b.a[0])}</td><td>${warTag(b.d[0])}</td>`
        + `<td>${b.sea ? 'Naval' : 'Land'}</td><td>${b.won ? 'Yes' : 'No'}</td>`
        + `<td class="num">${total(b).toLocaleString()}${b.sea ? ' <span class="rk">ships</span>' : ''}</td></tr>`)
      .join('')
    + `</tbody></table></div>`;
}

function warLegacy(w) {
  const lost = warSideLosses(w, warSides(w));
  const land = lost.land[1] + lost.land[-1] + lost.land[0];
  const sea = lost.sea[1] + lost.sea[-1] + lost.sea[0];
  const grid = rows => `<dl class="lggrid">${rows.map(([k, v]) =>
    `<dt>${k}:</dt><dd>${v}</dd>`).join('')}</dl>`;
  const general = [['Start date', w.start || '—'],
                   ['End date', w.active ? '<span class="rk">ongoing</span>' : w.end || '—'],
                   ['Total losses', land.toLocaleString()],
                   ['Total ships lost', sea.toLocaleString()],
                   ['Has ended', w.active ? 'No' : 'Yes']];
  const notes = ['Losses are men lost in land battles, ships lost those sunk in naval '
    + 'ones. A side&rsquo;s totals are its battles&rsquo; losses; they are not split by '
    + 'nation, since a save records one loss figure for each side of a battle, under '
    + 'the nation leading it.'];
  if (lost.land[0] || lost.sea[0])
    notes.push(`${lost.land[0].toLocaleString()} men and ${lost.sea[0].toLocaleString()} `
      + `ships were lost by armies neither side&rsquo;s list could place.`);
  return `<div class="lgwar">`
    + legacySide(w, 'attacker', lost, 1)
    + `<div class="lgcentre"><div class="lgpanel"><h3 class="lgtitle">${w.name}</h3>`
    + `<div class="lgcols"><div><div class="lgcap">General information</div>${grid(general)}</div>`
    + `<div><div class="lgcap">Original wargoal</div>${grid(legacyGoal(w))}</div></div></div>`
    + `<div class="lgpanel">${w.battles.length ? legacyBattles(w)
        : '<span class="rk">No battles recorded.</span>'}`
    + notes.map(n => `<p class="note">${n}</p>`).join('') + `</div></div>`
    + legacySide(w, 'defender', lost, -1)
    + `</div>`;
}

function drawWarDetail() {
  const box = document.getElementById('wardetail');
  const selected = warPick !== null && !!WARS[warPick];
  document.getElementById('warlist').hidden = selected;
  document.getElementById('warback').hidden = !selected;
  document.getElementById('warbar').hidden = !selected;
  if (warPick === null || !WARS[warPick]) {
    box.innerHTML = '';
    return;
  }
  const w = WARS[warPick];
  for (const view of ['infobox', 'legacy'])
    document.getElementById('warview-' + view).setAttribute('aria-pressed', warView === view);
  if (warView === 'legacy') {
    box.innerHTML = warLegacy(w);
    box.querySelectorAll('th[data-lk]').forEach(th => {
      th.onclick = () => {
        const k = th.dataset.lk;
        if (legacyBattleSort.key === k) legacyBattleSort.dir *= -1;
        else legacyBattleSort = {key: k, dir: k === 'total' ? -1 : 1};
        drawWarDetail();
      };
    });
    return;
  }
  const goals = w.goals.length
    ? `<table class="mini fitmini"><thead><tr><th>Demand</th><th>By</th><th>On</th>`
      + `<th>State</th><th>Taken at the peace</th><th>Occupied mid-war</th>`
      + `</tr></thead><tbody>`
      + w.goals.map(g =>
          `<tr><td>${gameName(g.cb)}</td>`
          + `<td>${warTag(g.actor)}</td><td>${warTag(g.receiver)}</td>`
          + `<td>${g.state || '—'}</td>`
          + `<td class="${g.met ? 'up' : g.part ? '' : g.checkable ? 'down' : ''}">`
          +   (!g.checkable ? '<span class="rk">not checkable</span>'
               : g.met ? `all ${g.of}` : g.part ? `${g.took} of ${g.of}` : 'none')
          + `</td>`
          + `<td class="rk">${g.sieged === null ? '—' : g.sieged ? 'yes' : 'no'}</td></tr>`)
        .join('')
      + `</tbody></table>`
      + `<p class="note">Taken at the peace shows territorial gains; occupied mid-war shows recorded occupation.</p>`
    : `<p class="note">No war goal was recorded for this war.</p>`;

  // What changed hands is the infobox's "Territorial changes" row now.
  const sea = w.battles.filter(b => b.sea), dry = w.battles.filter(b => !b.sea);
  const undated = w.battles.length - w.dated;
  box.innerHTML =
    `<div class="warlayout">${warInfobox(w)}<div class="warmain">`
    + `<div class="techsub">War goals</div>${goals}`
    + warBattleTable(dry, 'Land battles', 'land')
    + warBattleTable(sea, 'Naval battles', 'sea')
    + (undated ? `<p class="note">${undated} battle${undated === 1 ? ' has' : 's have'} no recorded date.</p>` : '')
    + `</div></div>`;

  drawWarTheatre(w);
  attachWarExport(box, w);

  box.querySelectorAll('th[data-bk]').forEach(th => {
    th.onclick = () => {
      const k = th.dataset.bk;
      if (warBattleSort.key === k) warBattleSort.dir *= -1;
      else warBattleSort = {key: k, dir: k === 'date' || k === 'name' ? 1 : -1};
      drawWarDetail();
    };
  });
  // Click a battle row to open/close its composition detail underneath it.
  // The row's own list ('land' or 'sea') is looked up fresh here rather than
  // trusting a captured closure, since dry/sea are rebuilt every draw.
  box.querySelectorAll('tr.battlerow').forEach(tr => {
    tr.onclick = () => {
      const b = (tr.dataset.bkind === 'sea' ? sea : dry)[+tr.dataset.bi];
      if (expandedBattles.has(b)) expandedBattles.delete(b);
      else expandedBattles.add(b);
      drawWarDetail();
    };
  });
}

for (const view of ['infobox', 'legacy']) {
  document.getElementById('warview-' + view).onclick = () => {
    warView = view;
    drawWarDetail();
  };
}

document.getElementById('warback').onclick = () => {
  const previous = warPick;
  warPick = null;
  drawWarTable();
  const row = document.querySelector(`#wartable tr[data-war="${previous}"]`);
  if (row) { row.tabIndex = -1; row.focus({preventScroll:true}); row.scrollIntoView({block:'nearest'}); }
  else document.getElementById('warfind').focus();
};

if (WARS.length) {
  document.getElementById('warfind').oninput = () => { warPick = null; drawWarTable(); };
} else {
  const tab = document.getElementById('tab-wars');
  if (tab) tab.hidden = true;
}

