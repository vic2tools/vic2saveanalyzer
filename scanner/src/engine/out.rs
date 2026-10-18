// What a run prints, and the lines a host reads beside it.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Everything a run says goes through here, and out as it is said.
//
// The lines the host reads (`@progress`, `@ready`, `@done`) are not these:
// they go out at once, and only when there is a host to read them.

use std::io::Write;
use std::sync::atomic::{AtomicBool, Ordering};

static PROTOCOL: AtomicBool = AtomicBool::new(true);

fn emit(to_stdout: bool, text: &str) {
    if to_stdout {
        let out = std::io::stdout();
        let mut out = out.lock();
        let _ = out.write_all(text.as_bytes());
        let _ = out.flush();
    } else {
        let err = std::io::stderr();
        let mut err = err.lock();
        let _ = err.write_all(text.as_bytes());
        let _ = err.flush();
    }
}

/// Say `text` on stdout (`to_stdout`) or stderr.
pub fn write(to_stdout: bool, text: String) {
    emit(to_stdout, &text);
}

/// Whether a host is reading the protocol lines.
pub fn set_protocol(on: bool) {
    PROTOCOL.store(on, Ordering::Relaxed);
}

/// One line for the host: `@progress`, `@ready`, `@done`.
pub fn protocol(line: &str) {
    if PROTOCOL.load(Ordering::Relaxed) {
        emit(true, &format!("{}\n", line));
    }
}

#[macro_export]
macro_rules! outln {
    () => { $crate::engine::out::write(true, "\n".to_string()) };
    ($($a:tt)*) => { $crate::engine::out::write(true, format!("{}\n", format_args!($($a)*))) };
}

#[macro_export]
macro_rules! errln {
    () => { $crate::engine::out::write(false, "\n".to_string()) };
    ($($a:tt)*) => { $crate::engine::out::write(false, format!("{}\n", format_args!($($a)*))) };
}
