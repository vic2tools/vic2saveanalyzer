# Prices come out of the save with real history

Prices and who supplied what: where the Market tab's numbers come from.

Unlike almost everything else, prices are not snapshot-only. Each save carries a
rolling buffer of **36 monthly price readings** for every good, in repeated
`price_history` blocks under `worldmarket`, stamped by
`price_history_last_update`. So one save yields three years of monthly prices,
and a run of saves stitches into a continuous series — buffers from consecutive
saves overlap heavily, and duplicates collapse on (date, good).

The interval is one month rather than one day: the `price_change` block caps
daily movement at about 0.01, while consecutive history entries differ by up to
0.30.

`prices.csv` is `date, year, good, category, price`. Categories come from a
vanilla goods list; anything a mod adds lands in `other` and still charts fine.

**Demand needs care.** Some goods carry a stored `demand` of roughly a billion
or two, which is nobody's economy: it is a standing order to buy without limit,
which mods hand a nation so raw materials always find a buyer. Every reading
carrying one, across the campaigns this was checked against, sits at exactly
five times the good's base cost -- the engine's price ceiling -- so for those
goods neither price nor demand reports on scarcity. The report flags them in a
**Pegged** column and falls back to `unsold` (supply that found no buyer at all)
as the glut signal. `market_snapshot.csv` keeps both the raw `demand` and the
honest `real_demand`; if you analyse the CSV yourself, use `real_demand` or you
will get nonsense.

Market tab controls worth knowing: **Top movers** picks the six goods that moved
most across the span, **Indexed (=100)** rebases every good to 100 at its first
reading so a 70-unit good and a 1-unit good can share an axis, and clicking a
row in the market table plots that good.

# Who supplied what

Each country block carries `saved_country_supply`: a good-by-good record of what
that nation put on the world market. It is production as the market sees it
rather than a stockpile or an income, and the check is that it adds up. Summed
over the nations that hold land in the 1908 IGoR save it comes to 41,072.85 of
grain against a world `supply_pool` of 41,072.85. Summed over *every* country
block it comes to 43,191, because a nation that no longer exists keeps the last
figure it ever had; the report only ever counts nations with population, which
is what makes the two agree.

The payload names the fourteen largest suppliers of each good at each save and
keeps the world total beside them, so the share the named ones do not account for
is still recoverable as one bar. Naming all of them for every good at every save
was most of a megabyte; fourteen is 370 KB, and the ninetieth supplier of grain
is not what makes a glut.

**A good that records no sale in any save is not traded at all.** Precious metal
is the standing case: the engine turns it into money at the mint rather than
putting it up for sale, so its supply is real and its `actual_sold` is always
nil. Read naively that is "100% unsold, for ever", which puts it at the top of
every glut list and says nothing, so those goods are left blank instead.
