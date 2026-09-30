// Deflate, gzip, zlib, CRC-32 and base64, written here rather than borrowed.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// The scanner takes no dependencies (Cargo.toml says why), and the report
// travels gzipped, its flags as PNGs, so the compressor is here. It is the
// algorithm zlib's `deflate_slow` uses -- hash chains over a 32 KB window,
// one match held back to see whether the next is longer, blocks of Huffman
// codes built for their own symbols -- with zlib's level-6 limits. It makes
// streams any inflater reads, not zlib's own bytes: Python on this machine
// links zlib-ng and Python on Windows classic zlib, which already disagree
// with each other byte for byte, so the checks compare what a stream holds.

const WSIZE: usize = 1 << 15;
const WMASK: usize = WSIZE - 1;
const HBITS: usize = 15;
const HSIZE: usize = 1 << HBITS;
const MIN_MATCH: usize = 3;
const MAX_MATCH: usize = 258;
/// zlib's MAX_DIST: a match may not reach into the last MIN_LOOKAHEAD bytes
/// of a window, so the chains never point at a slot that has been reused.
const MAX_DIST: usize = WSIZE - (MAX_MATCH + MIN_MATCH + 1);
const SYMBOLS_PER_BLOCK: usize = 16383;

/// zlib's level 6: (good_length, max_lazy, nice_length, max_chain).
const GOOD: usize = 8;
const LAZY: usize = 16;
const NICE: usize = 128;
const CHAIN: usize = 128;

// ------------------------------------------------------------------ checks

fn crc_tables() -> &'static [[u32; 256]; 8] {
    use std::sync::OnceLock;
    static T: OnceLock<Box<[[u32; 256]; 8]>> = OnceLock::new();
    T.get_or_init(|| {
        let mut t = Box::new([[0u32; 256]; 8]);
        for i in 0..256u32 {
            let mut c = i;
            for _ in 0..8 {
                c = if c & 1 != 0 { 0xedb8_8320 ^ (c >> 1) } else { c >> 1 };
            }
            t[0][i as usize] = c;
        }
        for i in 0..256 {
            for k in 1..8 {
                let prev = t[k - 1][i];
                t[k][i] = (prev >> 8) ^ t[0][(prev & 0xff) as usize];
            }
        }
        t
    })
}

/// CRC-32 as gzip and PNG use it, eight bytes at a step.
pub fn crc32(data: &[u8]) -> u32 {
    crc32_update(0, data)
}

pub fn crc32_update(crc: u32, data: &[u8]) -> u32 {
    let t = crc_tables();
    let mut c = !crc;
    let mut chunks = data.chunks_exact(8);
    for w in &mut chunks {
        let lo = u32::from_le_bytes([w[0], w[1], w[2], w[3]]) ^ c;
        let hi = u32::from_le_bytes([w[4], w[5], w[6], w[7]]);
        c = t[7][(lo & 0xff) as usize]
            ^ t[6][((lo >> 8) & 0xff) as usize]
            ^ t[5][((lo >> 16) & 0xff) as usize]
            ^ t[4][(lo >> 24) as usize]
            ^ t[3][(hi & 0xff) as usize]
            ^ t[2][((hi >> 8) & 0xff) as usize]
            ^ t[1][((hi >> 16) & 0xff) as usize]
            ^ t[0][(hi >> 24) as usize];
    }
    for &b in chunks.remainder() {
        c = t[0][((c ^ b as u32) & 0xff) as usize] ^ (c >> 8);
    }
    !c
}

pub fn adler32(data: &[u8]) -> u32 {
    let (mut a, mut b) = (1u32, 0u32);
    for chunk in data.chunks(5552) {
        for &x in chunk {
            a += x as u32;
            b += a;
        }
        a %= 65521;
        b %= 65521;
    }
    (b << 16) | a
}

// ------------------------------------------------------------------ base64

pub fn base64_into(out: &mut String, data: &[u8]) {
    const T: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    out.reserve(data.len().div_ceil(3) * 4);
    let mut buf = Vec::with_capacity(data.len().div_ceil(3) * 4);
    let mut chunks = data.chunks_exact(3);
    for c in &mut chunks {
        let n = (c[0] as u32) << 16 | (c[1] as u32) << 8 | c[2] as u32;
        buf.extend_from_slice(&[T[(n >> 18) as usize], T[((n >> 12) & 63) as usize],
                                T[((n >> 6) & 63) as usize], T[(n & 63) as usize]]);
    }
    let rest = chunks.remainder();
    if !rest.is_empty() {
        let n = (rest[0] as u32) << 16 | (*rest.get(1).unwrap_or(&0) as u32) << 8;
        buf.push(T[(n >> 18) as usize]);
        buf.push(T[((n >> 12) & 63) as usize]);
        buf.push(if rest.len() == 2 { T[((n >> 6) & 63) as usize] } else { b'=' });
        buf.push(b'=');
    }
    // Safe: the alphabet is ASCII.
    out.push_str(unsafe { std::str::from_utf8_unchecked(&buf) });
}

pub fn base64(data: &[u8]) -> String {
    let mut s = String::new();
    base64_into(&mut s, data);
    s
}

// ------------------------------------------------------------------ bits

struct Bits {
    out: Vec<u8>,
    acc: u64,
    n: u32,
}

impl Bits {
    fn new(capacity: usize) -> Bits {
        Bits { out: Vec::with_capacity(capacity), acc: 0, n: 0 }
    }

    #[inline]
    fn put(&mut self, value: u32, len: u32) {
        debug_assert!(len <= 32);
        self.acc |= (value as u64) << self.n;
        self.n += len;
        if self.n >= 32 {
            self.out.extend_from_slice(&(self.acc as u32).to_le_bytes());
            self.acc >>= 32;
            self.n -= 32;
        }
    }

    fn align(&mut self) {
        while self.n > 0 {
            self.out.push(self.acc as u8);
            self.acc >>= 8;
            self.n = self.n.saturating_sub(8);
        }
        self.acc = 0;
        self.n = 0;
    }

    fn finish(mut self) -> Vec<u8> {
        self.align();
        self.out
    }
}

// ------------------------------------------------------------------ tables

const LEN_BASE: [u16; 29] = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43,
                             51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258];
const LEN_EXTRA: [u8; 29] = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4,
                             4, 4, 5, 5, 5, 5, 0];
const DIST_BASE: [u16; 30] = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257,
                              385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289,
                              16385, 24577];
const DIST_EXTRA: [u8; 30] = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9,
                              9, 10, 10, 11, 11, 12, 12, 13, 13];
const CL_ORDER: [usize; 19] = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15];

struct Codes {
    len_code: [u8; 259],    // match length -> index into LEN_BASE
    dist_code: [u8; 512],   // zlib's _dist_code
}

fn codes() -> &'static Codes {
    use std::sync::OnceLock;
    static C: OnceLock<Codes> = OnceLock::new();
    C.get_or_init(|| {
        let mut len_code = [0u8; 259];
        for (code, &base) in LEN_BASE.iter().enumerate() {
            let span = 1usize << LEN_EXTRA[code];
            for l in 0..span {
                let length = base as usize + l;
                if length <= 258 {
                    len_code[length] = code as u8;
                }
            }
        }
        len_code[258] = 28;
        let mut dist_code = [0u8; 512];
        for (code, &base) in DIST_BASE.iter().enumerate() {
            let span = 1usize << DIST_EXTRA[code];
            for d in 0..span {
                let dist = base as usize - 1 + d; // 0-based
                if dist < 256 {
                    dist_code[dist] = code as u8;
                } else {
                    dist_code[256 + (dist >> 7)] = code as u8;
                }
            }
        }
        Codes { len_code, dist_code }
    })
}

#[inline]
fn dist_index(dist0: usize) -> usize {
    let c = codes();
    if dist0 < 256 { c.dist_code[dist0] as usize } else { c.dist_code[256 + (dist0 >> 7)] as usize }
}

fn reverse(code: u32, len: u32) -> u32 {
    code.reverse_bits() >> (32 - len.max(1))
}

/// Code lengths for these frequencies, none longer than `limit`: Huffman's,
/// then pushed under the limit the way Kraft's inequality allows.
fn lengths(freq: &[u32], limit: u32) -> Vec<u8> {
    let n = freq.len();
    let mut lens = vec![0u8; n];
    let mut used: Vec<usize> = (0..n).filter(|&i| freq[i] > 0).collect();
    // As zlib does: at least two codes, so a lone symbol still costs a bit
    // and every inflater takes the tree.
    let mut k = 0;
    while used.len() < 2 {
        if !used.contains(&k) {
            used.push(k);
        }
        k += 1;
    }
    used.sort_by_key(|&i| (freq[i].max(1), i));
    // Two-queue Huffman over the sorted leaves.
    let m = used.len();
    let mut weight: Vec<u64> = used.iter().map(|&i| freq[i].max(1) as u64).collect();
    let mut parent = vec![0usize; 2 * m];
    weight.resize(2 * m, 0);
    let (mut leaf, mut node, mut next) = (0usize, m, m);
    let take = |leaf: &mut usize, node: &mut usize, next: usize, weight: &Vec<u64>| -> usize {
        if *leaf < m && (*node >= next || weight[*leaf] <= weight[*node]) {
            *leaf += 1;
            *leaf - 1
        } else {
            *node += 1;
            *node - 1
        }
    };
    while next < 2 * m - 1 {
        let a = take(&mut leaf, &mut node, next, &weight);
        let b = take(&mut leaf, &mut node, next, &weight);
        weight[next] = weight[a] + weight[b];
        parent[a] = next;
        parent[b] = next;
        next += 1;
    }
    let root = 2 * m - 2;
    let mut depth = vec![0u32; 2 * m];
    for v in (0..root).rev() {
        depth[v] = depth[parent[v]] + 1;
    }
    let mut overflow = 0i64;
    let mut count = vec![0i64; limit as usize + 1];
    for &d in depth.iter().take(m) {
        if d > limit {
            overflow += 1;
        }
        count[d.min(limit) as usize] += 1;
    }
    if overflow > 0 {
        // zlib's `gen_bitlen`: the leaves past the limit are put at it, and
        // then, two at a time, a leaf above the limit is moved down one
        // level with an overflowed leaf as its brother -- which leaves the
        // lengths a complete code, as every inflater insists they are.
        // Each move takes exactly one unit of 2^-limit off the Kraft sum,
        // so it is repeated until the sum is whole again. (zlib counts its
        // clamped internal nodes as well as its leaves to know how many.)
        let cap = 1i64 << limit;
        let mut kraft: i64 = (1..=limit as usize).map(|b| count[b] << (limit as usize - b)).sum();
        while kraft > cap {
            let mut bits = limit as usize - 1;
            while count[bits] == 0 {
                bits -= 1;
            }
            count[bits] -= 1;
            count[bits + 1] += 2;
            count[limit as usize] -= 1;
            kraft -= 1;
        }
        overflow = 0;
        let _ = overflow;
        // The longest codes to the least frequent symbols; `used` is sorted
        // least frequent first.
        let mut j = 0;
        for bits in (1..=limit as usize).rev() {
            for _ in 0..count[bits] {
                lens[used[j]] = bits as u8;
                j += 1;
            }
        }
    } else {
        for (j, &sym) in used.iter().enumerate() {
            lens[sym] = depth[j] as u8;
        }
    }
    lens
}

/// Canonical codes for these lengths, bit-reversed for the LSB-first stream.
fn canonical(lens: &[u8]) -> Vec<u32> {
    let mut count = [0u32; 16];
    for &l in lens {
        count[l as usize] += 1;
    }
    count[0] = 0;
    let mut next = [0u32; 16];
    let mut code = 0u32;
    for bits in 1..16 {
        code = (code + count[bits - 1]) << 1;
        next[bits] = code;
    }
    lens.iter().map(|&l| {
        if l == 0 {
            0
        } else {
            let c = next[l as usize];
            next[l as usize] += 1;
            reverse(c, l as u32)
        }
    }).collect()
}

// ------------------------------------------------------------------ blocks

#[derive(Clone, Copy)]
struct Sym {
    /// 0 for a literal, else the distance.
    dist: u16,
    /// The literal byte, or the match length.
    len: u16,
}

fn fixed_lengths() -> (Vec<u8>, Vec<u8>) {
    let mut lit = vec![0u8; 288];
    for (i, l) in lit.iter_mut().enumerate() {
        *l = match i { 0..=143 => 8, 144..=255 => 9, 256..=279 => 7, _ => 8 };
    }
    (lit, vec![5u8; 30])
}

/// The code-length sequence of a dynamic header, run-length coded:
/// (symbol, extra value) pairs.
fn rle(all: &[u8]) -> Vec<(u8, u8)> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < all.len() {
        let v = all[i];
        let mut run = 1;
        while i + run < all.len() && all[i + run] == v {
            run += 1;
        }
        let mut left = run;
        if v == 0 {
            while left >= 11 {
                let take = left.min(138);
                out.push((18, (take - 11) as u8));
                left -= take;
            }
            if left >= 3 {
                out.push((17, (left - 3) as u8));
                left = 0;
            }
            for _ in 0..left {
                out.push((0, 0));
            }
        } else {
            out.push((v, 0));
            left -= 1;
            while left >= 3 {
                let take = left.min(6);
                out.push((16, (take - 3) as u8));
                left -= take;
            }
            for _ in 0..left {
                out.push((v, 0));
            }
        }
        i += run;
    }
    out
}

fn write_symbols(bits: &mut Bits, syms: &[Sym], lit_codes: &[u32], lit_lens: &[u8],
                 dist_codes: &[u32], dist_lens: &[u8]) {
    let c = codes();
    for s in syms {
        if s.dist == 0 {
            let l = s.len as usize;
            bits.put(lit_codes[l], lit_lens[l] as u32);
        } else {
            let len = s.len as usize;
            let lc = c.len_code[len] as usize;
            bits.put(lit_codes[257 + lc], lit_lens[257 + lc] as u32);
            let e = LEN_EXTRA[lc] as u32;
            if e > 0 {
                bits.put((len - LEN_BASE[lc] as usize) as u32, e);
            }
            let d0 = s.dist as usize - 1;
            let dc = dist_index(d0);
            bits.put(dist_codes[dc], dist_lens[dc] as u32);
            let e = DIST_EXTRA[dc] as u32;
            if e > 0 {
                bits.put((d0 + 1 - DIST_BASE[dc] as usize) as u32, e);
            }
        }
    }
    bits.put(lit_codes[256], lit_lens[256] as u32);
}

/// One block of `syms`, covering `raw` (the bytes they stand for), as
/// whichever of stored, fixed or dynamic codes is shortest.
fn emit_block(bits: &mut Bits, syms: &[Sym], raw: &[u8], last: bool) {
    let c = codes();
    let mut lit_freq = vec![0u32; 286];
    let mut dist_freq = vec![0u32; 30];
    for s in syms {
        if s.dist == 0 {
            lit_freq[s.len as usize] += 1;
        } else {
            lit_freq[257 + c.len_code[s.len as usize] as usize] += 1;
            dist_freq[dist_index(s.dist as usize - 1)] += 1;
        }
    }
    lit_freq[256] = 1;
    let lit_lens = lengths(&lit_freq, 15);
    let dist_lens = lengths(&dist_freq, 15);
    let hlit = (257..=286).rev().find(|&n| lit_lens[n - 1] != 0).unwrap_or(257).max(257);
    let hdist = (1..=30).rev().find(|&n| dist_lens[n - 1] != 0).unwrap_or(1).max(1);
    let mut all: Vec<u8> = lit_lens[..hlit].to_vec();
    all.extend_from_slice(&dist_lens[..hdist]);
    let runs = rle(&all);
    let mut cl_freq = vec![0u32; 19];
    for (s, _) in &runs {
        cl_freq[*s as usize] += 1;
    }
    let cl_lens = lengths(&cl_freq, 7);
    let hclen = (4..=19).rev().find(|&n| cl_lens[CL_ORDER[n - 1]] != 0).unwrap_or(4).max(4);

    let data_bits = |ll: &[u8], dl: &[u8]| -> u64 {
        let mut n = 0u64;
        for (i, &f) in lit_freq.iter().enumerate() {
            if f > 0 {
                n += f as u64 * ll[i] as u64;
                if i >= 257 {
                    n += f as u64 * LEN_EXTRA[i - 257] as u64;
                }
            }
        }
        for (i, &f) in dist_freq.iter().enumerate() {
            n += f as u64 * (dl[i] as u64 + DIST_EXTRA[i] as u64);
        }
        n
    };
    let mut dyn_bits = 3 + 5 + 5 + 4 + 3 * hclen as u64 + data_bits(&lit_lens, &dist_lens);
    for (s, _) in &runs {
        dyn_bits += cl_lens[*s as usize] as u64 + match s { 16 => 2, 17 => 3, 18 => 7, _ => 0 };
    }
    let (fl, fd) = fixed_lengths();
    let fixed_bits = 3 + data_bits(&fl, &fd);
    let stored_bytes = raw.len() + 5 * raw.len().div_ceil(65535).max(1);

    let final_bit = if last { 1 } else { 0 };
    if (stored_bytes as u64) * 8 + 7 < dyn_bits.min(fixed_bits) {
        let chunks: Vec<&[u8]> = if raw.is_empty() { vec![&[][..]] } else { raw.chunks(65535).collect() };
        let count = chunks.len();
        for (i, chunk) in chunks.into_iter().enumerate() {
            let fin = if last && i + 1 == count { 1 } else { 0 };
            bits.put(fin, 3);
            bits.align();
            let n = chunk.len() as u16;
            bits.out.extend_from_slice(&n.to_le_bytes());
            bits.out.extend_from_slice(&(!n).to_le_bytes());
            bits.out.extend_from_slice(chunk);
        }
    } else if fixed_bits <= dyn_bits {
        bits.put(final_bit | 1 << 1, 3);
        write_symbols(bits, syms, &canonical(&fl), &fl, &canonical(&fd), &fd);
    } else {
        bits.put(final_bit | 2 << 1, 3);
        bits.put((hlit - 257) as u32, 5);
        bits.put((hdist - 1) as u32, 5);
        bits.put((hclen - 4) as u32, 4);
        for &k in CL_ORDER.iter().take(hclen) {
            bits.put(cl_lens[k] as u32, 3);
        }
        let cl_codes = canonical(&cl_lens);
        for (s, extra) in &runs {
            let s = *s as usize;
            bits.put(cl_codes[s], cl_lens[s] as u32);
            match s {
                16 => bits.put(*extra as u32, 2),
                17 => bits.put(*extra as u32, 3),
                18 => bits.put(*extra as u32, 7),
                _ => {}
            }
        }
        write_symbols(bits, syms, &canonical(&lit_lens), &lit_lens,
                      &canonical(&dist_lens), &dist_lens);
    }
}

// ------------------------------------------------------------------ LZ77

struct Matcher {
    head: Vec<u32>,
    prev: Vec<u32>,
}

impl Matcher {
    fn new() -> Matcher {
        // Positions are stored plus one, so zero means "none".
        Matcher { head: vec![0u32; HSIZE], prev: vec![0u32; WSIZE] }
    }

    #[inline]
    fn hash(b: &[u8], i: usize) -> usize {
        let v = (b[i] as u32) << 16 | (b[i + 1] as u32) << 8 | b[i + 2] as u32;
        (v.wrapping_mul(0x9E37_79B1) >> (32 - HBITS as u32)) as usize
    }

    /// Enter position `i`, and answer the position most recently entered
    /// with the same three bytes (plus one), if any.
    #[inline]
    fn insert(&mut self, b: &[u8], i: usize) -> usize {
        let h = Self::hash(b, i);
        let was = self.head[h];
        self.prev[i & WMASK] = was;
        self.head[h] = i as u32 + 1;
        was as usize
    }

    /// The longest match for position `i` along the chain starting at
    /// `cand` (plus one), no shorter than `prev_len` + 1 to count.
    fn longest(&self, b: &[u8], i: usize, mut cand: usize, prev_len: usize) -> (usize, usize) {
        let limit = if i > MAX_DIST { i - MAX_DIST } else { 0 };
        let max = (b.len() - i).min(MAX_MATCH);
        let mut chain = if prev_len >= GOOD { CHAIN >> 2 } else { CHAIN };
        let mut best_len = prev_len;
        let mut best_pos = 0usize;
        let nice = NICE.min(max);
        while cand > 0 {
            let c = cand - 1;
            if c < limit || c >= i {
                break;
            }
            if best_len < max && b[c + best_len] == b[i + best_len] && b[c] == b[i] {
                let mut l = 0;
                // Eight bytes at a time, then the tail.
                while l + 8 <= max {
                    let x = u64::from_le_bytes(b[c + l..c + l + 8].try_into().unwrap());
                    let y = u64::from_le_bytes(b[i + l..i + l + 8].try_into().unwrap());
                    let d = x ^ y;
                    if d != 0 {
                        l += (d.trailing_zeros() / 8) as usize;
                        break;
                    }
                    l += 8;
                }
                if l + 8 > max {
                    while l < max && b[c + l] == b[i + l] {
                        l += 1;
                    }
                }
                let l = l.min(max);
                if l > best_len {
                    best_len = l;
                    best_pos = c;
                    if l >= nice {
                        break;
                    }
                }
            }
            chain -= 1;
            if chain == 0 {
                break;
            }
            cand = self.prev[c & WMASK] as usize;
        }
        (best_len, best_pos)
    }
}

/// Deflate `buf[start..]`, with `buf[..start]` as history a match may reach
/// back into (a preset dictionary, or the piece before this one). The stream
/// ends the deflate data when `last`, and otherwise stops on a byte boundary
/// with the stream still open (a sync flush), ready for the next piece.
pub fn deflate_raw(buf: &[u8], start: usize, last: bool) -> Vec<u8> {
    let mut bits = Bits::new((buf.len() - start) / 3 + 64);
    let mut m = Matcher::new();
    let n = buf.len();
    let from = start.saturating_sub(WSIZE);
    let mut i = from;
    while i < start && i + MIN_MATCH <= n {
        m.insert(buf, i);
        i += 1;
    }
    let mut syms: Vec<Sym> = Vec::with_capacity(SYMBOLS_PER_BLOCK + 1);
    let mut block_start = start;
    let mut pos = start;
    // The match found at the position before, held back while the next one
    // is looked at.
    let mut prev_len = MIN_MATCH - 1;
    let mut prev_pos = 0usize;
    let mut held = false;

    let flush = |syms: &mut Vec<Sym>, bits: &mut Bits, block_start: &mut usize, upto: usize, fin: bool| {
        emit_block(bits, syms, &buf[*block_start..upto], fin);
        syms.clear();
        *block_start = upto;
    };

    while pos < n {
        let mut cand = 0;
        if pos + MIN_MATCH <= n {
            cand = m.insert(buf, pos);
        }
        let (mut len, mut mpos) = (MIN_MATCH - 1, 0usize);
        if cand > 0 && prev_len < LAZY && pos - (cand - 1) <= MAX_DIST {
            let (l, p) = m.longest(buf, pos, cand, prev_len);
            if l > prev_len {
                len = l;
                mpos = p;
            }
            if len == MIN_MATCH && pos - mpos > 4096 {
                len = MIN_MATCH - 1;
            }
        }
        if prev_len >= MIN_MATCH && len <= prev_len {
            // The held match wins: emit it and step past it.
            let at = pos - 1;
            syms.push(Sym { dist: (at - prev_pos) as u16, len: prev_len as u16 });
            let end = at + prev_len;
            let mut k = pos + 1;
            while k < end {
                if k + MIN_MATCH <= n {
                    m.insert(buf, k);
                }
                k += 1;
            }
            held = false;
            prev_len = MIN_MATCH - 1;
            pos = end;
            if syms.len() >= SYMBOLS_PER_BLOCK {
                flush(&mut syms, &mut bits, &mut block_start, pos, false);
            }
            continue;
        }
        if held {
            syms.push(Sym { dist: 0, len: buf[pos - 1] as u16 });
            if syms.len() >= SYMBOLS_PER_BLOCK {
                flush(&mut syms, &mut bits, &mut block_start, pos, false);
            }
        }
        held = true;
        prev_len = len;
        prev_pos = mpos;
        pos += 1;
    }
    if held {
        syms.push(Sym { dist: 0, len: buf[n - 1] as u16 });
    }
    flush(&mut syms, &mut bits, &mut block_start, n, last);
    if !last {
        // An empty stored block: the stream stays open and ends on a byte.
        bits.put(0, 3);
        bits.align();
        bits.out.extend_from_slice(&[0, 0, 0xff, 0xff]);
    }
    bits.finish()
}

const GZIP_HEAD: [u8; 10] = [0x1f, 0x8b, 8, 0, 0, 0, 0, 0, 0, 0xff];

/// `gzip.compress(data)` in kind: one member, no name, no time.
pub fn gzip(data: &[u8]) -> Vec<u8> {
    let mut out = GZIP_HEAD.to_vec();
    out.extend_from_slice(&deflate_raw(data, 0, true));
    out.extend_from_slice(&crc32(data).to_le_bytes());
    out.extend_from_slice(&(data.len() as u32).to_le_bytes());
    out
}

/// `gzip`, a megabyte at a time on `threads` threads, each piece with the
/// 32 KB before it as history: one ordinary gzip stream, as `pigz` makes.
pub fn gzip_parallel(data: &[u8], threads: usize) -> Vec<u8> {
    const PIECE: usize = 1 << 20;
    if data.len() <= 2 * PIECE || threads <= 1 {
        return gzip(data);
    }
    let pieces: Vec<usize> = (0..data.len()).step_by(PIECE).collect();
    let next = std::sync::atomic::AtomicUsize::new(0);
    let mut crc = 0u32;
    let slots: Vec<std::sync::Mutex<Vec<u8>>> =
        (0..pieces.len()).map(|_| std::sync::Mutex::new(Vec::new())).collect();
    std::thread::scope(|s| {
        let crc_job = s.spawn(|| crc32(data));
        let workers: Vec<_> = (0..threads.min(pieces.len())).map(|_| {
            let (next, pieces, slots) = (&next, &pieces, &slots);
            s.spawn(move || loop {
                let k = next.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                if k >= pieces.len() {
                    break;
                }
                let at = pieces[k];
                let end = (at + PIECE).min(data.len());
                let from = at.saturating_sub(WSIZE);
                let got = deflate_raw(&data[from..end], at - from, end == data.len());
                *slots[k].lock().unwrap() = got;
            })
        }).collect();
        for w in workers {
            w.join().unwrap();
        }
        crc = crc_job.join().unwrap();
    });
    let parts: Vec<Vec<u8>> = slots.into_iter().map(|s| s.into_inner().unwrap()).collect();
    let total: usize = parts.iter().map(|p| p.len()).sum();
    let mut out = Vec::with_capacity(total + 18);
    out.extend_from_slice(&GZIP_HEAD);
    for p in &parts {
        out.extend_from_slice(p);
    }
    out.extend_from_slice(&crc.to_le_bytes());
    out.extend_from_slice(&(data.len() as u32).to_le_bytes());
    out
}

/// A zlib stream, as `zlib.compress` makes (PNG's IDAT wants one).
pub fn zlib(data: &[u8]) -> Vec<u8> {
    let mut out = vec![0x78, 0xda];
    out.extend_from_slice(&deflate_raw(data, 0, true));
    out.extend_from_slice(&adler32(data).to_be_bytes());
    out
}

/// Selftest: gzip (and zlib, and the parallel gzip) of a file, for Python
/// to decompress and compare. `selftest-deflate MODE FILE` writes to stdout.
pub fn selftest(mode: &str, path: &str) {
    use std::io::Write;
    if mode == "huff" {
        // Code lengths for many frequency sets, held to Kraft's equality:
        // every set must come out a complete code within its limit.
        let mut seed = 0x2545_f491_4f6c_dd1du64;
        let mut rnd = || {
            seed ^= seed << 13;
            seed ^= seed >> 7;
            seed ^= seed << 17;
            seed
        };
        let mut bad = 0;
        let tries: usize = path.parse().unwrap_or(100000);
        for t in 0..tries {
            let (n, limit) = match t % 3 { 0 => (19usize, 7u32), 1 => (30, 15), _ => (286, 15) };
            let mut freq = vec![0u32; n];
            let kind = rnd() % 4;
            for (i, f) in freq.iter_mut().enumerate() {
                *f = match kind {
                    0 => (rnd() % 1000) as u32,
                    1 => if rnd() % 3 == 0 { 0 } else { 1u32 << (rnd() % 20) },
                    2 => { let fib = [1u32, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610,
                                      987, 1597, 2584, 4181, 6765, 10946, 17711, 28657, 46368];
                           if i < fib.len() { fib[i] } else { 0 } }
                    _ => if rnd() % 5 == 0 { (rnd() % 100000) as u32 } else { 0 },
                };
            }
            let lens = lengths(&freq, limit);
            let kraft: u64 = lens.iter().filter(|&&l| l > 0).map(|&l| 1u64 << (limit - l as u32)).sum();
            let over = lens.iter().any(|&l| l as u32 > limit);
            let missing = freq.iter().zip(&lens).any(|(f, l)| *f > 0 && *l == 0);
            if kraft != 1u64 << limit || over || missing {
                bad += 1;
                if bad < 5 {
                    eprintln!("bad code: limit {} kind {} kraft {} of {} lens {:?}", limit, kind,
                              kraft, 1u64 << limit, lens);
                }
            }
        }
        println!("{} frequency sets, {} bad", tries, bad);
        return;
    }
    let data = std::fs::read(path).unwrap();
    let out = match mode {
        "gzip" => gzip(&data),
        "zlib" => zlib(&data),
        "pgzip" => gzip_parallel(&data, 8),
        "b64" => base64(&data).into_bytes(),
        _ => panic!("mode"),
    };
    std::io::stdout().write_all(&out).unwrap();
}
