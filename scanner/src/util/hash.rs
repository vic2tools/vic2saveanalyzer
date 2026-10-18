// The scanner's one hash for names that must change when what they name does:
// the mod's signature, the report's stamp, a cache entry's context.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Two 64-bit lanes, an FNV-1a and a rotate-and-multiply, over the same bytes:
// 128 bits, so two different inputs share a name only by accident, and nothing
// here is chosen by someone trying to collide them. `build.rs` names the
// build with the same two lanes, written out again there, because a build
// script cannot use the crate it builds.

pub struct TwoLane {
    a: u64,
    b: u64,
}

impl TwoLane {
    pub fn new() -> TwoLane {
        TwoLane { a: 0xcbf2_9ce4_8422_2325, b: 0x9e37_79b9_7f4a_7c15 }
    }

    pub fn update(&mut self, bytes: &[u8]) {
        for &c in bytes {
            self.a = (self.a ^ c as u64).wrapping_mul(0x0000_0100_0000_01b3);
            self.b = (self.b.rotate_left(5) ^ c as u64).wrapping_mul(0x51_7c_c1_b7_27_22_0a_95);
        }
    }

    /// The 32 hex digits.
    pub fn hex(&self) -> String {
        format!("{:016x}{:016x}", self.a, self.b)
    }
}

#[cfg(test)]
mod tests {
    use super::TwoLane;

    #[test]
    fn fed_in_pieces_is_fed_whole() {
        let mut whole = TwoLane::new();
        whole.update(b"abcdef");
        let mut pieces = TwoLane::new();
        pieces.update(b"ab");
        pieces.update(b"cdef");
        assert_eq!(whole.hex(), pieces.hex());
        assert_eq!(whole.hex().len(), 32);
    }

    #[test]
    fn one_byte_more_is_another_name() {
        let (mut x, mut y) = (TwoLane::new(), TwoLane::new());
        x.update(b"mod/common/countries.txt|10|1");
        y.update(b"mod/common/countries.txt|11|1");
        assert_ne!(x.hex(), y.hex());
    }
}
