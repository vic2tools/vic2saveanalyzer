# Military technology grouping

How military technologies are grouped in the Technology tab.

Saves list technologies as bare names with a researched flag and no folder
information, so `ARMY_LINES` and `NAVY_LINES` in `scanner/src/front/mod.rs` hold
the mapping from tech to army or navy line. Those are the vanilla names, which most mods reuse. Anything unrecognised
is reported under `other` in `technologies.csv` rather than dropped, so a mod's
own techs are still visible — add them to those lists to have
them appear in the report's technology matrix.
