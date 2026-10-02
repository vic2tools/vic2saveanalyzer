// JSON written as Python's `json.dumps(x, separators=(",", ":"))` writes it,
// for the parts of the page's payload built from maps.
// Copyright (C) 2026 vic2tools
//
// This program is free software: you can redistribute it and/or modify it
// under the terms of the GNU Affero General Public License as published by the
// Free Software Foundation, either version 3 of the License, or (at your
// option) any later version. It is distributed WITHOUT ANY WARRANTY; without
// even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
// PURPOSE. See <https://www.gnu.org/licenses/> for the full text.
//
// Key order, and an int against a float, count: the payload is held to what
// the Python wrote, as text.

use crate::omap::OMap;
use crate::pyfmt::{push_int, push_json_str};

pub fn obj<'a, V: 'a>(out: &mut String, pairs: impl Iterator<Item = (&'a str, V)>,
                      mut value: impl FnMut(&mut String, V)) {
    out.push('{');
    for (i, (k, v)) in pairs.enumerate() {
        if i > 0 {
            out.push(',');
        }
        push_json_str(out, k);
        out.push(':');
        value(out, v);
    }
    out.push('}');
}

pub fn int_keyed<V>(out: &mut String, m: &OMap<i64, V>, mut value: impl FnMut(&mut String, &V)) {
    out.push('{');
    for (i, (k, v)) in m.iter().enumerate() {
        if i > 0 {
            out.push(',');
        }
        out.push('"');
        push_int(out, *k);
        out.push_str("\":");
        value(out, v);
    }
    out.push('}');
}
