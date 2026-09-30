// The report page, taken out of `template.py` at build time, so the page
// has one source: the Python writes it from there, and so does the engine.
// And this build's identity: a hash of every source file that went into it,
// which is what the engine's caches and the report stamp name the program by.
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

    // Every file under src/, in name order, with its path, and the page
    // and the manifest beside them. A new build of the same sources gets
    // the same name; any change to them, a new one -- unlike a file's size
    // and time, which a frozen executable changes on every launch.
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let mut files = vec![source.clone(), root.join("Cargo.toml"), root.join("build.rs")];
    walk(&root.join("src"), &mut files);
    files.sort();
    let (mut a, mut b) = (0xcbf2_9ce4_8422_2325u64, 0x8422_2325_cbf2_9ce4u64);
    for f in &files {
        let name = f.strip_prefix(root).unwrap_or(f).to_string_lossy().replace('\\', "/");
        let body = std::fs::read(f).unwrap_or_default();
        for &c in name.as_bytes().iter().chain(b"\0").chain(body.iter()).chain(b"\0") {
            a = (a ^ c as u64).wrapping_mul(0x0000_0100_0000_01b3);
            b = (b.rotate_left(5) ^ c as u64).wrapping_mul(0x51_7c_c1_b7_27_22_0a_95);
        }
    }
    println!("cargo:rerun-if-changed=src");
    println!("cargo:rerun-if-changed=Cargo.toml");
    println!("cargo:rustc-env=VIC2_BUILD_ID={:016x}{:016x}", a, b);
}

fn walk(dir: &Path, out: &mut Vec<std::path::PathBuf>) {
    for e in std::fs::read_dir(dir).unwrap() {
        let p = e.unwrap().path();
        if p.is_dir() {
            walk(&p, out);
        } else {
            out.push(p);
        }
    }
}
