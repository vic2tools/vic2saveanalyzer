// The report's declarations -- its columns, its measures, its colours, the
// page itself -- as the analyzer's Python declares them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// They arrive in the run's spec (`engine.spec`), so an edit to `report.py`'s
// measures, `spending.py`'s columns or `template.py`'s page reaches the
// engine as it reaches the Python, with no rebuild and no second copy to
// forget. What is written here is only what a spec without them gets.

use crate::jsonr::J;
use crate::fx::FxMap;

pub struct Tables {
    /// (key, label, format)
    pub metrics: Vec<(String, String, String)>,
    /// (key, the measure it is the growth of, label)
    pub growth: Vec<(String, String, String)>,
    pub gain: Vec<(String, String, String)>,
    pub colours: Vec<String>,
    pub category_labels: Vec<(String, String)>,
    pub growth_span: f64,
    pub supply_named: usize,
    pub good_category: FxMap<String, String>,
    pub price_columns: Vec<String>,
    pub snapshot_columns: Vec<String>,
    /// The six tables every save writes into, and their columns.
    pub per_save: Vec<(String, Vec<String>)>,
    /// `readsave.STRATA`: (stratum, its vanilla pop types)
    pub strata: Vec<(String, Vec<String>)>,
    pub template: String,
}

const METRICS: [(&str, &str, &str); 36] = [
    ("total_pop", "Total population", "count"),
    ("accepted_pop", "Accepted-culture population", "count"),
    ("accepted_pct", "Accepted share", "percent"),
    ("primary_culture_pop", "Primary-culture population", "count"),
    ("avg_literacy", "Average literacy", "fraction"),
    ("avg_literacy_stated", "Literacy in own states", "fraction"),
    ("life_unmet", "Population with life needs unmet", "count"),
    ("life_unmet_pct", "Life needs unmet", "percent"),
    ("starving", "Starving population", "count"),
    ("starving_pct", "Starving share", "percent"),
    ("brigades", "Brigades (all)", "count"),
    ("regular_brigades", "Standing brigades", "count"),
    ("mobilized_brigades", "Mobilized brigades", "count"),
    ("mobilizing", "Mobilizing (queued)", "count"),
    ("brigade_cap", "Brigade cap", "count"),
    ("mobilization_pool", "Mobilizable population", "count"),
    ("mobilization_brigades", "Mobilization ceiling", "count"),
    ("ships", "Ships", "count"),
    ("factory_levels", "Factory levels", "count"),
    ("factory_count", "Factories", "count"),
    ("naval_base_levels", "Naval base levels", "count"),
    ("ports", "Provinces with a naval base", "count"),
    ("max_naval_base", "Largest naval base", "count"),
    ("railroad_levels", "Railroad levels", "count"),
    ("techs", "Technologies", "count"),
    ("prestige", "Prestige", "count"),
    ("provinces", "Provinces", "count"),
    ("states", "States", "count"),
    ("treasury", "Treasury", "count"),
    ("tax_base", "Tax base", "count"),
    ("avg_consciousness", "Average consciousness", "decimal"),
    ("avg_militancy", "Average militancy", "decimal"),
    ("infamy", "Infamy", "decimal"),
    ("pop_poor", "Poor strata", "count"),
    ("pop_middle", "Middle strata", "count"),
    ("pop_rich", "Rich strata", "count"),
];

const BASE_COLUMNS: [&str; 60] = [
    "date", "year", "tag", "is_player", "primary_culture", "civilized",
    "provinces", "states", "total_pop", "accepted_pop", "accepted_pct",
    "primary_culture_pop", "avg_literacy", "avg_literacy_stated",
    "pop_noncolonial", "avg_consciousness", "avg_militancy",
    "brigades", "regular_brigades", "mobilized_brigades", "mobilizing",
    "brigade_cap",
    "is_mobilized", "armies", "ships", "navies",
    "factory_count", "factory_levels", "ports", "naval_base_levels",
    "max_naval_base", "railroad_levels", "fort_levels",
    "mobilisation_size", "mobilization_pool", "mobilization_pops",
    "mobilization_brigades", "mobilization_cap",
    "mobilization_available", "mobilization_remaining", "war_policy",
    "techs", "army_techs", "navy_techs", "prestige", "infamy", "treasury", "tax_base",
    "research_points", "war_exhaustion", "plurality",
    "pop_poor", "pop_middle", "pop_rich",
    "soldiers_noncolonial", "soldiers_noncolonial_pct",
    "life_unmet", "life_unmet_pct", "starving", "starving_pct",
];

fn strs(v: &J) -> Vec<String> {
    v.list().iter().map(|x| x.str().to_string()).collect()
}

fn triples(v: &J) -> Vec<(String, String, String)> {
    v.list().iter().map(|t| {
        let t = t.list();
        (t[0].str().to_string(), t[1].str().to_string(), t[2].str().to_string())
    }).collect()
}

fn owned(v: &[(&str, &str, &str)]) -> Vec<(String, String, String)> {
    v.iter().map(|(a, b, c)| (a.to_string(), b.to_string(), c.to_string())).collect()
}

impl Tables {
    /// The spec's tables, or the built-in ones where it has none.
    pub fn from_spec(spec: &J, pop_columns: &[String]) -> Tables {
        let t = spec.at("tables");
        let template = match spec.at("template").as_str() {
            Some(s) => s.to_string(),
            None => include_str!(concat!(env!("OUT_DIR"), "/template.html")).to_string(),
        };
        if t.is_null() {
            return Tables::builtin(pop_columns, template);
        }
        let mut good_category = FxMap::default();
        for (cat, goods) in t.at("good_categories").pairs() {
            for g in goods.list() {
                good_category.insert(g.str().to_string(), cat.clone());
            }
        }
        Tables {
            metrics: triples(t.at("metrics")),
            growth: triples(t.at("growth")),
            gain: triples(t.at("gain")),
            colours: strs(t.at("colours")),
            category_labels: t.at("category_labels").pairs().iter()
                .map(|(k, v)| (k.clone(), v.str().to_string())).collect(),
            growth_span: t.at("growth_span").float(),
            supply_named: t.at("supply_named").int().max(0) as usize,
            good_category,
            price_columns: strs(t.at("price_columns")),
            snapshot_columns: strs(t.at("snapshot_columns")),
            per_save: t.at("per_save").list().iter()
                .map(|p| (p.list()[0].str().to_string(), strs(&p.list()[1]))).collect(),
            strata: t.at("strata").pairs().iter().map(|(k, v)| (k.clone(), strs(v))).collect(),
            template,
        }
    }

    pub fn builtin(pop_columns: &[String], template: String) -> Tables {
        let main: Vec<String> = BASE_COLUMNS.iter().map(|s| s.to_string())
            .chain(pop_columns.iter().map(|t| format!("pop_{}", t)))
            .chain(std::iter::once("accepted_cultures".to_string())).collect();
        let cols = |v: &[&str]| v.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        let mut good_category = FxMap::default();
        for (cat, goods) in [
            ("military", &["ammunition", "small_arms", "artillery", "canned_food", "barrels",
                           "tanks", "aeroplanes"][..]),
            ("raw", &["cattle", "coal", "cotton", "dye", "fish", "fruit", "grain", "iron", "oil",
                      "opium", "precious_metal", "rubber", "silk", "sulphur", "tea", "timber",
                      "tobacco", "tropical_wood", "wool", "coffee"][..]),
            ("industrial", &["cement", "clipper_convoy", "electric_gear", "explosives", "fabric",
                             "fertilizer", "fuel", "glass", "lumber", "machine_parts", "paper",
                             "steamer_convoy", "steel"][..]),
            ("consumer", &["automobiles", "furniture", "liquor", "luxury_clothes",
                           "luxury_furniture", "radio", "regular_clothes", "telephones",
                           "wine"][..]),
        ] {
            for g in goods {
                good_category.insert(g.to_string(), cat.to_string());
            }
        }
        Tables {
            metrics: owned(&METRICS),
            growth: owned(&[("pop_growth", "total_pop", "Population growth (%/yr)"),
                            ("accepted_growth", "accepted_pop", "Accepted-culture growth (%/yr)")]),
            gain: owned(&[("pop_gain", "total_pop", "Population gain (per save)"),
                          ("accepted_gain", "accepted_pop", "Accepted-culture gain (per save)")]),
            colours: cols(&["#E7C464", "#D4553F", "#8FB98C", "#8FA8C8", "#D48FA8", "#B5A85C",
                            "#B48FC0", "#EADFC2", "#6FA8A0", "#E09A4C", "#9BAF6F", "#A87FA0"]),
            category_labels: [("military", "Military"), ("industrial", "Industrial"),
                              ("raw", "Raw materials"), ("consumer", "Consumer"),
                              ("other", "Other")].iter()
                .map(|(k, v)| (k.to_string(), v.to_string())).collect(),
            growth_span: 0.25,
            supply_named: 14,
            good_category,
            price_columns: cols(&["date", "year", "good", "category", "price"]),
            snapshot_columns: cols(&["date", "year", "good", "category", "price", "world_pool",
                                     "supply", "demand", "real_demand", "actual_sold",
                                     "discovered"]),
            per_save: vec![
                ("nations_timeseries.csv".into(), main),
                ("ships_by_type.csv".into(),
                 cols(&["date", "year", "tag", "ship_type", "count", "effective"])),
                ("brigades_by_type.csv".into(),
                 cols(&["date", "year", "tag", "regiment_type", "count"])),
                ("technologies.csv".into(),
                 cols(&["date", "year", "tag", "technology", "branch", "line"])),
                ("pops_by_type.csv".into(), cols(&["date", "year", "tag", "pop_type", "size"])),
                ("pops_by_culture.csv".into(),
                 cols(&["date", "year", "tag", "culture", "size", "accepted"])),
            ],
            strata: vec![
                ("poor".into(), cols(&["farmers", "labourers", "slaves", "soldiers", "craftsmen"])),
                ("middle".into(), cols(&["artisans", "bureaucrats", "clergymen", "clerks",
                                         "officers"])),
                ("rich".into(), cols(&["aristocrats", "capitalists"])),
            ],
            template,
        }
    }

    /// `GOOD_CATEGORY.get(good, "other")`.
    pub fn category<'a>(&'a self, good: &str) -> &'a str {
        self.good_category.get(good).map(|s| s.as_str()).unwrap_or("other")
    }
}
