// The mod's files and folders, found as Python's os.path finds them.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use super::*;
pub(super) use crate::py::path::{dirname, join};

#[cfg(windows)]
pub(super) const SEP: char = '\\';
#[cfg(not(windows))]
pub(super) const SEP: char = '/';

pub(super) fn is_sep(c: char) -> bool {
    c == '/' || (cfg!(windows) && c == '\\')
}

pub(super) fn joins(a: &str, parts: &[&str]) -> String {
    parts.iter().fold(a.to_string(), |acc, p| join(&acc, p))
}

pub(super) fn is_file(p: &str) -> bool {
    std::path::Path::new(p).is_file()
}

pub(super) fn is_dir(p: &str) -> bool {
    std::path::Path::new(p).is_dir()
}

/// `str.lower()`.
pub(super) fn lower(s: &str) -> String {
    s.to_lowercase()
}

/// `os.listdir`, in the order the folder gives: None when it cannot be
/// listed, a decline for a name Python would hold as undecodable.
pub(super) fn listdir(folder: &str) -> D<Option<Vec<String>>> {
    let rd = match std::fs::read_dir(folder) {
        Ok(rd) => rd,
        Err(_) => return Ok(None),
    };
    let mut out = Vec::new();
    for e in rd {
        let e = match e {
            Ok(e) => e,
            Err(e) => return no(format!("listing {}: {}", folder, e)),
        };
        match e.file_name().into_string() {
            Ok(s) => out.push(s),
            Err(_) => return no(format!("a file name in {} is not text", folder)),
        }
    }
    Ok(Some(out))
}
