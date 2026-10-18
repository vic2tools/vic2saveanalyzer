// The report page, joined from the files under `src/page/` in the order
// `src/page/order.txt` names them, and built into the scanner. And this
// build's identity: a hash of every source file that went into it, which is
// what the engine's caches and the report stamp name the program by.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use std::path::{Path, PathBuf};

fn main() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let page_dir = root.join("src").join("page");
    let out = Path::new(&std::env::var("OUT_DIR").unwrap()).join("template.html");
    std::fs::write(out, page(&page_dir)).unwrap();

    // Every file under src/ -- the page included -- in name order, with its
    // path, and the manifest beside them. A new build of the same sources
    // gets the same name; any change to them, a new one -- unlike a file's
    // size and time, which a frozen executable changes on every launch.
    let mut files = vec![root.join("Cargo.toml"), root.join("build.rs")];
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

/// The page: `order.txt`'s files joined in its order. A file under `src/page/`
/// it does not name, or names twice, stops the build -- a page file nothing
/// includes would be a change that is silently not there.
fn page(dir: &Path) -> String {
    let order = std::fs::read_to_string(dir.join("order.txt"))
        .unwrap_or_else(|e| panic!("cannot read src/page/order.txt: {}", e));
    let mut named: Vec<String> = Vec::new();
    for line in order.lines().map(str::trim) {
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if named.iter().any(|n| n == line) {
            panic!("src/page/order.txt names {} twice", line);
        }
        named.push(line.to_string());
    }
    let mut present = Vec::new();
    walk(dir, &mut present);
    for p in &present {
        let rel = p.strip_prefix(dir).unwrap().to_string_lossy().replace('\\', "/");
        if rel != "order.txt" && !named.contains(&rel) {
            panic!("src/page/{} is not named in src/page/order.txt", rel);
        }
    }
    let mut text = String::new();
    for name in &named {
        let path = dir.join(name);
        println!("cargo:rerun-if-changed={}", path.display());
        let body = std::fs::read_to_string(&path)
            .unwrap_or_else(|e| panic!("cannot read src/page/{}: {}", name, e));
        // Joined as they are: a missing last newline would run this file's
        // last line into the next file's first, and a BOM or a CR would land
        // in the middle of the page.
        if !body.ends_with('\n') || body.starts_with('\u{feff}') || body.contains('\r') {
            panic!("src/page/{} must be UTF-8 without a BOM, with LF line ends, \
                    ending in a newline", name);
        }
        text += &body;
    }
    text
}

fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    for e in std::fs::read_dir(dir).unwrap() {
        let p = e.unwrap().path();
        if p.is_dir() {
            walk(&p, out);
        } else {
            out.push(p);
        }
    }
}
