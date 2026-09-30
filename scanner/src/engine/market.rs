// The world market across a campaign: `market.py`.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use crate::engine::dates::date_key;
use crate::engine::tables::Tables;
use crate::engine::model::Meta;
use crate::omap::OMap;
use crate::pickle::FxSet;
use crate::pyfmt::round;



/// (date, year, good, category, price)
pub type PriceRow<'a> = (String, String, String, &'a str, f64);

fn year_of(stamp: &str) -> String {
    stamp.split('.').next().unwrap_or("").to_string()
}

/// `merge_prices(parsed)`: every save's rolling buffer stitched into one
/// series, the newest save's reading of a month standing.
pub fn merge_prices<'a>(metas: &[&Meta], t: &'a Tables) -> Vec<PriceRow<'a>> {
    let mut prices: OMap<String, OMap<String, f64>> = OMap::new();
    for meta in metas.iter().rev() {
        let market = match &meta.market {
            Some(m) => m,
            None => continue,
        };
        {
            let day = prices.entry(meta.date.clone(), OMap::new);
            for (good, price) in market.current.iter() {
                if !day.contains_key(good.as_str()) {
                    day.set(good.clone(), *price);
                }
            }
        }
        for (stamp, good, price) in &market.history {
            let day = prices.entry(stamp.clone(), OMap::new);
            if !day.contains_key(good.as_str()) {
                day.set(good.clone(), *price);
            }
        }
    }
    let mut stamps: Vec<&String> = prices.keys().collect();
    stamps.sort_by(|a, b| date_key(a).cmp(&date_key(b)));
    let keys: Vec<Vec<i64>> = stamps.iter().map(|s| date_key(s)).collect();
    if keys.windows(2).any(|w| w[0] == w[1]) {
        return by_pair(metas, t);
    }
    let mut rows = Vec::new();
    for stamp in stamps {
        let day = prices.get(stamp.as_str()).unwrap();
        let year = year_of(stamp);
        let mut goods: Vec<&String> = day.keys().collect();
        goods.sort();
        for good in goods {
            rows.push((stamp.clone(), year.clone(), good.clone(), t.category(good),
                       round(*day.get(good.as_str()).unwrap(), 5)));
        }
    }
    rows
}

/// `_price_rows_by_pair`: the old way, for two spellings of one date.
fn by_pair<'a>(metas: &[&Meta], t: &'a Tables) -> Vec<PriceRow<'a>> {
    let mut prices: OMap<(String, String), f64> = OMap::new();
    for meta in metas.iter().rev() {
        let market = match &meta.market {
            Some(m) => m,
            None => continue,
        };
        for (good, price) in market.current.iter() {
            prices.entry((meta.date.clone(), good.clone()), || *price);
        }
        for (stamp, good, price) in &market.history {
            prices.entry((stamp.clone(), good.clone()), || *price);
        }
    }
    let mut rows: Vec<PriceRow> = prices.iter().map(|((stamp, good), price)| {
        (stamp.clone(), year_of(stamp), good.clone(), t.category(good), round(*price, 5))
    }).collect();
    rows.sort_by(|a, b| date_key(&a.0).cmp(&date_key(&b.0)).then(a.2.cmp(&b.2)));
    rows
}

/// One row of `market_snapshot.csv`.
pub struct SnapRow<'a> {
    pub date: String,
    pub year: String,
    pub good: String,
    pub category: &'a str,
    pub price: f64,
    pub world_pool: f64,
    pub supply: f64,
    pub demand: f64,
    pub real_demand: f64,
    pub actual_sold: f64,
    pub discovered: i64,
}

/// `market_snapshot_rows(parsed)`.
pub fn snapshot_rows<'a>(metas: &[&Meta], t: &'a Tables) -> Vec<SnapRow<'a>> {
    let mut rows = Vec::new();
    for meta in metas {
        let market = match &meta.market {
            Some(m) => m,
            None => continue,
        };
        let snap = &market.snapshot;
        let mut goods: FxSet<&String> = market.current.keys().collect();
        for field in snap.iter() {
            goods.extend(field.keys());
        }
        let mut goods: Vec<&String> = goods.into_iter().collect();
        goods.sort();
        let get = |i: usize, g: &str| snap[i].get(g).copied().unwrap_or(0.0);
        for good in goods {
            rows.push(SnapRow {
                date: meta.date.clone(),
                year: year_of(&meta.date),
                good: good.clone(),
                category: t.category(good),
                price: round(market.current.get(good.as_str()).copied().unwrap_or(0.0), 5),
                world_pool: round(get(0, good), 3),
                supply: round(get(1, good), 3),
                demand: round(get(2, good), 3),
                real_demand: round(get(3, good), 3),
                actual_sold: round(get(4, good), 3),
                discovered: (get(6, good) > 0.0) as i64,
            });
        }
    }
    rows
}
