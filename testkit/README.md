# Testing it

Two kinds of thing live here: checks that hold the analyzer to what it is
supposed to do, and stand-ins for the parts of the world it talks to.

## The checks

All of them, in the right order, with one command:

```
python3 testkit/all.py "/path/to/saves" --mod "/path/to/mod"
python3 testkit/all.py "/path/to/saves" --quick     # skip the slow ones
python3 testkit/all.py --update-expected           # after a deliberate change
```

The suite includes the recorded answers, cache invalidation, GUI, browser
and CLI checks. Allow a few minutes for a full campaign run. A check that cannot run here — no Firefox, no display, no
mod, no saves — says so, exits 77 (`outcome.SKIPPED`), and does not count
against the total. One that
fails prints its own output in full, because the point of a suite is the
one that broke.

Or one at a time:

```
python3 testkit/tooearly.py                       # no saves needed
python3 testkit/saveshapes.py                     # no saves needed
python3 testkit/edges.py                          # no saves needed
python3 testkit/facts.py out/report.html          # the report is optional
python3 testkit/invariants.py out/nations_timeseries.csv out/report.html
python3 testkit/mangled.py ["/path/to/one/save.v2"]
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
python3 testkit/raster.py                        # no saves needed
python3 testkit/staleness.py                     # no saves needed
python3 testkit/mobrate.py                       # no saves needed
python3 testkit/crossrows.py                     # no saves needed
python3 testkit/caching.py                       # no saves needed
python3 testkit/engine_runtime.py                # no saves needed
python3 testkit/enginefmt.py scanner/target/release/vic2scan 20000
python3 testkit/enginecompress.py scanner/target/release/vic2scan
python3 testkit/modread.py [--mod "/path/to/mod"] # no saves needed
python3 testkit/frontcheck.py                    # no saves needed
python3 testkit/window.py "/path/to/saves"
python3 testkit/enginecheck.py "/path/to/saves" --mod "/path/to/mod"
python3 testkit/smoke.py "/path/to/saves" --mod "/path/to/mod"
```

**Recorded answers.** Until 1 Oct 2026 every run could be made two ways,
by the Rust scanner and by the Python it replaced, and the checks held the
one to the other by running each case both ways. The Python is gone now,
and what it answered was written down first (`expected.py`): for every
case, the exit status, stdout and stderr, every file the run left but the
stamp, and the page as what it carries -- the payload as indented JSON with
its flags and state snapshots decoded, and the page around it as its
difference from the template. The synthetic cases are in `expected/`.
The real campaign's cases are in `expected-real/` (or wherever
`$VIC2_EXPECTED_REAL` points), keyed by the saves' file names and sizes and
the mod's folder name, so they run on any machine with the same saves and
mod; a check that finds none says so and skips them. The real mod's
answer names the folders it was read from MOD and GAME, so it holds
wherever the game is installed.

A check that disagrees with its record prints the difference, cut down to
where it is. After a deliberate change, one command writes the program's
present answers over the old ones, and `git diff testkit/expected` shows
what changed:

```
python3 testkit/all.py "/path/to/saves" --mod "/path/to/mod" --update-expected
```

Six checks hold a run to its record: `frontcheck.py`, `saveshapes.py`,
`mangled.py`, `crossrows.py`, `modread.py` and `enginecheck.py`. Each takes
`--update` on its own as well.

**`modread.py`** holds the report engine's mod reader
(`scanner/src/engine/modread.rs`) to its recorded answers: what
`vic2scan mod-export` makes of a folder, as JSON text, and which folders it
refuses. It runs the reader's regular expressions against Python's `re`,
reads a world written to be awkward (a mod over a game, names differing
only in case, Windows-1252 localisation with its gaps, a block where a
name belongs, `1_000`), then that world damaged at random a thousand
times, and the real mod when `--mod` names one.

**`frontcheck.py`** holds the scanner's `analyze` mode -- every run, from
the command line and the window alike -- to its recorded answers: every
refusal it words, one save, two saves of one date, `~` and `$VAR`, a
relative path, the settings, a table open elsewhere, "nothing has changed",
saves laid out another way, the diagnostics, `--peek`, `--verify`,
`--cross`, and files that cannot be read at all.

**`saveshapes.py`** reads the shapes a save can take and real campaigns
do not -- a pop with a mod's own block nested inside it, a province with no
owner, an army loaded onto a transport, a key that appears twice, two of a
nation's states in one region, a save with its countries first or laid out
with spaces -- each as a report, with `--peek` and with `--verify`, and
holds every answer to its record.

**`enginecheck.py`** runs the real program a dozen ways over a world of
edge cases, and over a handful of real saves under the real mod with rules
added that the campaign never meets, and holds every answer to its record.

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
no army and no war. The damage is seeded, so a failure is
reproducible, and without a save named each damaged copy of the furnished
save is held to its record.

**`invariants.py`** checks the arithmetic the report's own numbers have to
satisfy — 58 rules over every nation in every save, and, given the report
as well, the shape of the data inside it: that every column is as long as
the list of dates it is read against, that every technology index points at
a technology, that a war ends after it starts and its battles happen while
it is being fought, that a war's losses are its battles' losses. The
recorded answers prove a run says what it said before; they do not prove
it was right. These are the identities
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
reconstructs them is in the template while its description is `rebuild_facts`
in `facts.py`. This checks the pair; `boots.py` checks the template's copy,
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

**`raster.py`** decodes a small bitmap of awkward runs -- a colour the map
does not name, two colours for one province, runs carrying into the next
row, row padding, rows a scale skips -- and compares it with a reading done
a pixel at a time, at four scales.

**`caching.py`** holds a run read out of the engine's cache to one made
with `--no-cache` on the same saves, after something has changed under the
cache: a save rewritten to the same size within the same second, every
entry damaged and then cut in half, the mobilizable pop types changed, a
save replaced by another of the same name, and one save read at a time
against several at once.

**`engine_runtime.py`** checks the scanner's output relayed to the window
and a missing scanner refused with the command that builds it, and that no
writable test world links back into a real install.

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
