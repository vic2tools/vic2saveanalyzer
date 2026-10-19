"""
The analyzer's Python side: the window, the command line that hands a run to
the Rust scanner, and the autosave keeper. `launch` reads a run's settings
and hands the run to the scanner (`scanner/`), relaying what it says;
`report_tab` is the window's report tab and what it asks before a run;
`keeper` keeps every autosave the game writes, and `keeper_tab` is its tab;
`share` turns a finished report into a link; `settings` is what the window
remembers; and `__main__` is the executable's entry, the window, or the
command line when given arguments.
"""
