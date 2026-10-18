// The CSV tables, each written whole or named as refused.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::*;
use crate::engine::finish::csv_line;

/// One CSV file: its heading, then `body`. False when it could not be
/// opened for writing (a table open in Excel, on Windows).
pub(super) fn write_table(path: &std::path::Path, columns: &[&str], body: impl FnOnce(&mut dyn Write) -> std::io::Result<()>) -> Result<(), std::io::Error> {
    let f = std::fs::File::create(path)?;
    let mut w = std::io::BufWriter::with_capacity(1 << 20, f);
    let mut head = String::new();
    for (i, c) in columns.iter().enumerate() {
        if i > 0 {
            head.push(',');
        }
        push_csv_field(&mut head, c);
    }
    head.push_str("\r\n");
    w.write_all(head.as_bytes())?;
    body(&mut w)?;
    w.flush()
}

/// Whether a table could not be opened because something else holds it:
/// Python's `PermissionError`. On Windows that is a sharing or lock
/// violation as well as a denied access -- a table open in Excel fails with
/// the first (32), which Rust does not call `PermissionDenied`, and which
/// Python's C runtime reports as `EACCES`.
pub(super) fn held_elsewhere(e: &std::io::Error) -> bool {
    if e.kind() == std::io::ErrorKind::PermissionDenied {
        return true;
    }
    cfg!(windows) && matches!(e.raw_os_error(), Some(32) | Some(33))
}

/// A CSV table: one of the per-save tables finishing wrote (by its place in
/// `Tables::per_save`), or one of the two the campaign's market makes.
enum Table {
    PerSave(usize),
    Prices,
    Snapshot,
}

/// Every CSV table: (the paths written, the paths refused, what else failed).
/// A failure is said by the caller once the page is on disk, rather than
/// ending the process from this thread while the page is being written.
pub(super) fn write_outputs(out: &str, c: &Campaign, prices: &[PriceRow], snaps: &[SnapRow],
                 t: &Tables) -> (Vec<String>, Vec<String>, Vec<String>) {
    let mut paths = Vec::new();
    let mut refused = Vec::new();
    let mut failed = Vec::new();
    // `per_save[:1] + [prices, snapshot] + per_save[1:]`, as `write_outputs` orders them.
    let mut order: Vec<(Table, &str, &Vec<String>)> = vec![
        (Table::PerSave(0), &t.per_save[0].0, &t.per_save[0].1),
        (Table::Prices, "prices.csv", &t.price_columns),
        (Table::Snapshot, "market_snapshot.csv", &t.snapshot_columns)];
    for (k, (name, cols)) in t.per_save.iter().enumerate().skip(1) {
        order.push((Table::PerSave(k), name, cols));
    }
    for (k, name, cols) in order {
        let refs: Vec<&str> = cols.iter().map(|s| s.as_str()).collect();
        let path = std::path::Path::new(out).join(name);
        let got = write_table(&path, &refs, |w| {
            match k {
                Table::Prices => {
                    let mut s = String::with_capacity(1 << 20);
                    for (d, y, g, cat, p) in prices {
                        let vals = [Val::S(d), Val::S(y), Val::S(g), Val::S(cat), Val::F(*p)];
                        csv_line(&mut s, &vals);
                        if s.len() > 1 << 20 {
                            w.write_all(s.as_bytes())?;
                            s.clear();
                        }
                    }
                    w.write_all(s.as_bytes())
                }
                Table::Snapshot => {
                    let mut s = String::with_capacity(1 << 20);
                    for r in snaps {
                        let vals = [Val::S(&r.date), Val::S(&r.year), Val::S(&r.good),
                                    Val::S(r.category), Val::F(r.price), Val::F(r.world_pool),
                                    Val::F(r.supply), Val::F(r.demand), Val::F(r.real_demand),
                                    Val::F(r.actual_sold), Val::I(r.discovered)];
                        csv_line(&mut s, &vals);
                    }
                    w.write_all(s.as_bytes())
                }
                Table::PerSave(k) => {
                    for chunk in &c.text[k] {
                        w.write_all(chunk.as_bytes())?;
                    }
                    Ok(())
                }
            }
        });
        let shown = path.to_string_lossy().to_string();
        match got {
            Ok(()) => paths.push(shown),
            Err(e) if held_elsewhere(&e) => refused.push(shown),
            Err(e) => failed.push(format!("cannot write {}: {}", shown, e)),
        }
    }
    (paths, refused, failed)
}

