# tools

Things for the people working on the analyzer, not part of it.

## prepush.sh

The repository is public, under an identity kept apart from the people who
work on it. `prepush.sh` looks for words that must never be pushed -- a
name, a home folder -- in the files, the index, and every commit not yet on
`origin/main`, with their messages:

```
bash tools/prepush.sh
```

It prints `clean` and exits 0, or prints each match and exits 1. With no
words to look for it exits 2 and does not say `clean`. Run it before every
push. `testkit/prepushcheck.py` holds it to that.

## local.env

This machine's settings, read by `prepush.sh` and handy to source before
running the checks. It is not committed (`.gitignore`); write one on each
machine:

```
VIC2_SAVES="/path/to/save games"            # a campaign's saves
VIC2_MOD="/path/to/Victoria 2/mod/SomeMod"  # its mod
VIC2_BASELINE="$HOME/vic2-baseline"         # testkit/baseline.py's record of it
VIC2_PRIVATE='\bsomename\b|\bothername\b'   # what must never be pushed (a regex)
```

## Running it before every push

To have `prepush.sh` run before every push, and stop the push unless it says
`clean`, point this clone's hooks at `tools/hooks/`:

```
git config core.hooksPath tools/hooks
```
