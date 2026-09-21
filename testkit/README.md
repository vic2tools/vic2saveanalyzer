# Testing it

Two kinds of thing live here: checks that hold the analyzer to what it is
supposed to do, and stand-ins for the parts of the world it talks to.

## The checks

All of them, in the right order, with one command:

```
python3 testkit/all.py "/path/to/saves" --mod "/path/to/mod"
python3 testkit/all.py "/path/to/saves" --quick     # skip the slow ones
```

Ten checks, about twenty seconds without the smoke matrix and a few
minutes with it. A check that cannot run here — no Firefox, no display, no
mod, no saves — says so and does not count against the total. One that
fails prints its own output in full, because the point of a suite is the
one that broke.

Or one at a time:

```
python3 testkit/tooearly.py                       # no saves needed
python3 testkit/awkward.py                        # no saves needed
python3 testkit/countries.py                      # no saves needed
python3 testkit/edges.py                          # no saves needed
python3 testkit/facts.py out/report.html          # the report is optional
python3 testkit/invariants.py out/nations_timeseries.csv out/report.html
python3 testkit/mangled.py "/path/to/one/save.v2"
python3 testkit/parity.py "/path/to/saves" 8
python3 testkit/boots.py out/report.html
python3 testkit/keeping.py                        # no saves needed
python3 testkit/sharing.py                       # no saves needed
python3 testkit/packing.py                       # no saves needed
python3 testkit/window.py "/path/to/saves"
python3 testkit/spawned.py "/path/to/saves"
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

**`mangled.py`** feeds the reader damaged saves — cut in half, bytes
flipped, a piece missing from the middle, braces rubbed out, digits turned
into letters, the header gone, a run of nulls. A save folder collects these
in real life: a crash while the game was writing, a bad sector, a sync
client copying a file mid-write. The right answer is to read what is there
or refuse it in a sentence; a stack trace is never right, and it would take
the whole campaign down with it. The mutations are seeded, so a failure is
reproducible.

**`invariants.py`** checks the arithmetic the report's own numbers have to
satisfy — 58 rules over every nation in every save, and, given the report
as well, the shape of the data inside it: that every column is as long as
the list of dates it is read against, that every technology index points at
a technology, that a war ends after it starts and its battles happen while
it is being fought, that a war's losses are its battles' losses. Parity proves the two
readers agree; it does not prove either is right. These are the identities
that hold whatever the save says: the strata are a partition of the
population, a percentage is its own numerator over its own denominator,
brigades are the standing ones plus the mobilized ones, a count is never
negative, a share is never above a hundred.

Three of its first draft's rules were wrong rather than the code — a
factory under construction really is one factory and no levels, and the
soldier share really is taken against the whole nation including colonies,
which the comment beside it says and means. That is the useful failure
mode: a rule that breaks is either a bug or a thing worth understanding.

**`smoke.py`** runs every way the analyzer can be asked to run — quiet and
loud, with and without a mod, every diagnostic, `--cross` — and checks what
each one *says*. Exiting 0 is not enough: `--inventions` once exited 0 while
answering zero of 387, and `--explain-mob` exited 0 after replying "nothing
has changed" and explaining nothing. `--analyzer` points it at another
tree's code, which is how a new case is shown to fail on the version it was
written for.

**`facts.py`** holds the two halves of the `facts` split to being inverses.
The report ships `series` whole and `facts` stripped of everything `series`
already carries — the same numbers in two orientations, and a seventh of the
file when both travelled — and the page transposes them back at boot. So the
report shows numbers that are not in the file it came in, and the loop that
reconstructs them is in the template while the pair it has to agree with is
in `report.py`. This checks the pair; `boots.py` checks the template's copy,
because if the two drift every table on the page is empty or wrong.

**`tooearly.py`** looks for a local read on a line above every line that
binds it. That is an `UnboundLocalError` waiting for whichever path reaches
it first, and it has shipped twice.

**`sharing.py`** runs every way uploading a report can fail. The share
button is aimed at somebody who wants to show a friend their campaign and
would not know what to do with a stack trace, so nearly all of
`publish.upload` is error messages — seven of them — and none had been run.
Answers come from little servers started on the loopback address, one per
behaviour: nothing listening, an answer that is not JSON, a host that takes
the file and forgets to say where it put it, one that says it is too large,
one that refuses it, and one that works. Nothing leaves the machine and no
real report is used.

**`packing.py`** checks the executable would carry every module the program
needs. `build_exe.py` names them explicitly, because most are imported
inside functions and a bundler's scan does not always follow that — which is
right, and has the obvious failure: add a module, forget the list, and the
executable builds cleanly, starts cleanly, and dies on whichever button
reaches the missing import, on somebody else's machine. This walks the
imports out from `app.py` and compares.

**`keeping.py`** drives the keeper through a campaign, without the game and
without waiting. The keeper is the part that loses data when it is wrong:
Victoria 2 keeps three autosaves and drops the fourth, so a month it misses
is a month nobody has any more, and nothing later can notice. It had no test
at all.

It plays eighteen months a month at a time — synchronously, so the answer
never depends on a sleep being long enough — and checks that every month
comes out the other side, once, in one folder named for both the nation that
started and the one it became. Then it writes three months with the keeper
switched off and runs it once: all three have to arrive, because two months
behind is still inside the game's three-deep rotation.

Both halves were made to fail. A keeper reading only `autosave.v2` loses two
of the three. A keeper that cannot match a campaign across a formation turns
eighteen months into fifty-one folders.

**`window.py`** runs a real campaign through the window's own code path,
with the window withdrawn. Everything else drives the analyzer through its
command line, and the window is not that path: it builds its own argument
list, replaces stdout with a queue, and hands over a cancel check, a
progress callback and a report-ready callback. It checks that the report is
written and announced, that the progress bar counts up to the total and
stops there, that the report is opened *when it is written* rather than
only when the run ends, that something real gets launched to open it on
this platform, and that pressing Stop gives up quietly.

Writing it found that the window wired half its callbacks in `start`, next
to the buttons, and the other half in `work`. Anything driving `work`
directly got a run with the early open and the progress bar missing, and
nothing about the finished run looked different. A run owns its own wiring
now.

**`spawned.py`** reads a campaign the way Windows reads it. Linux forks its
workers, so each one begins with the parent's memory already in it; Windows
spawns a fresh interpreter that re-imports everything, which means anything
passed to a worker has to survive pickling by name and anything set up
after import has to be handed over rather than inherited. This is developed
on Linux and shipped as a Windows executable, and nothing had ever run it
the way it actually runs there. It builds the same campaign both ways and
compares every file byte for byte.

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

**`fake_save.py`** writes one save-shaped file — the header scalars, a
couple of thousand province blocks each holding a dozen pops, a couple of
hundred country blocks — in roughly the proportions a real save has them.
With `--campaign N` it also writes N monthly saves dated in order, which is
how the analyzer gets measured against a campaign nobody here owns:

```
python3 testkit/fake_save.py /tmp/base.v2 --mb 2 --campaign 1000
python3 vic2_analyzer.py /tmp/base-campaign --out /tmp/out
```

A thousand saves, 2.4 GB: 12.0 s cold, 9.9 s again, 0.06 s when nothing
changed, 1.1 GB at its peak, and the report opens. The cost is linear in
the number of saves — 9.7 times the saves for 9.6 times the runtime — which
is the thing worth knowing, because a century of monthly autosaves is the
case this was built for and is not a case anybody has lying around.

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
