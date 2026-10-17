# Wars

Wars: what a save keeps about them and how the Wars tab reads it.

Every war in the campaign, its battles, and what it actually took.

Battles are split into land and naval by the unit types present, read from the
mod's own `units/*.txt`, and every column of both tables sorts -- including each
side's losses, so the costliest engagement of a war is one click away. Land that
changed hands is reported by state rather than province: five names under Tabriz
is one line, not five.

**Battle dates take the whole folder.** A save dates only its most recent
battles and drops the dates from older ones -- the 1908 save can date 33 of its
1,310. Reading all 38 saves lifts that to **1,217 of 1,359, about 90%**, because
each save catches a different window and the windows tile the campaign. What is
still undated is shown as unknown.

The obvious shortcut does not work. Scanning the file and stamping each battle
with the last date seen -- which is what the one other tool of this kind does --
is **3% correct here**: in a finished war the battles are written *before* the
dated events, so every battle inherits a date from the war above it in the file.
Three battles of Dresden come out as 1836.8.25 against a true 1836.9.13,
1836.9.18 and 1836.9.26; Gharyan lands eleven months out.

**A war is identified by who fought it, not by when it started.** The start is
the earliest dated entry in a war's history, and that history is trimmed as the
war ages -- battles lose their dates first. A war caught while it was being
fought therefore starts at its first battle, and the same war read from a later
save starts at whatever dated entry survives, often the engine's own removal
events on the day it ended. Keying the merge on the start date gave those two
readings two identities, so the copy taken while the war was live was never
told it had finished and sat in the table marked **ongoing** for the rest of
the campaign, the real ended row beneath it. Wars are now folded on name and
original belligerents, and two fights that share those -- a name does repeat
across a century -- are separated by whether the stretches of time they cover
overlap. A record still being fought covers everything after it until some save
reports the war over; that is what lets a later, barely-dated reading rejoin
it, and what stops it swallowing the next war of the same name.

**A war cannot end before its own last battle.** The end date comes from the
first save that caught the war finished, whose history is already being
trimmed, and it can be earlier than battles other saves dated. The 3rd American
War of Independence came out ending 1874.8.3 -- the day one defender dropped
out -- with three battles running on to 1874.8.25. Where the two disagree the
battle wins, which also puts the before-and-after ownership check on the right
side of the peace.

**War goals are read, not inferred.** A war carries more than one demand: the
one it opened with plus any added while it ran, each naming a claimant, a target
and a state. Added demands are dropped when the war ends, so like battle dates
they survive only in a save taken while the war was live -- 52 of 270 wars here.

Those demands carry an `is_fulfilled` flag, and it is worth being clear about
what it is not. It means the claimant held the state **by siege at the moment
that save was taken** -- a live condition, not the peace. Across the goals where
both a flag and a territorial answer exist, the two agree only **44%** of the
time, and 26 goals were occupied mid-war and took nothing at all. So the report
shows them as separate columns: *taken at the peace*, from who owned the state
either side of the war, and *occupied mid-war*, from the flag.

This matters more than it sounds. The French Conquest of Friesland looks like a
Franco-Prussian affair, and its original goal is exactly that. Caught mid-war in
an 1857 save it turns out to carry three demands, the third an American claim on
Mexico for Georgia -- which is why Atlanta, Savannah and four more provinces
change hands in a war named after a Dutch province. All three demands read as
occupied; only that third one took anything.
