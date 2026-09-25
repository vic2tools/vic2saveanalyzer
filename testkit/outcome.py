"""
What a check's exit status tells `all.py` and `mutate.py`.

0 is "holds", `SKIPPED` is "could not run all of it on this machine" -- no
Firefox, no display, no scanner built, a report with no payload in it --
and anything else is "fails". It used to be read off the check's words:
`all.py` looked for four phrases in its output, so a check that reworded
its excuse would have been counted as holding.

77 is the number automake and meson already use for a skipped test.
"""

SKIPPED = 77
