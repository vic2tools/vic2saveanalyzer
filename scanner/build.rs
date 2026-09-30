// The report page, taken out of `template.py` at build time, so the page
// has one source: the Python writes it from there, and so does the engine.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use std::path::Path;

fn main() {
    let source = Path::new(env!("CARGO_MANIFEST_DIR")).join("..").join("template.py");
    println!("cargo:rerun-if-changed={}", source.display());
    let text = std::fs::read_to_string(&source)
        .unwrap_or_else(|e| panic!("cannot read {}: {}", source.display(), e));
    // `TEMPLATE = r"""...""" `: a raw string, so what is between the quotes
    // is the page as it stands.
    let open = "TEMPLATE = r\"\"\"";
    let start = text.find(open).expect("no TEMPLATE in template.py") + open.len();
    let end = start + text[start..].find("\"\"\"").expect("TEMPLATE is not closed");
    let out = Path::new(&std::env::var("OUT_DIR").unwrap()).join("template.html");
    std::fs::write(out, &text[start..end]).unwrap();
}
