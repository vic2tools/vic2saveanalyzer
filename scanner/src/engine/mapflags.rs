// The map's province bitmap and the report's flags, read off the game's
// files: `mod_reader.province_raster`, `raster_text`, `province_anchors`
// and `flag_images`.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Python decoded the bitmap in another process while the saves were read,
// and kept it in a cache, because twelve million pixels took it most of a
// second. Here it is a few tens of milliseconds, so it is decoded where it
// is wanted and not kept.

use crate::engine::dates::py_int;
use crate::deflate;
use crate::omap::OMap;
use crate::pickle::{FxMap, FxSet};
use crate::pyfmt::{floordiv, round};
use std::io::{Read, Seek, SeekFrom};

/// (width, height, runs) of the bitmap at 1/`scale`, or (0, 0, []) without one.
pub fn province_raster(bmp: &str, csv: &str, scale: i64) -> (i64, i64, Vec<(i64, i64)>) {
    let none = (0, 0, Vec::new());
    if bmp.is_empty() || csv.is_empty() {
        return none;
    }
    // Colour -> province, keyed as the bitmap stores a pixel: blue, green,
    // red, read as one little-endian number.
    let mut colour: FxMap<u32, i64> = FxMap::default();
    let raw = match std::fs::read(csv) {
        Ok(r) => r,
        Err(_) => return none,
    };
    let text = crate::text::latin1(&raw);
    // `next(fh)` skips the first line; the rest are split on `\n`, each
    // keeping its line ending in its last field.
    for line in text.split_inclusive('\n').skip(1) {
        let bits: Vec<&str> = line.split(';').collect();
        if bits.len() < 4 {
            continue;
        }
        if let (Some(r), Some(g), Some(b), Some(pid)) =
            (py_int(bits[1]), py_int(bits[2]), py_int(bits[3]), py_int(bits[0])) {
            let key = (b | g << 8 | r << 16) as u32;
            colour.insert(key, pid);
        }
    }
    let mut fh = match std::fs::File::open(bmp) {
        Ok(f) => f,
        Err(_) => return none,
    };
    let mut head = [0u8; 54];
    if fh.read_exact(&mut head).is_err() || &head[..2] != b"BM" {
        return none;
    }
    let offset = u32::from_le_bytes(head[10..14].try_into().unwrap()) as u64;
    let width = i32::from_le_bytes(head[18..22].try_into().unwrap()) as i64;
    let height = i32::from_le_bytes(head[22..26].try_into().unwrap()) as i64;
    let bpp = u16::from_le_bytes(head[28..30].try_into().unwrap()) as i64;
    if bpp != 24 {
        return none;
    }
    let stride = ((width * bpp + 31).div_euclid(32)) * 4;
    let (out_w, out_h) = (width.div_euclid(scale), height.div_euclid(scale));
    let step = (scale * 3) as usize;
    let mut runs: Vec<(i64, i64)> = Vec::new();
    let mut last: Option<i64> = None;
    let mut count = 0i64;
    let mut row = vec![0u8; stride.max(0) as usize];
    for oy in 0..out_h.max(0) {
        if fh.seek(SeekFrom::Start(offset + (oy * scale * stride) as u64)).is_err() {
            break;
        }
        let mut got = 0;
        while got < row.len() {
            match fh.read(&mut row[got..]) {
                Ok(0) | Err(_) => break,
                Ok(n) => got += n,
            }
        }
        let mut prev_key: Option<u32> = None;
        let mut pid = 0i64;
        for x in 0..out_w.max(0) as usize {
            let at = x * step;
            let key = if at + 2 < got {
                row[at] as u32 | (row[at + 1] as u32) << 8 | (row[at + 2] as u32) << 16
            } else {
                0
            };
            if prev_key != Some(key) {
                pid = colour.get(&key).copied().unwrap_or(0);
                prev_key = Some(key);
            }
            if Some(pid) == last {
                count += 1;
            } else {
                if let Some(l) = last {
                    runs.push((l, count));
                }
                last = Some(pid);
                count = 1;
            }
        }
    }
    if let Some(l) = last {
        runs.push((l, count));
    }
    (out_w, out_h, runs)
}

fn b36(mut n: i64, out: &mut String) {
    const D: &[u8; 36] = b"0123456789abcdefghijklmnopqrstuvwxyz";
    if n <= 0 {
        out.push('0');
        return;
    }
    let mut buf = [0u8; 16];
    let mut i = buf.len();
    while n > 0 {
        i -= 1;
        buf[i] = D[(n % 36) as usize];
        n /= 36;
    }
    out.push_str(std::str::from_utf8(&buf[i..]).unwrap());
}

/// `raster_text`: `province` or `province.count` in base 36, spaced.
pub fn raster_text(runs: &[(i64, i64)]) -> String {
    let mut out = String::with_capacity(runs.len() * 6);
    for (i, (p, c)) in runs.iter().enumerate() {
        if i > 0 {
            out.push(' ');
        }
        b36(*p, &mut out);
        if *c != 1 {
            out.push('.');
            b36(*c, &mut out);
        }
    }
    out
}

/// `province_anchors(width, runs, wanted)`: a point inside each wanted
/// province, nearest its middle, as [x, y] in cell units.
pub fn province_anchors(width: i64, runs: &[(i64, i64)], wanted: &FxSet<i64>) -> OMap<i64, [f64; 2]> {
    let mut out = OMap::new();
    if width == 0 || wanted.is_empty() {
        return out;
    }
    let segments = || {
        let mut segs = Vec::new();
        let mut at = 0i64;
        for &(pid, count) in runs {
            if wanted.contains(&pid) {
                let end = at + count;
                while at < end {
                    let (y, x0) = (at.div_euclid(width), at.rem_euclid(width));
                    let x1 = width.min(x0 + end - at) - 1;
                    segs.push((pid, y, x0, x1));
                    at += x1 - x0 + 1;
                }
            } else {
                at += count;
            }
        }
        segs
    };
    let segs = segments();
    let mut totals: OMap<i64, [i64; 3]> = OMap::new();
    for &(pid, y, x0, x1) in &segs {
        let n = x1 - x0 + 1;
        let t = totals.entry(pid, || [0, 0, 0]);
        t[0] += ((x0 + x1) * n).div_euclid(2);
        t[1] += y * n;
        t[2] += n;
    }
    let middle: FxMap<i64, (f64, f64)> = totals.iter()
        .map(|(pid, t)| (*pid, (t[0] as f64 / t[2] as f64, t[1] as f64 / t[2] as f64)))
        .collect();
    let mut best: OMap<i64, (f64, i64, i64)> = OMap::new();
    for &(pid, y, x0, x1) in &segs {
        let (cx, cy) = middle[&pid];
        let left = (floordiv(cx, 1.0) as i64).max(x0).min(x1);
        let xs: Vec<i64> = if left < x1 { vec![left, (left + 1).min(x1)] } else { vec![left] };
        for x in xs {
            let (dx, dy) = (x as f64 - cx, y as f64 - cy);
            let far = dx * dx + dy * dy;
            let better = match best.get(&pid) {
                None => true,
                Some(b) => far < b.0,
            };
            if better {
                best.set(pid, (far, x, y));
            }
        }
    }
    for (pid, (_, x, y)) in best.iter() {
        out.set(*pid, [round(*x as f64 + 0.5, 1), round(*y as f64 + 0.5, 1)]);
    }
    out
}

// ------------------------------------------------------------- flags

/// `flag_suffixes(government, styles)`.
pub fn flag_suffixes(government: &str, styles: &FxMap<String, (String, bool)>) -> [&'static str; 2] {
    let (variant, elects) = match styles.get(government) {
        Some((v, e)) => (v.as_str(), *e),
        None => ("", true),
    };
    if variant == "monarchy" && !elects {
        return ["_monarchy", ""];
    }
    match variant {
        "communist" => ["_communist", ""],
        "fascist" => ["_fascist", ""],
        _ => ["", "_republic"],
    }
}

/// `_read_tga`: (width, height, rgb) of an uncompressed or run-length TGA
/// at 24 or 32 bits, or None.
fn read_tga(blob: &[u8]) -> Option<(usize, usize, Vec<u8>)> {
    if blob.len() < 18 {
        return None;
    }
    let (idlen, cmaptype, imgtype) = (blob[0] as usize, blob[1], blob[2]);
    let width = u16::from_le_bytes([blob[12], blob[13]]) as usize;
    let height = u16::from_le_bytes([blob[14], blob[15]]) as usize;
    let (bpp, descriptor) = (blob[16] as usize, blob[17]);
    if !(imgtype == 2 || imgtype == 10) || !(bpp == 24 || bpp == 32) || width == 0 || height == 0 {
        return None;
    }
    let mut at = 18 + idlen;
    if cmaptype != 0 {
        at += u16::from_le_bytes([blob[5], blob[6]]) as usize * (blob[7] as usize / 8);
    }
    let step = bpp / 8;
    let want = width * height;
    let px: Vec<u8> = if imgtype == 2 {
        blob.get(at.min(blob.len())..(at + want * step).min(blob.len())).unwrap_or(&[]).to_vec()
    } else {
        let mut buf = Vec::with_capacity(want * step);
        while buf.len() < want * step && at < blob.len() {
            let packet = blob[at];
            at += 1;
            let count = (packet & 0x7f) as usize + 1;
            if packet & 0x80 != 0 {
                let one = &blob[at.min(blob.len())..(at + step).min(blob.len())];
                for _ in 0..count {
                    buf.extend_from_slice(one);
                }
                at += step;
            } else {
                buf.extend_from_slice(&blob[at.min(blob.len())..(at + count * step).min(blob.len())]);
                at += count * step;
            }
        }
        buf
    };
    if px.len() < want * step {
        return None;
    }
    let mut rgb = vec![0u8; want * 3];
    for i in 0..want {
        rgb[3 * i] = px[i * step + 2];
        rgb[3 * i + 1] = px[i * step + 1];
        rgb[3 * i + 2] = px[i * step];
    }
    if descriptor & 0x20 == 0 {
        let stride = width * 3;
        let mut flipped = Vec::with_capacity(rgb.len());
        for y in (0..height).rev() {
            flipped.extend_from_slice(&rgb[y * stride..(y + 1) * stride]);
        }
        rgb = flipped;
    }
    Some((width, height, rgb))
}

/// Python's `round(x)` to an int: halves to even.
fn round_int(x: f64) -> i64 {
    let r = x.round();
    if (x - x.trunc()).abs() == 0.5 {
        let t = x.trunc();
        let up = t + x.signum();
        return if (t as i64) % 2 == 0 { t as i64 } else { up as i64 };
    }
    r as i64
}

/// `_shrink`: nearest-neighbour down to `target` wide.
fn shrink(width: usize, height: usize, rgb: Vec<u8>, target: usize) -> (usize, usize, Vec<u8>) {
    if width <= target {
        return (width, height, rgb);
    }
    let out_w = target;
    let out_h = round_int(height as f64 * target as f64 / width as f64).max(1) as usize;
    let cols: Vec<usize> = (0..out_w).map(|x| (width - 1).min(x * width / out_w) * 3).collect();
    let mut out = Vec::with_capacity(out_w * out_h * 3);
    for y in 0..out_h {
        let row = (height - 1).min(y * height / out_h) * width * 3;
        for &col in &cols {
            out.extend_from_slice(&rgb[row + col..row + col + 3]);
        }
    }
    (out_w, out_h, out)
}

/// `_write_png`: IHDR, one IDAT, IEND, no filtering.
fn write_png(width: usize, height: usize, rgb: &[u8]) -> Vec<u8> {
    let mut raw = Vec::with_capacity(height * (width * 3 + 1));
    for y in 0..height {
        raw.push(0);
        raw.extend_from_slice(&rgb[y * width * 3..(y + 1) * width * 3]);
    }
    let chunk = |out: &mut Vec<u8>, tag: &[u8], data: &[u8]| {
        out.extend_from_slice(&(data.len() as u32).to_be_bytes());
        let mut both = tag.to_vec();
        both.extend_from_slice(data);
        out.extend_from_slice(&both);
        out.extend_from_slice(&deflate::crc32(&both).to_be_bytes());
    };
    let mut out = b"\x89PNG\r\n\x1a\n".to_vec();
    let mut ihdr = Vec::new();
    ihdr.extend_from_slice(&(width as u32).to_be_bytes());
    ihdr.extend_from_slice(&(height as u32).to_be_bytes());
    ihdr.extend_from_slice(&[8, 2, 0, 0, 0]);
    chunk(&mut out, b"IHDR", &ihdr);
    chunk(&mut out, b"IDAT", &deflate::zlib(&raw));
    chunk(&mut out, b"IEND", b"");
    out
}

/// `flag_images(path, [tag], {tag: government}, styles=styles)[tag]`: the
/// flag as a PNG data URI, or None.
pub fn flag_image(roots: &[String], tag: &str, government: &str,
                  styles: &FxMap<String, (String, bool)>) -> Option<String> {
    for suffix in flag_suffixes(government, styles) {
        let name = format!("{}{}.tga", tag, suffix);
        let found = roots.iter().map(|r| std::path::Path::new(r).join(&name))
            .find(|p| p.is_file());
        let found = match found {
            Some(f) => f,
            None => continue,
        };
        let image = std::fs::read(&found).ok().and_then(|b| read_tga(&b));
        if let Some((w, h, rgb)) = image {
            let (w, h, rgb) = shrink(w, h, rgb, 46);
            let mut uri = String::from("data:image/png;base64,");
            deflate::base64_into(&mut uri, &write_png(w, h, &rgb));
            return Some(uri);
        }
    }
    None
}
