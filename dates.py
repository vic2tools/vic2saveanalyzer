# Victoria 2 campaign analyzer
# Copyright (C) 2026 vic2tools
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# <https://www.gnu.org/licenses/> for the full text, or the LICENSE file beside
# this one.
"""
The game's dates, `1847.1.1`, turned into things that sort and plot.

Three answers, for three kinds of caller, each with its own answer for a
date it cannot read. `ymd` is strict and says None, for the keeper and
`--cross`, which decide things about one save at a time. `date_key` and
`year_fraction` are remembered, because a campaign asks each of them the
same few hundred dates a few million times -- once per price reading, per
chart point, per sort comparison -- and they sort an unreadable date first
rather than stopping on it.
"""


def ymd(stamp):
    """`1847.1.1` as (1847, 1, 1), or None."""
    parts = (stamp or "").split(".")
    if len(parts) != 3:
        return None
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


_DATE_KEYS = {}


def date_key(date):
    """Sortable tuple for a `YYYY.M.D` string; (0, 0, 0) for anything else."""
    try:
        got = _DATE_KEYS.get(date)
    except TypeError:
        return (0, 0, 0)              # not even hashable, let alone a date
    if got is not None:
        return got
    try:
        got = tuple(int(p) for p in date.split("."))
    except (ValueError, AttributeError):
        got = (0, 0, 0)
    _DATE_KEYS[date] = got
    return got


_YEAR_FRACTIONS = {}


def year_fraction(date):
    """A date as a position on a year axis; 0.0 for anything else."""
    try:
        got = _YEAR_FRACTIONS.get(date)
    except TypeError:
        return 0.0
    if got is not None:
        return got
    try:
        y, m, d = (int(p) for p in date.split("."))
        got = y + (m - 1) / 12.0 + (d - 1) / 365.0
    except (ValueError, AttributeError):
        got = 0.0
    _YEAR_FRACTIONS[date] = got
    return got
