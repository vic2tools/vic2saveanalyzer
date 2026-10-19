// Where a mod sits: the install it runs on, and what its .mod file says.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// In Victoria II a mod is what a `.mod` file in `<install>/mod/` says it is:
// `path` names its folder, relative to the install, and each
// `replace_path` a folder the game then takes from the mod alone. Most mods
// sit at `mod/<name>`, but nothing makes them: a mod kept as a clone of its
// repository is a level deeper, at `mod/<name>/<name>`. So a mod's install
// is the nearest install above it, however far up, and `report_tab.py`
// finds it the same way.

use super::*;
use crate::py::path as pypath;

/// What one `.mod` file says: the folder it points to, made absolute, and
/// the folders it replaces, as written.
pub struct Descriptor {
    pub path: String,
    pub replace: Vec<String>,
}

/// `_base_game_path`: the install a mod sits in, the nearest folder above
/// it that is one, or None when there isn't one. For a path already made
/// absolute.
pub fn base_game_path(path: &str) -> Option<String> {
    if path.is_empty() {
        return None;
    }
    let mut up = dirname(path);
    loop {
        if is_install(&up) {
            return Some(up);
        }
        let next = dirname(&up);
        if next == up || next.is_empty() {
            return None;
        }
        up = next;
    }
}

/// `key = value` and `key = "value"` lines, comments cut.
fn pairs(text: &[u8]) -> Vec<(String, String)> {
    let mut out = Vec::new();
    for line in text.split(|&c| c == b'\n') {
        let line = l1(line);
        let mut quoted = false;
        let cut = line.char_indices().find(|&(_, c)| {
            if c == '"' {
                quoted = !quoted;
            }
            c == '#' && !quoted
        }).map_or(line.len(), |(i, _)| i);
        let line = &line[..cut];
        let (key, value) = match line.split_once('=') {
            Some(kv) => kv,
            None => continue,
        };
        let value = value.trim();
        let value = match value.strip_prefix('"') {
            Some(rest) => rest.split('"').next().unwrap_or(""),
            None => value,
        };
        out.push((key.trim().to_lowercase(), value.to_string()));
    }
    out
}

/// Every `.mod` file in `<install>/mod/` that names a folder, in file-name
/// order.
pub fn descriptors(install: &str) -> Vec<Descriptor> {
    let home = join(install, "mod");
    let mut names: Vec<String> = match std::fs::read_dir(&home) {
        Ok(rd) => rd.flatten().filter_map(|e| e.file_name().into_string().ok())
            .filter(|n| lower(n).ends_with(".mod")).collect(),
        Err(_) => return Vec::new(),
    };
    names.sort_by_cached_key(|n| lower(n));
    let mut out = Vec::new();
    for name in names {
        let text = match std::fs::read(join(&home, &name)) {
            Ok(t) => t,
            Err(_) => continue,
        };
        let said = pairs(&text);
        let path = match said.iter().find(|(k, v)| k == "path" && !v.is_empty()) {
            Some((_, v)) => v.replace(['/', '\\'], &SEP.to_string()),
            None => continue,
        };
        let path = pypath::normpath(&if pypath::isabs(&path) { path } else { join(install, &path) });
        let replace = said.into_iter().filter(|(k, _)| k == "replace_path").map(|(_, v)| v).collect();
        out.push(Descriptor { path, replace });
    }
    out
}

/// The same folder, however it was spelled.
pub fn same_folder(a: &str, b: &str) -> bool {
    pypath::normcase(&pypath::realpath(a)) == pypath::normcase(&pypath::realpath(b))
}

/// Whether `path` lies inside `folder`.
pub fn lies_in(path: &str, folder: &str) -> bool {
    let inner = pypath::normcase(&pypath::realpath(path));
    let outer = pypath::normcase(&pypath::realpath(folder));
    inner.len() > outer.len() && inner.starts_with(&outer)
        && inner[outer.len()..].starts_with(|c: char| is_sep(c) || outer.ends_with(SEP))
}

/// The folders the `.mod` file pointing at `path` replaces, each as
/// `a/b` in lower case: the first such file in name order, nothing when
/// none points here.
pub fn replaced(path: &str, install: &str) -> Vec<String> {
    match descriptors(install).into_iter().find(|d| same_folder(&d.path, path)) {
        Some(d) => d.replace.iter().map(|r| folder_key(r)).filter(|r| !r.is_empty()).collect(),
        None => Vec::new(),
    }
}

/// A folder under a mod as `a/b`, in lower case, for comparing.
pub(super) fn folder_key(folder: &str) -> String {
    lower(folder).replace('\\', "/").trim_matches('/').to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_mod_file_is_read_as_the_game_reads_it() {
        let said = pairs(b"name = \"GGG: Gozomedes' Great Game 1.0\"\r\npath = \"mod/GGG/GGG\" # a clone\n\
                           replace_path = \"common\"\nreplace_path = history/pops/1836.1.1\n");
        assert_eq!(said, vec![
            ("name".to_string(), "GGG: Gozomedes' Great Game 1.0".to_string()),
            ("path".to_string(), "mod/GGG/GGG".to_string()),
            ("replace_path".to_string(), "common".to_string()),
            ("replace_path".to_string(), "history/pops/1836.1.1".to_string()),
        ]);
    }

    #[test]
    fn a_hash_inside_quotes_is_not_a_comment() {
        assert_eq!(pairs(b"name = \"Mod #2\"\n"), vec![("name".to_string(), "Mod #2".to_string())]);
    }

    #[test]
    fn folders_compare_as_written_any_way() {
        assert_eq!(folder_key("History\\Pops/1836.1.1/"), "history/pops/1836.1.1");
    }
}
