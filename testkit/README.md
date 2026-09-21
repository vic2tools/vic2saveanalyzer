# Testing it without Victoria 2

Two stand-ins, for working on this on a machine that has no saves on it — or
no Windows.

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
