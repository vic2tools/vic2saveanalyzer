# Testing it

Two kinds of thing live here: checks that hold the analyzer to what it is
supposed to do, and stand-ins for the parts of the world it talks to.

## The checks

Run in this order. The first four are seconds; the last two are minutes.

```
python3 testkit/tooearly.py                       # no saves needed
python3 testkit/awkward.py                        # no saves needed
python3 testkit/countries.py                      # no saves needed
python3 testkit/edges.py                          # no saves needed
python3 testkit/parity.py "/path/to/saves" 8
python3 testkit/boots.py out/report.html
python3 testkit/smoke.py "/path/to/saves" --mod "/path/to/mod"
```

**`parity.py`** holds the Rust scanner to the Python parser, save by save,
field by field, exactly — no tolerance, because the floats are accumulated
in the same order on both sides and a tolerance would hide the drift this
exists to catch.

**`awkward.py`** and **`countries.py`** write saves with the layouts that
are legal but rare — a pop with a mod's own block nested inside it, an army
loaded onto a transport, a province with no owner — and read them both ways.

**`edges.py`** builds the campaigns nobody has: an empty folder, one save, a
first-month save with nothing researched, a save with no pops, a truncated
one, a zip, files that are not saves. A case passes if it works or refuses
in a sentence a person could act on. A stack trace is a failure.

**`smoke.py`** runs every way the analyzer can be asked to run — quiet and
loud, with and without a mod, every diagnostic, `--cross` — and checks what
each one *says*. Exiting 0 is not enough: `--inventions` once exited 0 while
answering zero of 387, and `--explain-mob` exited 0 after replying "nothing
has changed" and explaining nothing. `--analyzer` points it at another
tree's code, which is how a new case is shown to fail on the version it was
written for.

**`tooearly.py`** looks for a local read on a line above every line that
binds it. That is an `UnboundLocalError` waiting for whichever path reaches
it first, and it has shipped twice.

**`boots.py`** opens a built report in headless Firefox, with a handler on
`window.onerror` and on unhandled rejections, and asks the page what it
managed to draw. Everything else here compares the bytes of a report to the
bytes of another one, which catches a changed number and misses the only
failure a reader would notice: a page that does not run. A helper called
from outside the function that defined it is a `ReferenceError` at boot and
a blank page, and the file is byte-for-byte what it was supposed to be.
Needs Firefox; says so and passes if there is none. A `--split` report will
fail it, and should: its payload is a separate file, and a browser will not
fetch that over `file://`.

## The stand-ins

For working on this on a machine that has no saves on it — or no Windows.

**`fake_game.py`** pretends to be the game: it writes autosaves into a folder
and rotates them the way Victoria 2 does, three deep and then gone. Each save
carries a real header, so the keeper reads it exactly as it reads a real one.
Halfway through, Prussia forms Germany and every later save says `GER` — so
the keeper's folder should rename itself to `PRU-GER 1836` rather than
starting a second campaign.

```
python3 testkit/fake_game.py ~/vic2-testkit/saves --months 12 --every 3
```

Then point **Keep autosaves** at that folder and press Start.

On anything but Windows the keeper falls back to polling, because waking on
the write is a Windows call, so leave `--every` above the poll interval or it
will look like it is missing saves when it is only asleep.

**`mock_host.py`** pretends to be the report host in `host/`, speaking the
same two endpoints and applying the same checks — including reading the
Content-Security-Policy straight out of `worker.js`, so the two cannot drift
apart.

```
python3 testkit/mock_host.py 8753
```

Then put `http://127.0.0.1:8753` into **Share → Upload to a report host**. The
link it gives back opens in a browser like a real one would, under the real
policy, which is the part worth testing: a policy that quietly breaks every
hosted report would be an unpleasant thing to discover in production.

Neither of these is needed to use the analyzer, and neither is in the
executable.
