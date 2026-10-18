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

#[cfg(windows)]
pub(super) const SEP: char = '\\';
#[cfg(not(windows))]
pub(super) const SEP: char = '/';

pub(super) fn is_sep(c: char) -> bool {
    c == '/' || (cfg!(windows) && c == '\\')
}

/// `os.path.join(a, b)`.
#[cfg(not(windows))]
pub fn join(a: &str, b: &str) -> String {
    if b.starts_with('/') {
        b.to_string()
    } else if a.is_empty() || a.ends_with('/') {
        format!("{}{}", a, b)
    } else {
        format!("{}/{}", a, b)
    }
}

/// `os.path.join(a, b)`, ntpath's: a part with a root keeps the drive
/// before it, a part with another drive starts again.
#[cfg(windows)]
pub fn join(a: &str, b: &str) -> String {
    pub(super) fn drive(p: &str) -> &str {
        let c: Vec<char> = p.chars().take(2).collect();
        if c.len() == 2 && c[1] == ':' && c[0].is_ascii_alphabetic() { &p[..2] } else { "" }
    }
    let (ad, bd) = (drive(a), drive(b));
    let b_rest = &b[bd.len()..];
    if b_rest.starts_with(is_sep) {
        return if !bd.is_empty() || ad.is_empty() { b.to_string() } else { format!("{}{}", ad, b_rest) };
    }
    if !bd.is_empty() && !bd.eq_ignore_ascii_case(ad) {
        return b.to_string();
    }
    let a_rest = &a[ad.len()..];
    if a_rest.is_empty() || a_rest.ends_with(is_sep) {
        format!("{}{}", a, b_rest)
    } else {
        format!("{}{}{}", a, SEP, b_rest)
    }
}

pub(super) fn joins(a: &str, parts: &[&str]) -> String {
    parts.iter().fold(a.to_string(), |acc, p| join(&acc, p))
}

/// `os.path.dirname`, for an absolute path.
pub(super) fn dirname(p: &str) -> String {
    match p.rfind(is_sep) {
        None => String::new(),
        Some(i) => {
            let head = &p[..i + 1];
            let trimmed = head.trim_end_matches(is_sep);
            if trimmed.is_empty() || (cfg!(windows) && trimmed.ends_with(':')) {
                head.to_string()
            } else {
                trimmed.to_string()
            }
        }
    }
}

pub(super) fn basename(p: &str) -> &str {
    match p.rfind(is_sep) {
        None => p,
        Some(i) => &p[i + 1..],
    }
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
