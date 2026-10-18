/* =============== shared bits =============== */
const years = DATA.years;
const xMin = Math.min(...years), xMax = Math.max(...years);
const xOfSave = y => M.l + (xMax === xMin ? 0 : (y - xMin) / (xMax - xMin)) * (W - M.l - M.r);
/* Vertical rules at round years, evenly spaced.
   They used to mark the saves themselves, one gridline and one label each,
   which reads as a calendar when a campaign is thirty hand-made saves and as
   a picket fence the moment it is monthly autosaves -- a rule every few
   pixels behind the very lines it is there to help read. Years do not care
   how the campaign was saved: the spacing stays even and the count stays
   the same whether the run holds thirty saves or nine hundred.
   The step is the first of the usual round numbers that leaves the labels
   room to breathe, so they never need thinning out afterwards. */
const TICK_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200];
function yearTicks(lo, hi) {
  const room = Math.max(2, Math.floor((W - M.l - M.r) / 74));
  const step = TICK_STEPS.find(v => (hi - lo) / v <= room)
            || TICK_STEPS[TICK_STEPS.length - 1];
  const out = [];
  for (let y = Math.ceil(lo / step) * step; y <= hi; y += step)
    out.push({v: y, label: String(y)});
  return out;
}
const saveTicks = yearTicks(xMin, xMax);
const saveHovers = DATA.dates.map((d, i) => ({v: years[i], label: d}));

/* The eight great powers, in the game's own rank order, at whichever save is
   being looked at. This is the same list the Nations tab ranks, read from the
   save's `great_nations`, so a picker and the ranking never disagree. */
function greatPowersAt(date) {
  const list = DATA.greatPowers[date] || [];
  return list.map(([tag]) => tag);
}
function greatPowersNear(date) {
  const found = greatPowersAt(date);
  if (found.length) return found;
  // Not every save carries the list; fall back to the nearest one that does.
  const order = DATA.dates.slice().reverse();
  for (const d of order) {
    const some = greatPowersAt(d);
    if (some.length) return some.filter(t => tagsAt(date).includes(t));
  }
  return [];
}

const defaultTags = (greatPowersAt(DATA.dates[DATA.dates.length - 1]).length
  ? greatPowersAt(DATA.dates[DATA.dates.length - 1])
  : DATA.tags).slice(0, 8);
// For single-nation dropdowns, opening on the largest example is more useful
// than opening on whatever sorts first.
function largestBy(key) {
  const at = DATA.facts[DATA.dates[DATA.dates.length - 1]] || {};
  return [...DATA.tags].sort((a, b) =>
    ((at[b] || {})[key] || 0) - ((at[a] || {})[key] || 0))[0] || DATA.tags[0];
}

/* Nations that exist in a given save: holding land, and therefore a country
   rather than a tag the mod defines and the campaign never used. Anything read
   at one date -- a tech tree, a force comparison, the map -- offers only these.
   Anything plotted across every date keeps the full list, because a nation that
   ends in 1860 still has a line worth drawing. */
function tagsAt(date) {
  const at = DATA.facts[date] || {};
  return DATA.tags.filter(t => at[t] && at[t].provinces > 0);
}

function biggestAt(date, key, n) {
  const at = DATA.facts[date] || {};
  return tagsAt(date)
    .sort((a, b) => ((at[b] || {})[key] || 0) - ((at[a] || {})[key] || 0))
    .slice(0, n);
}

/* Every country somebody was playing. Each carries `human=yes` in its own
   block of the save, so a multiplayer campaign names all of its players rather
   than only whoever pressed save -- which is what the report used to have to
   assume. A nation counts if it was played at any point in the run: the tags
   worth picking out of a hundred and twenty are the ones a person steered,
   whether or not they were still steering it at the end. */
const PLAYER_TAGS = DATA.tags.filter(t =>
  DATA.dates.some(d => ((DATA.facts[d] || {})[t] || {}).is_player));

function tagPickerCfg(selected, onChange, dateOf) {
  return {
    items: DATA.tags,
    labelFor: t => t,
    subLabelFor: t => nameOf(t) === t ? '' : nameOf(t),
    colourFor,
    selected,
    noun: 'nations',
    available: dateOf ? () => tagsAt(dateOf()) : null,
    fallback: dateOf ? () => biggestAt(dateOf(), 'total_pop', 1) : null,
    presets: [
      ...(PLAYER_TAGS.length ? [['Players', () => dateOf
        ? PLAYER_TAGS.filter(t => tagsAt(dateOf()).includes(t)) : PLAYER_TAGS]] : []),
      ['Great powers', () => greatPowersNear(dateOf ? dateOf() : DATA.lastDate)],
      ['Top 8 by pop', () => dateOf ? biggestAt(dateOf(), 'total_pop', 8)
        : [...DATA.tags].sort((a, b) =>
            (DATA.series[b].total_pop[DATA.dates.length - 1] || 0) -
            (DATA.series[a].total_pop[DATA.dates.length - 1] || 0)).slice(0, 8)],
      ['All', () => dateOf ? tagsAt(dateOf()) : DATA.tags],
      ['None', () => []],
    ],
    onChange,
  };
}

/* The same idea for a plain <select>: options the save does not have are hidden
   rather than removed, so the search box beside them keeps working and the list
   does not have to be rebuilt every time the date moves. */
function limitSelect(select, allowed, fallback) {
  if (!select) return;
  const ok = new Set(allowed);
  let first = null;
  for (const o of select.options) {
    const on = ok.has(o.value);
    o.dataset.off = on ? '' : '1';
    o.hidden = !on;
    if (on && first === null) first = o.value;
  }
  if (ok.size && !ok.has(select.value)) select.value = fallback || first;
}
DATA.lastDate = DATA.dates[DATA.dates.length - 1];

/* =============== fleet power ===============
   How much a hull is worth in a fight, after Boltun's reading of the naval
   combat code. Two ships trading fire deal damage in proportion to their own
   gun power and in inverse proportion to the other's hull, and evasion throws
   away a share of the ticks aimed at it -- so asking "who out-damages whom"
   and moving each ship's terms to its own side of the comparison leaves

       power = gun power x hull / (1 - evasion)

   which is a number that can be added up over a fleet and compared. Torpedoes
   count only against a big ship, so they are a second power level rather than
   part of the first. The stats are the mod's own, upgraded by the inventions
   each nation actually rolled; without a mod folder there are no unit files
   and the whole measure is unavailable. */
const NAVAL = DATA.naval || null;
const navalStats = (tag, date) => {
  if (!NAVAL) return null;
  const idx = (NAVAL.of[tag] || {})[date];
  return idx === undefined ? null : NAVAL.profiles[idx];
};
const shipPower = (stats, vsHeavy) => !stats ? 0
  : (stats.gun_power + (vsHeavy ? stats.torpedo_attack : 0))
    * stats.hull / (1 - stats.evasion);
/** What one hull of this type is worth to this nation at this date. */
function shipPowerOf(tag, date, type, vsHeavy) {
  const stats = navalStats(tag, date);
  return stats && stats[type] ? shipPower(stats[type], vsHeavy) : 0;
}
/** Every hull a side has, added up.

    `atStrength` asks for the fleet as it stands rather than as it was drawn:
    the damage formula multiplies by the firing ship's strength and divides by
    one minus the target's experience, and rearranging the duel leaves both on
    their owner's side. Boltun holds them equal because he is ranking ship
    designs -- "all ships have the same experience... strength is maxed at
    100%" -- which is right for that question and not for this one. A fleet at
    half strength fights at half strength, and a veteran one above its paper
    figure; `crews` carries the sum of `strength / (1 - experience)` over the
    hulls of each type, and is absent wherever it comes to the count. */
function fleetPower(tags, date, vsHeavy, atStrength) {
  let total = 0;
  tags.forEach(tag => {
    const at = (DATA.ships[tag] || {})[date] || {};
    const crew = atStrength ? (DATA.crews[tag] || {})[date] || {} : null;
    for (const type in at) {
      const hulls = crew && crew[type] !== undefined ? crew[type] : at[type];
      total += shipPowerOf(tag, date, type, vsHeavy) * hulls;
    }
  });
  return total;
}
/** Whether any hull on either side carries a torpedo, which is the only thing
    that makes the second power level differ from the first. */
function torpedoesAbout(tags, date) {
  return tags.some(tag => {
    const stats = navalStats(tag, date);
    const at = (DATA.ships[tag] || {})[date] || {};
    return stats && Object.keys(at).some(t => stats[t] && stats[t].torpedo_attack > 0);
  });
}
const fmtPower = v => !v ? '0'
  : v >= 100 ? Math.round(v).toLocaleString()
  : v >= 10 ? v.toFixed(1) : v.toFixed(2);

// A nation's flag as the payload carries it: the one `key` names (the great
// powers' cards name the flag of their government), else its usual one,
// else ''.
function flagSrc(tag, key) {
  return (key && DATA.flags[key]) || DATA.flags[tag + '|'] || '';
}

// The flag as an image, or a nation-colour swatch when the report has none.
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

const shipCount = (tag, date, type) => {
  const at = (DATA.ships[tag] || {})[date];
  if (!at) return undefined;
  if (type === '__all') return Object.values(at).reduce((a, b) => a + b, 0);
  return at[type];
};
