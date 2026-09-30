// What the engine made of each save, as JSON, for a check to hold against
// what the analyzer's Python made of it (`~/.cache/vic2speed/rw/dumpcheck.py`).
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Each piece is written as `json.dumps(piece, separators=(",", ":"))` would
// write the Python's, so the two can be compared as text: key order, and an
// int against a float, count.

use crate::engine::finish::{Kept, Spent};
use crate::engine::model::{Market, Meta, SNAPSHOT_FIELDS};
use crate::omap::OMap;
use crate::pickle::FxSet;
use crate::pyfmt::{push_int, push_json_float, push_json_str};
use crate::engine::rules::{Mod, SHIP_KEYS};
use std::io::Write;

pub fn obj<'a, V: 'a>(out: &mut String, pairs: impl Iterator<Item = (&'a str, V)>,
                      mut value: impl FnMut(&mut String, V)) {
    out.push('{');
    for (i, (k, v)) in pairs.enumerate() {
        if i > 0 {
            out.push(',');
        }
        push_json_str(out, k);
        out.push(':');
        value(out, v);
    }
    out.push('}');
}

pub fn int_keyed<V>(out: &mut String, m: &OMap<i64, V>, mut value: impl FnMut(&mut String, &V)) {
    out.push('{');
    for (i, (k, v)) in m.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push('"');
        push_int(out, *k);
        out.push_str("\":");
        value(out, v);
    }
    out.push('}');
}

fn str_list(out: &mut String, v: &[String]) {
    out.push('[');
    for (i, s) in v.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        push_json_str(out, s);
    }
    out.push(']');
}

fn counts(out: &mut String, m: &OMap<String, i64>) {
    obj(out, m.iter().map(|(k, v)| (k.as_str(), *v)), |o, v| push_int(o, v));
}

fn market(out: &mut String, m: &Market) {
    out.push_str("{\"current\":");
    obj(out, m.current.iter().map(|(k, v)| (k.as_str(), *v)), |o, v| push_json_float(o, v));
    out.push_str(",\"history\":[");
    for (i, (d, g, p)) in m.history.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push('[');
        push_json_str(out, d);
        out.push(',');
        push_json_str(out, g);
        out.push(',');
        push_json_float(out, *p);
        out.push(']');
    }
    out.push_str("],\"snapshot\":{");
    for (i, name) in SNAPSHOT_FIELDS.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        push_json_str(out, name);
        out.push(':');
        obj(out, m.snapshot[i].iter().map(|(k, v)| (k.as_str(), *v)), |o, v| push_json_float(o, v));
    }
    out.push_str("}}");
}

pub fn meta(out: &mut String, m: &Meta) {
    out.push_str("{\"date\":");
    push_json_str(out, &m.date);
    out.push_str(",\"player\":");
    push_json_str(out, &m.player);
    out.push_str(",\"file\":");
    push_json_str(out, &m.file);
    out.push_str(",\"province_owner\":{");
    for (i, (pid, o, c)) in m.province_owner.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push('"');
        push_int(out, *pid);
        out.push_str("\":[");
        push_json_str(out, o);
        out.push(',');
        push_json_str(out, c);
        out.push(']');
    }
    out.push_str("},\"great_nations\":[");
    for (i, g) in m.great_nations.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        push_int(out, *g);
    }
    out.push_str("],\"world_pop\":");
    push_int(out, m.world_pop);
    out.push_str(",\"market\":");
    match &m.market {
        Some(mk) => market(out, mk),
        None => out.push_str("null"),
    }
    out.push('}');
}

fn kept(out: &mut String, k: &Kept) {
    out.push_str("{\"units_at\":");
    int_keyed(out, &k.units_at, counts);
    out.push_str(",\"men_at\":");
    int_keyed(out, &k.men_at, counts);
    out.push_str(",\"primary_culture\":");
    push_json_str(out, &k.primary_culture);
    out.push_str(",\"accepted_cultures\":");
    str_list(out, &k.accepted_cultures);
    out.push_str(",\"government\":");
    push_json_str(out, &k.government);
    out.push_str(",\"total_pop\":");
    push_int(out, k.total_pop);
    if let Some(p) = k.is_player {
        out.push_str(",\"is_player\":");
        out.push_str(if p { "true" } else { "false" });
    }
    out.push_str(",\"capital\":");
    push_json_str(out, &k.capital);
    out.push('}');
}

pub fn write(folder: &str, spent: &[Spent], m: &Mod, live: &FxSet<String>) {
    std::fs::create_dir_all(folder).unwrap();
    let mut f = std::io::BufWriter::new(std::fs::File::create(format!("{}/rust.jsonl", folder)).unwrap());
    let mut head = String::from("{\"live\":");
    let mut l: Vec<String> = live.iter().cloned().collect();
    l.sort();
    str_list(&mut head, &l);
    head.push_str(",\"index_base\":");
    match m.index_base {
        Some(b) => push_int(&mut head, b),
        None => head.push_str("null"),
    }
    head.push('}');
    writeln!(f, "{}", head).unwrap();
    for s in spent {
        let mut out = String::with_capacity(1 << 20);
        out.push_str("{\"date\":");
        push_json_str(&mut out, &s.meta.date);
        out.push_str(",\"text\":[");
        for (i, t) in s.text.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            push_json_str(&mut out, t);
        }
        out.push_str("],\"tables\":{\"ships\":");
        obj(&mut out, s.tables.ships.iter().map(|(t, v)| (t.as_str(), v)), |o, v| {
            obj(o, v.iter().map(|(k, n)| (k.as_str(), *n)), |o, n| push_int(o, n))
        });
        out.push_str(",\"crews\":");
        obj(&mut out, s.tables.crews.iter().map(|(t, v)| (t.as_str(), v)), |o, v| {
            obj(o, v.iter().map(|(k, n)| (k.as_str(), *n)), |o, n| push_json_float(o, n))
        });
        out.push_str(",\"brigades\":");
        obj(&mut out, s.tables.brigades.iter().map(|(t, v)| (t.as_str(), v)), |o, v| {
            obj(o, v.iter().map(|(k, n)| (k.as_str(), *n)), |o, n| push_int(o, n))
        });
        out.push_str(",\"techs\":");
        obj(&mut out, s.tables.techs.iter().map(|(t, v)| (t.as_str(), v)), |o, v| str_list(o, v));
        out.push_str(",\"pops\":");
        obj(&mut out, s.tables.pops.iter().map(|(t, v)| (t.as_str(), v)), |o, v| {
            obj(o, v.iter().map(|(k, n)| (k.as_str(), *n)), |o, n| push_int(o, n))
        });
        out.push_str(",\"cultures\":");
        obj(&mut out, s.tables.cultures.iter().map(|(t, v)| (t.as_str(), v)), |o, v| {
            o.push('[');
            for (i, (c, n, a)) in v.iter().enumerate() {
                if i > 0 {
                    o.push(',');
                }
                o.push('[');
                push_json_str(o, c);
                o.push(',');
                push_int(o, *n);
                o.push(',');
                push_int(o, *a);
                o.push(']');
            }
            o.push(']');
        });
        out.push_str("},\"naval\":[");
        for (i, (tag, _key, profile)) in s.naval.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push('[');
            push_json_str(&mut out, tag);
            out.push(',');
            obj(&mut out, profile.iter().map(|(n, st, h)| (n.as_str(), (st, h))), |o, (st, h)| {
                o.push('{');
                for (k, key) in SHIP_KEYS.iter().enumerate() {
                    push_json_str(o, key);
                    o.push(':');
                    push_json_float(o, st[k]);
                    o.push(',');
                }
                o.push_str("\"heavy\":");
                push_int(o, *h);
                o.push('}');
            });
            out.push(']');
        }
        out.push_str("],\"supply\":[");
        for (i, (g, t, a)) in s.supply.iter().enumerate() {
            if i > 0 {
                out.push(',');
            }
            out.push('[');
            push_json_str(&mut out, g);
            out.push(',');
            push_json_str(&mut out, t);
            out.push(',');
            push_json_float(&mut out, *a);
            out.push(']');
        }
        out.push_str("],\"meta\":");
        meta(&mut out, &s.meta);
        out.push_str(",\"nations\":");
        obj(&mut out, s.nations.iter().map(|k| (k.tag.as_str(), k)), kept);
        out.push_str(",\"chunk\":");
        push_json_str(&mut out, &s.chunk);
        out.push('}');
        writeln!(f, "{}", out).unwrap();
    }
}
