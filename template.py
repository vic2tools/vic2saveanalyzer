# Victoria 2 campaign analyzer
# Copyright (C) 2026 vic2tools
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU Affero General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version. It is distributed WITHOUT ANY WARRANTY; without even the
# implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
# <https://www.gnu.org/licenses/> for the full text, or the LICENSE file beside
# this one.
"""HTML template for the report. Kept apart so report.py stays readable."""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campaign returns</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@400;500;600&family=Playfair+Display:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  /* Burgundy, parchment and gilt, after the Victoria 2 interface. */
  --ground:#4A1C28; --ground-deep:#2A0F17; --panel:#5E2733;
  --rule:#B08D3F; --grid:#6E3341;
  --ink:#F4E7CC; --ink-dim:#C9AC80;
  --brass:#E7C464; --minium:#D4553F;
  --gilt-hi:#F0D68C; --gilt-lo:#7C5E22;
  --parchment:#EADFC2;
  --sheet-pad:clamp(16px,4vw,44px);
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--ground-deep);color:var(--ink);
  font-family:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased;
}
.sheet{
  max-width:1180px;margin:0 auto;padding:var(--sheet-pad);
  background:
    radial-gradient(120% 60% at 50% 0%,rgba(231,196,100,.10),transparent 60%),
    linear-gradient(180deg,#54212E 0%,var(--ground) 32%,#3E1622 100%);
  min-height:100vh;
  border-left:3px double var(--rule);border-right:3px double var(--rule);
  box-shadow:0 0 0 1px rgba(124,94,34,.55) inset;
}
.titleblock{
  border:1px solid var(--rule);background:rgba(8,25,44,.86);
  display:grid;grid-template-columns:1.6fr 1fr 1fr 1fr;
}
.titleblock>div{padding:12px 16px;border-right:1px solid var(--rule)}
.titleblock>div:last-child{border-right:0}
.tb-label{
  font-family:'Barlow Condensed','Arial Narrow',sans-serif;
  text-transform:uppercase;letter-spacing:.18em;font-size:11px;
  color:var(--ink-dim);margin-bottom:3px;
}
.tb-value{
  font-family:'Barlow Condensed','Arial Narrow',sans-serif;
  font-size:clamp(19px,2.4vw,27px);font-weight:500;letter-spacing:.02em;line-height:1.1;
}
h1.tb-value{margin:0;font-weight:700;letter-spacing:.03em;
  font-family:'Playfair Display',Georgia,serif;color:var(--brass);
  text-shadow:0 1px 0 rgba(0,0,0,.55)}
.tb-value.mono{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:19px}
@media(max-width:760px){.titleblock{grid-template-columns:1fr 1fr}
  .titleblock>div{border-bottom:1px solid var(--rule)}}

.tabs{display:flex;flex-wrap:wrap;margin:0 0 26px;border-bottom:1px solid var(--rule)}
.tab{
  font-family:'Playfair Display',Georgia,serif;
  text-transform:uppercase;letter-spacing:.14em;font-size:13px;font-weight:600;
  background:linear-gradient(180deg,rgba(94,39,51,.85),rgba(42,15,23,.85));
  border:1px solid var(--rule);border-bottom:0;
  color:var(--ink-dim);padding:11px 20px;cursor:pointer;
  margin-right:-1px;margin-bottom:-1px;
}
.tab[aria-selected="true"]{
  background:linear-gradient(180deg,#6B2E3C,var(--ground));color:var(--brass);
  box-shadow:inset 0 3px 0 var(--brass)}
.tab:focus-visible{outline:2px solid var(--brass);outline-offset:-4px}
[role="tabpanel"][hidden]{display:none}

section{margin-bottom:34px}
h2{
  font-family:'Playfair Display',Georgia,serif;
  text-transform:uppercase;letter-spacing:.16em;font-size:15px;font-weight:600;
  color:var(--brass);margin:0 0 12px;padding-bottom:7px;
  border-bottom:1px solid var(--rule);
  text-shadow:0 1px 0 rgba(0,0,0,.5);
}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
select,button,input[type=search]{
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;
  background:linear-gradient(180deg,var(--panel),#431B26);color:var(--ink);
  border:1px solid var(--rule);border-radius:0;padding:7px 11px;
}
select,button{cursor:pointer}
select:focus-visible,button:focus-visible,input:focus-visible{
  outline:2px solid var(--brass);outline-offset:2px}
.controls > button[aria-pressed="true"]{
  background:linear-gradient(180deg,var(--gilt-hi),var(--brass));
  color:#3A1420;border-color:var(--gilt-hi);font-weight:500}

/* ---- searchable picker ---- */
.picker{position:relative;display:inline-block}
.picker-toggle{display:flex;align-items:center;gap:9px;min-width:210px;text-align:left}
.picker-toggle .caret{margin-left:auto;color:var(--ink-dim)}
.picker-panel{
  position:absolute;z-index:20;top:calc(100% + 3px);left:0;width:330px;max-width:88vw;
  background:#3A1420;border:1px solid var(--rule);padding:10px;
  box-shadow:0 10px 28px rgba(0,0,0,.5);
}
.picker-panel[hidden]{display:none}
.picker-search{width:100%;margin-bottom:8px}
.picker-presets{display:flex;gap:6px;margin-bottom:8px;flex-wrap:wrap}
.picker-presets button{padding:5px 9px;font-size:12px}
.picker-list{max-height:260px;overflow-y:auto;border-top:1px solid var(--grid)}
.picker-opt{
  display:flex;align-items:center;gap:9px;width:100%;text-align:left;
  background:transparent;border:0;border-bottom:1px solid var(--grid);
  color:var(--ink-dim);padding:7px 6px;cursor:pointer;
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px;
}
.picker-opt:hover{background:rgba(63,110,150,.24)}
.picker-opt[aria-pressed="true"]{color:var(--ink);background:rgba(242,180,65,.10)}
.picker-opt[aria-pressed="true"] .tag{color:var(--brass)}
.picker-opt .swatch{width:10px;height:10px;flex:0 0 10px;opacity:.25}
.picker-opt[aria-pressed="true"] .swatch{opacity:1}
.picker-opt .tag{width:42px;flex:0 0 42px;color:var(--ink)}
.picker-opt .nm{color:var(--ink-dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.picker-empty{padding:12px 6px;color:var(--ink-dim);font-size:12.5px}

figure{margin:0;border:1px solid var(--rule);background:rgba(42,15,23,.62);
  box-shadow:0 0 0 1px rgba(124,94,34,.35) inset}
svg{display:block;width:100%;height:auto}
/* The map is a fixed-aspect box with the canvas stretched over it. Without the
   explicit CSS size the canvas falls back to its width/height attributes, which
   are the raster's -- 2808px -- and it bursts straight out of the page. */
/* 1-4 down the left, 5-8 down the right, the way the game arranges them */
.gpgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));
  grid-template-rows:repeat(4,auto);grid-auto-flow:column;gap:8px}
@media(max-width:760px){.gpgrid{grid-template-columns:1fr;grid-template-rows:none;
  grid-auto-flow:row}}
.gpcard{display:flex;align-items:center;gap:10px;padding:8px 10px;
  border:1px solid var(--rule);
  background:linear-gradient(180deg,rgba(94,39,51,.9),rgba(42,15,23,.9));
  box-shadow:0 0 0 1px rgba(124,94,34,.4) inset}
.gprank{font-family:'Playfair Display',Georgia,serif;font-size:26px;font-weight:700;
  color:var(--brass);min-width:26px;text-align:right;text-shadow:0 1px 0 rgba(0,0,0,.6)}
.gpflag{width:34px;height:23px;border:1px solid rgba(0,0,0,.6);flex:none;
  object-fit:fill;image-rendering:auto;display:block}
.gpbody{min-width:0;flex:1}
.gpname{font-family:'Playfair Display',Georgia,serif;font-size:17px;color:var(--ink);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gpstats{display:flex;flex-wrap:wrap;gap:10px;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:11px;color:var(--ink)}
.gpstats .rk{color:var(--ink-dim)}
.techgrid{display:grid;gap:6px;align-items:start;margin-bottom:12px}
.techcol{display:flex;flex-direction:column;gap:5px;min-width:0}
.techhead{font-family:'Playfair Display',Georgia,serif;font-size:12px;
  text-transform:uppercase;letter-spacing:.1em;color:var(--brass);
  text-align:center;padding:5px 4px;border:1px solid var(--rule);
  background:linear-gradient(180deg,#6B2E3C,#4A1C28)}
.techbox{font-family:'IBM Plex Sans',system-ui,sans-serif;font-size:12px;
  text-align:left;padding:7px 8px;border:1px solid var(--grid);
  background:rgba(42,15,23,.55);color:var(--ink-dim);cursor:pointer;
  white-space:normal;line-height:1.25;min-height:34px}
.techbox.done{background:linear-gradient(180deg,#4C6B3A,#38502A);
  color:var(--ink);border-color:var(--rule)}
.techbox.open{outline:2px solid var(--brass);outline-offset:-2px}
.techbox:hover{border-color:var(--brass)}
/* A search only means anything relative to its misses: a highlighted match
   reads as "found" mainly because everything else has visibly stepped back. */
.techbox.techmatch{outline:2px solid var(--brass);outline-offset:-1px;
  background:linear-gradient(180deg,#6B4A24,#4A3018);color:var(--ink)}
.techbox.techmatch.done{background:linear-gradient(180deg,#5C7A3E,#3E5828)}
.techbox.techdim{opacity:.32}
.techcatbadge{display:inline-block;margin-left:5px;padding:0 5px;
  border-radius:8px;background:var(--brass);color:#2A0F17;font-size:10px;
  font-weight:700;line-height:15px;vertical-align:1px}
.techinv{margin:1px 0}
.techinv .rk{font-size:10.5px}
.techtitle{font-family:'Playfair Display',Georgia,serif;font-size:16px;
  color:var(--brass);width:100%;margin-bottom:4px}
.techcols2{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));
  gap:14px;width:100%}
.techsub{font-family:'Playfair Display',Georgia,serif;font-size:11px;
  text-transform:uppercase;letter-spacing:.14em;color:var(--ink-dim);margin-bottom:4px}
.techcols2 ul{margin:0;padding-left:16px}
.techcols2 li{margin:1px 0}
#techdetail{display:block}
@media(max-width:760px){.techgrid{grid-template-columns:1fr !important}}
.warrow{cursor:pointer}
.warrow.on{background:rgba(231,196,100,.14)}
.warname{white-space:normal;min-width:230px}
.tagflag{width:18px;height:12px;object-fit:fill;vertical-align:-1px;
  margin-right:5px;border:1px solid rgba(0,0,0,.55)}
.warhead{font-family:'Playfair Display',Georgia,serif;font-size:19px;
  color:var(--brass);margin-bottom:6px}
table.mini{width:auto;min-width:100%}
table.mini td{vertical-align:top}
table.mini td .rk{font-size:11px;white-space:normal}
.selsearch{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;
  background:linear-gradient(180deg,var(--panel),#431B26);color:var(--ink);
  border:1px solid var(--rule);border-radius:0;padding:7px 11px;width:150px}
.selsearch::placeholder{color:var(--ink-dim);opacity:.8}
.mapwrap{position:relative;width:100%;overflow:hidden;background:var(--ground-deep);
  border:1px solid var(--rule);box-shadow:0 0 0 1px rgba(124,94,34,.35) inset}
.mapwrap canvas{position:absolute;inset:0;width:100%!important;height:100%!important;
  image-rendering:pixelated;cursor:grab;touch-action:none}
@media(max-width:640px){
  figure{overflow-x:auto}
  figure svg{min-width:640px}
  .readout{position:sticky;left:0}
}
.axis text{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:10px;fill:var(--ink-dim)}
.gridline{stroke:var(--grid);stroke-width:1}
.axisline{stroke:var(--rule);stroke-width:1}
.plotline{fill:none;stroke-width:1.75;stroke-linejoin:round;stroke-linecap:round}
.plotline.thin{stroke-width:1.35}
/* A tag longer than the gutter still reaches back over the plot, so each
   one carries its own dark outline rather than relying on the space it
   landed in being empty. The leader joining a moved tag to its line is
   drawn faint: it is there to be followed when asked, not to be read. */
.endlab{font-family:'IBM Plex Mono',ui-monospace,monospace;
  paint-order:stroke;stroke:var(--ground-deep);stroke-width:3.2px;
  stroke-linejoin:round;stroke-linecap:round}
.leader{fill:none;stroke-width:.9;opacity:.5}
@media(prefers-reduced-motion:no-preference){
  .plotline{stroke-dasharray:var(--len);stroke-dashoffset:var(--len);
    animation:draw .9s cubic-bezier(.3,.7,.3,1) forwards}
  @keyframes draw{to{stroke-dashoffset:0}}
}
.readout{
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px;
  border-top:1px solid var(--rule);padding:11px 14px;
  display:flex;flex-wrap:wrap;gap:5px 22px;min-height:42px;align-items:center;
}
.readout .rk{color:var(--ink-dim)}
.readout b{font-weight:500}
table{width:100%;border-collapse:collapse;
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12.5px}
th,td{padding:7px 9px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child{text-align:left}
th{
  font-family:'Barlow Condensed','Arial Narrow',sans-serif;font-size:12px;
  text-transform:uppercase;letter-spacing:.13em;color:var(--ink-dim);
  cursor:pointer;user-select:none;border-bottom:1px solid var(--rule);
}
th:hover{color:var(--ink)}
th[aria-sort]{color:var(--brass)}
tbody tr:hover{background:rgba(231,196,100,.10)}
.tablewrap{overflow:auto;max-height:560px;
  border:1px solid var(--rule);background:rgba(42,15,23,.62);
  box-shadow:0 0 0 1px rgba(124,94,34,.35) inset}
/* Without this the table shrinks to the wrapper instead of overflowing, so
   wide tables clip their right-hand columns with nothing to scroll to. */
.tablewrap table{min-width:max-content}
.tablewrap thead th{position:sticky;top:0;background:#3A1420;z-index:2}
/* Pin the label column so nation columns stay identifiable when scrolled. */
.tablewrap.pinned td:first-child,
.tablewrap.pinned th:first-child{position:sticky;left:0;background:#3A1420}
.tablewrap.pinned td:first-child{z-index:1}
.tablewrap.pinned thead th:first-child{z-index:3}
.tablewrap.pinned tbody tr:hover td:first-child{background:#5A2532}
/* Wars are read, not scrubbed: a war and a battle have to be legible without
   dragging sideways, so these tables give up `min-width:max-content` and let
   their cells wrap instead. Numbers still refuse to break mid-figure. */
.tablewrap.fit{overflow-x:hidden}
.tablewrap.fit table{min-width:0;width:100%}
.tablewrap.fit th,.tablewrap.fit td{white-space:normal;overflow-wrap:anywhere}
.tablewrap.fit td.num,.tablewrap.fit th.num{white-space:nowrap;text-align:right}
/* Each side of a battle is a column of its own: nation, then who led it, then
   what it was made of, one line each. Laid out across, the unit list alone was
   wider than the screen. Used in the expanded battle detail, not the row. */
.side{display:flex;flex-direction:column;gap:2px;align-items:flex-start;
  text-align:left}
.side .unit{color:var(--ink-dim);font-size:11px;line-height:1.35}
.side .who{color:var(--ink-dim);font-size:11px;font-style:italic}
/* Battle rows stay one line so many fit on screen; clicking one opens a detail
   row beneath it with the composition either side brought and lost. */
.battlerow{cursor:pointer}
.battlerow.on{background:rgba(231,196,100,.14)}
.battledetail td{padding:12px 14px 16px;background:rgba(42,15,23,.4);
  border-bottom:1px solid var(--rule)}
.battlesides{display:flex;flex-wrap:wrap;gap:10px 36px}
.battleside{min-width:190px}
.battleside .side{gap:4px}
.battleside .sidehead{display:flex;align-items:baseline;gap:6px;
  font-size:11px;text-transform:uppercase;letter-spacing:.1em;
  color:var(--ink-dim);margin-bottom:3px}
.sidetotal{margin-top:6px;font-size:11px;color:var(--ink-dim)}
.sidetotal b{color:var(--ink);font-weight:500}
/* table-layout:fixed pins every column to its declared share of the width
   from the colgroup, regardless of content -- a long battle name or a wide
   number wraps inside its own cell instead of stretching the table (and the
   page) wider than the screen. auto layout can't guarantee that; it only
   wraps once a cell has nowhere left to grow, which can still be past the
   viewport edge. */
.battletable{table-layout:fixed}
.battletable td,.battletable th{overflow-wrap:anywhere}
/* Defenders on the left, attackers on the right, each split into who was in
   it from the start and who joined later. Two columns side by side rather
   than one long flag list, so a reader can tell at a glance how a war grew
   past its original two sides. A rule down the middle gives the gutter
   between them a reason to be there instead of reading as leftover space. */
.belligerents{display:grid;grid-template-columns:1fr auto 1fr;gap:0 28px;
  padding:4px 0 14px;border-bottom:1px solid var(--rule)}
.beldivider{width:1px;background:var(--rule)}
@media(max-width:640px){
  .belligerents{grid-template-columns:1fr}
  .beldivider{display:none}
}
.belcolhead{font-family:'Playfair Display',Georgia,serif;font-size:12.5px;
  text-transform:uppercase;letter-spacing:.12em;color:var(--brass);
  margin-bottom:6px}
.belgroup{margin-bottom:10px}
.belgrouphead{font-size:11px;text-transform:uppercase;letter-spacing:.1em;
  color:var(--ink-dim);margin-bottom:3px}
/* Name flush left, join date flush right, joined by a dotted rule that takes
   up whatever's between them -- a ledger line, not a gap. */
.belrow{display:flex;align-items:baseline;gap:6px;font-size:12.5px;
  padding:3px 0}
.belleader{flex:1;min-width:10px;border-bottom:1px dotted rgba(231,196,100,.22);
  margin-bottom:3px}
.belrow .rk{font-size:11px;white-space:nowrap}
/* The belligerent list keeps its "A v B" reading order and wraps within the
   column rather than stretching it. */
.sides{white-space:normal;line-height:1.7}
/* The war-goal and land tables sit outside a .tablewrap, so they need the
   same release from max-content on their own. */
table.mini.fitmini{width:100%;min-width:0;table-layout:auto}
table.mini.fitmini th,table.mini.fitmini td{white-space:normal;
  overflow-wrap:anywhere}
.groupcell{color:var(--brass);background:#54212E !important;position:static !important}
/* A full-width colspan cell cannot stick, so pin the label inside it. */
.groupcell span{position:sticky;left:9px;display:inline-block}
.up{color:#9BD65E}.down{color:var(--minium)}
/* Centre labels sit over the donut hole; they must never eat hover events. */
#milpies text{pointer-events:none}
.note{color:var(--ink-dim);font-size:13px;margin:10px 2px 0}
.stackwrap{display:flex;flex-wrap:wrap;gap:7px;margin-top:11px}
.slegend{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:11.5px;
  color:var(--ink-dim);display:flex;align-items:center;gap:6px}
.slegend i{width:9px;height:9px;display:block}
footer{color:var(--ink-dim);font-size:12.5px;border-top:1px solid var(--rule);
  padding-top:14px;margin-top:8px}
</style>
</head>
<body>
<main class="sheet">

  <div class="titleblock">
    <div><div class="tb-label">Sheet</div><h1 class="tb-value">Campaign returns</h1></div>
    <div><div class="tb-label">Span</div><div class="tb-value mono">__SPAN__</div></div>
    <div><div class="tb-label">Saves</div><div class="tb-value mono">__SAVECOUNT__</div></div>
    <div><div class="tb-label">Nations</div><div class="tb-value mono">__NATIONCOUNT__</div></div>
  </div>

  <div class="tabs" role="tablist" aria-label="Views">
    <button class="tab" role="tab" id="tab-nations" aria-controls="panel-nations" aria-selected="true">Nations</button>
    <button class="tab" role="tab" id="tab-compare" aria-controls="panel-compare" aria-selected="false">Compare</button>
    <button class="tab" role="tab" id="tab-pops" aria-controls="panel-pops" aria-selected="false">Pops</button>
    <button class="tab" role="tab" id="tab-military" aria-controls="panel-military" aria-selected="false">Military</button>
    <button class="tab" role="tab" id="tab-fleets" aria-controls="panel-fleets" aria-selected="false">Fleets</button>
    <button class="tab" role="tab" id="tab-wars" aria-controls="panel-wars" aria-selected="false">Wars</button>
    <button class="tab" role="tab" id="tab-tech" aria-controls="panel-tech" aria-selected="false">Technology</button>
    <button class="tab" role="tab" id="tab-market" aria-controls="panel-market" aria-selected="false">Market</button>
  </div>

  <!-- ============ NATIONS ============ -->
  <div role="tabpanel" id="panel-nations" aria-labelledby="tab-nations">
    <section>
      <h2>Deployment at <span id="mapdate"></span></h2>
      <div class="controls">
        <label for="mapsave">Save</label>
        <select id="mapsave"></select>
        <button id="mapocc" aria-pressed="true" title="Shade land by who currently controls it rather than who owns it">Control</button>
        <button id="mapreset" title="Back to the whole world">Reset</button>
        <span class="rk" id="mapzoom">1.0&times;</span>
        <span id="pick-map"></span>
      </div>
      <figure>
        <div class="mapwrap"><canvas id="mapcanvas" role="img"
             aria-label="Political map with army positions"></canvas></div>
        <div class="readout" id="mapreadout"></div>
      </figure>
      <p class="note">Every army in the save is drawn at the province the game
        stacks it on, sized by brigade count and coloured by its nation. Hover a
        marker for the province, the nations stacked there and what they are made
        of. Narrow the nation list to strip the map back to the ones you care
        about &mdash; the land stays shaded, only the markers are filtered.
        Land is shaded by whoever controls it; press <strong>Control</strong> to
        switch to who owns it, which separates occupied ground from annexed.
        Scroll to zoom, drag to pan, double-click to zoom in, and click a marker
        to pin its readout while you look elsewhere.</p>
    </section>

    <section>
      <h2>Great powers at <span id="gpdate"></span></h2>
      <div class="gpgrid" id="gpgrid"></div>
      <p class="note">The ranking is the game's own: saves carry a
        <code>great_nations</code> list in rank order. <strong>Prestige</strong> is
        read straight from the save. Industrial and military score are
        <em>not</em> stored anywhere in a save, so the columns beside prestige are
        the real quantities behind them rather than the game's own two numbers.</p>
    </section>
  </div>

  <!-- ============ COMPARE ============ -->
  <div role="tabpanel" id="panel-compare" aria-labelledby="tab-compare" hidden>
    <section>
      <h2>Series</h2>
      <div class="controls">
        <label class="tb-label" for="metric" style="margin:0">Measure</label>
        <select id="metric"></select>
        <span id="pick-nations"></span>
        <button id="scale" aria-pressed="false" title="Switch between linear and logarithmic vertical scale">Linear</button>
      </div>
      <figure>
        <svg id="chart" viewBox="0 0 1000 460" role="img" aria-label="Metric plotted over time by nation"></svg>
        <div class="readout" id="readout"></div>
      </figure>
      <p class="note" id="succnote"></p>
    </section>

    <section>
      <h2>Standing at <span id="lastdate"></span></h2>
      <div class="tablewrap"><table id="ledger"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Click a column heading to sort. Only the nations selected above are listed.</p>
    </section>
  </div>

  <!-- ============ MILITARY ============ -->
  <div role="tabpanel" id="panel-military" aria-labelledby="tab-military" hidden>
    <section>
      <h2>Head to head at <span id="mildate"></span></h2>
      <div class="controls">
        <label class="tb-label" for="milsave" style="margin:0">Save</label>
        <select id="milsave"></select>
        <button id="milmode" aria-pressed="false" title="Switch the pies between land regiments and naval hulls">Army</button>
        <button id="milmob" aria-pressed="true" title="Show each side's full potential -- standing brigades plus everything its mobilization ceiling could still add -- instead of just its brigades right now. Army only.">Potential</button>
      </div>
      <div class="controls">
        <label class="tb-label" style="margin:0">Left</label>
        <span id="pick-milA"></span>
        <label class="tb-label" style="margin:0">Right</label>
        <span id="pick-milB"></span>
        <button id="milswap" title="Swap the two sides">Swap</button>
        <button id="milview" aria-pressed="false" title="Totals compares the two sides as one pie; composition breaks each side down by unit type">Totals</button>
      </div>
      <figure>
        <svg id="milpies" viewBox="0 0 1000 400" role="img" aria-label="Force composition compared between two nations"></svg>
        <div class="readout" id="milreadout"></div>
      </figure>
      <div class="stackwrap" id="millegend"></div>
      <p class="note">Hover a slice on either pie and both nations' counts for that type are shown together.</p>
    </section>

    <section>
      <h2>Overview</h2>
      <div class="controls">
        <span id="pick-military"></span>
      </div>
      <div class="tablewrap pinned"><table id="miltable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Click a heading to sort. Scroll sideways for the remaining unit-type columns.
        <strong>Brigades</strong> counts every raised regiment, professionals plus any currently
        mobilized. <strong>Professionals</strong> are the ones raised from soldier pops, which
        stand whether or not the nation is mobilized. <strong>Mob ceiling</strong> is every brigade
        the mobilizable population could raise at the nation's mobilisation size &mdash; the whole
        pool, including any brigades already mobilized out of it. <strong>Total military
        potential</strong> is professionals plus that ceiling: the largest army the nation could
        field. With <code>--mod-path</code> the mobilisation size is read from the mod; without it,
        it comes from <code>--mobilisation-size</code>.</p>
    </section>

    <section>
      <h2>Military technology</h2>
      <div class="tablewrap pinned"><table id="techtable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note" id="technote">Rows follow research order within each line, so progress reads top to
        bottom. Columns are ordered by military tech, so scroll sideways for the nations with least.</p>
    </section>
  </div>



  <!-- ============ TECHNOLOGY ============ -->
  <div role="tabpanel" id="panel-tech" aria-labelledby="tab-tech" hidden>
    <section>
      <h2>Technology &middot; <span id="techwho"></span></h2>
      <div class="controls">
        <label class="tb-label" for="techtag" style="margin:0">Nation</label>
        <select id="techtag"></select>
        <label class="tb-label" for="techsave" style="margin:0">Save</label>
        <select id="techsave"></select>
        <input type="search" id="techfind" class="selsearch" style="width:230px"
               placeholder="search modifiers or inventions" aria-label="search modifiers or inventions">
      </div>
      <div class="controls" id="techcats"></div>
      <div class="techgrid" id="techgrid"></div>
      <div class="readout" id="techdetail"></div>
      <p class="note">Every technology in the mod, laid out as the game lays it
        out: one column per research area, in order. Filled boxes are researched
        at the chosen save. Click one for its effects and the inventions it
        makes available. Search matches a technology's own effects and the
        name and effects of anything it unlocks -- a match in another
        category shows as a count on that category's button rather than
        switching you to it, since the same search term can turn up in more
        than one.</p>
    </section>
  </div>


  <!-- ============ WARS ============ -->
  <div role="tabpanel" id="panel-wars" aria-labelledby="tab-wars" hidden>
    <section>
      <h2>Wars &middot; <span id="warcount"></span></h2>
      <div class="controls">
        <input type="search" id="warfind" class="selsearch" style="width:230px"
               placeholder="search wars or nations" aria-label="search wars or nations">
      </div>
      <div class="tablewrap fit"><table id="wartable"></table></div>
      <p class="note">Click a heading to sort, a row for the detail. Casualties
        are the sum of both sides' losses across every recorded battle.</p>
    </section>
    <section>
      <div id="wardetail"></div>
    </section>
  </div>

  <!-- ============ FLEETS ============ -->
  <div role="tabpanel" id="panel-fleets" aria-labelledby="tab-fleets" hidden>
    <section>
      <h2>Compare navies</h2>
      <div class="controls">
        <label class="tb-label" for="shiptype" style="margin:0">Hull</label>
        <select id="shiptype"></select>
        <span id="pick-fleet"></span>
        <button id="fscale" aria-pressed="false">Linear</button>
      </div>
      <figure>
        <svg id="fleetchart" viewBox="0 0 1000 460" role="img" aria-label="Ship counts over time by nation"></svg>
        <div class="readout" id="fleetreadout"></div>
      </figure>
    </section>

    <section>
      <h2>Fleets at <span id="fleetdate"></span></h2>
      <div class="controls">
        <label class="tb-label" for="fleetsave" style="margin:0">Save</label>
        <select id="fleetsave"></select>
      </div>
      <div class="tablewrap"><table id="fleettable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Every hull type present in the save gets a column. Click a heading to sort.</p>
    </section>

    <section>
      <h2>Fleet composition</h2>
      <div class="controls">
        <label class="tb-label" for="navtag" style="margin:0">Nation</label>
        <select id="navtag"></select>
      </div>
      <figure>
        <svg id="navy" viewBox="0 0 1000 360" role="img" aria-label="Ship counts by type over time"></svg>
      </figure>
      <div class="stackwrap" id="navlegend"></div>
      <p class="note">Hull types are read straight from the save, so mod-added ships appear under their own names.</p>
    </section>
  </div>

  <!-- ============ POPS ============ -->
  <div role="tabpanel" id="panel-pops" aria-labelledby="tab-pops" hidden>
    <section>
      <h2>Pops at <span id="popdate"></span></h2>
      <div class="controls">
        <label class="tb-label" for="popsave" style="margin:0">Save</label>
        <select id="popsave"></select>
        <button id="popshare" aria-pressed="false" title="Show each pop type as a share of the nation's population">Counts</button>
      </div>
      <div class="tablewrap"><table id="poptable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Click a heading to sort, or a row to see that nation's cultures below.</p>
    </section>

    <section>
      <h2>Cultures &middot; <span id="cultag"></span></h2>
      <div class="controls">
        <label class="tb-label" for="cultagsel" style="margin:0">Nation</label>
        <select id="cultagsel"></select>
      </div>
      <div class="tablewrap"><table id="cultable"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Accepted cultures are the primary culture plus anything in the nation's accepted list at that save.</p>
    </section>

    <section>
      <h2>Population composition</h2>
      <div class="controls">
        <label class="tb-label" for="poptag" style="margin:0">Nation</label>
        <select id="poptag"></select>
      </div>
      <figure>
        <svg id="popchart" viewBox="0 0 1000 360" role="img" aria-label="Pop sizes by type over time"></svg>
      </figure>
      <div class="stackwrap" id="poplegend"></div>
    </section>
  </div>

  <!-- ============ MARKET ============ -->
  <div role="tabpanel" id="panel-market" aria-labelledby="tab-market" hidden>
    <section>
      <h2>World prices &middot; <span>__PRICESPAN__</span></h2>
      <div class="controls">
        <span id="pick-goods"></span>
        <button id="topmovers">Top movers</button>
        <button id="pscale" aria-pressed="false">Linear</button>
        <button id="pindex" aria-pressed="false" title="Rebase every good to 100 at its first reading so goods at different price levels can be compared">Absolute</button>
      </div>
      <figure>
        <svg id="pricechart" viewBox="0 0 1000 460" role="img" aria-label="Goods prices over time"></svg>
        <div class="readout" id="pricereadout"></div>
      </figure>
      <p class="note" id="pricenote"></p>
    </section>

    <section>
      <h2>Market at <span id="snapdate"></span></h2>
      <div class="controls">
        <label class="tb-label" for="snapsel" style="margin:0">Save</label>
        <select id="snapsel"></select>
      </div>
      <div class="tablewrap"><table id="market"><thead><tr></tr></thead><tbody></tbody></table></div>
      <p class="note">Supply, demand and quantity sold are stored only for the save's own date, so this
        is a snapshot rather than a series. Demand is the real figure: Victoria&nbsp;II inflates the
        stored value by about two billion to hold a good at its price floor, and those goods are
        marked. Change is measured across the whole price span. Click a row to plot that good.</p>
    </section>
  </div>

  <footer>
    Generated from Victoria&nbsp;II save files. Population counts are the sum of
    pop sizes in owned provinces; literacy, consciousness and militancy are
    weighted by pop size. Prices come from the rolling monthly buffer each save
    carries, stitched together across saves.
  </footer>
</main>

<script>
const DATA = __DATA__;
const C = DATA.colours;
/**
 * A stable colour for the nth series in a set.
 *
 * `C` is a hand-picked palette sized for a vanilla campaign. Mods run past
 * it -- Ferrum Mare fields a 13th regiment type and a 13th pop type, and the
 * market runs to about 48 goods -- and plain `C[i % C.length]` then hands two
 * different series the *identical* colour: `tank` came out the same gold as
 * `artillery`, one indistinguishable wedge in the composition pie.
 *
 * The first `C.length` series keep their hand-picked colours exactly, so
 * every chart that fitted before is unchanged. Past that, hues are placed at
 * the golden angle -- which spreads any number of them about as evenly as a
 * circle allows -- at the palette's own saturation, so the overflow still
 * reads as part of the same set.
 *
 * Lightness steps every `C.length` on top of that, because the golden angle
 * only guarantees a wide gap between *consecutive* series: the pair that
 * ends up closest in hue is always about 21 or 34 apart, which is far enough
 * to land on a different step. The goods list, the worst case here, comes
 * out with no two colours nearer than a tone apart.
 */
const seriesColour = i => {
  if (i < 0) return C[0];
  if (i < C.length) return C[i];
  const over = i - C.length;
  const hue = ((over * 137.508) + 21) % 360;
  const light = [63, 52, 74][Math.floor(over / C.length) % 3];
  return `hsl(${hue.toFixed(1)} 38% ${light}%)`;
};
const SVGNS = 'http://www.w3.org/2000/svg';
const el = (n, a) => { const e = document.createElementNS(SVGNS, n);
  for (const k in a) e.setAttribute(k, a[k]); return e; };
// The right margin is wide because the end-of-line tags live in it: a tag
// laid over the plot has to fight the gridlines and the lines it names,
// and a stack of them has nowhere to go but on top of each other.
const W = 1000, H = 460, M = {t: 20, r: 58, b: 40, l: 80};

const nameOf = t => DATA.tagNames[t] || t;
/* A nation is drawn in its own colour out of the mod, so the report reads like
   the game. Half of them are unusable as ink on a burgundy page, though --
   Prussia is nearly black, Russia a deep green -- so each is lifted until it
   clears a contrast ratio against the ground, keeping its hue and saturation
   and moving only its lightness. A nation with no colour, or no mod to read one
   from, falls back to the report's own palette. */
const GROUND_RGB = [0x4A, 0x1C, 0x28];

function _chan(v) {
  const s = v / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}
function _luminance([r, g, b]) {
  return 0.2126 * _chan(r) + 0.7152 * _chan(g) + 0.0722 * _chan(b);
}
function _contrast(rgb) {
  const a = _luminance(rgb), b = _luminance(GROUND_RGB);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}
function _toHsl([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const hi = Math.max(r, g, b), lo = Math.min(r, g, b), d = hi - lo;
  let h = 0;
  if (d) {
    if (hi === r) h = ((g - b) / d) % 6;
    else if (hi === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
    if (h < 0) h += 360;
  }
  const l = (hi + lo) / 2;
  const s = d ? d / (1 - Math.abs(2 * l - 1)) : 0;
  return [h, s, l];
}
function _fromHsl([h, s, l]) {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return [r, g, b].map(v => Math.round((v + m) * 255));
}

const READABLE = 3.4;          // enough for a bold tag and a 2px chart line
function _readable(hex) {
  const m = /^#?([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(hex || '');
  if (!m) return null;
  let rgb = [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)];
  if (_contrast(rgb) >= READABLE) return '#' + m[1] + m[2] + m[3];
  const [h, s] = _toHsl(rgb);
  // Saturation gets a floor so near-greys do not lift into flat white, and a
  // ceiling so a fully saturated dark -- Prussia's navy, Russia's bottle green
  // -- comes up as ink rather than as neon. Lightness climbs from low, and the
  // first value that clears the threshold wins, so nothing is lifted further
  // than it has to be.
  const sat = Math.min(Math.max(s, 0.22), 0.58);
  for (let l = 0.38; l <= 0.9; l += 0.03) {
    const lifted = _fromHsl([h, sat, l]);
    if (_contrast(lifted) >= READABLE) {
      return '#' + lifted.map(v => v.toString(16).padStart(2, '0')).join('');
    }
  }
  return null;
}

const NATION_INK = {};
(() => {
  const own = (DATA.map && DATA.map.colours) || {};
  DATA.tags.forEach(t => {
    const ink = _readable(own[t]);
    NATION_INK[t] = ink || seriesColour(DATA.tags.indexOf(t));
  });
})();

const colourFor = t => NATION_INK[t] || seriesColour(DATA.tags.indexOf(t));
const goodColour = g => seriesColour(DATA.goods.indexOf(g));

const fmtCount = v => {
  const a = Math.abs(v);
  if (a >= 1e9) return (v/1e9).toFixed(2)+'bn';
  if (a >= 1e6) return (v/1e6).toFixed(2)+'m';
  if (a >= 1e4) return Math.round(v/1e3)+'k';
  if (a >= 1e3) return v.toLocaleString();
  return (Math.round(v*100)/100).toString();
};
const formatters = {
  count: fmtCount,
  percent: v => v.toFixed(1)+'%',
  fraction: v => (v*100).toFixed(1)+'%',
  decimal: v => v.toFixed(2),
};

function niceTicks(lo, hi, count) {
  if (hi <= lo) return [lo];
  const raw = (hi - lo) / count;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].find(s => s * mag >= raw) * mag;
  const out = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(v);
  return out;
}
function logTicks(lo, hi) {
  const out = [];
  for (let e = Math.floor(lo); e <= Math.ceil(hi); e++)
    for (const m of [1, 3]) {
      const v = e + Math.log10(m);
      if (v >= lo - 1e-9 && v <= hi + 1e-9) out.push(v);
    }
  return out.length >= 3 ? out : niceTicks(lo, hi, 5);
}
/* Stack one column of labels, moving each as little as it can be moved.

   The obvious way -- walk down the list and push anything too close to its
   neighbour further down -- drags a whole run downhill from whichever label
   happened to come first, so labels with room to spare still end up moved and
   the run as a whole finishes low. Here labels that already clear each other
   are left exactly where their line ended, and only a run that genuinely
   collides is evened out, centred on where its own members wanted to be. */
function packColumn(items, gap, top, bottom) {
  items.sort((a, b) => a.want - b.want);
  // A run's `sum / n` is the first position it would like: every member
  // contributes the start it implies, which is its own wanted position less
  // the gaps that would sit above it inside the run.
  const runs = [];
  for (const item of items) {
    let run = {n: 1, sum: item.want, items: [item]};
    while (runs.length) {
      const prev = runs[runs.length - 1];
      if (prev.sum / prev.n + prev.n * gap <= run.sum / run.n) break;
      runs.pop();
      run = {n: prev.n + run.n,
             sum: prev.sum + run.sum - prev.n * run.n * gap,
             items: prev.items.concat(run.items)};
    }
    runs.push(run);
  }
  const out = [];
  for (const run of runs) {
    const start = Math.max(top, Math.min(run.sum / run.n,
                                         bottom - (run.n - 1) * gap));
    run.items.forEach((it, i) => { it.y = start + i * gap; out.push(it); });
  }
  if (!out.length) return out;
  // Holding a run inside the band can push it into the run below, so the stack
  // is settled downhill, slid back up by however far that overran the bottom,
  // then settled uphill and slid back down the same way. Settling one way only
  // walks the last labels out of the chart and onto the axis.
  for (let i = 1; i < out.length; i++)
    if (out[i].y - out[i-1].y < gap) out[i].y = out[i-1].y + gap;
  const over = out[out.length - 1].y - bottom;
  if (over > 0) out.forEach(it => { it.y -= over; });
  for (let i = out.length - 2; i >= 0; i--)
    if (out[i+1].y - out[i].y < gap) out[i].y = out[i+1].y - gap;
  const under = top - out[0].y;
  if (under > 0) out.forEach(it => { it.y += under; });
  // Sliding only works while the stack fits. If it does not -- more labels than
  // even the extra columns could absorb -- spread what is there evenly and take
  // the tighter spacing: crowded inside the frame beats legible outside it.
  if (out.length > 1 && out[out.length - 1].y - out[0].y > bottom - top) {
    const even = (bottom - top) / (out.length - 1);
    out.forEach((it, i) => { it.y = top + i * even; });
  }
  return out;
}

/* Place every end-of-line label: in, its wanted y, which is where its own line
   ended; out, the y to draw it at, plus the anchor and column to draw it from. */
function placeLabels(labels, gap, top, bottom) {
  const fits = Math.max(1, Math.floor((bottom - top) / gap) + 1);
  labels.forEach(l => { l.col = 0; l.lo = l.bx0; l.hi = l.bx1; });
  // A label only contends with the ones it would actually collide with. Nearly
  // all of them sit at the last save, but a nation that stopped existing partway
  // leaves its tag out in the middle of the chart, where it is nowhere near the
  // right-hand stack and has no business being shoved about by it. So they are
  // grouped by whether the space they take overlaps at all, merging as it goes:
  // two tags that each clear a third but not each other still have to end up in
  // one group, which a fixed distance test gets wrong.
  //
  // Grouping and column count feed each other, though -- a group that needs a
  // second column takes more width, which can reach the group beside it, which
  // then belongs in the same group -- so the two are settled together, grouping
  // and sizing in turn until nothing more moves. The space a group claims only
  // ever grows, so groups only ever combine and this always comes to a stop.
  let columns = [];
  for (let pass = 0; pass < 8; pass++) {
    const next = [];
    let open = null;
    labels.slice().sort((a, b) => a.lo - b.lo).forEach(l => {
      if (open && l.lo < open.edge) {
        open.list.push(l);
        open.wide = Math.max(open.wide, l.wide);
        open.edge = Math.max(open.edge, l.hi);
      } else {
        open = {list: [l], wide: l.wide, edge: l.hi};
        next.push(open);
      }
    });
    let settled = next.length === columns.length;
    next.forEach(col => {
      // More labels than the height holds at a legible gap. Squeezing them in
      // regardless only trades one unreadable pile for another, so the stack
      // steps sideways into a second column, a third, as many as it takes. The
      // one limit is width -- labels may eat into the plot, but not swallow
      // it -- and past that the packer falls back to crowding.
      const room = Math.max(1, Math.floor((W - M.l) * 0.5 / col.wide));
      col.k = Math.min(room, Math.max(1, Math.ceil(col.list.length / fits)));
      // Every tag in a group hangs off one shared anchor rather than off its
      // own line's end. Stepping each label sideways from wherever its own line
      // stopped would put one group's second column straight through the next
      // group's first, which is the collision the grouping just went to the
      // trouble of ruling out.
      col.end = col.list.some(l => l.atEnd);
      const left = Math.min(...col.list.map(l => l.bx0));
      col.anchor = col.end ? W - 4 : Math.max(...col.list.map(l => l.bx0));
      const span = col.k * col.wide;
      // The claim runs from the leftmost line end to the far side of the last
      // column: leaders cross that ground too, and it is what the next group
      // has to clear.
      const lo = col.end ? Math.min(left, col.anchor - span) : left;
      const hi = col.end ? col.anchor : col.anchor + span;
      col.list.forEach(l => {
        if (lo !== l.lo || hi !== l.hi) settled = false;
        l.lo = lo;
        l.hi = hi;
        l.anchor = col.anchor;
        l.end = col.end;
      });
    });
    columns = next;
    if (settled) break;
  }
  columns.forEach(col => {
    col.list.forEach(l => { l.step = col.wide; });
    col.list.sort((a, b) => a.want - b.want);
    // Every k-th label goes to the same column, which leaves each column's
    // labels about k times further apart than they started; handing each column
    // a contiguous block would put the whole crowded run back into one column
    // and fix nothing.
    for (let c = 0; c < col.k; c++) {
      const part = col.list.filter((_, i) => i % col.k === c);
      part.forEach(l => { l.col = c; });
      packColumn(part, gap, top, bottom);
    }
  });
  return labels;
}

/* =============== searchable picker =============== */
function makePicker(mount, cfg) {
  // cfg: {items, labelFor, subLabelFor, colourFor, selected, presets, noun, onChange}
  const selected = new Set(cfg.selected || []);
  const wrap = document.createElement('span');
  wrap.className = 'picker';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'picker-toggle';
  toggle.setAttribute('aria-expanded', 'false');
  const panel = document.createElement('div');
  panel.className = 'picker-panel';
  panel.hidden = true;

  const search = document.createElement('input');
  search.type = 'search';
  search.className = 'picker-search';
  search.placeholder = 'Search ' + cfg.noun + '…';
  search.setAttribute('aria-label', 'Search ' + cfg.noun);

  const presets = document.createElement('div');
  presets.className = 'picker-presets';
  const list = document.createElement('div');
  list.className = 'picker-list';

  panel.append(search, presets, list);
  wrap.append(toggle, panel);
  mount.replaceWith(wrap);

  // A picker tied to a save only offers what that save has. `available`
  // returns the current list; everything else is built once and hidden, so
  // switching saves costs nothing and a nation that comes back is still there.
  let allowed = null;
  const permitted = item => allowed === null || allowed.has(item);

  const optFor = {};
  cfg.items.forEach(item => {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'picker-opt';
    const sub = cfg.subLabelFor ? cfg.subLabelFor(item) : '';
    b.innerHTML = `<span class="swatch" style="background:${cfg.colourFor(item)}"></span>`
      + `<span class="tag">${cfg.labelFor(item)}</span>`
      + (sub ? `<span class="nm">${sub}</span>` : '');
    b.onclick = () => {
      selected.has(item) ? selected.delete(item) : selected.add(item);
      sync(); cfg.onChange(ordered());
    };
    optFor[item] = b;
    list.appendChild(b);
  });
  const empty = document.createElement('div');
  empty.className = 'picker-empty';
  empty.textContent = 'Nothing matches.';
  empty.hidden = true;
  list.appendChild(empty);

  (cfg.presets || []).forEach(([label, fn]) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = label;
    b.onclick = () => {
      selected.clear(); fn().filter(permitted).forEach(i => selected.add(i));
      sync(); cfg.onChange(ordered());
    };
    presets.appendChild(b);
  });

  // Always report in the item list's own order so table columns stay put.
  const ordered = () => cfg.items.filter(i => selected.has(i) && permitted(i));

  // One place decides whether an option shows: the search box and the save
  // filter both feed it, so neither can undo the other.
  function applyFilter() {
    const q = search.value.trim().toLowerCase();
    let visible = 0;
    cfg.items.forEach(i => {
      const hay = (cfg.labelFor(i) + ' ' + (cfg.subLabelFor ? cfg.subLabelFor(i) : '')).toLowerCase();
      const on = permitted(i) && (!q || hay.includes(q));
      optFor[i].style.display = on ? '' : 'none';
      if (on) visible++;
    });
    empty.hidden = visible > 0;
  }

  function sync() {
    cfg.items.forEach(i => optFor[i].setAttribute('aria-pressed', selected.has(i)));
    applyFilter();
    const n = ordered().length;
    const word = n === 1 ? cfg.noun.replace(/s$/, '') : cfg.noun;
    toggle.innerHTML = `<span>${n} ${word} selected</span><span class="caret">▾</span>`;
  }
  search.oninput = applyFilter;
  toggle.onclick = () => {
    const open = panel.hidden;
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', open);
    if (open) search.focus();
  };
  document.addEventListener('click', ev => {
    if (!wrap.contains(ev.target)) { panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); }
  });
  panel.addEventListener('keydown', ev => {
    if (ev.key === 'Escape') { panel.hidden = true; toggle.setAttribute('aria-expanded','false'); toggle.focus(); }
  });

  if (cfg.available) allowed = new Set(cfg.available());
  sync();
  return {
    get: ordered,
    set: list => { selected.clear(); list.forEach(i => selected.add(i)); sync(); cfg.onChange(ordered()); },
    // Called when the save changes. Anything selected that the new save does
    // not have drops out of the report without being forgotten, so stepping
    // back to an earlier save brings it straight back.
    refresh: () => {
      if (!cfg.available) return;
      allowed = new Set(cfg.available());
      if (!ordered().length) {
        (cfg.fallback ? cfg.fallback() : []).forEach(i => selected.add(i));
      }
      sync();
      cfg.onChange(ordered());
    },
  };
}

/* =============== generic line plot =============== */
function plot(svg, cfg) {
  svg.textContent = '';
  const readout = cfg.readout;
  const idle = cfg.idle || 'Hover the plot to read values.';
  if (!cfg.series.length || !cfg.series.some(s => s.pts.length)) {
    const t = el('text', {x: W/2, y: H/2, 'text-anchor': 'middle', fill: '#C9AC80',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = cfg.emptyMsg || 'Nothing to plot.';
    svg.appendChild(t);
    if (readout) readout.textContent = '';
    return;
  }

  const log = cfg.log;
  let vals = [];
  cfg.series.forEach(s => s.pts.forEach(([, v]) => { if (!log || v > 0) vals.push(v); }));
  if (!vals.length) {
    const t = el('text', {x: W/2, y: H/2, 'text-anchor': 'middle', fill: '#C9AC80',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = 'No positive values to show on a log scale.';
    svg.appendChild(t);
    if (readout) readout.textContent = '';
    return;
  }

  let lo = Math.min(...vals), hi = Math.max(...vals);
  if (log) { lo = Math.log10(lo); hi = Math.log10(hi); }
  else { lo = Math.min(lo, cfg.zeroFloor === false ? lo : 0); }
  if (hi === lo) hi = lo + 1;
  hi += (hi - lo) * 0.06;
  const yOf = v => {
    const s = log ? Math.log10(Math.max(v, 1e-9)) : v;
    return M.t + (1 - (s - lo) / (hi - lo)) * (H - M.t - M.b);
  };
  const xOf = cfg.xOf;

  const axis = el('g', {class: 'axis'});
  (log ? logTicks(lo, hi) : niceTicks(lo, hi, 6)).forEach(tick => {
    const y = M.t + (1 - (tick - lo) / (hi - lo)) * (H - M.t - M.b);
    if (y < M.t - 1 || y > H - M.b + 1) return;
    axis.appendChild(el('line', {x1: M.l, x2: W - M.r, y1: y, y2: y, class: 'gridline'}));
    const label = el('text', {x: M.l - 9, y: y + 3.5, 'text-anchor': 'end'});
    label.textContent = cfg.fmt(log ? Math.pow(10, tick) : tick);
    axis.appendChild(label);
  });
  // One save can sit weeks from the next while the whole plot spans decades,
  // so a tick label per save (the old behaviour) ran them together into an
  // unreadable smear. Gridlines still mark every save -- useful reference
  // points on hover -- but a label only draws once it clears the minimum
  // pixel gap from the last one shown. The final tick always shows -- a
  // reader needs the plot's actual end date -- but forcing it on unmodified
  // could still land it right next to whatever the greedy pass had already
  // placed just before it, so any of those that are now too close to it get
  // dropped in a second pass instead of just the first tick being exempted.
  const xTickGap = cfg.xLabelGap || 44;
  const ticked = cfg.xTicks.map(t => ({...t, x: xOf(t.v)}));
  ticked.forEach(({x}) => axis.appendChild(
    el('line', {x1: x, x2: x, y1: M.t, y2: H - M.b, class: 'gridline'})));
  if (ticked.length) {
    const shown = [];
    for (let i = 0; i < ticked.length - 1; i++) {
      const t = ticked[i];
      if (!shown.length || t.x - shown[shown.length - 1].x >= xTickGap) shown.push(t);
    }
    const last = ticked[ticked.length - 1];
    while (shown.length && last.x - shown[shown.length - 1].x < xTickGap) shown.pop();
    shown.push(last);
    shown.forEach(({x, label: txt}) => {
      const label = el('text', {x, y: H - M.b + 17, 'text-anchor': 'middle'});
      label.textContent = txt;
      axis.appendChild(label);
    });
  }
  if (cfg.baseline != null) {
    const y = yOf(cfg.baseline);
    if (y > M.t && y < H - M.b)
      axis.appendChild(el('line', {x1: M.l, x2: W - M.r, y1: y, y2: y,
        stroke: 'var(--rule)', 'stroke-width': 1, 'stroke-dasharray': '3 3'}));
  }
  axis.appendChild(el('line', {x1: M.l, x2: M.l, y1: M.t, y2: H - M.b, class: 'axisline'}));
  axis.appendChild(el('line', {x1: M.l, x2: W - M.r, y1: H - M.b, y2: H - M.b, class: 'axisline'}));
  svg.appendChild(axis);

  // Sits before the series so a join is drawn under the lines it connects.
  const joins = el('g', {});
  svg.appendChild(joins);

  const endLabels = [];
  const span = {};
  cfg.series.forEach(s => {
    const pts = s.pts.filter(([, v]) => !log || v > 0);
    if (!pts.length) return;
    const xy = pts.map(([x, v]) => [xOf(x), yOf(v)]);
    if (xy.length > 1) {
      const path = el('path', {
        d: xy.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' '),
        stroke: s.colour, class: 'plotline' + (cfg.thin ? ' thin' : ''),
      });
      let len = 0;
      for (let i = 1; i < xy.length; i++)
        len += Math.hypot(xy[i][0] - xy[i-1][0], xy[i][1] - xy[i-1][1]);
      path.style.setProperty('--len', len.toFixed(0));
      svg.appendChild(path);
    }
    if (cfg.markers)
      xy.forEach(p => svg.appendChild(el('rect', {
        x: p[0] - 2.5, y: p[1] - 2.5, width: 5, height: 5,
        fill: 'var(--ground)', stroke: s.colour, 'stroke-width': 1.5})));
    const last = xy[xy.length - 1];
    span[s.name] = {first: xy[0], last, colour: s.colour};
    endLabels.push({name: s.name, colour: s.colour, x: last[0], y: last[1]});
  });

  // One nation became another: join where the old line stops to where the new
  // one starts. Only drawn when both are on the chart, since a join to nothing
  // would be a line to nowhere.
  (cfg.links || []).forEach(([from, to]) => {
    const a = span[from], b = span[to];
    if (!a || !b) return;
    joins.appendChild(el('line', {
      x1: a.last[0], y1: a.last[1], x2: b.first[0], y2: b.first[1],
      stroke: b.colour, 'stroke-width': 1.3, 'stroke-dasharray': '3 4',
      opacity: 0.8}));
  });
  /* The tags on the ends of the lines. Eight nations whose values run close
     together finish the chart within a few pixels of one another, and eight
     tags crammed into those few pixels are worth less than the room they cost.
     The gap is the type size plus real leading rather than the bare clearance
     it used to be, the stack is packed by least displacement so a tag only
     moves as far as it must, and a leader joins each tag back to the point it
     names, so buying the separation never costs the reader the one thing the
     tag was for. A flat leader says the tag sits at its line's own height; a
     sloped one says it had to be nudged to make room. */
  const fs = cfg.thin ? 10.5 : 11;
  const charW = fs * 0.6;              // IBM Plex Mono runs 0.6em to the glyph
  const gutter = W - M.r;
  endLabels.forEach(l => {
    l.want = l.y;
    l.atEnd = l.x > gutter - 24;
    // The box the tag would take if nothing were in its way, padded, which is
    // both what decides who it collides with and how far a second column steps.
    l.wide = l.name.length * charW + 10;
    l.bx0 = l.atEnd ? W - 4 - l.wide : l.x + 6;
    l.bx1 = l.bx0 + l.wide;
  });
  placeLabels(endLabels, fs + 3.5, M.t + 4, H - M.b - 2);
  endLabels.forEach(l => {
    const tx = l.end ? l.anchor - l.col * l.step : l.anchor + l.col * l.step;
    const width = l.name.length * charW;
    // A tag still sitting on its line's last point says so by being there and
    // needs no leader. One that had to move, in either direction, gets a line
    // back to the point it belongs to.
    const near = l.end ? tx - width : tx;
    if (Math.abs(l.y - l.want) > 1.2 || near - l.x > 9) {
      const from = l.x + 3, to = near - 4;
      const stub = (to - from) * 0.3;
      svg.appendChild(el('path', {class: 'leader', stroke: l.colour,
        d: `M${from.toFixed(1)} ${l.want.toFixed(1)}`
         + `L${(from + stub).toFixed(1)} ${l.want.toFixed(1)}`
         + `L${(to - stub).toFixed(1)} ${l.y.toFixed(1)}`
         + `L${to.toFixed(1)} ${l.y.toFixed(1)}`}));
    }
    const label = el('text', {x: tx, y: l.y + fs * 0.34, fill: l.colour,
      class: 'endlab', 'font-size': fs,
      'text-anchor': l.end ? 'end' : 'start'});
    label.textContent = l.name;
    svg.appendChild(label);
  });

  if (!readout || !cfg.hoverXs) return;
  const hover = el('line', {x1: 0, x2: 0, y1: M.t, y2: H - M.b,
    stroke: 'var(--brass)', 'stroke-width': 1, opacity: 0});
  svg.appendChild(hover);
  readout.textContent = idle;
  svg.onpointerleave = () => { hover.setAttribute('opacity', 0); readout.textContent = idle; };
  svg.onpointermove = ev => {
    const box = svg.getBoundingClientRect();
    const px = (ev.clientX - box.left) / box.width * W;
    let best = 0, bestD = Infinity;
    cfg.hoverXs.forEach((h, i) => {
      const d = Math.abs(xOf(h.v) - px);
      if (d < bestD) { bestD = d; best = i; }
    });
    const at = cfg.hoverXs[best];
    hover.setAttribute('x1', xOf(at.v));
    hover.setAttribute('x2', xOf(at.v));
    hover.setAttribute('opacity', .65);
    const parts = cfg.series.map(s => {
      const hit = s.pts.find(p => p[0] === at.v);
      return hit ? [s, hit[1]] : null;
    }).filter(Boolean).sort((a, b) => b[1] - a[1])
      .map(([s, v]) => `<span><span class="rk">${s.name}</span> <b style="color:${s.colour}">${cfg.fmt(v)}</b></span>`);
    readout.innerHTML = `<span class="rk">${at.label}</span>` + parts.join('');
  };
}

/* =============== generic sortable table =============== */
function renderTable(table, cols, rows, state, onRow) {
  const head = table.querySelector('thead tr');
  head.textContent = '';
  cols.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col.label; th.tabIndex = 0;
    if (col.title) th.title = col.title;
    if (col.key === state.key) th.setAttribute('aria-sort', state.dir < 0 ? 'descending' : 'ascending');
    const go = () => {
      if (state.key === col.key) state.dir *= -1; else { state.key = col.key; state.dir = -1; }
      renderTable(table, cols, rows, state, onRow);
    };
    th.onclick = go;
    th.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
    head.appendChild(th);
  });
  const body = table.querySelector('tbody');
  body.textContent = '';
  [...rows].sort((a, b) => {
    const x = a[state.key], y = b[state.key];
    if (x === undefined) return 1;
    if (y === undefined) return -1;
    return state.dir * (typeof x === 'string' ? x.localeCompare(y) : x - y);
  }).forEach(row => {
    const tr = document.createElement('tr');
    cols.forEach(col => {
      const td = document.createElement('td');
      const v = row[col.key];
      td.textContent = col.fmt ? col.fmt(v, row) : (v === undefined ? '—' : v);
      if (col.colour) td.style.color = col.colour(row);
      if (col.cls) td.className = col.cls(row);
      tr.appendChild(td);
    });
    if (onRow) { tr.style.cursor = 'pointer'; tr.onclick = () => onRow(row); }
    body.appendChild(tr);
  });
}

/* =============== shared bits =============== */
const years = DATA.years;
const xMin = Math.min(...years), xMax = Math.max(...years);
const xOfSave = y => M.l + (xMax === xMin ? 0 : (y - xMin) / (xMax - xMin)) * (W - M.l - M.r);
const saveTicks = DATA.dates.map((d, i) => ({v: years[i], label: d.split('.')[0]}));
const saveHovers = DATA.dates.map((d, i) => ({v: years[i], label: d}));

/* The eight great powers, in the game's own rank order, at whichever save is
   being looked at. This is the same list the Nations tab ranks, read from the
   save's `great_nations`, so a picker and the ranking never disagree. */
function greatPowersAt(date) {
  const list = (DATA.greatPowers || {})[date] || [];
  return list.map(([tag]) => tag);
}
function greatPowersNear(date) {
  const found = greatPowersAt(date);
  if (found.length) return found;
  // Not every save carries the list; fall back to the nearest one that does.
  const order = DATA.dates.slice().reverse();
  for (const d of order) {
    const some = greatPowersAt(d);
    if (some.length) return some.filter(t => tagsAt(date).includes(t));
  }
  return [];
}

const defaultTags = (greatPowersAt(DATA.dates[DATA.dates.length - 1]).length
  ? greatPowersAt(DATA.dates[DATA.dates.length - 1])
  : DATA.tags).slice(0, 8);
// For single-nation dropdowns, opening on the largest example is more useful
// than opening on whatever sorts first.
function largestBy(key) {
  const at = DATA.facts[DATA.dates[DATA.dates.length - 1]] || {};
  return [...DATA.tags].sort((a, b) =>
    ((at[b] || {})[key] || 0) - ((at[a] || {})[key] || 0))[0] || DATA.tags[0];
}

/* Nations that exist in a given save: holding land, and therefore a country
   rather than a tag the mod defines and the campaign never used. Anything read
   at one date -- a tech tree, a force comparison, the map -- offers only these.
   Anything plotted across every date keeps the full list, because a nation that
   ends in 1860 still has a line worth drawing. */
function tagsAt(date) {
  const at = DATA.facts[date] || {};
  return DATA.tags.filter(t => at[t] && at[t].provinces > 0);
}

function biggestAt(date, key, n) {
  const at = DATA.facts[date] || {};
  return tagsAt(date)
    .sort((a, b) => ((at[b] || {})[key] || 0) - ((at[a] || {})[key] || 0))
    .slice(0, n);
}

function tagPickerCfg(selected, onChange, dateOf) {
  return {
    items: DATA.tags,
    labelFor: t => t,
    subLabelFor: t => nameOf(t) === t ? '' : nameOf(t),
    colourFor,
    selected,
    noun: 'nations',
    available: dateOf ? () => tagsAt(dateOf()) : null,
    fallback: dateOf ? () => biggestAt(dateOf(), 'total_pop', 1) : null,
    presets: [
      ['Great powers', () => greatPowersNear(dateOf ? dateOf() : DATA.lastDate)],
      ['Top 8 by pop', () => dateOf ? biggestAt(dateOf(), 'total_pop', 8)
        : [...DATA.tags].sort((a, b) =>
            (DATA.series[b].total_pop[DATA.lastDate] || 0) -
            (DATA.series[a].total_pop[DATA.lastDate] || 0)).slice(0, 8)],
      ['All', () => dateOf ? tagsAt(dateOf()) : DATA.tags],
      ['None', () => []],
    ],
    onChange,
  };
}

/* The same idea for a plain <select>: options the save does not have are hidden
   rather than removed, so the search box beside them keeps working and the list
   does not have to be rebuilt every time the date moves. */
function limitSelect(select, allowed, fallback) {
  if (!select) return;
  const ok = new Set(allowed);
  let first = null;
  for (const o of select.options) {
    const on = ok.has(o.value);
    o.dataset.off = on ? '' : '1';
    o.hidden = !on;
    if (on && first === null) first = o.value;
  }
  if (ok.size && !ok.has(select.value)) select.value = fallback || first;
}
DATA.lastDate = DATA.dates[DATA.dates.length - 1];

/* =============== NATIONS =============== */
let natTags = defaultTags.slice();
let logScale = false;

const metricSel = document.getElementById('metric');
DATA.metrics.forEach(m => {
  const o = document.createElement('option');
  o.value = m.key; o.textContent = m.label; metricSel.appendChild(o);
});
const fmtFor = key => {
  const m = DATA.metrics.find(m => m.key === key);
  return formatters[m ? m.fmt : 'count'] || fmtCount;
};
metricSel.onchange = drawChart;

makePicker(document.getElementById('pick-nations'),
  tagPickerCfg(natTags, sel => { natTags = sel; drawChart(); drawLedger(); }));

const scaleBtn = document.getElementById('scale');
scaleBtn.onclick = () => {
  logScale = !logScale;
  scaleBtn.setAttribute('aria-pressed', logScale);
  scaleBtn.textContent = logScale ? 'Logarithmic' : 'Linear';
  drawChart();
};

/* [predecessor, successor] for every nation that turned into another one. */
const SUCCESSIONS = Object.entries(DATA.succession || {}).flatMap(
  ([to, info]) => (info.from || []).map(([from]) => [from, to]));

(() => {
  const note = document.getElementById('succnote');
  if (!note) return;
  const lines = Object.entries(DATA.succession || {}).map(([to, info]) =>
    `${(info.from || []).map(([f, , decided]) =>
        nameOf(f) + (decided ? '' : '*')).join(' and ')} became `
    + `<b>${nameOf(to)}</b> by ${info.date}`);
  const guessed = Object.values(DATA.succession || {})
    .some(i => (i.from || []).some(([, , d]) => !d));
  note.innerHTML = lines.length
    ? 'A dashed line joins a nation to the one it became. A save records none '
      + 'of this: a nation that formed another leaves a block holding only its '
      + 'diplomatic relations, and the decision that does the forming changes '
      + 'the tag without leaving a flag behind. So these come from the '
      + 'decisions the mod itself ships, which declare who may form what, '
      + 'matched against the '
      + 'province ledger, which says who did: the newcomer appears holding land '
      + 'the old nation held one save earlier, and the old nation holds none. A '
      + 'nation that merely releases a puppet keeps its own line. In this '
      + 'campaign: ' + lines.join('; ') + '.'
      + (guessed ? ' Starred nations are not named by any decision -- they are '
                 + 'released or event-formed, and are matched by their people '
                 + 'being people the new nation accepts.' : '')
    : 'No nation in this campaign turned into another one.';
})();

function drawChart() {
  const key = metricSel.value;
  const shown = DATA.tags.filter(t => natTags.includes(t));
  plot(document.getElementById('chart'), {
    series: shown.map(tag => ({
      name: tag, colour: colourFor(tag),
      pts: DATA.dates.map((d, i) => [years[i], DATA.series[tag][key][d]])
                     .filter(p => p[1] !== undefined),
    })),
    xOf: xOfSave, xTicks: saveTicks, hoverXs: saveHovers,
    fmt: fmtFor(key), log: logScale, markers: true,
    links: SUCCESSIONS,
    readout: document.getElementById('readout'),
    idle: 'Hover the plot to read values at a date.',
    emptyMsg: shown.length ? 'No data for this measure.' : 'Select a nation.',
  });
}

const LEDGER_COLS = [
  {key: 'tag', label: 'Tag', colour: r => colourFor(r.tag)},
  {key: 'name', label: 'Nation'},
  {key: 'primary_culture', label: 'Primary culture', fmt: v => v || '—'},
  {key: 'provinces', label: 'Prov', fmt: v => v.toLocaleString()},
  {key: 'total_pop', label: 'Population', fmt: v => v.toLocaleString()},
  {key: 'accepted_pct', label: 'Accepted', fmt: v => v.toFixed(1) + '%'},
  {key: 'avg_literacy', label: 'Literacy', fmt: v => (v * 100).toFixed(1) + '%'},
  {key: 'brigades', label: 'Brigades', fmt: v => v.toLocaleString()},
  {key: 'ships', label: 'Ships', fmt: v => v.toLocaleString()},
  {key: 'factory_levels', label: 'Fct lvl', fmt: v => v.toLocaleString()},
  {key: 'prestige', label: 'Prestige', fmt: v => Math.round(v).toLocaleString()},
];
const ledgerState = {key: 'total_pop', dir: -1};
function drawLedger() {
  const at = DATA.facts[DATA.lastDate] || {};
  const rows = natTags.filter(t => at[t]).map(t => ({tag: t, name: nameOf(t), ...at[t]}));
  renderTable(document.getElementById('ledger'), LEDGER_COLS, rows, ledgerState);
}

/* =============== MILITARY =============== */
let milTags = defaultTags.slice(0, 6);
let milMode = 'army';       // army | navy
let milView = 'totals';     // totals | composition
let milPotential = true;    // true = standing + mobilization ceiling, false = brigades right now
// Horizon blue against field grey: the two uniforms the period ended in, and
// far enough apart on a burgundy ground to read at a glance. Mobilization is
// the same blue and grey held back to a khaki, so an added ceiling reads as
// part of the same army rather than a third force.
const MOB_COLOUR = '#B79B6E';
const SIDE_COLOUR = ['#5E8CB8', '#9DA08D'];

const milSave = document.getElementById('milsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  milSave.appendChild(o);
});
milSave.value = DATA.lastDate;

const byBrigades = [...DATA.tags].sort((a, b) =>
  (((DATA.facts[DATA.lastDate] || {})[b] || {}).brigades || 0) -
  (((DATA.facts[DATA.lastDate] || {})[a] || {}).brigades || 0));
let sideA = [byBrigades[0]].filter(Boolean);
let sideB = [byBrigades[1]].filter(Boolean);

const pickerA = makePicker(document.getElementById('pick-milA'),
  tagPickerCfg(sideA, sel => { sideA = sel; drawMilPies(); }, () => milSave.value));
const pickerB = makePicker(document.getElementById('pick-milB'),
  tagPickerCfg(sideB, sel => { sideB = sel; drawMilPies(); }, () => milSave.value));

const milModeBtn = document.getElementById('milmode');
milModeBtn.onclick = () => {
  milMode = milMode === 'army' ? 'navy' : 'army';
  milModeBtn.setAttribute('aria-pressed', milMode === 'navy');
  milModeBtn.textContent = milMode === 'army' ? 'Army' : 'Navy';
  drawMilPies();
};
const milViewBtn = document.getElementById('milview');
milViewBtn.onclick = () => {
  milView = milView === 'totals' ? 'composition' : 'totals';
  milViewBtn.setAttribute('aria-pressed', milView === 'composition');
  milViewBtn.textContent = milView === 'totals' ? 'Totals' : 'Composition';
  drawMilPies();
};
const milMobBtn = document.getElementById('milmob');
milMobBtn.onclick = () => {
  milPotential = !milPotential;
  milMobBtn.setAttribute('aria-pressed', milPotential);
  milMobBtn.textContent = milPotential ? 'Potential' : 'Current';
  drawMilPies();
};
document.getElementById('milswap').onclick = () => {
  const a = sideA.slice();
  pickerA.set(sideB.slice());
  pickerB.set(a);
};
milSave.onchange = () => {
  pickerA.refresh(); pickerB.refresh(); milPicker.refresh();
  drawMilPies(); drawMilTable(); drawTechTable();
};

const milPicker = makePicker(document.getElementById('pick-military'),
  tagPickerCfg(milTags, sel => { milTags = sel; drawMilTable(); drawTechTable(); },
               () => milSave.value));

const milTypes = () => milMode === 'army' ? DATA.regimentTypes : DATA.shipTypes;
const milColour = t => seriesColour(milTypes().indexOf(t));
const milSource = tag => (milMode === 'army' ? DATA.brigades : DATA.ships)[tag] || {};

/** Sum a side's unit counts by type across every nation in the group. */
function groupCounts(tags, date) {
  const out = {};
  tags.forEach(tag => {
    const at = milSource(tag)[date] || {};
    for (const key in at) out[key] = (out[key] || 0) + at[key];
  });
  return out;
}
const groupTotal = (tags, date) => {
  const at = groupCounts(tags, date);
  let n = 0;
  for (const key in at) n += at[key];
  return n;
};
/**
 * Standing (non-mobilized) brigades for a side. Kept separate from
 * `groupTotal` -- which is every brigade a side currently has, mobilized or
 * not -- specifically so it can be added to the mobilization ceiling below
 * without double-counting: `mobilization_brigades` is the *total* a side
 * could ever raise through mobilizing, already inclusive of whatever it's
 * mobilized so far, so adding it to `groupTotal` (which also already
 * includes those same mobilized brigades) counted them twice.
 */
function groupStanding(tags, date) {
  if (milMode !== 'army') return groupTotal(tags, date);
  const at = DATA.facts[date] || {};
  return tags.reduce((sum, t) => sum + ((at[t] || {}).regular_brigades || 0), 0);
}
/** Mobilization ceiling for a side. Naval hulls cannot be mobilized. */
function groupMob(tags, date) {
  if (milMode !== 'army') return 0;
  const at = DATA.facts[date] || {};
  return tags.reduce((sum, t) => sum + ((at[t] || {}).mobilization_brigades || 0), 0);
}
/** How many of a side's current brigades came from mobilizing already,
    rather than standing recruitment -- regular_brigades + this always sums
    to groupTotal, since a brigade is one or the other, never both. */
function groupMobilized(tags, date) {
  if (milMode !== 'army') return 0;
  const at = DATA.facts[date] || {};
  return tags.reduce((sum, t) => sum + ((at[t] || {}).mobilized_brigades || 0), 0);
}
/**
 * A side's headline total: its brigades right now, or -- with "Potential"
 * selected -- its standing brigades plus everything its mobilization
 * ceiling could still add. See `groupStanding` for why that's the ceiling
 * added to *standing*, not to the current brigade count.
 */
function sideTotal(tags, date) {
  return milPotential
    ? groupStanding(tags, date) + groupMob(tags, date)
    : groupTotal(tags, date);
}
const sideLabel = tags => !tags.length ? 'nobody'
  : tags.length <= 3 ? tags.join(' + ')
  : `${tags.slice(0, 2).join(' + ')} +${tags.length - 2} more`;

function arcPath(cx, cy, r0, r1, a0, a1) {
  const at = (r, a) => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  const large = (a1 - a0) > Math.PI ? 1 : 0;
  const [x0, y0] = at(r1, a0), [x1, y1] = at(r1, a1);
  const [x2, y2] = at(r0, a1), [x3, y3] = at(r0, a0);
  return `M${x0} ${y0}A${r1} ${r1} 0 ${large} 1 ${x1} ${y1}`
       + `L${x2} ${y2}A${r0} ${r0} 0 ${large} 0 ${x3} ${y3}Z`;
}

/**
 * Draw a donut. A single slice covering the ring needs two arcs.
 *
 * With opts.split and exactly two slices the ring is drawn as a head-to-head:
 * both slices start at the top, the first sweeping anticlockwise so it fills the
 * left half and the second clockwise so it fills the right. That puts each
 * side's colour on the side of the chart its label is on, which the plain
 * clockwise-from-top order gets backwards.
 */
function donut(svg, cx, cy, r0, r1, slices, onHover, opts) {
  const total = slices.reduce((sum, s) => sum + s.value, 0);
  if (!total) {
    svg.appendChild(el('circle', {cx, cy, r: r1, fill: 'none',
      stroke: 'var(--grid)', 'stroke-width': 1}));
    return;
  }
  const top = -Math.PI / 2;
  const split = !!(opts && opts.split) && slices.length === 2;
  let angle = top;
  slices.forEach((slice, i) => {
    if (!slice.value) return;
    const sweep = slice.value / total * Math.PI * 2;
    const full = sweep >= Math.PI * 2 - 1e-6;
    const a0 = split ? (i === 0 ? top - sweep : top) : angle;
    const a1 = split ? (i === 0 ? top : top + sweep) : angle + sweep;
    const path = el('path', {
      d: full
        ? arcPath(cx, cy, r0, r1, a0, a0 + Math.PI)
          + arcPath(cx, cy, r0, r1, a0 + Math.PI, a0 + Math.PI * 2)
        : arcPath(cx, cy, r0, r1, a0, a1),
      fill: slice.colour, 'fill-opacity': .85,
      stroke: 'var(--ground)', 'stroke-width': 1,
    });
    const title = document.createElementNS(SVGNS, 'title');
    title.textContent = `${slice.label}: ${slice.value.toLocaleString()} `
      + `(${(slice.value / total * 100).toFixed(1)}%)`;
    path.appendChild(title);
    path.style.cursor = 'pointer';
    path.onpointerenter = () => { path.setAttribute('fill-opacity', 1); onHover(slice); };
    path.onpointerleave = () => path.setAttribute('fill-opacity', .85);
    svg.appendChild(path);
    angle += sweep;
  });
}

function centreText(svg, cx, cy, big, small) {
  const a = el('text', {x: cx, y: cy - 2, 'text-anchor': 'middle', fill: 'var(--ink)',
    'font-family': 'Barlow Condensed, sans-serif', 'font-size': 34, 'font-weight': 600});
  a.textContent = big;
  svg.appendChild(a);
  const b = el('text', {x: cx, y: cy + 20, 'text-anchor': 'middle', fill: 'var(--ink-dim)',
    'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
  b.textContent = small;
  svg.appendChild(b);
}

function drawMilPies() {
  const svg = document.getElementById('milpies');
  svg.textContent = '';
  const legend = document.getElementById('millegend');
  legend.textContent = '';
  const readout = document.getElementById('milreadout');
  const date = milSave.value;
  document.getElementById('mildate').textContent = date;
  const noun = milMode === 'army' ? 'brigades' : 'ships';

  const raised = [groupTotal(sideA, date), groupTotal(sideB, date)];
  const standing = [groupStanding(sideA, date), groupStanding(sideB, date)];
  const mobs = [groupMob(sideA, date), groupMob(sideB, date)];
  const mobilized = [groupMobilized(sideA, date), groupMobilized(sideB, date)];
  const totals = [sideTotal(sideA, date), sideTotal(sideB, date)];
  if (!sideA.length && !sideB.length) {
    const t = el('text', {x: 500, y: 200, 'text-anchor': 'middle', fill: '#C9AC80',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = 'Pick at least one nation for a side.';
    svg.appendChild(t);
    readout.textContent = '';
    return;
  }

  const ratioText = totals[1] ? (totals[0] / totals[1]).toFixed(2) + '×' : '—';
  const mobOf = tags => tags.reduce((sum, t) =>
    sum + (((DATA.facts[date] || {})[t] || {}).mobilized_brigades || 0), 0);
  const mobBits = milMode === 'army'
    ? [sideA, sideB].map(mobilizedSide).filter(Boolean).join('') : '';
  function mobilizedSide(tags) {
    const n = mobOf(tags);
    if (!n) return '';
    return `<span><span class="rk">${sideLabel(tags)} mobilized</span> <b>${n.toLocaleString()}</b></span>`;
  }
  const split = milMode === 'army' && (milPotential ? (mobs[0] || mobs[1]) : (mobilized[0] || mobilized[1]))
    ? `<span><span class="rk">standing</span> <b>${standing[0].toLocaleString()}</b>`
      + ` <span class="rk">v</span> <b>${standing[1].toLocaleString()}</b></span>`
      + `<span><span class="rk">${milPotential ? 'mob ceiling' : 'mobilized'}</span> `
      + `<b>${(milPotential ? mobs[0] : mobilized[0]).toLocaleString()}</b>`
      + ` <span class="rk">v</span> <b>${(milPotential ? mobs[1] : mobilized[1]).toLocaleString()}</b></span>`
    : '';
  const idle = `<span class="rk">left</span> <b style="color:${SIDE_COLOUR[0]}">`
    + `${totals[0].toLocaleString()}</b>`
    + `<span><span class="rk">right</span> <b style="color:${SIDE_COLOUR[1]}">`
    + `${totals[1].toLocaleString()}</b></span>`
    + `<span><span class="rk">ratio</span> <b>${ratioText}</b></span>` + split
    + mobBits
    + `<span class="rk">${totals[0] + totals[1] ? '' : 'no ' + noun + ' at this save'}</span>`;
  const setIdle = () => readout.innerHTML = idle;

  if (milView === 'totals') {
    // One pie, one slice per side: the broad "who has more" view.
    const slices = [
      {label: sideLabel(sideA), value: totals[0], colour: SIDE_COLOUR[0], tags: sideA, side: 0},
      {label: sideLabel(sideB), value: totals[1], colour: SIDE_COLOUR[1], tags: sideB, side: 1},
    ];
    donut(svg, 500, 196, 84, 138, slices, slice => {
      const share = (totals[0] + totals[1])
        ? (slice.value / (totals[0] + totals[1]) * 100).toFixed(1) : '0.0';
      const parts = slice.tags.map(tag => {
        const n = sideTotal([tag], date);
        return `<span><span class="rk">${tag}</span> <b style="color:${colourFor(tag)}">`
             + `${n.toLocaleString()}</b></span>`;
      });
      readout.innerHTML = `<span class="rk">${slice.label}</span>`
        + `<span><b style="color:${slice.colour}">${slice.value.toLocaleString()}</b> `
        + `<span class="rk">${noun} (${share}% of both)</span></span>`
        + (slice.tags.length > 1 ? parts.join('') : '');
    }, {split: true});
    // The donut hole is only ~2x its inner radius wide, so the centre label
    // has to stay short -- "both sides" fits; tacking the noun and a
    // mobilization note on (as this used to) ran past the ring itself. That
    // detail moves to sit under each side's own number instead, where there
    // is room for it and it reads as "how this side's total breaks down"
    // rather than a caption on the aggregate.
    centreText(svg, 500, 196, (totals[0] + totals[1]).toLocaleString(), 'both sides');

    [[sideA, 0, 232], [sideB, 1, 768]].forEach(([tags, side, x]) => {
      const head = el('text', {x, y: 34, 'text-anchor': 'middle', fill: SIDE_COLOUR[side],
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 13});
      head.textContent = sideLabel(tags);
      svg.appendChild(head);
      const val = el('text', {x, y: 82, 'text-anchor': 'middle', fill: 'var(--ink)',
        'font-family': 'Barlow Condensed, sans-serif', 'font-size': 40, 'font-weight': 600});
      val.textContent = totals[side].toLocaleString();
      svg.appendChild(val);
      const sub = el('text', {x, y: 104, 'text-anchor': 'middle', fill: 'var(--ink-dim)',
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
      sub.textContent = noun;
      svg.appendChild(sub);
      // A second line under each side's number only when there is something
      // to split it into -- a side with no mobilization ceiling (navy, or a
      // nation that can't mobilize) has nothing worth breaking out.
      if (milMode === 'army' && (milPotential ? mobs[side] : mobilized[side])) {
        const breakdown = el('text', {x, y: 122, 'text-anchor': 'middle',
          fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
        breakdown.textContent = milPotential
          ? `${standing[side].toLocaleString()} standing `
            + `+ ${mobs[side].toLocaleString()} mob ceiling`
          : `${standing[side].toLocaleString()} standing `
            + `+ ${mobilized[side].toLocaleString()} mobilized`;
        svg.appendChild(breakdown);
      }
    });
    const ratio = el('text', {x: 500, y: 362, 'text-anchor': 'middle', fill: 'var(--brass)',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 16, 'font-weight': 600});
    ratio.textContent = ratioText;
    svg.appendChild(ratio);
    const ratioLabel = el('text', {x: 500, y: 380, 'text-anchor': 'middle',
      fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
    ratioLabel.textContent = 'ratio';
    svg.appendChild(ratioLabel);

    slices.forEach(slice => {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${slice.colour}"></i>${slice.label} `
        + `(${slice.value.toLocaleString()})`;
      legend.appendChild(item);
    });
  } else {
    // Two pies broken down by unit type, shared colour scale. The unit-type
    // counts already include every brigade a side has raised so far,
    // mobilized ones among them -- so the ceiling can only be added on top
    // as *remaining* headroom (ceiling minus what's mobilized already), and
    // only in Potential mode. Adding the full ceiling regardless of mode, as
    // this used to, double-counted a nation's already-mobilized brigades:
    // once inside its unit-type slices, again as part of "the ceiling".
    const counts = [groupCounts(sideA, date), groupCounts(sideB, date)];
    const remainingMob = milPotential
      ? [0, 1].map(i => Math.max(0, mobs[i] - mobilized[i])) : [0, 0];
    const present = milTypes().filter(t => counts.some(c => c[t]));
    const setType = type => {
      const parts = [0, 1].map(i => {
        const n = type === '__mob' ? remainingMob[i] : (counts[i][type] || 0);
        const pct = totals[i] ? (n / totals[i] * 100).toFixed(1) : '0.0';
        return `<span><span class="rk">${i ? 'right' : 'left'}</span> `
             + `<b style="color:${SIDE_COLOUR[i]}">${n.toLocaleString()}</b> `
             + `<span class="rk">(${pct}%)</span></span>`;
      });
      const [x, y] = type === '__mob' ? remainingMob
                   : [counts[0][type] || 0, counts[1][type] || 0];
      const r = y ? (x / y).toFixed(2) + '×' : (x ? '—' : '');
      const label = type === '__mob' ? 'still mobilizable' : type.replace(/_/g, ' ');
      readout.innerHTML = `<span class="rk">${label}</span>` + parts.join('')
        + (r ? `<span><span class="rk">ratio</span> <b>${r}</b></span>` : '');
    };

    [[sideA, 0, 268], [sideB, 1, 732]].forEach(([tags, side, cx]) => {
      const head = el('text', {x: cx, y: 34, 'text-anchor': 'middle', fill: SIDE_COLOUR[side],
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 13});
      head.textContent = sideLabel(tags);
      svg.appendChild(head);
      const slices = present.map(type => ({
        label: `${sideLabel(tags)} · ${type}`, value: counts[side][type] || 0,
        colour: milColour(type), type,
      }));
      if (remainingMob[side]) slices.push({
        label: `${sideLabel(tags)} · still mobilizable`, value: remainingMob[side],
        colour: MOB_COLOUR, type: '__mob',
      });
      donut(svg, cx, 196, 74, 122, slices, slice => setType(slice.type));
      centreText(svg, cx, 196, totals[side].toLocaleString(), noun);
    });

    const ratio = el('text', {x: 500, y: 190, 'text-anchor': 'middle', fill: 'var(--brass)',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 15});
    ratio.textContent = ratioText;
    svg.appendChild(ratio);
    const ratioLabel = el('text', {x: 500, y: 208, 'text-anchor': 'middle',
      fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
    ratioLabel.textContent = 'ratio';
    svg.appendChild(ratioLabel);

    present.forEach(type => {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${milColour(type)}"></i>${type.replace(/_/g, ' ')}`;
      item.style.cursor = 'pointer';
      item.onmouseenter = () => setType(type);
      legend.appendChild(item);
    });
    if (remainingMob[0] || remainingMob[1]) {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${MOB_COLOUR}"></i>still mobilizable`;
      item.style.cursor = 'pointer';
      item.onmouseenter = () => setType('__mob');
      legend.appendChild(item);
    }
  }

  svg.onpointerleave = setIdle;
  setIdle();
}

const milState = {key: 'brigades', dir: -1};
function drawMilTable() {
  const date = milSave.value;
  const facts = DATA.facts[date] || {};
  const usedReg = DATA.regimentTypes.filter(rt =>
    milTags.some(t => ((DATA.brigades[t] || {})[date] || {})[rt]));
  const cols = [
    {key: 'tag', label: 'Tag', colour: r => colourFor(r.tag)},
    {key: 'name', label: 'Nation'},
    {key: 'brigades', label: 'Brigades', fmt: v => v.toLocaleString()},
    {key: 'regular_brigades', label: 'Professionals', fmt: v => v.toLocaleString(),
     title: 'Brigades raised from soldier pops, which stand whether or not the '
          + 'nation is mobilized'},
    {key: 'mobilized_brigades', label: 'Mobilized', fmt: v => v.toLocaleString(),
     title: 'Brigades raised from non-soldier pops, which only exist while mobilized',
     cls: r => r.mobilized_brigades ? 'up' : ''},
    {key: 'mobilizing', label: 'Queued', fmt: v => v.toLocaleString(),
     title: 'Mobilization orders that have not spawned a brigade yet'},
    {key: 'mobilization_brigades', label: 'Mob ceiling', fmt: v => v.toLocaleString(),
     title: 'Brigades the mobilizable population could raise at the mobilisation '
          + 'size the report was built with. A ceiling, not the in-game number.'},
    {key: 'total_military_potential', label: 'Total military potential',
     fmt: v => v.toLocaleString(),
     title: 'Professionals plus the mobilization ceiling: the largest army this '
          + 'nation could field. Mobilized brigades are already inside the '
          + 'ceiling, so they are not added again.'},
    {key: 'mobilisation_size', label: 'Mob size', fmt: v => (v * 100).toFixed(2) + '%',
     title: "Share of the poor strata this nation can mobilize"},
    {key: 'mobilization_pool', label: 'Mobilizable pop', fmt: v => v.toLocaleString(),
     title: 'Accepted-culture farmers, labourers and craftsmen'},
    {key: 'ships', label: 'Ships', fmt: v => v.toLocaleString()},
    {key: 'army_techs', label: 'Army tech', fmt: v => v.toLocaleString()},
    {key: 'navy_techs', label: 'Navy tech', fmt: v => v.toLocaleString()},
    {key: 'soldiers', label: 'Soldier pops', fmt: v => v.toLocaleString()},
    {key: 'soldier_pct', label: 'Soldier %', fmt: v => v.toFixed(2) + '%',
     title: "Soldier pops as a share of the nation's population"},
    ...usedReg.map(rt => ({key: rt, label: rt.replace(/_/g, ' '),
                           fmt: v => (v || 0).toLocaleString()})),
  ];
  const rows = milTags.map(tag => {
    const f = facts[tag] || {};
    const at = (DATA.brigades[tag] || {})[date] || {};
    const soldiers = ((DATA.pops[tag] || {})[date] || {}).soldiers || 0;
    const row = {
      tag, name: nameOf(tag),
      brigades: f.brigades || 0,
      regular_brigades: f.regular_brigades || 0,
      mobilized_brigades: f.mobilized_brigades || 0,
      mobilizing: f.mobilizing || 0,
      mobilization_brigades: f.mobilization_brigades || 0,
      total_military_potential: (f.regular_brigades || 0) + (f.mobilization_brigades || 0),
      mobilisation_size: f.mobilisation_size || 0,
      mobilization_pool: f.mobilization_pool || 0,
      ships: f.ships || 0,
      army_techs: f.army_techs || 0,
      navy_techs: f.navy_techs || 0,
      soldiers,
      soldier_pct: f.total_pop ? soldiers / f.total_pop * 100 : 0,
    };
    usedReg.forEach(rt => row[rt] = at[rt] || 0);
    return row;
  }).filter(r => r.brigades || r.ships);
  renderTable(document.getElementById('miltable'), cols, rows, milState);
}

function drawTechTable() {
  const table = document.getElementById('techtable');
  const date = milSave.value;
  const facts = DATA.facts[date] || {};
  const milScore = t => ((facts[t] || {}).army_techs || 0) + ((facts[t] || {}).navy_techs || 0);
  // Order by military tech so the nations worth reading sit nearest the label
  // column; the rest are still there, just further right.
  const tags = milTags.slice().sort((a, b) => milScore(b) - milScore(a)).slice(0, 24);

  const head = table.querySelector('thead tr');
  head.textContent = '';
  ['Technology'].concat(tags).forEach((label, i) => {
    const th = document.createElement('th');
    th.textContent = label;
    if (i) th.style.color = colourFor(label);
    th.style.cursor = 'default';
    head.appendChild(th);
  });

  const has = {};
  tags.forEach(t => has[t] = new Set(((DATA.techsBy[t] || {})[date]) || []));

  const body = table.querySelector('tbody');
  body.textContent = '';
  const totals = document.createElement('tr');
  const totalsLabel = document.createElement('td');
  totalsLabel.textContent = 'Army + navy techs';
  totals.appendChild(totalsLabel);
  tags.forEach(t => {
    const td = document.createElement('td');
    const f = facts[t] || {};
    td.textContent = `${f.army_techs || 0} + ${f.navy_techs || 0}`;
    td.style.color = 'var(--brass)';
    totals.appendChild(td);
  });
  body.appendChild(totals);

  let lastLine = null;
  DATA.techOrder.forEach((tech, idx) => {
    const [branch, line] = DATA.techMeta[idx];
    if (branch === 'other') return;
    // Skip techs no nation in the save has -- mods leave gaps in the lines.
    if (!DATA.tags.some(t => (((DATA.techsBy[t] || {})[date]) || []).includes(idx))) return;
    if (line !== lastLine) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = 1 + tags.length;
      td.className = 'groupcell';
      const label = document.createElement('span');
      label.textContent = (branch === 'army' ? 'Army · ' : 'Navy · ') + line;
      td.appendChild(label);
      tr.appendChild(td);
      body.appendChild(tr);
      lastLine = line;
    }
    const tr = document.createElement('tr');
    const name = document.createElement('td');
    name.textContent = tech.replace(/_/g, ' ');
    tr.appendChild(name);
    tags.forEach(t => {
      const td = document.createElement('td');
      const got = has[t].has(idx);
      td.textContent = got ? 'yes' : '—';
      td.className = got ? 'up' : 'down';
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });

  const note = document.getElementById('technote');
  const extra = milTags.length > tags.length
    ? ` Showing the ${tags.length} with most military tech of ${milTags.length} selected.` : '';
  note.textContent = 'Rows follow research order within each line, so progress reads top to '
    + 'bottom. Columns are ordered by military tech, so scroll sideways for the nations with '
    + 'least.' + extra;
}

/* =============== FLEETS =============== */
let fleetTags = defaultTags.slice();
let fleetLog = false;

const shipSel = document.getElementById('shiptype');
[['__all', 'All ships'], ...DATA.shipTypes.map(s => [s, s])].forEach(([v, label]) => {
  const o = document.createElement('option'); o.value = v; o.textContent = label;
  shipSel.appendChild(o);
});
shipSel.onchange = drawFleetChart;

makePicker(document.getElementById('pick-fleet'),
  tagPickerCfg(fleetTags, sel => { fleetTags = sel; drawFleetChart(); }));

const fscale = document.getElementById('fscale');
fscale.onclick = () => {
  fleetLog = !fleetLog;
  fscale.setAttribute('aria-pressed', fleetLog);
  fscale.textContent = fleetLog ? 'Logarithmic' : 'Linear';
  drawFleetChart();
};

const shipCount = (tag, date, type) => {
  const at = (DATA.ships[tag] || {})[date];
  if (!at) return undefined;
  if (type === '__all') return Object.values(at).reduce((a, b) => a + b, 0);
  return at[type];
};

function drawFleetChart() {
  const type = shipSel.value;
  const shown = DATA.tags.filter(t => fleetTags.includes(t));
  plot(document.getElementById('fleetchart'), {
    series: shown.map(tag => ({
      name: tag, colour: colourFor(tag),
      pts: DATA.dates.map((d, i) => [years[i], shipCount(tag, d, type)])
                     .filter(p => p[1] !== undefined),
    })),
    xOf: xOfSave, xTicks: saveTicks, hoverXs: saveHovers,
    fmt: fmtCount, log: fleetLog, markers: true,
    readout: document.getElementById('fleetreadout'),
    idle: 'Hover the plot to read fleet sizes at a date.',
    emptyMsg: shown.length ? 'No ships of this type in these saves.' : 'Select a nation.',
  });
}

const fleetSave = document.getElementById('fleetsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  fleetSave.appendChild(o);
});
fleetSave.value = DATA.lastDate;
fleetSave.onchange = drawFleetTable;

const fleetState = {key: 'total', dir: -1};
function drawFleetTable() {
  const date = fleetSave.value;
  document.getElementById('fleetdate').textContent = date;
  const used = DATA.shipTypes.filter(st => DATA.tags.some(t => shipCount(t, date, st)));
  const cols = [
    {key: 'tag', label: 'Tag', colour: r => colourFor(r.tag)},
    {key: 'name', label: 'Nation'},
    {key: 'total', label: 'Total', fmt: v => v.toLocaleString()},
    ...used.map(st => ({key: st, label: st.replace(/_/g, ' '),
                        fmt: v => (v || 0).toLocaleString()})),
  ];
  const rows = DATA.tags.map(tag => {
    const row = {tag, name: nameOf(tag), total: shipCount(tag, date, '__all') || 0};
    used.forEach(st => row[st] = shipCount(tag, date, st) || 0);
    return row;
  }).filter(r => r.total > 0);
  renderTable(document.getElementById('fleettable'), cols, rows, fleetState,
              row => { shipSel.value = '__all'; drawFleetChart(); navSel.value = row.tag; drawNavy(); });
}

const navSel = document.getElementById('navtag');
DATA.tags.forEach(t => {
  const o = document.createElement('option'); o.value = t;
  o.textContent = nameOf(t) === t ? t : `${t} · ${nameOf(t)}`;
  navSel.appendChild(o);
});
navSel.value = largestBy('ships');
navSel.onchange = () => drawNavy();

function stackedBars(svgId, legendId, byDate, keys, emptyMsg) {
  const svg = document.getElementById(svgId);
  svg.textContent = '';
  const legend = document.getElementById(legendId);
  legend.textContent = '';
  const NW = 1000, NH = 360, NM = {t: 16, r: 20, b: 38, l: 70};
  const used = keys.filter(k => DATA.dates.some(d => (byDate[d] || {})[k]));
  const totals = DATA.dates.map(d =>
    used.reduce((s, k) => s + ((byDate[d] || {})[k] || 0), 0));
  const peak = Math.max(1, ...totals);

  if (!used.length) {
    const t = el('text', {x: NW/2, y: NH/2, 'text-anchor': 'middle', fill: '#C9AC80',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = emptyMsg;
    svg.appendChild(t);
    return;
  }

  const axis = el('g', {class: 'axis'});
  niceTicks(0, peak, 5).forEach(tick => {
    const y = NM.t + (1 - tick / peak) * (NH - NM.t - NM.b);
    axis.appendChild(el('line', {x1: NM.l, x2: NW - NM.r, y1: y, y2: y, class: 'gridline'}));
    const label = el('text', {x: NM.l - 9, y: y + 3.5, 'text-anchor': 'end'});
    label.textContent = fmtCount(tick);
    axis.appendChild(label);
  });
  axis.appendChild(el('line', {x1: NM.l, x2: NW - NM.r, y1: NH - NM.b, y2: NH - NM.b, class: 'axisline'}));
  svg.appendChild(axis);

  const slot = (NW - NM.l - NM.r) / DATA.dates.length;
  const barW = Math.min(56, slot * 0.62);
  DATA.dates.forEach((d, i) => {
    const x = NM.l + slot * (i + 0.5) - barW / 2;
    let y = NH - NM.b;
    used.forEach((k, si) => {
      const count = (byDate[d] || {})[k] || 0;
      if (!count) return;
      const h = count / peak * (NH - NM.t - NM.b);
      y -= h;
      const rect = el('rect', {x, y, width: barW, height: h,
        fill: seriesColour(si), 'fill-opacity': .82,
        stroke: 'var(--ground)', 'stroke-width': .5});
      const title = document.createElementNS(SVGNS, 'title');
      title.textContent = `${d} · ${k}: ${count.toLocaleString()}`;
      rect.appendChild(title);
      svg.appendChild(rect);
    });
    const mk = (txt, yy, size, fill) => {
      const t = el('text', {x: x + barW/2, y: yy, 'text-anchor': 'middle'});
      t.setAttribute('font-family', 'IBM Plex Mono, monospace');
      t.setAttribute('font-size', size); t.setAttribute('fill', fill);
      t.textContent = txt; svg.appendChild(t);
    };
    mk(d.split('.')[0], NH - NM.b + 17, 10, '#C9AC80');
    if (totals[i]) mk(fmtCount(totals[i]), y - 6, 10.5, '#F4E7CC');
  });

  used.forEach((k, si) => {
    const item = document.createElement('span');
    item.className = 'slegend';
    item.innerHTML = `<i style="background:${seriesColour(si)}"></i>${k.replace(/_/g, ' ')}`;
    legend.appendChild(item);
  });
}

const drawNavy = () => stackedBars('navy', 'navlegend',
  DATA.ships[navSel.value] || {}, DATA.shipTypes,
  nameOf(navSel.value) + ' has no ships in these saves.');

/* =============== POPS =============== */
const popSave = document.getElementById('popsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  popSave.appendChild(o);
});
popSave.value = DATA.lastDate;
popSave.onchange = () => { culLimit(); drawPopTable(); drawCultureTable(); };

let popShare = false;
const popShareBtn = document.getElementById('popshare');
popShareBtn.onclick = () => {
  popShare = !popShare;
  popShareBtn.setAttribute('aria-pressed', popShare);
  popShareBtn.textContent = popShare ? 'Shares' : 'Counts';
  drawPopTable();
};

const popState = {key: 'total', dir: -1};
function drawPopTable() {
  const date = popSave.value;
  document.getElementById('popdate').textContent = date;
  const facts = DATA.facts[date] || {};
  const used = DATA.popTypes.filter(pt =>
    DATA.tags.some(t => ((DATA.pops[t] || {})[date] || {})[pt]));
  const cell = (v, row) => {
    if (!v) return popShare ? '—' : '0';
    return popShare ? (v / row.total * 100).toFixed(1) + '%' : v.toLocaleString();
  };
  const cols = [
    {key: 'tag', label: 'Tag', colour: r => colourFor(r.tag)},
    {key: 'name', label: 'Nation'},
    {key: 'total', label: 'Total pop', fmt: v => v.toLocaleString()},
    {key: 'accepted_pct', label: 'Accepted', fmt: v => v.toFixed(1) + '%'},
    {key: 'avg_literacy', label: 'Literacy', fmt: v => (v * 100).toFixed(1) + '%'},
    {key: 'avg_militancy', label: 'Mil', fmt: v => v.toFixed(2)},
    {key: 'avg_consciousness', label: 'Con', fmt: v => v.toFixed(2)},
    ...used.map(pt => ({key: pt, label: pt, fmt: cell})),
  ];
  const rows = DATA.tags.map(tag => {
    const at = (DATA.pops[tag] || {})[date] || {};
    const f = facts[tag] || {};
    const row = {
      tag, name: nameOf(tag),
      total: f.total_pop || 0,
      accepted_pct: f.accepted_pct || 0,
      avg_literacy: f.avg_literacy || 0,
      avg_militancy: f.avg_militancy || 0,
      avg_consciousness: f.avg_consciousness || 0,
    };
    used.forEach(pt => row[pt] = at[pt] || 0);
    return row;
  }).filter(r => r.total > 0);
  renderTable(document.getElementById('poptable'), cols, rows, popState,
              row => { culSel.value = row.tag; drawCultureTable(); popTag.value = row.tag; drawPopChart(); });
}

const culSel = document.getElementById('cultagsel');
DATA.tags.forEach(t => {
  const o = document.createElement('option'); o.value = t;
  o.textContent = nameOf(t) === t ? t : `${t} · ${nameOf(t)}`;
  culSel.appendChild(o);
});
culSel.value = largestBy('total_pop');
const culLimit = () => limitSelect(culSel, tagsAt(popSave.value),
                                   biggestAt(popSave.value, 'total_pop', 1)[0]);
culLimit();
culSel.onchange = drawCultureTable;

const culState = {key: 'size', dir: -1};
function drawCultureTable() {
  const tag = culSel.value, date = popSave.value;
  document.getElementById('cultag').textContent =
    (nameOf(tag) === tag ? tag : `${tag} · ${nameOf(tag)}`) + ' at ' + date;
  const list = ((DATA.cultures[tag] || {})[date]) || [];
  const total = list.reduce((s, c) => s + c[1], 0);
  const rows = list.map(([culture, size, accepted]) => ({
    culture, size, accepted,
    share: total ? size / total * 100 : 0,
  }));
  const cols = [
    {key: 'culture', label: 'Culture'},
    {key: 'size', label: 'Pops', fmt: v => v.toLocaleString()},
    {key: 'share', label: 'Share', fmt: v => v.toFixed(1) + '%'},
    {key: 'accepted', label: 'Accepted', fmt: v => v ? 'yes' : '—',
     cls: r => r.accepted ? 'up' : 'down'},
  ];
  renderTable(document.getElementById('cultable'), cols, rows, culState);
}

const popTag = document.getElementById('poptag');
DATA.tags.forEach(t => {
  const o = document.createElement('option'); o.value = t;
  o.textContent = nameOf(t) === t ? t : `${t} · ${nameOf(t)}`;
  popTag.appendChild(o);
});
popTag.value = largestBy('total_pop');
popTag.onchange = () => drawPopChart();

const drawPopChart = () => stackedBars('popchart', 'poplegend',
  DATA.pops[popTag.value] || {}, DATA.popTypes,
  nameOf(popTag.value) + ' has no pops in these saves.');

/* =============== MARKET =============== */
const PD = DATA.priceDates, PY = DATA.priceYears;
let goodsOn = [];
let priceLog = false, priceIndex = false;

const pxMin = PY.length ? Math.min(...PY) : 0, pxMax = PY.length ? Math.max(...PY) : 1;
const pxOf = y => M.l + (pxMax === pxMin ? 0 : (y - pxMin) / (pxMax - pxMin)) * (W - M.l - M.r);

const topMovers = n => [...DATA.goods]
  .filter(g => DATA.movement[g] > 0)
  .sort((a, b) => DATA.movement[b] - DATA.movement[a])
  .slice(0, n);

const goodsPicker = makePicker(document.getElementById('pick-goods'), {
  items: DATA.goods,
  labelFor: g => g,
  subLabelFor: g => DATA.categoryLabels[DATA.goodCategory[g]] || DATA.goodCategory[g] || '',
  colourFor: goodColour,
  selected: [],
  noun: 'goods',
  presets: [
    ['Military', () => DATA.goods.filter(g => DATA.goodCategory[g] === 'military')],
    ['Industrial', () => DATA.goods.filter(g => DATA.goodCategory[g] === 'industrial')],
    ['Raw', () => DATA.goods.filter(g => DATA.goodCategory[g] === 'raw')],
    ['Consumer', () => DATA.goods.filter(g => DATA.goodCategory[g] === 'consumer')],
    ['None', () => []],
  ],
  onChange: sel => { goodsOn = sel; drawPrices(); },
});
document.getElementById('topmovers').onclick = () => goodsPicker.set(topMovers(6));

const pscale = document.getElementById('pscale');
pscale.onclick = () => {
  priceLog = !priceLog;
  pscale.setAttribute('aria-pressed', priceLog);
  pscale.textContent = priceLog ? 'Logarithmic' : 'Linear';
  drawPrices();
};
const pindex = document.getElementById('pindex');
pindex.onclick = () => {
  priceIndex = !priceIndex;
  pindex.setAttribute('aria-pressed', priceIndex);
  pindex.textContent = priceIndex ? 'Indexed (=100)' : 'Absolute';
  drawPrices();
};

function priceSeries(good) {
  const by = DATA.prices[good] || {};
  const pts = [];
  let base = null;
  for (let i = 0; i < PD.length; i++) {
    let v = by[PD[i]];
    if (v === undefined) continue;
    if (priceIndex) {
      if (base === null) { base = v; if (!base) continue; }
      v = v / base * 100;
    }
    pts.push([PY[i], v]);
  }
  return pts;
}

function drawPrices() {
  const note = document.getElementById('pricenote');
  const shown = DATA.goods.filter(g => goodsOn.includes(g));
  const firstYear = Math.ceil(pxMin), lastYear = Math.floor(pxMax);
  const step = Math.max(1, Math.ceil((lastYear - firstYear + 1) / 12));
  const xTicks = [];
  for (let yr = firstYear; yr <= lastYear; yr += step) xTicks.push({v: yr, label: yr});

  plot(document.getElementById('pricechart'), {
    series: shown.map(g => ({name: g, colour: goodColour(g), pts: priceSeries(g)})),
    xOf: pxOf, xTicks,
    hoverXs: PD.map((d, i) => ({v: PY[i], label: d})),
    fmt: v => priceIndex ? Math.round(v).toString() : (v >= 10 ? v.toFixed(0) : v.toFixed(2)),
    log: priceLog, thin: true, baseline: priceIndex ? 100 : null,
    zeroFloor: !priceIndex,
    readout: document.getElementById('pricereadout'),
    idle: 'Hover the plot to read prices at a date.',
    emptyMsg: PD.length ? 'Select a good, or press Top movers.' : 'No price data in these saves.',
  });

  const flat = DATA.goods.filter(g => DATA.movement[g] === 0).length;
  note.textContent = PD.length
    ? `${PD.length} dated readings across ${DATA.goods.length} goods.`
      + (flat ? ` ${flat} never moved in this span, so they are undiscovered or untraded.` : '')
    : '';
}

const snapSel = document.getElementById('snapsel');
DATA.snapshotDates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  snapSel.appendChild(o);
});
if (DATA.snapshotDates.length)
  snapSel.value = DATA.snapshotDates[DATA.snapshotDates.length - 1];
snapSel.onchange = drawMarketTable;

const MARKET_COLS = [
  {key: 'good', label: 'Good', colour: r => goodColour(r.good)},
  {key: 'category', label: 'Category'},
  {key: 'price', label: 'Price', fmt: v => v.toFixed(2)},
  {key: 'base', label: 'Base', fmt: v => v == null ? '—' : v.toFixed(2),
   title: "The good's base cost from the mod's common/goods.txt"},
  {key: 'vsBase', label: 'vs base',
   fmt: v => v == null ? '—' : (v >= 0 ? '+' : '') + v.toFixed(0) + '%',
   title: 'How far the world price sits above or below that base cost',
   cls: r => r.vsBase == null ? '' : r.vsBase > 1 ? 'up' : r.vsBase < -1 ? 'down' : ''},
  {key: 'change', label: 'Change',
   fmt: v => (v >= 0 ? '+' : '') + v.toFixed(1) + '%',
   cls: r => r.change > 0.05 ? 'up' : r.change < -0.05 ? 'down' : ''},
  {key: 'supply', label: 'Supply', fmt: fmtCount},
  {key: 'demand', label: 'Demand', fmt: fmtCount},
  {key: 'actual_sold', label: 'Sold', fmt: fmtCount},
  {key: 'floored', label: 'At floor', fmt: v => v ? 'yes' : '—'},
];
const marketState = {key: 'change', dir: -1};
function drawMarketTable() {
  const date = snapSel.value;
  document.getElementById('snapdate').textContent = date || '—';
  const snap = DATA.snapshot[date] || {};
  const rows = Object.keys(snap).map(good => {
    const by = DATA.prices[good] || {};
    const seen = PD.filter(d => by[d] !== undefined);
    const first = seen.length ? by[seen[0]] : 0;
    const last = seen.length ? by[seen[seen.length - 1]] : 0;
    const base = (DATA.basePrices || {})[good];
    return {
      good, category: DATA.goodCategory[good] || 'other',
      price: snap[good].price,
      base: base == null ? null : base,
      vsBase: base ? (snap[good].price - base) / base * 100 : null,
      change: first ? (last - first) / first * 100 : 0,
      supply: snap[good].supply,
      demand: snap[good].demand,
      actual_sold: snap[good].actual_sold,
      floored: snap[good].floored,
      discovered: snap[good].discovered,
    };
  }).filter(r => r.discovered);
  renderTable(document.getElementById('market'), MARKET_COLS, rows, marketState,
              row => goodsPicker.set([row.good]));
}

/* =============== MAP =============== */
const MAP = DATA.map;
let mapTags = null;          // null means every nation
let mapByControl = true;
let mapProv = null;          // province id for every pixel
let mapOwners = null;        // date -> {own: Map, occ: Map}
let mapDots = [];            // what is currently drawn, for hit testing
let mapBase = null;          // the political map, painted once per view
let mapBaseKey = '';
let mapZoom = 1;             // 1 fits the whole world to the panel width
let mapOX = 0, mapOY = 0;    // map coordinate sitting at the panel's top left
let mapPinned = null;        // a marker clicked, so the readout stays put

function mapDecode() {
  const grid = new Int32Array(MAP.w * MAP.h);
  let at = 0;
  for (const token of MAP.runs.split(' ')) {
    if (!token) continue;
    const dot = token.indexOf('.');
    const pid = parseInt(dot < 0 ? token : token.slice(0, dot), 36);
    const run = dot < 0 ? 1 : parseInt(token.slice(dot + 1), 36);
    grid.fill(pid, at, at + run);
    at += run;
  }
  return grid;
}

/* Ownership ships as a delta per save, so replay them in order. */
function mapOwnerTables() {
  const out = {};
  let cur = new Map();
  for (const step of MAP.owners) {
    if (step.base) cur = new Map();
    if (step.clear) for (const p of step.clear.split(',')) cur.delete(+p);
    if (step.set) for (const pair of step.set.split(',')) {
      const c = pair.indexOf(':');
      cur.set(+pair.slice(0, c), +pair.slice(c + 1));
    }
    const occ = new Map();
    if (step.occ) for (const pair of step.occ.split(',')) {
      const c = pair.indexOf(':');
      occ.set(+pair.slice(0, c), +pair.slice(c + 1));
    }
    out[step.date] = {own: new Map(cur), occ};
  }
  return out;
}

const mapSea = new Set((MAP && MAP.sea) || []);
const MAP_WATER = [38, 54, 74], MAP_WILD = [122, 106, 78], MAP_EDGE = [32, 18, 14];
/* Land is painted in a nation's own colour and so are the army counters
   standing on it, which left a nation's brigades all but invisible inside its
   own borders -- an orange stack on orange ground, separated by half a pixel
   of outline. The counter is what gives way: it keeps the nation's hue but
   drops toward MAP_SHADE, so the political map reads at full strength and a
   stack still reads against the country it is standing in. Going the other
   way -- dimming the land -- worked too, but it dulled the whole map to fix
   a few hundred circles. Dark counters also carry a pale numeral, which a
   full-strength one could not. */
const MAP_SHADE = [16, 14, 20], MAP_SHADE_MIX = 0.48;
/** A #rrggbb string in the same hue, dropped toward MAP_SHADE. */
const mapDim = hex => {
  const rgb = parseInt((hex || '#ffffff').slice(1), 16);
  const keep = 1 - MAP_SHADE_MIX;
  const mix = (v, i) => Math.round(v * keep + MAP_SHADE[i] * MAP_SHADE_MIX);
  return `rgb(${mix((rgb >> 16) & 255, 0)} ${mix((rgb >> 8) & 255, 1)} `
       + `${mix(rgb & 255, 2)})`;
};

function mapPalette(date) {
  const book = mapOwners[date] || {own: new Map(), occ: new Map()};
  const owners = new Map(book.own);
  if (mapByControl) book.occ.forEach((idx, pid) => owners.set(pid, idx));
  let top = 0;
  mapSea.forEach(p => { if (p > top) top = p; });
  owners.forEach((_i, p) => { if (p > top) top = p; });
  const table = new Int32Array(top + 1);
  const wild = (MAP_WILD[0] << 16) | (MAP_WILD[1] << 8) | MAP_WILD[2];
  const water = (MAP_WATER[0] << 16) | (MAP_WATER[1] << 8) | MAP_WATER[2];
  for (let p = 0; p <= top; p++) table[p] = mapSea.has(p) ? water : wild;
  owners.forEach((idx, pid) => {
    const hex = MAP.colours[MAP.tags[idx]];
    if (hex) table[pid] = parseInt(hex.slice(1), 16);
  });
  return table;
}

/* The political map only changes with the save or the shading, so it is painted
   into an offscreen canvas and then blitted at whatever zoom is in force. */
function mapPaintBase(date) {
  const key = date + '|' + mapByControl;
  if (mapBase && mapBaseKey === key) return;
  if (!mapProv) { mapProv = mapDecode(); mapOwners = mapOwnerTables(); }
  mapBase = document.createElement('canvas');
  mapBase.width = MAP.w; mapBase.height = MAP.h;
  const ctx = mapBase.getContext('2d');
  const img = ctx.createImageData(MAP.w, MAP.h);
  const px = img.data;
  const table = mapPalette(date);
  const top = table.length;
  const wild = (MAP_WILD[0] << 16) | (MAP_WILD[1] << 8) | MAP_WILD[2];
  for (let i = 0, o = 0; i < mapProv.length; i++, o += 4) {
    const pid = mapProv[i];
    const c = pid < top ? table[pid] : wild;
    px[o] = (c >> 16) & 255; px[o + 1] = (c >> 8) & 255; px[o + 2] = c & 255;
    px[o + 3] = 255;
  }
  // a one-pixel edge wherever neighbouring pixels sit in different provinces
  for (let y = 0; y < MAP.h; y++) {
    for (let x = 0; x < MAP.w; x++) {
      const i = y * MAP.w + x;
      const p = mapProv[i];
      if (p !== (x + 1 < MAP.w ? mapProv[i + 1] : p) ||
          p !== (y + 1 < MAP.h ? mapProv[i + MAP.w] : p)) {
        const o = i * 4;
        px[o] = MAP_EDGE[0]; px[o + 1] = MAP_EDGE[1]; px[o + 2] = MAP_EDGE[2];
      }
    }
  }
  ctx.putImageData(img, 0, 0);
  mapBaseKey = key;
}

function mapFit() {          // screen pixels per map pixel at zoom 1
  const canvas = document.getElementById('mapcanvas');
  return (canvas.clientWidth || MAP.w) / MAP.w;
}

function mapClamp() {
  const canvas = document.getElementById('mapcanvas');
  const s = mapFit() * mapZoom;
  const viewW = (canvas.clientWidth || MAP.w) / s;
  const viewH = (canvas.clientHeight || MAP.h) / s;
  mapOX = viewW >= MAP.w ? (MAP.w - viewW) / 2
                         : Math.min(Math.max(mapOX, 0), MAP.w - viewW);
  mapOY = viewH >= MAP.h ? (MAP.h - viewH) / 2
                         : Math.min(Math.max(mapOY, 0), MAP.h - viewH);
}

/* Provinces the last mapStacks() could not place, so the readout can own up
   to an under-drawn map instead of quietly showing a fraction of the army.
   With the base-game fallback in the mod loader this should stay at zero. */
let mapUnplaced = 0, mapUnplacedBrigades = 0;

function mapStacks(date) {
  const armies = (MAP.armies || {})[date] || {};
  // `mapTags` is null until the picker is touched, which is what makes the
  // map open showing every nation. After that an empty list is a real
  // choice -- "None" -- and has to draw nothing rather than fall back to all.
  const wanted = mapTags === null ? null : new Set(mapTags);
  const dots = [];
  mapUnplaced = 0; mapUnplacedBrigades = 0;
  for (const pid in armies) {
    const spot = MAP.spots[pid];
    if (!spot) {
      mapUnplaced++;
      for (const a of armies[pid]) mapUnplacedBrigades += a[1];
      continue;
    }
    const stacks = armies[pid]
      .map(a => ({tag: MAP.tags[a[0]], n: a[1], mix: a[2]}))
      .filter(a => !wanted || wanted.has(a.tag));
    if (!stacks.length) continue;
    stacks.sort((a, b) => b.n - a.n);
    dots.push({x: spot[0], y: spot[1], pid: +pid, stacks,
               total: stacks.reduce((s, a) => s + a.n, 0)});
  }
  dots.sort((a, b) => b.total - a.total);   // small stacks draw last, on top
  return dots;
}

function mapRender() {
  if (!MAP) return;
  const canvas = document.getElementById('mapcanvas');
  const date = document.getElementById('mapsave').value || DATA.lastDate;
  document.getElementById('mapdate').textContent = date;
  mapPaintBase(date);

  const dpr = window.devicePixelRatio || 1;
  const cw = canvas.clientWidth || MAP.w, ch = canvas.clientHeight || MAP.h;
  if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) {
    canvas.width = Math.round(cw * dpr);
    canvas.height = Math.round(ch * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cw, ch);

  mapClamp();
  const s = mapFit() * mapZoom;
  // crisp province edges when magnifying, but let the browser average when the
  // raster is finer than the screen, or shrinking it turns into noise
  ctx.imageSmoothingEnabled = s < 1;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(mapBase, -mapOX * s, -mapOY * s, MAP.w * s, MAP.h * s);

  mapDots = mapStacks(date);
  // markers grow with zoom, but slower than the map, so a dense theatre thins
  // out as you go in instead of turning into one blob
  const grow = Math.pow(mapZoom, 0.45);
  const labelled = [];
  for (const dot of mapDots) {
    dot.sx = (dot.x - mapOX) * s;
    dot.sy = (dot.y - mapOY) * s;
    dot.sr = Math.max(2.2, Math.min(26, Math.sqrt(dot.total) * 1.3 * grow));
    if (dot.sx < -20 || dot.sy < -20 || dot.sx > cw + 20 || dot.sy > ch + 20) continue;
    const ink = t => mapDim(MAP.colours[t] || '#ffffff');
    // The nation's hue, dropped toward black, so the counter reads against
    // its own country without the map having to give up any colour.
    ctx.beginPath();
    ctx.arc(dot.sx, dot.sy, dot.sr, 0, Math.PI * 2);
    ctx.fillStyle = ink(dot.stacks[0].tag);
    ctx.fill();
    // A province holding more than one nation -- a battle, or allies stacked
    // together -- carries the split as a band round the rim rather than as a
    // whole pie. The middle has to stay one flat colour for the numeral to be
    // legible on it, and the rim is where a share is easiest to judge anyway,
    // since that is where the counter has the most room. Below a few pixels
    // the band would be noise, so a small counter stays the dominant colour
    // and the breakdown is a hover away.
    if (dot.stacks.length > 1 && dot.sr >= 5.5) {
      const band = Math.max(2, dot.sr * 0.4);
      const inner = dot.sr - band;
      // Neutral middle, not the biggest nation's colour: an even split
      // between two nations otherwise reads as mostly whoever holds the
      // core. It leaves the ring to carry the proportion on its own, and
      // makes a shared province tell itself apart from a plain one at a
      // glance -- solid disc for one nation, ringed for several.
      ctx.beginPath();
      ctx.arc(dot.sx, dot.sy, inner, 0, Math.PI * 2);
      ctx.fillStyle = 'rgb(26 24 30)';
      ctx.fill();
      let angle = -Math.PI / 2;
      for (const part of dot.stacks) {
        const sweep = part.n / dot.total * Math.PI * 2;
        ctx.beginPath();
        ctx.arc(dot.sx, dot.sy, dot.sr, angle, angle + sweep);
        ctx.arc(dot.sx, dot.sy, inner, angle + sweep, angle, true);
        ctx.closePath();
        ctx.fillStyle = ink(part.tag);
        ctx.fill();
        angle += sweep;
      }
      // Neighbouring nations can be close in colour, so the segments are
      // parted rather than left to run together -- but only once the band is
      // thick enough that a line across it is not most of the segment.
      if (dot.sr >= 9) {
        ctx.lineWidth = Math.min(1.1, .45 * grow);
        ctx.strokeStyle = 'rgba(0,0,0,.6)';
        angle = -Math.PI / 2;
        for (const part of dot.stacks) {
          ctx.beginPath();
          ctx.moveTo(dot.sx + inner * Math.cos(angle), dot.sy + inner * Math.sin(angle));
          ctx.lineTo(dot.sx + dot.sr * Math.cos(angle), dot.sy + dot.sr * Math.sin(angle));
          ctx.stroke();
          angle += part.n / dot.total * Math.PI * 2;
        }
        ctx.beginPath();
        ctx.arc(dot.sx, dot.sy, inner, 0, Math.PI * 2);
        ctx.stroke();
      }
    }
    // A pale ring rather than a dark one, now that the counter is the dark
    // thing: it is the edge that survives on a dark nation's land.
    ctx.beginPath();
    ctx.arc(dot.sx, dot.sy, dot.sr, 0, Math.PI * 2);
    ctx.lineWidth = Math.min(1.6, .7 * grow);
    ctx.strokeStyle = 'rgba(255,240,214,.7)';
    ctx.stroke();
    if (mapPinned && mapPinned.pid === dot.pid) {
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = '#ffffff';
      ctx.stroke();
    }
    labelled.push(dot);
  }
  // Numerals last, so a small stack drawn over a big one cannot have its
  // count half-covered. Only where the circle can hold the digits: below
  // that the number would be a smudge, and the count is a hover away.
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const dot of labelled) {
    const text = dot.total.toLocaleString();
    // Fitted to whatever the numeral actually sits on: the whole circle, or
    // just the core when a band has been taken out of the rim for the split.
    const room = dot.stacks.length > 1 && dot.sr >= 5.5
      ? dot.sr - Math.max(2, dot.sr * 0.4) : dot.sr;
    // Circles are sized by area, so a 4-digit stack is not much wider than a
    // 2-digit one; the fit has to be checked against the digits themselves.
    const size = Math.min(room * 1.5, room * 3.2 / text.length);
    if (size < 7) continue;
    ctx.font = `600 ${size.toFixed(1)}px "IBM Plex Mono", monospace`;
    ctx.lineWidth = Math.max(1.6, size / 5);
    ctx.strokeStyle = 'rgba(0,0,0,.55)';
    ctx.strokeText(text, dot.sx, dot.sy);
    ctx.fillStyle = '#F6ECD8';
    ctx.fillText(text, dot.sx, dot.sy);
  }
  document.getElementById('mapzoom').textContent = mapZoom.toFixed(1) + '×';
  mapShow(mapPinned);
}

function mapIdle() {
  const shown = mapDots.reduce((s, d) => s + d.total, 0);
  document.getElementById('mapreadout').innerHTML =
    `<span class="rk">stacks</span> <b>${mapDots.length.toLocaleString()}</b>`
    + `<span><span class="rk">brigades shown</span> <b>${shown.toLocaleString()}</b></span>`
    + `<span><span class="rk">shading</span> <b>${mapByControl ? 'controller' : 'owner'}</b></span>`
    + (mapUnplaced
        ? `<span><span class="rk">no map position</span> `
          + `<b>${mapUnplaced.toLocaleString()}</b>`
          + `<span class="rk"> provinces, ${mapUnplacedBrigades.toLocaleString()} brigades</span></span>`
        : '')
    + `<span class="rk">hover a marker, click to pin it</span>`;
}

function mapShow(dot) {
  if (!dot) return mapIdle();
  const name = (MAP.names && MAP.names[dot.pid]) || ('province ' + dot.pid);
  const bits = dot.stacks.map(s => {
    const mix = s.mix.split(';').map(part => {
      const c = part.lastIndexOf(':');
      return `${part.slice(0, c)} ${part.slice(c + 1)}`;
    }).join(', ');
    return `<span><b style="color:${MAP.colours[s.tag] || '#fff'}">${s.tag}</b> `
         + `<b>${s.n.toLocaleString()}</b> <span class="rk">${mix}</span></span>`;
  });
  document.getElementById('mapreadout').innerHTML =
    `<span class="rk">${name}</span>`
    + `<span><b>${dot.total.toLocaleString()}</b> <span class="rk">brigades</span></span>`
    + bits.join('');
}

function mapAt(e) {
  const canvas = document.getElementById('mapcanvas');
  const box = canvas.getBoundingClientRect();
  return {x: e.clientX - box.left, y: e.clientY - box.top};
}

function mapPick(p) {
  let best = null, bestD = 1e9;
  for (const dot of mapDots) {
    if (dot.sx === undefined) continue;
    const dx = dot.sx - p.x, dy = dot.sy - p.y;
    const d = dx * dx + dy * dy;
    const reach = Math.max(dot.sr, 5) + 2;
    if (d < reach * reach && d < bestD) { best = dot; bestD = d; }
  }
  return best;
}

if (MAP) {
  const wrap = document.querySelector('.mapwrap');
  wrap.style.aspectRatio = MAP.w + ' / ' + MAP.h;

  const mapSave = document.getElementById('mapsave');
  DATA.dates.forEach(d => {
    const o = document.createElement('option'); o.value = d; o.textContent = d;
    mapSave.appendChild(o);
  });
  mapSave.value = DATA.lastDate;
  mapSave.onchange = () => {
    mapPinned = null; mapPicker.refresh(); mapRender(); drawGreatPowers();
  };

  const occBtn = document.getElementById('mapocc');
  occBtn.onclick = () => {
    mapByControl = !mapByControl;
    occBtn.setAttribute('aria-pressed', mapByControl);
    occBtn.textContent = mapByControl ? 'Control' : 'Ownership';
    mapRender();
  };
  document.getElementById('mapreset').onclick = () => {
    mapZoom = 1; mapOX = 0; mapOY = 0; mapPinned = null; mapRender();
  };

  const mapPicker = makePicker(document.getElementById('pick-map'),
    tagPickerCfg(DATA.tags.slice(), sel => { mapTags = sel; mapRender(); },
                 () => mapSave.value));

  const canvas = document.getElementById('mapcanvas');

  function mapZoomTo(factor, at) {
    const before = mapFit() * mapZoom;
    const mx = mapOX + at.x / before, my = mapOY + at.y / before;
    mapZoom = Math.min(24, Math.max(1, mapZoom * factor));
    const after = mapFit() * mapZoom;
    mapOX = mx - at.x / after;
    mapOY = my - at.y / after;
    mapRender();
  }

  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    mapZoomTo(Math.exp(-e.deltaY * 0.0016), mapAt(e));
  }, {passive: false});

  canvas.addEventListener('dblclick', e => mapZoomTo(2, mapAt(e)));

  let drag = null;
  canvas.addEventListener('pointerdown', e => {
    drag = {...mapAt(e), ox: mapOX, oy: mapOY, moved: false};
    canvas.setPointerCapture(e.pointerId);
    canvas.style.cursor = 'grabbing';
  });
  canvas.addEventListener('pointermove', e => {
    const p = mapAt(e);
    if (drag) {
      const s = mapFit() * mapZoom;
      if (Math.abs(p.x - drag.x) + Math.abs(p.y - drag.y) > 3) drag.moved = true;
      mapOX = drag.ox - (p.x - drag.x) / s;
      mapOY = drag.oy - (p.y - drag.y) / s;
      mapRender();
      return;
    }
    if (!mapPinned) mapShow(mapPick(p));
  });
  canvas.addEventListener('pointerup', e => {
    const moved = drag && drag.moved;
    drag = null;
    canvas.style.cursor = 'grab';
    if (moved) return;
    const hit = mapPick(mapAt(e));
    mapPinned = (mapPinned && hit && mapPinned.pid === hit.pid) ? null : hit;
    mapRender();
  });
  canvas.addEventListener('pointerleave', () => { if (!mapPinned) mapIdle(); });
  window.addEventListener('resize', () => { if (mapBase) mapRender(); });
} else {
  // No --mod-path, so there is no province bitmap and no country order: hide the
  // map and the great power ranking rather than showing empty frames.
  for (const id of ['mapcanvas', 'gpgrid']) {
    const el = document.getElementById(id);
    const section = el && el.closest('section');
    if (section) section.hidden = true;
  }
}


/* =============== GREAT POWERS =============== */
function drawGreatPowers() {
  const grid = document.getElementById('gpgrid');
  if (!grid) return;
  const date = (document.getElementById('mapsave') || {}).value || DATA.lastDate;
  const list = (DATA.greatPowers || {})[date] || [];
  document.getElementById('gpdate').textContent = date;
  const section = grid.closest('section');
  if (section) section.hidden = !list.length;
  grid.innerHTML = '';
  const facts = DATA.facts[date] || {};
  list.forEach((entry, i) => {
    const [tag, flagKey] = Array.isArray(entry) ? entry : [entry, ''];
    const f = facts[tag] || {};
    const colour = (DATA.map && DATA.map.colours[tag]) || colourFor(tag);
    const flag = (DATA.flags || {})[flagKey];
    const card = document.createElement('div');
    card.className = 'gpcard';
    const stat = (label, v, fmt) =>
      `<span><span class="rk">${label}</span> <b>${v == null ? '—' : (fmt ? fmt(v) : v.toLocaleString())}</b></span>`;
    card.innerHTML =
      `<div class="gprank">${i + 1}</div>`
      + (flag ? `<img class="gpflag" src="${flag}" alt="">`
              : `<div class="gpflag" style="background:${colour}"></div>`)
      + `<div class="gpbody">`
      +   `<div class="gpname">${nameOf(tag)} <span class="rk">${tag}</span></div>`
      +   `<div class="gpstats">`
      +     stat('prestige', f.prestige, v => Math.round(v).toLocaleString())
      +     stat('craftsmen', ((DATA.pops[tag] || {})[date] || {}).craftsmen)
      +     stat('factories', f.factory_levels)
      +     stat('brigades', f.brigades)
      +     stat('ships', f.ships)
      +   `</div>`
      + `</div>`;
    grid.appendChild(card);
  });
}


/* A long <select> of nations is unusable without one. Filters the options in
   place and jumps to the first match, so the select stays the source of truth
   and every existing onchange keeps working. */
function searchSelect(select, placeholder) {
  if (!select) return;
  const box = document.createElement('input');
  box.type = 'search';
  box.className = 'selsearch';
  box.placeholder = placeholder || 'search';
  box.setAttribute('aria-label', placeholder || 'search');
  select.parentNode.insertBefore(box, select);
  box.oninput = () => {
    const q = box.value.trim().toLowerCase();
    let first = null;
    for (const o of select.options) {
      // `off` is set by limitSelect for nations this save does not have; the
      // search must not bring them back.
      const hit = o.dataset.off !== '1'
        && (!q || o.textContent.toLowerCase().includes(q));
      o.hidden = !hit;
      if (hit && !first) first = o;
    }
    if (q && first && select.value !== first.value) {
      select.value = first.value;
      if (select.onchange) select.onchange();
    }
  };
}

/* =============== TECHNOLOGY =============== */
const TECH = DATA.technology && DATA.technology.tree ? DATA.technology : null;
let techCat = null;
let techPick = null;          // {category, area, index} of the opened tech

function techResearched(tag, date) {
  const have = new Set();
  const idx = ((DATA.techsBy[tag] || {})[date]) || [];
  for (const i of idx) have.add(DATA.techOrder[i]);
  return have;
}

// A tech matches a search if the term turns up in its own name or effects,
// or in the name or effects of anything it unlocks -- a mobilization search
// should surface both a tech that directly grants it and one that only does
// so through an invention gated behind it.
function techMatches(t, q) {
  const hit = (label, value) => label.toLowerCase().includes(q)
    || String(value).toLowerCase().includes(q);
  if (t.name.toLowerCase().includes(q)) return true;
  if (t.effects.some(([l, v]) => hit(l, v))) return true;
  return t.inventions.some(([, name, effs]) =>
    name.toLowerCase().includes(q) || effs.some(([l, v]) => hit(l, v)));
}
function techCatMatchCount(cat, q) {
  let n = 0;
  for (const col of TECH.tree[cat])
    for (const t of col.techs)
      if (techMatches(t, q)) n++;
  return n;
}

function drawTechTree() {
  if (!TECH) return;
  const tag = document.getElementById('techtag').value;
  const date = document.getElementById('techsave').value;
  document.getElementById('techwho').textContent =
    (nameOf(tag) === tag ? tag : nameOf(tag) + ' · ' + tag) + ' at ' + date;
  const have = techResearched(tag, date);
  const query = (document.getElementById('techfind').value || '').trim().toLowerCase();

  // category buttons, with a researched count each, plus a match count badge
  // when a search is active -- so a hit sitting in a category the reader
  // isn't currently looking at is visible without jumping them there.
  const bar = document.getElementById('techcats');
  bar.innerHTML = '';
  const cats = Object.keys(TECH.tree);
  if (!techCat || !TECH.tree[techCat]) techCat = cats[0];
  for (const cat of cats) {
    let total = 0, done = 0;
    for (const col of TECH.tree[cat])
      for (const t of col.techs) { total++; if (have.has(t.key)) done++; }
    const b = document.createElement('button');
    b.textContent = (TECH.categories[cat] || cat) + '  ' + done + '/' + total;
    if (query) {
      const n = techCatMatchCount(cat, query);
      if (n) {
        const badge = document.createElement('span');
        badge.className = 'techcatbadge';
        badge.textContent = n;
        badge.title = n + ' match' + (n === 1 ? '' : 'es') + ' in ' + (TECH.categories[cat] || cat);
        b.appendChild(badge);
      }
    }
    b.setAttribute('aria-pressed', cat === techCat);
    b.onclick = () => { techCat = cat; techPick = null; drawTechTree(); };
    bar.appendChild(b);
  }

  const grid = document.getElementById('techgrid');
  grid.innerHTML = '';
  grid.style.gridTemplateColumns =
    'repeat(' + TECH.tree[techCat].length + ',minmax(0,1fr))';
  TECH.tree[techCat].forEach((col, ci) => {
    const wrap = document.createElement('div');
    wrap.className = 'techcol';
    const head = document.createElement('div');
    head.className = 'techhead';
    head.textContent = col.label;
    wrap.appendChild(head);
    col.techs.forEach((t, ti) => {
      const box = document.createElement('button');
      const done = have.has(t.key);
      box.className = 'techbox' + (done ? ' done' : '');
      const open = techPick && techPick.category === techCat
                && techPick.area === ci && techPick.index === ti;
      if (open) box.classList.add('open');
      if (query) box.classList.add(techMatches(t, query) ? 'techmatch' : 'techdim');
      box.textContent = t.name;
      box.title = t.name + ' · ' + t.year + ' · ' + t.cost.toLocaleString() + ' research points';
      box.onclick = () => {
        techPick = open ? null : {category: techCat, area: ci, index: ti};
        drawTechTree();
      };
      wrap.appendChild(box);
    });
    grid.appendChild(wrap);
  });

  const panel = document.getElementById('techdetail');
  if (!techPick) {
    panel.innerHTML = '<span class="rk">Click a technology for its effects and '
                    + 'the inventions it unlocks.</span>';
    return;
  }
  const t = TECH.tree[techPick.category][techPick.area].techs[techPick.index];
  const done = have.has(t.key);
  const effects = t.effects.length
    ? t.effects.map(([label, value]) =>
        `<li><span class="rk">${label}</span> <b>${value}</b></li>`).join('')
    : '<li class="rk">No direct modifiers.</li>';
  const invs = t.inventions.length
    ? t.inventions.map(([, name, effs]) => `<li>${name}`
        + (effs.length
            ? `<div class="techinv"><span class="rk">${effs.map(([l, v]) =>
                `${l} <b>${v}</b>`).join(' &middot; ')}</span></div>`
            : '')
        + `</li>`).join('')
    : '<li class="rk">Nothing gated behind it.</li>';
  panel.innerHTML =
    `<div class="techtitle">${t.name}`
    + `<span class="rk"> ${t.year} · ${t.cost.toLocaleString()} rp · `
    + `${done ? 'researched' : 'not researched'}</span></div>`
    + `<div class="techcols2">`
    +   `<div><div class="techsub">Effects</div><ul>${effects}</ul></div>`
    +   `<div><div class="techsub">Inventions it makes available</div>`
    +     `<ul>${invs}</ul>`
    +     `<p class="note">These are the inventions the technology makes`
    +     ` available, not the ones this nation has rolled.</p></div>`
    + `</div>`;
}

if (TECH) {
  const tagSel = document.getElementById('techtag');
  DATA.tags.forEach(t => {
    const o = document.createElement('option'); o.value = t;
    o.textContent = nameOf(t) === t ? t : `${t} · ${nameOf(t)}`;
    tagSel.appendChild(o);
  });
  tagSel.onchange = () => { techPick = null; drawTechTree(); };
  const saveSel = document.getElementById('techsave');
  DATA.dates.forEach(d => {
    const o = document.createElement('option'); o.value = d; o.textContent = d;
    saveSel.appendChild(o);
  });
  saveSel.value = DATA.lastDate;
  const techLimit = () => limitSelect(tagSel, tagsAt(saveSel.value),
                                      biggestAt(saveSel.value, 'total_pop', 1)[0]);
  tagSel.value = largestBy('total_pop');
  techLimit();
  saveSel.onchange = () => { techPick = null; techLimit(); drawTechTree(); };
  document.getElementById('techfind').oninput = () => drawTechTree();
} else {
  const tab = document.getElementById('tab-tech');
  if (tab) tab.hidden = true;
}

/* =============== WARS =============== */
const WARS = DATA.wars || [];
let warPick = null;
let warSort = {key: 'losses', dir: -1};

function warLosses(w) { return w.losses[0] + w.losses[1]; }
function warSide(list) {
  return list.map(t => `<b style="color:${colourFor(t)}">${t}</b>`).join(' ');
}

function drawWarTable() {
  if (!WARS.length) return;
  const q = (document.getElementById('warfind').value || '').trim().toLowerCase();
  const rows = WARS.filter(w => !q
    || w.name.toLowerCase().includes(q)
    || w.attackers.concat(w.defenders).some(t =>
         t.toLowerCase() === q || nameOf(t).toLowerCase().includes(q)));
  const get = {
    name: w => w.name.toLowerCase(),
    start: w => w.start || '',
    losses: warLosses,
    battles: w => w.battles.length,
    land: w => w.transfers.length,
    outcome: w => w.outcome || 'zz',
  }[warSort.key] || warLosses;
  rows.sort((a, b) => {
    const x = get(a), y = get(b);
    return (x < y ? -1 : x > y ? 1 : 0) * warSort.dir;
  });

  const head = [['name', 'War'], ['start', 'From'], ['start', 'To'],
                ['losses', 'Casualties'], ['battles', 'Battles'],
                ['land', 'States'], ['outcome', 'Goals taken']];
  const wide = k => k === 'name' ? '' : ' class="num"';
  const body = rows.map((w, i) => {
    const idx = WARS.indexOf(w);
    return `<tr class="warrow${warPick === idx ? ' on' : ''}" data-war="${idx}">`
      + `<td class="warname">${w.name}`
      + `<div class="rk sides">${warSide(w.attackers)} <span class="rk">v</span> `
      + `${warSide(w.defenders)}</div></td>`
      + `<td class="num">${w.start || '—'}</td>`
      + `<td class="num">${w.active ? '<b>ongoing</b>' : (w.end || '—')}</td>`
      + `<td class="num">${warLosses(w).toLocaleString()}</td>`
      + `<td class="num">${w.battles.length}${w.battles.length && w.dated < w.battles.length
            ? ` <span class="rk">(${w.dated} dated)</span>` : ''}</td>`
      + `<td class="num">${w.transfers.length || '—'}</td>`
      + `<td class="num">${w.outcome || '<span class="rk">—</span>'}</td></tr>`;
  }).join('');
  document.getElementById('wartable').innerHTML =
    `<thead><tr>${head.map(([k, label]) =>
      `<th data-k="${k}"${wide(k)}${warSort.key === k ? ' aria-sort="' +
        (warSort.dir < 0 ? 'descending' : 'ascending') + '"' : ''}>${label}</th>`)
      .join('')}</tr></thead><tbody>${body}</tbody>`;
  document.querySelectorAll('#wartable th').forEach(th => {
    th.onclick = () => {
      const k = th.dataset.k;
      if (warSort.key === k) warSort.dir *= -1;
      else warSort = {key: k, dir: k === 'name' || k === 'start' ? 1 : -1};
      drawWarTable();
    };
  });
  document.querySelectorAll('#wartable tbody tr').forEach(tr => {
    tr.onclick = () => {
      const idx = +tr.dataset.war;
      warPick = warPick === idx ? null : idx;
      drawWarTable(); drawWarDetail();
    };
  });
  document.getElementById('warcount').textContent =
    `${rows.length} of ${WARS.length} wars`;
  drawWarDetail();
}

let warBattleSort = {key: 'date', dir: 1};
// Which battles currently have their detail row open. Battle objects are
// parsed once and only ever reordered, never recreated, so the object itself
// is a stable key across re-sorts -- no need to invent a string id for it.
let expandedBattles = new Set();

function warFlag(tag) {
  const src = (DATA.flags || {})[tag + '|'];
  return src ? `<img class="tagflag" src="${src}" alt="">` : '';
}
function warTag(tag) {
  if (!tag) return '<span class="rk">&mdash;</span>';
  return `${warFlag(tag)}<b style="color:${colourFor(tag)}">${tag}</b>`;
}

// A war's own attackers/defenders lists are flat tags with no join info; the
// *_parties lists (when present) carry a join date and an original/later
// split per tag. Older data that predates that field falls back to treating
// everyone as original, so the layout still works either way.
function belParties(w, side) {
  const parties = w[side + '_parties'];
  if (parties) return parties;
  return (w[side + 's'] || []).map(tag => ({tag, joined: '', original: true}));
}
function belRow(p) {
  const known = nameOf(p.tag) !== p.tag;
  return `<div class="belrow">${warFlag(p.tag)}`
    + `<b style="color:${colourFor(p.tag)}">${known ? nameOf(p.tag) : p.tag}</b>`
    + `<span class="belleader"></span>`
    + `<span class="rk">${p.joined || 'from the start'}</span></div>`;
}
function belColumn(title, parties) {
  const original = parties.filter(p => p.original);
  const later = parties.filter(p => !p.original);
  return `<div class="belcol"><div class="belcolhead">${title}</div>`
    + (original.length
        ? `<div class="belgroup"><div class="belgrouphead">Original ${title.toLowerCase()}</div>`
          + original.map(belRow).join('') + `</div>`
        : '')
    + (later.length
        ? `<div class="belgroup"><div class="belgrouphead">Later interventions</div>`
          + later.map(belRow).join('') + `</div>`
        : '')
    + `</div>`;
}

// A side's unit string is "kind:n;kind:n", largest first. Parsed once here for
// both the (unused in the row) army total and the expanded composition list.
function sideUnits(s) {
  const units = s[3] ? s[3].split(';').map(p => {
    const [kind, n] = p.split(':');
    return [kind.replace(/_/g, ' '), +n];
  }) : [];
  return {units, army: units.reduce((sum, [, n]) => sum + n, 0)};
}

function battleDetail(b) {
  const side = (label, s) => {
    const {units, army} = sideUnits(s);
    return `<div class="battleside"><div class="sidehead">${label}</div>`
      + `<div class="side">${warTag(s[0])}`
      + `<span class="who">${s[1] || '—'}</span>`
      + units.map(([kind, n]) =>
          `<span class="unit">${kind} ${n.toLocaleString()}</span>`).join('')
      + `</div>`
      + `<div class="sidetotal">army <b>${army.toLocaleString()}</b>`
      +   ` &nbsp; lost <b>${s[2].toLocaleString()}</b></div>`
      + `</div>`;
  };
  return `<tr class="battledetail"><td colspan="8"><div class="battlesides">`
    + side('Defender', b.d) + side('Attacker', b.a)
    + `</div></td></tr>`;
}

function warBattleTable(list, title, kind) {
  if (!list.length) return '';
  const get = {
    date: b => b.date || '9999',
    name: b => b.name.toLowerCase(),
    alost: b => b.a[2],
    dlost: b => b.d[2],
    total: b => b.a[2] + b.d[2],
  }[warBattleSort.key] || (b => b.date || '9999');
  const rows = list.slice().sort((x, y) => {
    const a = get(x), b = get(y);
    return (a < b ? -1 : a > b ? 1 : 0) * warBattleSort.dir;
  });
  // Defender before Attacker, matching how a reader asks "who held, who came
  // for it" -- the Winner column already carries whichever side actually won.
  const head = [['date', 'Date'], ['name', 'Battle'], ['', 'Winner'],
                ['', 'Defender'], ['dlost', 'Lost'],
                ['', 'Attacker'], ['alost', 'Lost'], ['total', 'Total losses']];
  // Column widths sum to 100%. Fixed rather than content-driven -- see
  // .battletable -- so this table can never push the page wider than the
  // screen no matter how long a battle or nation name gets.
  const widths = [9, 23, 9, 11, 11, 11, 11, 15];
  const numCol = [true, false, false, false, true, false, true, true];
  return `<div class="techsub" style="margin-top:12px">${title} `
    + `<span class="rk">${list.length}</span></div>`
    + `<div class="tablewrap fit"><table class="mini battletable">`
    + `<colgroup>${widths.map(w => `<col style="width:${w}%">`).join('')}</colgroup>`
    + `<thead><tr>`
    + head.map(([k, label], i) => {
        const cls = numCol[i] ? ' class="num"' : '';
        return k
          ? `<th data-bk="${k}"${cls}${warBattleSort.key === k ? ' aria-sort="' +
              (warBattleSort.dir < 0 ? 'descending' : 'ascending') + '"' : ''}>${label}</th>`
          : `<th${cls}>${label}</th>`;
      }).join('')
    + `</tr></thead><tbody>`
    + rows.map((b, i) => {
        const win = b.won ? b.a[0] : b.d[0];
        const open = expandedBattles.has(b);
        return `<tr class="battlerow${open ? ' on' : ''}" `
            + `data-bkind="${kind}" data-bi="${list.indexOf(b)}">`
          + `<td class="num">${b.date || '<span class="rk">unknown</span>'}</td>`
          + `<td>${b.name}</td><td>${warTag(win)}</td>`
          + `<td>${warTag(b.d[0])}</td>`
          + `<td class="num">${b.d[2].toLocaleString()}</td>`
          + `<td>${warTag(b.a[0])}</td>`
          + `<td class="num">${b.a[2].toLocaleString()}</td>`
          + `<td class="num">${(b.a[2] + b.d[2]).toLocaleString()}</td></tr>`
          + (open ? battleDetail(b) : '');
      }).join('')
    + `</tbody></table></div>`;
}

function drawWarDetail() {
  const box = document.getElementById('wardetail');
  if (warPick === null || !WARS[warPick]) {
    box.innerHTML = '<p class="note">Pick a war for its battles and the land it moved.</p>';
    return;
  }
  const w = WARS[warPick];
  const goals = w.goals.length
    ? `<table class="mini fitmini"><thead><tr><th>Demand</th><th>By</th><th>On</th>`
      + `<th>State</th><th>Taken at the peace</th><th>Occupied mid-war</th>`
      + `</tr></thead><tbody>`
      + w.goals.map(g =>
          `<tr><td>${g.cb.replace(/_/g, ' ')}</td>`
          + `<td>${warTag(g.actor)}</td><td>${warTag(g.receiver)}</td>`
          + `<td>${g.state || '—'}</td>`
          + `<td class="${g.met ? 'up' : g.part ? '' : g.checkable ? 'down' : ''}">`
          +   (!g.checkable ? '<span class="rk">not checkable</span>'
               : g.met ? `all ${g.of}` : g.part ? `${g.took} of ${g.of}` : 'none')
          + `</td>`
          + `<td class="rk">${g.sieged === null ? '—' : g.sieged ? 'yes' : 'no'}</td></tr>`)
        .join('')
      + `</tbody></table>`
      + `<p class="note">A war carries more than one demand: the one it opened `
      + `with, plus any added while it ran. Added demands are dropped when the `
      + `war ends, so they survive only where a save caught the war still being `
      + `fought. <strong>Taken at the peace</strong> compares who held the state `
      + `either side of the war. <strong>Occupied mid-war</strong> is the save's `
      + `own <code>is_fulfilled</code> flag: the claimant held the state by siege `
      + `at that moment, a live condition rather than an outcome.</p>`
    : `<p class="note">No war goal was recorded for this war.</p>`;

  const land = w.transfers.length
    ? `<div class="techsub" style="margin-top:12px">States that changed hands</div>`
      + `<table class="mini fitmini"><thead><tr><th>State</th><th>Provinces</th>`
      + `<th>From</th><th>To</th></tr></thead><tbody>`
      + w.transfers.map(t =>
          `<tr><td>${t[1] || t[0] || '—'}</td>`
          + `<td>${t[4]}${t[5] && t[5] !== t[4] ? ` <span class="rk">of ${t[5]}</span>` : ''}</td>`
          + `<td>${warTag(t[2])}</td><td>${warTag(t[3])}</td></tr>`).join('')
      + `</tbody></table>`
    : '';

  const sea = w.battles.filter(b => b.sea), dry = w.battles.filter(b => !b.sea);
  const undated = w.battles.length - w.dated;
  box.innerHTML =
    `<div class="warhead">${w.name}</div>`
    + `<div class="readout" style="border:0;padding:0 0 8px">`
    +   `<span><span class="rk">from</span> <b>${w.start || '—'}</b></span>`
    +   `<span><span class="rk">to</span> <b>${w.active ? 'ongoing' : (w.end || '—')}</b></span>`
    +   `<span><span class="rk">casualties</span> <b>${warLosses(w).toLocaleString()}</b></span>`
    + `</div>`
    + `<div class="belligerents">`
    +   belColumn('Defenders', belParties(w, 'defender'))
    +   `<div class="beldivider"></div>`
    +   belColumn('Attackers', belParties(w, 'attacker'))
    + `</div>`
    + `<div class="techsub">War goals</div>${goals}${land}`
    + warBattleTable(dry, 'Land battles', 'land')
    + warBattleTable(sea, 'Naval battles', 'sea')
    + (undated ? `<p class="note">${undated} battle${undated === 1 ? ' has' : 's have'} `
        + `no date. A save keeps dates only on its most recent battles, so a battle `
        + `is dated here when some save in the folder still remembered it.</p>` : '');

  box.querySelectorAll('th[data-bk]').forEach(th => {
    th.onclick = () => {
      const k = th.dataset.bk;
      if (warBattleSort.key === k) warBattleSort.dir *= -1;
      else warBattleSort = {key: k, dir: k === 'date' || k === 'name' ? 1 : -1};
      drawWarDetail();
    };
  });
  // Click a battle row to open/close its composition detail underneath it.
  // The row's own list ('land' or 'sea') is looked up fresh here rather than
  // trusting a captured closure, since dry/sea are rebuilt every draw.
  box.querySelectorAll('tr.battlerow').forEach(tr => {
    tr.onclick = () => {
      const b = (tr.dataset.bkind === 'sea' ? sea : dry)[+tr.dataset.bi];
      if (expandedBattles.has(b)) expandedBattles.delete(b);
      else expandedBattles.add(b);
      drawWarDetail();
    };
  });
}

if (WARS.length) {
  document.getElementById('warfind').oninput = () => { warPick = null; drawWarTable(); };
} else {
  const tab = document.getElementById('tab-wars');
  if (tab) tab.hidden = true;
}

/* =============== TABS =============== */
const tabs = [...document.querySelectorAll('.tab')];
function selectTab(id) {
  tabs.forEach(t => {
    const on = t.id === id;
    t.setAttribute('aria-selected', on);
    document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
  });
}
tabs.forEach((t, i) => {
  t.onclick = () => selectTab(t.id);
  t.onkeydown = e => {
    const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const next = tabs[(i + d + tabs.length) % tabs.length];
    next.focus(); selectTab(next.id);
  };
});

document.getElementById('lastdate').textContent = DATA.lastDate;
goodsPicker.set(topMovers(6));
drawChart(); drawLedger();
drawMilPies(); drawMilTable(); drawTechTable();
drawFleetChart(); drawFleetTable(); drawNavy();
drawPopTable(); drawCultureTable(); drawPopChart();
searchSelect(document.getElementById('cultagsel'), 'search nations');
searchSelect(document.getElementById('poptag'), 'search nations');
drawMarketTable();
if (TECH) drawTechTree();
if (WARS.length) drawWarTable();
searchSelect(document.getElementById('techtag'), 'search nations');
if (MAP) mapRender();
drawGreatPowers();
</script>
</body>
</html>
"""
