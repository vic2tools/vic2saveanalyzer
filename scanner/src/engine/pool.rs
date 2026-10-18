// The threads a run reads its saves on: how many, and the order their results
// are taken in.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.

use crate::util::fx::FxMap;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::mpsc;

/// How many threads read the saves: cores bar one, the saves left, and
/// memory.
///
/// Every logical core helps (the 1880s campaign's empty-cache run: 3.83 s
/// on 8 threads, 3.50 s on 15, 3.47 s on 16, on 8 cores of two threads
/// each); one is left for the window. A thread holds the save it reads --
/// mapped, or in its buffer where saves are not mapped -- and ~0.15 of a
/// save's size more while it reads it (measured: 43 MB a thread for 42 MB
/// saves, read into buffers). Threads are allowed half of the memory the
/// system could hand out, at a save and a quarter each; the rest is for
/// the campaign the run holds, which is the same whatever the count.
pub fn worker_count(jobs: usize, biggest: u64, asked: Option<i64>) -> usize {
    if let Some(a) = asked {
        return (a.max(1) as usize).min(jobs).max(1);
    }
    let cores = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(1)
        .saturating_sub(1).max(1);
    let mut room = jobs;
    if let Some(avail) = available_memory() {
        let per_thread = (biggest + biggest / 4).max(1);
        room = (avail / 2 / per_thread).max(1) as usize;
    }
    cores.min(jobs).min(room).max(1)
}

#[cfg(target_os = "linux")]
fn available_memory() -> Option<u64> {
    // MemAvailable: free pages and what the page cache would give back.
    // MemFree alone, which the Python read, leaves the page cache out, and
    // moved with it from run to run (8, 11 or 15 threads here).
    let text = std::fs::read_to_string("/proc/meminfo").ok()?;
    for line in text.lines() {
        if let Some(rest) = line.strip_prefix("MemAvailable:") {
            let kb: u64 = rest.trim().trim_end_matches("kB").trim().parse().ok()?;
            return Some(kb * 1024);
        }
    }
    None
}

#[cfg(windows)]
fn available_memory() -> Option<u64> {
    #[repr(C)]
    struct Status {
        length: u32,
        load: u32,
        total_phys: u64,
        avail_phys: u64,
        total_page: u64,
        avail_page: u64,
        total_virtual: u64,
        avail_virtual: u64,
        avail_extended: u64,
    }
    extern "system" {
        fn GlobalMemoryStatusEx(status: *mut Status) -> i32;
    }
    let mut s = Status { length: std::mem::size_of::<Status>() as u32, load: 0, total_phys: 0,
                         avail_phys: 0, total_page: 0, avail_page: 0, total_virtual: 0,
                         avail_virtual: 0, avail_extended: 0 };
    if unsafe { GlobalMemoryStatusEx(&mut s) } != 0 { Some(s.avail_phys) } else { None }
}

#[cfg(not(any(target_os = "linux", windows)))]
fn available_memory() -> Option<u64> {
    None
}

/// Run `job` over `0..n` on `workers` threads, handing each answer to
/// `take` in index order as soon as it and everything before it are done.
pub fn in_order<T: Send, F, G>(n: usize, workers: usize, job: F, mut take: G)
where
    F: Fn(usize) -> T + Sync,
    G: FnMut(usize, T),
{
    if workers <= 1 || n <= 1 {
        for i in 0..n {
            take(i, job(i));
        }
        return;
    }
    let next = AtomicUsize::new(0);
    let (tx, rx) = mpsc::channel::<(usize, T)>();
    std::thread::scope(|s| {
        for _ in 0..workers.min(n) {
            let tx = tx.clone();
            let (next, job) = (&next, &job);
            s.spawn(move || loop {
                let i = next.fetch_add(1, Ordering::Relaxed);
                if i >= n {
                    break;
                }
                if tx.send((i, job(i))).is_err() {
                    break;
                }
            });
        }
        drop(tx);
        let mut waiting: FxMap<usize, T> = FxMap::default();
        let mut due = 0;
        for (i, v) in rx {
            waiting.insert(i, v);
            while let Some(v) = waiting.remove(&due) {
                take(due, v);
                due += 1;
            }
        }
    });
}
