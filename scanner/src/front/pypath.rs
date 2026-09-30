// Python's `os.path`, for the paths the analyzer is handed.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// A path the analyzer prints -- "Path not found: ...", "Victoria II at ..."
// -- and a path it keys a cache or a stamp by are the ones Python's
// `posixpath` or `ntpath` made of what was typed, so these are theirs, rule
// for rule: `~` and `$HOME`, `%USERPROFILE%` and `${VAR}`, `..` folded
// away, two leading slashes kept on POSIX, drives and roots on Windows.

#[cfg(windows)]
pub const SEP: char = '\\';
#[cfg(not(windows))]
pub const SEP: char = '/';
#[cfg(windows)]
pub const SEP_STR: &str = "\\";
#[cfg(not(windows))]
pub const SEP_STR: &str = "/";

fn env(name: &str) -> Option<String> {
    if name.is_empty() || name.contains('=') || name.contains('\0') {
        return None;
    }
    std::env::var(name).ok()
}

// ------------------------------------------------------------ Windows

/// `ntpath.splitroot`: (drive, root, rest).
#[cfg(windows)]
pub fn splitroot(p: &str) -> (&str, &str, &str) {
    let norm: String = p.replace('/', "\\");
    let nb = norm.as_bytes();
    if nb.first() == Some(&b'\\') {
        if nb.get(1) == Some(&b'\\') {
            // `get`, not a slice: byte 8 can fall inside a character.
            let start = if norm.get(..8).is_some_and(|h| h.eq_ignore_ascii_case("\\\\?\\UNC\\")) { 8 } else { 2 };
            let index = match norm[start.min(norm.len())..].find('\\') {
                Some(i) => start + i,
                None => return (p, "", ""),
            };
            let index2 = match norm[index + 1..].find('\\') {
                Some(i) => index + 1 + i,
                None => return (p, "", ""),
            };
            return (&p[..index2], &p[index2..index2 + 1], &p[index2 + 1..]);
        }
        return ("", &p[..1], &p[1..]);
    }
    if nb.len() >= 2 && nb[1] == b':' && p.is_char_boundary(2) {
        if nb.get(2) == Some(&b'\\') {
            return (&p[..2], &p[2..3], &p[3..]);
        }
        return (&p[..2], "", &p[2..]);
    }
    ("", "", p)
}

/// `os.path.join(a, b)`.
#[cfg(windows)]
pub fn join(a: &str, b: &str) -> String {
    let (mut drive, mut root, rest) = splitroot(a);
    let mut path = rest.to_string();
    let (d, r, p) = splitroot(b);
    let owned;
    if !r.is_empty() {
        if !d.is_empty() || drive.is_empty() {
            drive = d;
        }
        root = r;
        path = p.to_string();
    } else {
        if !d.is_empty() && d != drive {
            if d.to_lowercase() != drive.to_lowercase() {
                return b.to_string();
            }
            owned = d.to_string();
            drive = &owned;
        }
        if !path.is_empty() && !path.ends_with(['\\', '/']) {
            path.push('\\');
        }
        path.push_str(p);
    }
    if !path.is_empty() && root.is_empty() && !drive.is_empty() && !drive.ends_with([':', '\\', '/']) {
        return format!("{}\\{}", drive, path);
    }
    format!("{}{}{}", drive, root, path)
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

/// `os.path.split`.
#[cfg(windows)]
pub fn split(p: &str) -> (String, String) {
    let (d, r, rest) = splitroot(p);
    let i = rest.rfind(['\\', '/']).map_or(0, |i| i + 1);
    let (head, tail) = (&rest[..i], &rest[i..]);
    (format!("{}{}{}", d, r, head.trim_end_matches(['\\', '/'])), tail.to_string())
}

/// `os.path.split`.
#[cfg(not(windows))]
pub fn split(p: &str) -> (String, String) {
    let i = p.rfind('/').map_or(0, |i| i + 1);
    let (head, tail) = (&p[..i], &p[i..]);
    let head = if !head.is_empty() && head.chars().any(|c| c != '/') {
        head.trim_end_matches('/')
    } else {
        head
    };
    (head.to_string(), tail.to_string())
}

#[cfg_attr(not(windows), allow(dead_code))]
pub fn dirname(p: &str) -> String {
    split(p).0
}

pub fn basename(p: &str) -> String {
    split(p).1
}

/// `os.path.isabs`.
#[cfg_attr(windows, allow(dead_code))]
pub fn isabs(p: &str) -> bool {
    #[cfg(windows)]
    {
        let p = p.replace('/', "\\");
        if p.starts_with("\\\\") {
            return true;
        }
        let (d, r, _) = splitroot(&p);
        !d.is_empty() && !r.is_empty()
    }
    #[cfg(not(windows))]
    {
        p.starts_with('/')
    }
}

/// `os.path.normpath`.
#[cfg(not(windows))]
pub fn normpath(path: &str) -> String {
    if path.is_empty() {
        return ".".into();
    }
    let mut initial = if path.starts_with('/') { 1 } else { 0 };
    if path.starts_with("//") && !path.starts_with("///") {
        initial = 2;
    }
    let mut comps: Vec<&str> = Vec::new();
    for comp in path.split('/') {
        if comp.is_empty() || comp == "." {
            continue;
        }
        if comp != ".." || (initial == 0 && comps.is_empty()) || comps.last() == Some(&"..") {
            comps.push(comp);
        } else if !comps.is_empty() {
            comps.pop();
        }
    }
    let joined = comps.join("/");
    let out = format!("{}{}", "/".repeat(initial), joined);
    if out.is_empty() { ".".into() } else { out }
}

/// `os.path.normpath`.
#[cfg(windows)]
pub fn normpath(path: &str) -> String {
    let path = path.replace('/', "\\");
    let (drive, root, rest) = splitroot(&path);
    let prefix = format!("{}{}", drive, root);
    let mut comps: Vec<&str> = rest.split('\\').collect();
    let mut i = 0;
    while i < comps.len() {
        if comps[i].is_empty() || comps[i] == "." {
            comps.remove(i);
        } else if comps[i] == ".." {
            if i > 0 && comps[i - 1] != ".." {
                comps.drain(i - 1..=i);
                i -= 1;
            } else if i == 0 && !root.is_empty() {
                comps.remove(i);
            } else {
                i += 1;
            }
        } else {
            i += 1;
        }
    }
    if prefix.is_empty() && comps.is_empty() {
        comps.push(".");
    }
    format!("{}{}", prefix, comps.join("\\"))
}

/// `os.path.abspath`.
pub fn abspath(p: &str) -> String {
    #[cfg(windows)]
    {
        // `_getfullpathname(normpath(p))`, which is what `absolute` asks
        // Windows for.
        match std::path::absolute(normpath(p)) {
            Ok(full) => full.to_string_lossy().to_string(),
            Err(_) => normpath(&join(&cwd(), p)),
        }
    }
    #[cfg(not(windows))]
    {
        if isabs(p) {
            normpath(p)
        } else {
            normpath(&join(&cwd(), p))
        }
    }
}

fn cwd() -> String {
    std::env::current_dir().map(|p| p.to_string_lossy().to_string()).unwrap_or_default()
}

/// `os.path.normcase`.
pub fn normcase(p: &str) -> String {
    if cfg!(windows) { p.replace('/', "\\").to_lowercase() } else { p.to_string() }
}

/// `os.path.realpath`, for a path that exists; itself when it does not.
pub fn realpath(p: &str) -> String {
    match std::fs::canonicalize(p) {
        Ok(full) => full.to_string_lossy().to_string(),
        Err(_) => abspath(p),
    }
}

pub fn exists(p: &str) -> bool {
    std::fs::metadata(p).is_ok()
}

pub fn isdir(p: &str) -> bool {
    std::path::Path::new(p).is_dir()
}

// ------------------------------------------------------------ ~ and $VAR

/// `os.path.expanduser`.
#[cfg(not(windows))]
pub fn expanduser(path: &str) -> String {
    if !path.starts_with('~') {
        return path.to_string();
    }
    let i = path[1..].find('/').map_or(path.len(), |k| k + 1);
    let home = if i == 1 {
        match env("HOME") {
            Some(h) => h,
            None => match passwd_home(None) {
                Some(h) => h,
                None => return path.to_string(),
            },
        }
    } else {
        match passwd_home(Some(&path[1..i])) {
            Some(h) => h,
            None => return path.to_string(),
        }
    };
    let home = home.trim_end_matches('/');
    let out = format!("{}{}", home, &path[i..]);
    if out.is_empty() { "/".into() } else { out }
}

/// A home folder out of `/etc/passwd`: the named user's, or this process's
/// own when `name` is None.
#[cfg(not(windows))]
fn passwd_home(name: Option<&str>) -> Option<String> {
    let uid = if name.is_none() {
        let status = std::fs::read_to_string("/proc/self/status").ok()?;
        let line = status.lines().find(|l| l.starts_with("Uid:"))?;
        Some(line.split_whitespace().nth(1)?.to_string())
    } else {
        None
    };
    let table = std::fs::read_to_string("/etc/passwd").ok()?;
    for line in table.lines() {
        let f: Vec<&str> = line.split(':').collect();
        if f.len() < 6 {
            continue;
        }
        let hit = match (name, &uid) {
            (Some(n), _) => f[0] == n,
            (None, Some(u)) => f[2] == u,
            _ => false,
        };
        if hit {
            return Some(f[5].to_string());
        }
    }
    None
}

/// `os.path.expanduser`.
#[cfg(windows)]
pub fn expanduser(path: &str) -> String {
    if !path.starts_with('~') {
        return path.to_string();
    }
    let i = path[1..].find(['\\', '/']).map_or(path.len(), |k| k + 1);
    let mut home = match env("USERPROFILE") {
        Some(h) => h,
        None => match env("HOMEPATH") {
            None => return path.to_string(),
            Some(hp) => join(&env("HOMEDRIVE").unwrap_or_default(), &hp),
        },
    };
    if i != 1 {
        let target = &path[1..i];
        let current = env("USERNAME");
        if current.as_deref() != Some(target) {
            if current.as_deref() != Some(basename(&home).as_str()) {
                return path.to_string();
            }
            home = join(&dirname(&home), target);
        }
    }
    format!("{}{}", home, &path[i..])
}

/// `os.path.expandvars`: `$NAME` and `${NAME}`, a name of ASCII word
/// characters; an unset name is left as written.
#[cfg(not(windows))]
pub fn expandvars(path: &str) -> String {
    if !path.contains('$') {
        return path.to_string();
    }
    let word = |c: char| c.is_ascii_alphanumeric() || c == '_';
    let mut path = path.to_string();
    let mut i = 0;
    loop {
        // `\$(\w+|\{[^}]*\})`, searched from `i`.
        let mut found = None;
        let bytes = path.as_bytes();
        let mut at = i;
        while at < bytes.len() {
            if bytes[at] == b'$' {
                let rest = &path[at + 1..];
                if rest.starts_with('{') {
                    if let Some(close) = rest.find('}') {
                        found = Some((at, at + 1 + close + 1, rest[1..close].to_string()));
                        break;
                    }
                } else {
                    let n = rest.chars().take_while(|&c| word(c)).count();
                    if n > 0 {
                        found = Some((at, at + 1 + n, rest[..n].to_string()));
                        break;
                    }
                }
            }
            at += 1;
        }
        let (start, end, name) = match found {
            Some(f) => f,
            None => break,
        };
        match env(&name) {
            None => i = end,
            Some(value) => {
                let tail = path[end..].to_string();
                path.truncate(start);
                path.push_str(&value);
                i = path.len();
                path.push_str(&tail);
            }
        }
    }
    path
}

/// `os.path.expandvars`, ntpath's: `%NAME%`, `$NAME`, `${NAME}`, `%%` and
/// `$$` for themselves, and nothing expanded inside single quotes.
#[cfg(windows)]
pub fn expandvars(path: &str) -> String {
    if !path.contains('$') && !path.contains('%') {
        return path.to_string();
    }
    let varchar = |c: char| c.is_ascii_alphanumeric() || c == '_' || c == '-';
    let mut path: Vec<char> = path.chars().collect();
    let mut res = String::new();
    let mut index = 0usize;
    let mut n = path.len();
    let find = |p: &[char], c: char| p.iter().position(|&x| x == c);
    while index < n {
        let c = path[index];
        if c == '\'' {
            path = path[index + 1..].to_vec();
            n = path.len();
            match find(&path, '\'') {
                Some(k) => {
                    res.push('\'');
                    res.extend(&path[..k + 1]);
                    index = k;
                }
                None => {
                    res.push('\'');
                    res.extend(&path);
                    index = n.wrapping_sub(1);
                }
            }
        } else if c == '%' {
            if path.get(index + 1) == Some(&'%') {
                res.push('%');
                index += 1;
            } else {
                path = path[index + 1..].to_vec();
                n = path.len();
                match find(&path, '%') {
                    None => {
                        res.push('%');
                        res.extend(&path);
                        index = n.wrapping_sub(1);
                    }
                    Some(k) => {
                        let var: String = path[..k].iter().collect();
                        match env(&var) {
                            Some(v) => res.push_str(&v),
                            None => {
                                res.push('%');
                                res.push_str(&var);
                                res.push('%');
                            }
                        }
                        index = k;
                    }
                }
            }
        } else if c == '$' {
            if path.get(index + 1) == Some(&'$') {
                res.push('$');
                index += 1;
            } else if path.get(index + 1) == Some(&'{') {
                path = path[index + 2..].to_vec();
                n = path.len();
                match find(&path, '}') {
                    None => {
                        res.push_str("${");
                        res.extend(&path);
                        index = n.wrapping_sub(1);
                    }
                    Some(k) => {
                        let var: String = path[..k].iter().collect();
                        match env(&var) {
                            Some(v) => res.push_str(&v),
                            None => {
                                res.push_str("${");
                                res.push_str(&var);
                                res.push('}');
                            }
                        }
                        index = k;
                    }
                }
            } else {
                let mut var = String::new();
                index += 1;
                let mut c = path.get(index).copied();
                while let Some(ch) = c {
                    if !varchar(ch) {
                        break;
                    }
                    var.push(ch);
                    index += 1;
                    c = path.get(index).copied();
                }
                match env(&var) {
                    Some(v) => res.push_str(&v),
                    None => {
                        res.push('$');
                        res.push_str(&var);
                    }
                }
                if c.is_some() {
                    index -= 1;
                }
            }
        } else {
            res.push(c);
        }
        index = index.wrapping_add(1);
    }
    res
}

/// `tempfile.gettempdir()`: the first of Python's candidates this process
/// can write a file in.
pub fn gettempdir() -> String {
    let mut candidates: Vec<String> = Vec::new();
    for name in ["TMPDIR", "TEMP", "TMP"] {
        if let Some(v) = env(name) {
            if !v.is_empty() {
                candidates.push(v);
            }
        }
    }
    #[cfg(windows)]
    {
        candidates.push(expanduser("~\\AppData\\Local\\Temp"));
        candidates.push(expandvars("%SYSTEMROOT%\\Temp"));
        for c in ["c:\\temp", "c:\\tmp", "\\temp", "\\tmp"] {
            candidates.push(c.to_string());
        }
    }
    #[cfg(not(windows))]
    {
        for c in ["/tmp", "/var/tmp", "/usr/tmp"] {
            candidates.push(c.to_string());
        }
    }
    candidates.push(cwd());
    for dir in candidates {
        let dir = if dir != "." { abspath(&dir) } else { dir };
        let probe = join(&dir, &format!("vic2probe{}", std::process::id()));
        if std::fs::OpenOptions::new().write(true).create_new(true).open(&probe).is_ok() {
            let _ = std::fs::remove_file(&probe);
            return dir;
        }
    }
    cwd()
}
