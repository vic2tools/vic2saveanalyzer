// What a run prints, held back while the run might still be handed back.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Everything a run says goes through here. It can be held -- kept in the
// order it was said and let out at once, or dropped with the run -- which
// the front end did while it still handed runs back after speaking; nothing
// holds it now, and the output streams as it is said.
//
// The lines the host reads (`@progress`, `@ready`, `@done`) are not these:
// they go out at once, and only when there is a host to read them.

use std::io::Write;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;

static HELD: Mutex<Option<Vec<(bool, String)>>> = Mutex::new(None);
static PROTOCOL: AtomicBool = AtomicBool::new(true);
static QUIET_DECLINES: AtomicBool = AtomicBool::new(false);

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

/// Say `text` on stdout (`to_stdout`) or stderr, now or when let out.
pub fn write(to_stdout: bool, text: String) {
    let mut held = HELD.lock().unwrap();
    match held.as_mut() {
        Some(v) => v.push((to_stdout, text)),
        None => {
            drop(held);
            emit(to_stdout, &text);
        }
    }
}

/// Let out what was kept, in order, and stop keeping.
pub fn release() {
    let kept = HELD.lock().unwrap().take();
    for (to_stdout, text) in kept.unwrap_or_default() {
        emit(to_stdout, &text);
    }
}

/// Whether a host is reading the protocol lines.
pub fn set_protocol(on: bool) {
    PROTOCOL.store(on, Ordering::Relaxed);
}

/// Whether a run handed back says why on stderr: only to `engine.py`,
/// which keeps the engine's stderr for its own error, and not through the
/// front end, whose stderr is the person's.
pub fn say_declines() -> bool {
    !QUIET_DECLINES.load(Ordering::Relaxed)
}

pub fn quiet_declines() {
    QUIET_DECLINES.store(true, Ordering::Relaxed);
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
