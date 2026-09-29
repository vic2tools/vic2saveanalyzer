# Testing it

Two kinds of thing live here: checks that hold the analyzer to what it is
supposed to do, and stand-ins for the parts of the world it talks to.

## The checks

All of them, in the right order, with one command:

```
python3 testkit/all.py "/path/to/saves" --mod "/path/to/mod"
python3 testkit/all.py "/path/to/saves" --quick     # skip the slow ones
```

The suite includes parser parity, cache invalidation, worker startup, GUI,
browser and CLI checks. Allow a few minutes for a full campaign run. A check that cannot run here — no Firefox, no display, no
mod, no saves — says so, exits 77 (`outcome.SKIPPED`), and does not count
against the total. One that
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
python3 testkit/parity.py ["/path/to/saves"] [8]   # builds one if none
python3 testkit/boots.py out/report.html
python3 testkit/state_history_ui.py out/report.html # every decoded state value and order
python3 testkit/map_rendering.py out/report.html # map pixels, seams, and cache reuse
python3 testkit/looks.py out/report.html shot.png   # for eyes, not for CI
python3 testkit/keeping.py                        # no saves needed
python3 testkit/histories.py                      # no saves needed
python3 testkit/sharing.py                       # no saves needed
python3 testkit/savefmt.py                       # no saves needed
python3 testkit/packing.py                       # no saves needed
python3 testkit/matching.py                      # no saves needed
python3 testkit/modcache.py                      # no saves needed
python3 testkit/raster.py                        # no saves needed
python3 testkit/noworkers.py                     # no saves needed
python3 testkit/staleness.py                     # no saves needed
python3 testkit/mobrate.py                       # no saves needed
python3 testkit/crossrows.py                     # no saves needed
python3 testkit/record.py                        # no saves needed
python3 testkit/caching.py                       # no saves needed
python3 testkit/window.py "/path/to/saves"
python3 testkit/spawned.py "/path/to/saves"
python3 testkit/smoke.py "/path/to/saves" --mod "/path/to/mod"
```

**`savefmt.py`** writes save-shaped text, and is the only place in here
that knows the format. The tab depth *is* the format — both the reader and
the mod sniffer find things by it — so a builder one tab out writes a file
that parses without complaint and carries none of what it was supposed to.
Four files here had each encoded that separately, and it had already gone
wrong once: `matching.py` wrote its technology blocks flat, the sniffer
found no technologies in them, and the check that was meant to prove a
campaign is matched by its technologies passed for a different reason
entirely. Running it on its own builds a save with every shape in it — a
pop with a nested id and an ideology block, a country with a stockpile and
an army — and reads it back through *both* readers, because the tolerant
one alone catches nothing:

```
python3 testkit/savefmt.py
```

**`parity.py`** holds the Rust scanner to the Python parser, save by save,
field by field, exactly — no tolerance, because the floats are accumulated
in the same order on both sides and a tolerance would hide the drift this
exists to catch. It had stopped doing it: the scanner was switched off by
replacing `fastscan.scan`, which `analyze_save` does not call — it calls
`start`, `head` and `collect`, because it works between the scanner's two
halves rather than waiting for both — so the "slow" read ran the scanner
too and this compared it against itself, reporting "identical across 41
nations" for free. It uses `analyze_save`'s own `use_scanner` argument now
and then *checks the scanner stayed off*, because a comparison that has
quietly stopped comparing is the failure this file is for. Given no save
folder it builds one with `savefmt.furnished`, so it runs on a machine that
has never seen a Victoria 2 campaign; real saves are still better where
there are any, since they carry shapes nobody thought to write on purpose.

**`awkward.py`** and **`countries.py`** write saves with the layouts that
are legal but rare — a pop with a mod's own block nested inside it, an army
loaded onto a transport, a province with no owner — and read them both ways.
All three read a save both ways through `readboth.py`. The two smaller ones
had kept the old `fastscan.scan` switch after `parity.py` lost it, so until
they shared it they too compared the scanner with itself: either would
pass with the Python reader raising on every call.

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
the whole campaign down with it. A save cut short is the one that must be
refused, by both readers: read, it is a whole save with most of it missing,
and two thirds of one used to go into the report as 34 of 41 nations with
no army and no war. The mutations are seeded, so a failure is
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

**`matching.py`** builds two nearly identical mods and the save that
belongs to one of them. Reading a campaign under the wrong mod is the worst
answer this program can give, because it is not a wrong label — two mods on
a shared base rate the same cruiser differently, so the same save read under
the other reports guns it never had. Four discriminators, each tried in both
orderings, and the decoy is named so that a tie goes to it: switch any one
discriminator off and exactly its own case fails.

**`modcache.py`** checks cached mod data against fresh reads, including
changes to inherited base-game files, local overrides, parser dependencies,
corrupt cache entries and failed atomic writes. It also checks quoted braces
and the shared tokenizer's block skip.

**`raster.py`** decodes a small bitmap of awkward runs -- a colour the map
does not name, two colours for one province, runs carrying into the next
row, row padding, rows a scale skips -- and compares it with a reading done
a pixel at a time, at four scales. It also checks that `raster_ahead` leaves
the cache entry behind, and starts nothing without a map or with one cached.

**`caching.py`** checks that invention summaries preserve order, skip invalid
saves, survive corruption, and expire after same-size edits within one second.
It compares cached and uncached runs after changing mobilizable pop types,
and checks scanner cleanup on completion, abandonment and timeout.

**`noworkers.py`** takes the workers away and checks the campaign is still
read. A machine that cannot start worker processes is not exotic — a
locked-down laptop, a container with a tight process limit, a sandbox that
refuses `fork`, or a temp folder with a long path, which is the one that
actually happened: Python 3.14 starts workers through a forkserver whose
socket lives in `TMPDIR`, an `AF_UNIX` path cannot exceed 108 bytes, and a
deep enough temp folder took every run down with a stack trace out of the
depths of `multiprocessing`. None of it has to be fatal — every save can be
read one at a time and the answer is the same answer. What made it fatal was
where the guard sat: `ProcessPoolExecutor(...)` succeeds even when no worker
can start, because it starts them on the first `submit`, and the guard was
around the constructor.

**`mobrate.py`** asks what a nation's mobilisation size is, in the cases a
real campaign does not happen to contain. The subtle part is what an empty
contribution list means: **zero**, because an uncivilized nation has no
technology or invention granting mobilisation size — not "unknown, use the
command line". Getting that backwards is a bug this codebase has had twice.
The second time `--explain-mob-pool` wrote `rate_for(...) or args.mob_rate`,
and since `--mobilisation-size` defaults to 1.0 it printed **100%** and a
matching brigade ceiling for nations the report itself scored at **0%**. It
survived because no campaign it was run against had an uncivilized nation in
it, and `smoke.py` only ever asks about ENG.

**`crossrows.py`** builds two campaigns on two mods and runs `--cross` over
them, then checks that the campaign the report is *about* was measured the
same way twice. It is measured twice because that is what `--cross` does: it
compares several campaigns in one block and then builds the rest of the
report out of the largest of them. Those two readings were made by two
copies of one recipe, and the copies had drifted in five places. The cross
one never applied the mod's `POP_SIZE_PER_REGIMENT`, so the same nation's
brigades were divided by the vanilla 3000 in the cross block and by the
mod's own number in the chart directly above it. It overrode `--mob-types`
where the report deferred to it, read the mod's pop list when parsing and
the caller's when counting, counted only `human=yes` as a player so
`--player-nations` went unread, and dropped every nation under one person
where the report keeps them. The check watches the one finishing function
both paths now call, so it compares the settings each path asked for *and*
the numbers each got back -- putting any one of the five divergences back
fails it.

**`record.py`** holds the nation record and its two readers to each other
without needing either of them to run. A save is read in Python by
`readsave` and, where it has been built, by the Rust scanner, whose answer
`nation.fold_provinces` and `nation.fold_country` fold into the same
seventy-two fields. Two implementations of one thing are safe only while
something proves continuously that they agree, and the proof was
`parity.py` alone -- which needs a folder of real saves *and* a compiled
binary and says nothing without both. That is the wrong shape for the
failure it guards: the dangerous drift is not a wrong number on a machine
with a scanner, it is a field one side learns about and the other does not,
which on a machine without one looks exactly like everything working. So
this checks the shape instead, from the sources: every fold rule names a
field the record declares, no field is claimed twice, the save-key names
Python and `scanner/src/country.rs` each keep a copy of still match, every
key the scanner emits is handled and every key handled is emitted, the fold
fills the containers `blank_nation` made rather than replacing them, and a
key nobody accounted for raises instead of being dropped in silence. Seven
ways of drifting were each put in and each came out.

**`caching.py`** checks that a cached answer is the answer the run would
have computed, and that the key it is filed under says everything that
changes it. Part of that is `readsave.Reading`, the one object that says how
a run reads a save, handed to every read with the save: one save read under
a mod, then plain, then under the mod again, with the scanner and without,
has to come back with the mod's pops the first and third time and none of
them the second, and a campaign read in workers has to come back under the
run's reading. That is the shape of the worst bug this file has seen -- a
pop-type set that only grew carried one mod's `bankers` into the next
campaign, read one anyway, and cached it under a key that said it had not. Five ways of making the key and the state
disagree were each put in and each came out.

**`mobrate.py`** also holds the line a mod must not cross when nobody has
decoded its invention indices. A save writes each nation's inventions as
bare numbers into an array the engine builds at load time, and which number
means which invention is only decidable against a save -- so a freshly
loaded mod does not know. It used to say so with `index_base = None`, which
is also what it says once the indices *have* been checked and do not decode.
Those are not the same answer: decoded, a nation's mobilisation size counts
the inventions the save says it rolled; undecodable, `breakdown` falls back
to every invention whose requirements it meets, an upper bound that
overstates nations with poor luck. A caller who forgot to decode got that
upper bound silently, for every nation. The mod refuses the question now
until it has been asked, and the check holds both halves -- refusing before,
and still falling back after.

**`staleness.py`** touches every source file the program has, in a copy of it,
and checks each one moves the report stamp. The stamp is what lets a second run
say "Nothing has changed since this was built" and skip everything — the most
dangerous switch in the program, because when it is wrong nothing looks wrong:
the report opens and every number in it is from the last time somebody looked.
It *was* wrong. The stamp hashed a hand-written list of five filenames, and
`modrules.py` — which decides every nation's mobilisation size — was lifted out
of `mod_reader.py`, which was on that list, and did not inherit its place.
Doubling every rate then changed nothing the stamp could see. The suite could
not catch it, because it tested that the skip happens and never what it is
keyed on.

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

**`histories.py`** holds the rule that tells one game's saves from
another's by their event flags (`savehead`), where the keeper and `--cross`
both use it: two games played as the same nation from the same start must
get two folders from the keeper, and a campaign folder whose first save is
from another game must have that save, and only that one, named by
`history_breaks`. Each used to carry its own copy of the rule, and neither
copy had a check.

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
It also opens every war, and the first battle of each, because a war's detail is drawn only when its row is clicked: until it did, no check had ever run the infobox, which writes more names out of saves into HTML than anything else on the page.
Then it builds a campaign of its own whose war name and one of whose belligerents are script, and requires both to stay text, and the page not to throw: names come out of saves and mods, and a war named `<img onerror=...>` used to run when the Wars tab drew. `boots.py --hostile` runs that part alone.
It also checks the tab the reader lands on has something on it. That one
is there because counting missed it: a report built without a mod opened on
the map tab with no map in it, every section inside hidden, the page blank
— and the counts all looked fine, because the panel still had its children.

Needs Firefox; says so and passes if there is none. A `--split` report will
fail it, and should: its payload is a separate file, and a browser will not
fetch that over `file://`.

**`looks.py`** takes a picture of a report so somebody can look at it.
Nothing here can pass or fail on a picture, and it earned its place anyway:
counting found eight tabs, eight tables and 352 rows in a report whose first
page was blank, and one glance at it found the same thing. The report draws
after the page loads and Firefox screenshots at load, so it holds the load
event open with an image served slowly from the loopback address while the
page gets on with its work.

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
couple of thousand province blocks each holding a handful of pops, a couple of
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
