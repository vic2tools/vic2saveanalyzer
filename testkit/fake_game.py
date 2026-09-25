#!/usr/bin/env python3
"""
A stand-in for Victoria 2, for testing the keeper without the game.

Writes autosaves into a folder and rotates them exactly as the game does --
`autosave.v2` becomes `oldautosave.v2` becomes `olderautosave.v2`, and the
fourth one is gone. Each save carries a real header: a date, the player's tag,
a start date and a flags block, which is what the keeper reads to work out
which campaign a save belongs to.

Halfway through, Prussia forms Germany. The tag in every later save changes
from PRU to GER, and the keeper should follow the campaign across that rather
than starting a second folder -- watch its folder rename itself to
`PRU-GER 1836`.

    python3 fake_game.py ~/vic2-testkit/saves --months 24 --every 2

Ctrl-C stops it. Nothing here touches a real Victoria 2 install.
"""

import argparse
import os
import sys
import time

FLAGS = ["the_great_trek", "liberal_revolution_somewhere", "MozartFest1838",
         "piet_retief_massacre", "botanical_expedition_in_progress",
         "doctrine_of_lapse_has_been_used", "Nabucco", "LouisNapoleonExtradite",
         "marching_on_the_trail_of_tears", "liberal_revolutions_should_now_fire",
         "money_setup_done", "crimean_war_has_begun", "opium_war_started",
         "sonderbund_crisis", "risorgimento_started", "meiji_restoration"]

# A real save carries a good handful of these within a few years, and the
# keeper needs at least `savehead.FLAG_FLOOR` of them on both sides before it
# can tell two readings of one campaign from two campaigns. Granting only
# two, as this did at first, made a formation look like a new game -- which
# is a true thing about the keeper worth knowing, but not what this is here
# to demonstrate.
FLAGS_AT_START = 6


def a_save(year, month, tag, size, n=0, flags=FLAGS):
    """
    A plausible save: a real-looking header, then filler to size. `flags` is
    the history it grants from; another list is another game.
    """
    head = ['date="%d.%d.1"' % (year, month), 'player="%s"' % tag,
            "government=3", "automate_trade=no", "rebel=0", "flags=", "{"]
    # Flags accumulate as a game runs, which is how two saves are recognised
    # as one campaign. So grant one more of them every few months.
    for flag in flags[:min(len(flags), FLAGS_AT_START + n // 3)]:
        head.append("\t%s=yes" % flag)
    head += ["}", 'start_date="1836.1.1"', "start_pop_index=152437",
             "worldmarket=", "{", "\tworldmarket_pool=", "\t{"]
    text = "\n".join(head) + "\n"
    filler = "\t\tgoods_%d=%d.00000\n" % (0, 1000)
    while len(text) < size:
        text += filler
    return (text + "\t}\n}\n").encode("latin-1")


def rotate(folder):
    """Shuffle the three names along, dropping whatever falls off the end."""
    auto = os.path.join(folder, "autosave.v2")
    old = os.path.join(folder, "oldautosave.v2")
    older = os.path.join(folder, "olderautosave.v2")
    if os.path.exists(old):
        os.replace(old, older)
    if os.path.exists(auto):
        os.replace(auto, old)


def main():
    ap = argparse.ArgumentParser(description="Pretend to be Victoria 2.")
    ap.add_argument("folder", help="where to write the autosaves")
    ap.add_argument("--months", type=int, default=24,
                    help="how many autosaves to write (default: %(default)s)")
    ap.add_argument("--every", type=float, default=2.0, metavar="SECONDS",
                    help="seconds between them (default: %(default)s)")
    ap.add_argument("--size", type=float, default=4.0, metavar="MB",
                    help="size of each save; the real thing is 20-30 "
                         "(default: %(default)s)")
    ap.add_argument("--forms-at", type=int, default=None, metavar="N",
                    help="month at which Prussia forms Germany "
                         "(default: halfway)")
    args = ap.parse_args()

    os.makedirs(args.folder, exist_ok=True)
    forms = args.forms_at if args.forms_at is not None else args.months // 2
    size = int(args.size * 1024 * 1024)
    print("Writing %d autosaves of %.1f MB into %s, one every %.1fs."
          % (args.months, args.size, args.folder, args.every))
    print("Prussia forms Germany at save %d.\n" % forms)

    year, month = 1836, 1
    try:
        for n in range(1, args.months + 1):
            tag = "PRU" if n < forms else "GER"
            rotate(args.folder)
            # Written to one side and moved into place, so the keeper never
            # sees a half-written file -- which is what the game does too.
            part = os.path.join(args.folder, "autosave.v2.writing")
            with open(part, "wb") as fh:
                fh.write(a_save(year, month, tag, size, n))
            os.replace(part, os.path.join(args.folder, "autosave.v2"))
            print("  %s %d.%d.1 as %s" % (time.strftime("%H:%M:%S"), year,
                                          month, tag))
            month += 1
            if month > 12:
                year, month = year + 1, 1
            time.sleep(args.every)
    except KeyboardInterrupt:
        print("\nstopped")
        return 0
    print("\nDone. The game kept the last three; the keeper should have "
          "kept all %d." % args.months)
    return 0


if __name__ == "__main__":
    sys.exit(main())
