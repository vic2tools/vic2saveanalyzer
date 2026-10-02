// The Victoria 2 campaign analyzer's scanner: every run, from the saves to
// the report.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
//     vic2scan analyze --run RUN.json ...   a run, as the launcher hands it
//                                           over (`front`)
//     vic2scan mod-export MOD               the mod folder as JSON
//     vic2scan mod-signature MOD            what keys a mod's read
//     vic2scan bench-engine RUN.json [N]    pass one's parts, timed
//     vic2scan selftest-...                 what the checks hold the parts to
//
// The rules the readers follow are not this program's own. They are the
// Python's it replaced, reproduced exactly on purpose: the pop culture found
// by elimination, `int(float(x))` truncation, a building level read from
// either a bare pair or a dict. Where they look strange, that is why, and
// the recorded answers in `testkit/expected/` hold them to it.

mod clause;
mod country;
mod deflate;
mod engine;
mod front;
mod fx;
mod jsonr;
mod md5;
mod omap;
mod province;
mod pyfmt;
mod pyre;
mod text;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("analyze") => front::main(&args),
        Some("mod-export") if args.len() == 3 => engine::modread::main(&args),
        Some("mod-signature") => front::signature_main(&args),
        Some("bench-engine") => engine::bench(&args),
        Some("selftest-fmt") => pyfmt::selftest(),
        Some("selftest-sniff") => front::cross::selftest(&args[2..]),
        Some("selftest-re") => pyre::selftest(),
        Some("selftest-deflate") if args.len() == 4 => deflate::selftest(&args[2], &args[3]),
        _ => {
            eprintln!("usage: vic2scan analyze --run RUN.json [--refused FILE] [--protocol]\n\
                       \x20      vic2scan mod-export MOD | mod-signature MOD");
            std::process::exit(2);
        }
    }
}
