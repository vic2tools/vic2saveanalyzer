"""
Streaming parser for Victoria 2 (.v2) save files.

Vic2 saves are Clausewitz-format text: `key=value`, `key={ ... }`, and bare
lists `{ a b c }`. Files run 20-150 MB, so this walks the token stream and only
builds Python objects for the branches we actually want; everything else is
skipped by brace counting.
"""

import re

TOKEN_RE = re.compile(r'"[^"]*"|[{}=]|[^\s{}=]+')

# The vanilla pop types. Inside a province block these appear as sub-blocks,
# and the same key can repeat (one block per culture/religion combination).
#
# Mods add their own -- IGoR has `bankers` -- and a pop type missing from this
# set is skipped by `read_province`, so its people vanish from every total.
# `register_pop_types` lets the caller fold in whatever the mod's `poptypes/`
# folder declares before any save is read.
POP_TYPES = {
    "aristocrats", "artisans", "bureaucrats", "capitalists", "clergymen",
    "clerks", "craftsmen", "farmers", "labourers", "officers", "slaves",
    "soldiers",
}


def register_pop_types(names):
    """Add mod-defined pop types so their province blocks are read, not skipped."""
    POP_TYPES.update(n for n in names if n)


# Everything a pop block can hold *other* than the culture=religion line.
# The culture line has no fixed key -- it is literally `british=protestant` --
# so we identify it by elimination.
POP_KNOWN_FIELDS = frozenset([
    "id", "size", "money", "ideology", "issues", "mil", "con", "literacy",
    "bank", "con_factor", "luxury_needs", "everyday_needs", "life_needs",
    "size_changes", "movement", "promoted", "demoted", "days_of_loss",
    "converted", "local_migration", "external_migration", "colonial_migration",
    "assimilated", "type", "faction", "random", "political_movement",
    "social_movement", "supported_regiment", "employed", "stockpile",
    "movement_tag", "movement_issue",
    "need", "production_type", "last_spending", "current_producing",
    "percent_afforded", "percent_sold_domestic", "percent_sold_export",
    "leftover", "throttle", "needs_cost", "production_income", "promotion",
    "literacy_change", "con_change", "mil_change",
])


class Tokens:
    """Token cursor with one-token pushback."""

    __slots__ = ("_it", "_pushed")

    def __init__(self, text):
        self._it = TOKEN_RE.finditer(text)
        self._pushed = None

    def next(self):
        if self._pushed is not None:
            tok = self._pushed
            self._pushed = None
            return tok
        m = next(self._it, None)
        return m.group() if m is not None else None

    def push(self, tok):
        self._pushed = tok


def unquote(tok):
    if len(tok) >= 2 and tok[0] == '"' and tok[-1] == '"':
        return tok[1:-1]
    return tok


def skip_block(tok):
    """Consume tokens until the block opened by the caller's `{` closes."""
    depth = 1
    while depth:
        t = tok.next()
        if t is None:
            return
        if t == "{":
            depth += 1
        elif t == "}":
            depth -= 1


def parse_block(tok):
    """
    Parse a block whose opening `{` has already been consumed.

    Returns a dict. Repeated keys collapse into a list under that key. A block
    made of bare values (`{ "irish" "welsh" }`) returns a list instead.
    """
    out = {}
    items = []
    while True:
        t = tok.next()
        if t is None or t == "}":
            break
        if t == "{":
            items.append(parse_block(tok))
            continue
        if t == "=":
            continue
        nxt = tok.next()
        if nxt == "=":
            val_tok = tok.next()
            if val_tok == "{":
                val = parse_block(tok)
            elif val_tok is None:
                break
            else:
                val = unquote(val_tok)
            key = unquote(t)
            if key in out:
                cur = out[key]
                if isinstance(cur, list) and getattr(cur, "_multi", False):
                    cur.append(val)
                else:
                    multi = _MultiList([cur, val])
                    out[key] = multi
            else:
                out[key] = val
        else:
            items.append(unquote(t))
            tok.push(nxt)
    if items:
        if not out:
            return items
        out["_items"] = items
    return out


class _MultiList(list):
    """Marks a list that came from repeated keys, not a bare value list."""
    _multi = True


def as_list(value):
    """Normalise a field that may be absent, single, or repeated."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def pop_culture(pop):
    """
    Pull (culture, religion) out of a parsed pop block.

    The pair is stored as a bare `culture=religion` line with no stable key,
    so we take the first entry that isn't a known field and isn't numeric.
    """
    for key, val in pop.items():
        if key in POP_KNOWN_FIELDS or key.startswith("_"):
            continue
        if not isinstance(val, str):
            continue
        try:
            float(val)
        except ValueError:
            return key, val
    return None, None


def looks_like_country_tag(key):
    """Vic2 tags are three chars: ENG, FRA, plus dynamic ones like D01, U03."""
    return (
        len(key) == 3
        and key[0].isalpha()
        and key[0].isupper()
        and all(c.isalnum() for c in key)
        and not key.isdigit()
    )


def read_save_text(path):
    """
    Read a .v2 save as text, with a clear error if it isn't plaintext.

    Vic2 can write compressed/binary saves. Launching the game in debug mode
    and re-saving produces a plaintext file (about 10x larger).
    """
    with open(path, "rb") as fh:
        head = fh.read(4096)
        if head[:2] == b"PK":
            raise ValueError(
                f"{path} is a zip archive. Extract it, or re-save the game in "
                f"debug mode to get plaintext."
            )
        if b"date=" not in head and b'date =' not in head:
            raise ValueError(
                f"{path} does not look like a plaintext Vic2 save (no `date=` "
                f"in the header). If it is binary, launch Victoria 2 in debug "
                f"mode and re-save."
            )
        fh.seek(0)
        raw = fh.read()
    # Vic2 files are Windows-1252 / ANSI. latin-1 never raises, which matters
    # because province names carry stray high bytes in some mods.
    return raw.decode("latin-1")
