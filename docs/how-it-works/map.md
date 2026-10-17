# The deployment map

The deployment map: how armies, fleets and occupation are drawn on it, and how the campaign plays back.

With `--mod-path` the **Nations** tab opens on a map: a political map of the campaign
with every army drawn where the game stacks it, sized by brigade count and
coloured by its nation, using the nation colours out of the mod's own
`common/countries/*.txt`. Hovering a marker names the province and breaks the
stack down by nation and unit type — "Bern, 113 brigades, KUK 85 artillery 71
hussar 14, FRA 28 artillery 28".

It is built to stay light enough to carry every save in a campaign:

- The province bitmap is 5616x2160 and 36 MB. It ships as a run-length encoded
  grid of province ids at half scale -- 2808x1080, about 660 KB of base36 text.
  Only sampled rows are read, so building it costs a fraction of a second rather
  than the minute a full decode would take.
- One raster serves every save. Only ownership changes, and that ships as a
  delta against the previous save: an 1836 base of 2,297 provinces is followed
  by a few hundred changes per snapshot.
- Occupation rides along as a full list each save, because it is a couple of
  dozen provinces rather than thousands. The **Control** button switches the
  shading between who holds ground and who owns it, which separates a front line
  from an annexation.

Roughly 300 KB for two saves. Narrow the nation list to strip the markers back
to the nations you care about; the land stays shaded so the geography does not
move under you.

**The hole in the Tibesti.** Victoria 2 paints about 8,000 pixels of northern
Chad into `provinces.bmp` in a magenta -- RGB 208,17,223 -- that `definition.csv`
never names, and it is the only unnamed colour on the map. Vanilla has it, and so
does every mod built on the vanilla bitmap. It is drawn as unclaimed land and
left that way. Filling it from its neighbours was tried and reverted: the map
would have shown someone owning ground nobody owns, which is worse than a blank
patch that matches what the game itself shows.

**Nations are drawn in their own colours.** Tags, chart lines and picker
swatches take the colour the mod gives the nation in `common/countries/*.txt`,
so the report reads like the game. About a third of them are unusable as ink on
a burgundy page -- Prussia ships a near-black navy, Russia a bottle green -- so
each is checked against the ground and lifted only if it fails, keeping its hue
and moving its lightness until it clears a contrast ratio of 3.4. Saturation is
floored so near-greys do not wash out and capped so a fully saturated dark comes
up as ink rather than neon. On one campaign 91 of 126 nations keep their exact
game colour and the worst contrast on the page is 3.42. The map itself is
untouched: it paints the raw colours, because there it is the map.

**Nations in a picker are the ones in the save.** Anything read at one date --
the tech tree, the culture table, the force comparison, the map -- offers only
the nations that hold land in the save selected beside it, which on a late save
is twenty-one rather than the campaign's hundred and twenty-six. The options are
hidden rather than removed, so stepping back to an earlier save brings them
straight back with the selection intact. Anything plotted across every date
keeps the full list, because a nation that ended in 1860 still has a line worth
drawing.

**Zoom and pan.** Scroll to zoom on the cursor, drag to pan, double-click to zoom
in, **Reset** for the whole world. Markers grow more slowly than the map, so a
crowded theatre thins out as you go in rather than turning into one blob: at
6.8x only 88 of 371 stacks are on screen. Click a marker to pin its readout while
you look elsewhere. The political map is painted once per save into an offscreen
canvas and blitted at whatever zoom is in force, so panning does not repeat the
per-pixel work.

One trap worth recording. The province bitmap declares a positive height, which
in a BMP means the rows are stored bottom-up, but this one is stored top-down:
file row 168 holds Sitka, whose own position is 168 rows from the top. Trusting
the header puts Alaska in the southern ocean. Check orientation against a
province you can place rather than against the spec.

`--map-scale` trades size against sharpness, and it is a one-off cost however
many saves are in the report: the default 2 gives 2808x1080 for about 660 KB, 3
gives 1872x720 for 410 KB, 5 gives 1123x432 for 230 KB and is visibly blocky
once you zoom, and 1 is the map at native resolution for 1.4 MB. Decoding half
scale takes 24 ms and the first paint 38 ms; native quadruples both. Without
`--mod-path` there is no bitmap to read and the tab is dropped rather than shown
empty.

Two traps, both recorded because each cost an afternoon. The bitmap declares a
positive height, which in a BMP means bottom-up rows, but this one is stored
top-down -- file row 168 holds Sitka, whose own position is 168 rows from the
top -- so trusting the header puts Alaska in the southern ocean. And the canvas
needs an explicit CSS size: without one it falls back to its `width`/`height`
attributes, which are the raster's, and a 2808px canvas bursts straight out of
the page.

## One column, as wide as the window

The sheet was 1180 pixels wide, chosen when the widest thing on it was a
paragraph. What is on it now is mostly a twenty-column table, a chart or a world
map, and on an ordinary 1080p screen that left a third of the window empty on
either side. It is `min(1800px, 96vw)` instead.

A `max-width` only ever gives room back, so this costs a small screen nothing:
at 1366 the sheet is 1311 and at 3840 it stops at 1800 rather than becoming a
two-thousand-pixel wall of text. `vw` rather than `%` because the sheet is the
page's only column, and the 4% left over covers the scrollbar `100vw` counts and
`clientWidth` does not.

The map briefly had a `.bleed` rule stepping it out of the column and across the
whole window, on the grounds that the world raster is 2.6 times as wide as it is
tall. It looked wrong for a simpler reason than any of that: a map wider than
the sheet it sits in reads as a mistake, whatever its aspect ratio. Widening the
column and leaving the map inside it gets the same map at the same size with
nothing sticking out.

The notes under each figure were given a reading measure of their own for a
while, on the grounds that prose runs to two hundred characters a line at 1,700
pixels. It looked worse than the long line did: a paragraph that stops half a
screen short of the chart it is explaining reads as text that has been cut off.
Everything in the column is now the width of the column.

## Occupation is drawn over the map, not into it

Shading a province in the colour of whoever is holding it made a siege and an
annexation look identical, so land keeps its owner's colour and occupied ground
is hatched diagonally in the occupier's on top.

The hatching is a mask applied on the screen rather than stripes painted into
the raster. The raster is 5,616 pixels wide and the panel is about 1,100, so a
stripe baked into it at a width that reads at zoom 1 would be half a province at
zoom 24 -- the hatching would grow with the map instead of staying a texture on
it. So `mapPaintBase` builds a second canvas holding only the occupied
provinces, in the occupier's colours, everything else transparent; each frame
that layer is drawn into a screen-sized scratch canvas, masked with
`destination-in` against a repeating 9-pixel diagonal tile, and blitted over the
map. The tile is built once from an `ImageData` where alpha follows
`(x + y) % 9`, which wraps cleanly at the tile edge so the stripes join up.

Two canvases rather than one because `destination-in` eats everything already on
the canvas it runs on, and the map underneath has to survive.

Two things keep the owner readable under all that. The occupation layer skips
every pixel the edge mask marks, so province borders are never hatched over --
without that, a stripe of occupier colour ran straight across the line between
two provinces and it became a guess which one the ground belonged to. And the
stripes cover three pixels of the nine-pixel tile rather than five: the occupier
has to be legible, but it is the owner's province and the owner's colour should
still be the one the eye lands on.

Neither is a substitute for saying it outright, so hovering any land names the
province, its owner and whoever is holding it. `mapProvinceAt` is the painting's
own lookup run backwards -- screen point to map pixel to `mapProv[y * w + x]` --
which round-trips exactly at every zoom from 1 to 24, and costs one array read
per pointer move. An army marker still wins the readout when the cursor is on
one, and it now carries the same two lines above its brigade count.

## Playing the campaign back

A run of saves is a campaign in the order it happened, and the only way to watch
it move used to be picking each date in turn. The slider beside the save
dropdown is the same choice by another route -- both set the save and go through
`mapSave.onchange`, so the picker, the great power panel and the readout stay in
step -- and **Play** walks it, at 250 ms a frame, or half or a fifth of that
under the 1x/2x/5x button beside it. A repaint costs about 120 ms and the picker
refresh doubles it to roughly 300 ms, so even first gear is asking for frames
faster than they can be drawn. What is waited is the rest of the frame's slot
rather than the whole slot on top of the drawing, so 1x is a quarter of a second
a frame and not a quarter of a second plus however long the frame took -- which
is the difference between a third of the old pace and half of it.

That is why each frame books the next one after it has finished drawing rather
than every frame being booked in advance on an interval. An interval would keep
firing while the previous frame was still painting and the queue would run away
from the machine; a chain of timeouts simply plays back as fast as the machine
manages, which is the failure worth having -- and it is what makes asking for
50 ms a frame at 5x a reasonable thing to do rather than a way to hang the tab. Pressing Play while sitting
on the last save rewinds to the first, and leaving the tab stops the timer,
since a slideshow nobody is looking at is just work.
