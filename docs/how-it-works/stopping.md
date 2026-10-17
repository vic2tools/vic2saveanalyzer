# Stopping a run

What Stop does, and why a stopped run costs nothing next time.

The window runs the scanner as a child process and relays what it prints
(`vic2_analyzer.py`, `_relayed`). Between lines it asks whether Stop was
pressed; when it was, it kills the scanner and the run ends as stopped, with
`Cancelled`. `testkit/engine_runtime.py` holds that a Stop ends the scanner
and leaves no process behind. A run from a terminal has no Stop: Ctrl-C ends
it.

Every save the scanner finished reading is already in its cache
(`vic2_analyzer_cache`, in the temp folder), so starting again picks up where
it left off.
