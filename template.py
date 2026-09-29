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
  /* Tells the browser this page is dark, so the parts it draws itself -- the
     open list under a <select>, its scrollbar, the focus ring -- come out dark
     too instead of on a white ground this page's pale ink cannot be read on. */
  color-scheme:dark;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{
  background:var(--ground-deep);color:var(--ink);
  font-family:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif;
  font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased;
}
/* The column was 1180px, chosen when the widest thing on it was a paragraph.
   Most of what is on it now is a table with twenty columns, a chart, or a
   world map, so it takes the window instead: 96vw fills a 1080p screen and
   still fits a laptop, since a max-width only ever gives room back. The cap
   is for the very wide screen, where 96vw would be a wall of text. */
.sheet{
  max-width:min(1800px,96vw);margin:0 auto;padding:var(--sheet-pad);
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
/* Compact controls belong to the plot frame, leaving the data unobstructed. */
.chart-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:10px 12px;
  border-bottom:1px solid var(--grid)}
.chart-toolbar select,.chart-toolbar button,.chart-toolbar input[type=search]{font-size:12px;padding:6px 8px}
.chart-toolbar select{max-width:220px;min-width:0}
.chart-toolbar .metric-browser{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.metric-browser [hidden]{display:none}
.chart-toolbar .export-controls{margin:0 0 0 auto;gap:8px}
.chart-toolbar .export-controls .note{margin:0;font-size:11px}
.chart-toolbar .export-controls .note:empty{display:none}
.chart-toolbar .picker-toggle{min-width:0}
.table-frame{border:1px solid var(--rule);background:rgba(42,15,23,.62)}
.table-frame .tablewrap{border:0;margin:0;box-shadow:none;background:none}
.table-frame .chart-toolbar:only-child{border-bottom:0}
.table-frame .note{margin:0;padding:9px 12px;border-top:1px solid var(--grid)}
.chart-toolbar .selsearch{max-width:160px}

.chart-toolbar .toolbar-group{display:inline-flex;align-items:center;gap:6px}
.chart-toolbar .toolbar-group>label{font-size:11px;color:var(--ink-dim)}
.chart-toolbar [hidden]{display:none}
.map-toolbar #mapstep{flex:1 1 110px;min-width:90px;max-width:200px}
.map-options #mapspeed{width:60px}
.map-options #mapspeedout{font-size:11px}
.head-toolbar .picker-toggle{max-width:190px}
#millegend{padding:10px 12px;margin:0;border-top:1px solid var(--grid)}
#millegend:empty{display:none}
@media(max-width:700px){
  .chart-toolbar .metric-browser{flex-basis:100%}
  .chart-toolbar select{max-width:180px}
}
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-bottom:14px}
select,button,input[type=search]{
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:13px;
  /* A solid colour under the gradient. The list a <select> opens is drawn by
     the browser, which cannot use a gradient and falls back to a flat colour;
     without one named here that is the platform's, and this page's near-white
     ink lands on a near-white ground. */
  background-color:#431B26;
  background-image:linear-gradient(180deg,var(--panel),#431B26);
  color:var(--ink);
  border:1px solid var(--rule);border-radius:0;padding:7px 11px;
}
/* And the rows in that list, named at both ends for the same reason. */
option{background-color:var(--ground-deep);color:var(--ink)}
option:checked{background-color:var(--brass);color:var(--ground-deep)}
option:disabled{color:var(--ink-dim)}
select,button{cursor:pointer}
select:focus-visible,button:focus-visible,input:focus-visible{
  outline:2px solid var(--brass);outline-offset:2px}
.controls > button[aria-pressed="true"],.chart-toolbar > button[aria-pressed="true"]{
  background:linear-gradient(180deg,var(--gilt-hi),var(--brass));
  color:#3A1420;border-color:var(--gilt-hi);font-weight:500}
/* A control that cannot be used has to look like it, and the pressed styling
   above must not outrank that -- a button left switched on and then disabled
   otherwise sat there in full brass looking like it was still doing something. */
.controls > button:disabled,
.controls > button[aria-pressed="true"]:disabled,.chart-toolbar > button:disabled{
  background:none;color:var(--ink-dim);border-color:var(--rule);
  font-weight:400;cursor:not-allowed;opacity:.55}

/* A slider the same weight as the buttons beside it: a brass thumb on a thin
   rule, rather than whatever the platform draws. */
.timeline{
  -webkit-appearance:none;appearance:none;background:transparent;
  width:180px;height:22px;cursor:pointer;padding:0;margin:0;
}
.timeline.narrow{width:84px}
.timeline:focus-visible{outline:2px solid var(--brass);outline-offset:2px}
.timeline::-webkit-slider-runnable-track{
  height:3px;background:var(--grid);border:1px solid var(--rule);border-width:0 0 0 0}
.timeline::-moz-range-track{height:3px;background:var(--grid)}
.timeline::-webkit-slider-thumb{
  -webkit-appearance:none;appearance:none;width:11px;height:17px;margin-top:-8px;
  background:linear-gradient(180deg,var(--gilt-hi),var(--brass));
  border:1px solid var(--ground-deep)}
.timeline::-moz-range-thumb{
  width:11px;height:17px;border-radius:0;
  background:linear-gradient(180deg,var(--gilt-hi),var(--brass));
  border:1px solid var(--ground-deep)}

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
/* Controls float over the atlas; the canvas alone owns pan and zoom. */
.world-atlas{position:relative;isolation:isolate}
.world-atlas .mapwrap{min-height:660px;border:0}
.map-overlay{position:absolute;z-index:2;background:rgba(30,15,23,.78);border:1px solid rgba(183,155,110,.65);
  box-shadow:0 3px 14px rgba(0,0,0,.22);backdrop-filter:blur(5px)}
.map-caption{top:14px;left:14px;max-width:calc(100% - 360px);padding:10px 12px;pointer-events:none}
.map-caption h2{font-size:14px;margin:0;padding:0;border:0}
.map-caption #mapworld{display:block;font-size:10px;letter-spacing:.04em;margin-top:4px}
.map-console{left:14px;bottom:14px;width:min(620px,calc(100% - 360px))}
.map-overlay>summary{padding:9px 12px;color:var(--brass);cursor:pointer;font-size:13px}
.map-console .chart-toolbar{border:0;padding:8px 12px}
.map-console #mapstep{flex:1;min-width:70px;max-width:none}
.map-console .export-controls{margin:0 0 0 auto}
.map-console .map-options{border-top:1px solid var(--grid);border-bottom:0}
.map-console .map-options .note{font-size:11px;margin:6px 0}
.map-inspection{position:absolute;z-index:2;left:14px;top:86px;max-width:min(580px,calc(100% - 360px))}
.map-inspection>summary{width:fit-content;background:rgba(30,15,23,.78);padding:5px 9px;font-size:11px;cursor:pointer;color:var(--ink-dim)}
.map-inspection .readout{background:rgba(30,15,23,.86);max-height:220px;overflow:auto;font-size:11px}
.gpstrip{right:14px;top:14px;width:304px;max-height:calc(100% - 28px);overflow:auto}
.gpstrip[hidden]{display:none}
.gpstrip>summary{font-family:'Playfair Display',Georgia,serif;font-size:17px}
.gpstrip[open]>summary{padding-bottom:4px}
.gpbody{padding:0 12px 8px}
.gplabel{font-size:10px;color:var(--ink-dim);margin-bottom:8px}
.gpgrid{display:grid;gap:0}
.gpcard{padding:5px 0;border-top:1px solid var(--grid);min-width:0}
.gpidentity{line-height:20px;display:flex;align-items:center;gap:8px;border-left:3px solid var(--nation-colour);padding-left:7px}
.gprank{color:var(--brass);font-size:18px;font-family:'Playfair Display',Georgia,serif;min-width:15px}
.gpflag{width:27px;height:18px;flex:none;object-fit:fill}
.gpname{font-family:'IBM Plex Sans',system-ui,sans-serif;font-size:13px;font-weight:600;min-width:0;text-align:left;border:0;background:none;padding:0;color:var(--ink)}
.gpname:hover{color:var(--brass);text-decoration:underline}
.gpstats{display:grid;grid-template-columns:1fr 1fr;gap:2px 12px;margin:4px 0 0 10px;font-size:11px;line-height:14px}
.gpstats span{display:flex;justify-content:space-between;gap:5px;color:var(--ink-dim)}
.gpstats b{color:var(--ink);font-weight:500;font-family:'IBM Plex Mono',monospace}
.map-options{border-bottom:1px solid var(--grid);padding:7px 12px;font-size:12px;color:var(--ink-dim)}
.map-options summary{cursor:pointer;width:fit-content}
.map-options .chart-toolbar{border:0;padding:10px 0 3px}
@media(max-width:900px){
  .gpstrip{width:264px}
  .gpstats{font-size:10px;gap:2px 8px;margin-left:0}
  .map-caption{max-width:calc(100% - 310px)}
  .map-console{width:calc(100% - 310px)}
  .map-inspection{max-width:calc(100% - 310px)}
}
@media(max-width:600px){
  .world-atlas .mapwrap{min-height:850px}
  .map-caption{top:8px;left:8px;max-width:calc(100% - 16px)}
  .map-caption #mapworld{display:none}
  .gpstrip{top:55px;right:8px;width:244px;max-height:610px}
  .map-console{left:8px;bottom:8px;width:calc(100% - 16px)}
  .map-inspection{top:55px;left:8px;max-width:calc(100% - 16px)}
  .map-inspection[open]{z-index:3}
}
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
/* Several nations on one tile ran as one long wrapping sentence, which put
   Austria's brigade count under Spain's composition and left the widest column
   of the readout empty. One row a nation, and the numbers line up down the
   page where they can be compared. */
.readout .natgrid{
  display:grid;grid-template-columns:auto auto auto auto minmax(0,1fr);
  gap:3px 16px;width:100%;align-items:baseline;margin-top:2px;
}
.readout .natgrid .num{text-align:right;font-variant-numeric:tabular-nums}
.readout .natgrid .mix{color:var(--ink-dim);overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap}
.readout .sidehead{width:100%;margin-top:5px;
  border-top:1px solid var(--rule);padding-top:5px}
.readout .sidehead:first-of-type{border-top:0;margin-top:0}
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
/* A picked war opens the way an encyclopedia sets one out: an infobox with
   the name in a box at the top, the flags of the principal belligerents
   under it where the picture would go, the facts a reader looks for first in
   labelled rows, and then each side in a column of its own -- who fought, who
   led them, what they had and what they lost. The goals and the battles sit
   beside it, where the article would be.

   Defenders on the left and attackers on the right, the same way round as
   the battle tables beside it, so a reader never has to swap sides between
   the two.

   Side by side only where the battle table beside the box still has room for
   its eight columns -- about 800px. On a narrower screen the box stands on its
   own and the tables run the full width beneath it. */
.warlayout{display:grid;grid-template-columns:minmax(0,1fr);gap:24px 30px;
  align-items:start}
.ib{max-width:680px}
@media(min-width:1600px){
  .warlayout{grid-template-columns:minmax(0,620px) minmax(0,1fr)}
  .ib{max-width:none}
}
.warmain{min-width:0}
.ib{border:1px solid var(--rule);background:rgba(42,15,23,.62);
  box-shadow:0 0 0 1px rgba(124,94,34,.35) inset;font-size:13px;line-height:1.4}
.ib .rk{color:var(--ink-dim)}
#popcountrydetail .controls[hidden],.popatlas[hidden]{display:none}
.popatlas{display:block;width:100%;height:auto;cursor:pointer}
.popcountrylayout{align-items:start;display:grid;grid-template-columns:minmax(260px,1fr) minmax(0,2fr);gap:24px;margin-bottom:28px}
.popcountrylayout .ib{max-width:none}
#popcountryfacts section{padding:0 16px 16px;margin:0}
.popscope{text-align:center;padding:10px;color:var(--gold);font-size:18px}
.poppie{display:grid;grid-template-columns:minmax(130px,1fr) minmax(110px,1fr);gap:8px;align-items:center}
.poppie svg{width:100%;max-height:240px}
.poppielegend{max-height:220px;overflow:auto;display:flex;flex-direction:column;gap:3px}
.poppiekey{display:flex;align-items:center;text-align:left;border:0;padding:3px;background:transparent;font-size:11px}
.poppiekey i{width:10px;height:10px;flex-shrink:0;margin-right:7px}
.poppiehint{grid-column:1/-1;min-height:36px;font-size:12px;color:#e8d3ae}
#popfind{max-width:210px}
@media(max-width:760px){.popcountrylayout{grid-template-columns:1fr}}
.wartheatre{margin:0;border:0;border-bottom:1px solid var(--rule)}
.wartheatre canvas{display:block;width:100%;height:auto}
.wartheatre figcaption{padding:8px 12px;font-size:11px;line-height:1.5;color:var(--ink-dim)}
.war-export{display:inline-flex;vertical-align:middle;margin-left:10px;padding:5px;border:0;background:none;color:var(--brass)}
.war-export svg{width:18px;height:18px}
.war-export-status{display:block;font:11px sans-serif;letter-spacing:0;margin-top:5px}
.war-export-status:empty{display:none}
.ibtitle{background:rgba(8,25,44,.86);border-bottom:1px solid var(--rule);
  padding:13px 16px 12px;text-align:center;
  font-family:'Playfair Display',Georgia,serif;font-size:21px;font-weight:600;
  line-height:1.2;color:var(--brass);text-shadow:0 1px 0 rgba(0,0,0,.5);
  overflow-wrap:anywhere}
/* The picture slot: the principal belligerents' flags, large, facing each
   other across a "v". */
.ibbanner{display:flex;align-items:center;gap:14px;padding:16px 14px 15px;
  border-bottom:1px solid var(--grid);
  background:radial-gradient(80% 130% at 50% 0%,rgba(231,196,100,.09),transparent 70%)}
.ibflags{flex:1;min-width:0;display:flex;gap:8px;align-items:center}
.ibflags.left{justify-content:flex-end}
.ibvs{flex:none;font-family:'Playfair Display',Georgia,serif;font-style:italic;
  font-size:19px;color:var(--ink-dim)}
.ibmore{flex:none;font-family:'IBM Plex Mono',ui-monospace,monospace;
  font-size:12px;color:var(--ink-dim)}
.ibflag{flex:none;display:block;width:21px;height:14px;object-fit:fill;
  border:1px solid rgba(0,0,0,.6);box-shadow:0 1px 2px rgba(0,0,0,.35)}
.ibflag.big{width:36px;height:24px}
/* Four great powers on one side shrink to fit their half rather than wrap and
   leave the war leader alone on a second row. */
.ibflag.hero{flex:0 1 60px;width:60px;min-width:0;height:auto;aspect-ratio:3/2}
/* No flag to fly -- a mod with no game beneath it has almost none -- so the
   nation's own colour stands in for the cloth, with its tag on the larger
   ones so it still says whose. */
.ibflag.blank{display:flex;align-items:center;justify-content:center;
  background-image:linear-gradient(180deg,rgba(255,255,255,.18),rgba(0,0,0,.16));
  font:600 9.5px/1 'IBM Plex Mono',ui-monospace,monospace;letter-spacing:.03em;
  color:#2A0F17}
.ibflag.hero.blank{font-size:13px}
.ibfacts{display:grid;grid-template-columns:max-content minmax(0,1fr);
  gap:8px 16px;margin:0;padding:13px 16px 14px}
.ibfacts dt{font-family:'Barlow Condensed','Arial Narrow',sans-serif;
  font-size:12.5px;text-transform:uppercase;letter-spacing:.12em;
  color:var(--ink-dim);padding-top:1px}
.ibfacts dd{margin:0;min-width:0}
.ibfacts ul{margin:0;padding-left:16px}
.ibfacts li{margin:2px 0}
.ibfacts .tagflag{vertical-align:-2px}
.ibband{background:rgba(8,25,44,.86);border-top:1px solid var(--rule);
  border-bottom:1px solid var(--rule);padding:5px 10px;text-align:center;
  font-family:'Playfair Display',Georgia,serif;font-size:12px;font-weight:600;
  text-transform:uppercase;letter-spacing:.16em;color:var(--brass)}
.ibcaption{padding:8px 14px 0;font-size:11.5px;color:var(--ink-dim);
  text-align:center}
.ibcols{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.ibcol{padding:10px 14px 12px;min-width:0}
.ibcol+.ibcol{border-left:1px solid var(--grid)}
.ibside,.ibgroup{font-family:'Barlow Condensed','Arial Narrow',sans-serif;
  text-transform:uppercase;color:var(--ink-dim)}
.ibside{font-size:12px;letter-spacing:.16em;margin-bottom:6px}
/* Which side a column is, said again under every band once the columns are
   stacked and left and right no longer say it. */
.ibside.stacked{display:none}
.ibgroup{font-size:11px;letter-spacing:.14em;margin:9px 0 4px;padding-top:7px;
  border-top:1px dotted rgba(231,196,100,.25)}
.ibnat{display:flex;align-items:center;gap:8px;padding:3px 0;min-width:0}
.ibnat.major{padding:5px 0 6px}
.ibnat b{font-weight:500}
.ibnat.major b{font-family:'Playfair Display',Georgia,serif;font-size:15.5px;
  font-weight:600;line-height:1.2}
/* A name gives way down to its longest word and no further; below that it is
   the date beside it that wraps. Breaking a name anywhere stood "Algeria" one
   letter to a line on a phone. */
.ibwho{flex:1 1 auto;min-width:min-content;overflow-wrap:break-word}
.ibmeta{display:block;font-size:11.5px;color:var(--ink-dim);line-height:1.3;
  margin-top:1px}
.ibaside{flex:0 1 auto;font-size:11.5px;color:var(--ink-dim);text-align:right}
.ibnum{flex:none;margin-left:auto;padding-left:8px;
  font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:12px;
  white-space:nowrap;font-variant-numeric:tabular-nums}
.ibnum small{font-size:11px;color:var(--ink-dim)}
.ibhead{display:flex;justify-content:flex-end;gap:0;font-size:10.5px;
  font-family:'Barlow Condensed','Arial Narrow',sans-serif;
  text-transform:uppercase;letter-spacing:.12em;color:var(--ink-dim)}
.ibhead span,.ibnum.pair span{display:inline-block;min-width:52px;text-align:right}
.ibtotal{display:flex;gap:8px;margin-top:6px;padding-top:6px;
  border-top:1px solid var(--grid);font-weight:500}
.ibtotal .ibnum{font-weight:500;color:var(--brass)}
.ib details>summary{cursor:pointer;list-style:none;color:var(--ink-dim);
  font-size:12px;padding:4px 0 1px}
.ib details>summary::-webkit-details-marker{display:none}
.ib details>summary:hover{color:var(--ink)}
.ib details[open]>summary{display:none}
.ibnote{border-top:1px solid var(--grid);padding:9px 16px 11px;
  font-size:11.5px;line-height:1.45;color:var(--ink-dim)}
.ibnote p{margin:0}
.ibnote p+p{margin-top:4px}
@media(max-width:560px){
  .ibcols{grid-template-columns:minmax(0,1fr)}
  .ibcol+.ibcol{border-left:0;border-top:1px solid var(--grid)}
  .ibside.stacked{display:block}
  .ibfacts{grid-template-columns:minmax(0,1fr);gap:2px 0}
  .ibfacts dd{margin-bottom:8px}
}
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
/* A note explains the figure above it, so it is set to the same width. It had
   a reading measure of its own for a while, which only made it look like the
   text had been cut short of the chart it belongs to -- a paragraph ending
   half a screen inside the frame above it reads as a mistake, and the long
   line is the smaller cost. */
.note{color:var(--ink-dim);font-size:13px;margin:10px 2px 0}
.stackwrap{display:flex;flex-wrap:wrap;gap:7px;margin-top:11px}
.slegend{font-family:'IBM Plex Mono',ui-monospace,monospace;font-size:11.5px;
  color:var(--ink-dim);display:flex;align-items:center;gap:6px}
#popchart rect[data-pop-type]{cursor:pointer}
#popchart rect[data-pop-type]:hover,#popchart rect[data-pop-type]:focus-visible{fill-opacity:1;stroke:var(--brass);stroke-width:1.5}
.slegend i{width:9px;height:9px;display:block}
footer{color:var(--ink-dim);font-size:12.5px;border-top:1px solid var(--rule);
  padding-top:14px;margin-top:8px}
/* Strength returns: one compact ledger with details on demand. */
.segments{display:inline-flex;gap:0;flex-wrap:wrap}
.segments button{border-radius:0;margin:0}
.segments button[aria-pressed="true"]{background:var(--brass);color:var(--ground-deep);box-shadow:inset 0 -3px 0 var(--gilt-lo)}
.ledger-heading{display:flex;align-items:center;justify-content:space-between;gap:18px}
.ledger-heading h2{border:0;margin:0;padding:0}
.ledger-heading .tb-label{margin:0 0 5px}
.ledger-toolbar{padding:14px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule)}
.strength-ledger{width:100%;font-variant-numeric:tabular-nums}
.strength-ledger th button{border:0;background:transparent;color:var(--ink-dim);padding:5px 0}
.strength-ledger th[aria-sort="ascending"] button::after{content:" ↑"}
.strength-ledger th[aria-sort="descending"] button::after{content:" ↓"}
.strength-ledger td:first-child,.strength-ledger th:first-child{text-align:left}
.strength-ledger .nation-toggle{text-align:left;background:transparent;border:0;color:var(--ink);padding:6px 0;white-space:normal}
.strength-ledger .nation-toggle[aria-expanded="true"]{color:var(--brass)}
.strength-ledger .return-details>td{text-align:left;white-space:normal;background:rgba(0,0,0,.15);padding:18px}
.return-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:24px}
.return-grid h3{margin:0 0 10px;color:var(--brass);font-size:14px}
.return-grid dl{margin:0}.return-grid dl>div{display:flex;justify-content:space-between;gap:16px;border-bottom:1px solid var(--grid);padding:5px 0}
.return-grid dd{margin:0;font-family:'IBM Plex Mono',monospace}.return-grid dt{color:var(--ink-dim)}
.return-details[hidden],[id^="compare-"][hidden]{display:none}
@media(max-width:650px){.ledger-heading{align-items:flex-start;flex-direction:column}.strength-ledger{min-width:650px}}
.military-ledger-wrap{max-height:none}
.tablewrap>table.strength-ledger{min-width:650px;table-layout:fixed}
.strength-ledger>thead>tr>th:first-child{width:34%}
.strength-ledger>thead>tr>th{white-space:normal}
.strength-ledger>thead>tr>th button{white-space:normal}
/* Country dossiers share the infobox vocabulary of Population and Wars. */
.strength-ledger .strength-row{cursor:pointer}
.strength-ledger .strength-row:hover{background:rgba(231,196,100,.09)}
.strength-ledger .strength-row:has([aria-expanded="true"]){background:rgba(231,196,100,.12)}
.strength-ledger .nation-toggle{display:inline-flex;align-items:center;gap:10px;font-size:14px}
.military-flag{width:30px;height:20px;object-fit:fill;box-shadow:0 0 0 1px rgba(0,0,0,.5);flex:none}
.military-flag.blank{display:inline-block;border:1px solid var(--rule)}
.military-dossier{display:grid;grid-template-columns:minmax(240px,1fr) minmax(0,2fr);gap:20px;align-items:start}
.military-dossier .ib{max-width:none;min-width:0}
.military-identity{padding:22px 16px;text-align:center;border-bottom:1px solid var(--rule);background:rgba(8,25,44,.35)}
.military-identity .military-flag{width:90px;height:60px;margin-bottom:12px}
.military-number{font-family:'Barlow Condensed',sans-serif;font-size:46px;line-height:1.2;color:var(--brass)}
.military-identity .tb-label{margin:5px 0 0}
.military-facts{padding:16px}.military-facts .return-grid{display:block}
.military-main{min-width:0}.military-main .ibtitle{text-align:left;font-size:18px}
.military-rivals{margin-bottom:20px}.military-rivals .controls{padding:12px 14px;margin:0}
.military-rivals .note{padding:0 14px 12px;margin:0}
.strength-ledger .rival-table{width:100%;min-width:0;table-layout:auto;font-size:12px}
.strength-ledger .rival-table td,.strength-ledger .rival-table th{padding:10px;text-align:right;white-space:nowrap}
.strength-ledger .rival-table td:first-child,.strength-ledger .rival-table th:first-child{text-align:left}
.rival-name{white-space:normal;display:flex;align-items:center;gap:8px}.rival-name .military-flag{width:24px;height:16px}
.military-rivals .tablewrap{max-height:none;border:0;margin-bottom:12px}
.military-menu{padding:14px}.military-menu .segments{margin-bottom:16px}
.military-menu .return-grid{grid-template-columns:1fr}
.military-menu .note{margin-bottom:0}
@media(max-width:1000px){.military-dossier{grid-template-columns:1fr}.military-identity{padding:12px}.military-identity .military-flag{width:60px;height:40px}}
#military-browse[hidden],#military-country[hidden]{display:none}
#miloverview.country-open>.ledger-heading,#miloverview.country-open>.note,#miloverview.country-open>.ledger-toolbar .picker{display:none}
.military-country-header{display:flex;align-items:center;gap:14px;margin-bottom:18px;flex-wrap:wrap}
.military-country-header h2{margin:0;padding:0;border:0;font-size:23px;letter-spacing:.03em;text-transform:none}
.military-country-header .military-flag{width:42px;height:28px}
.military-country-header .note{margin-left:auto}
.military-strength-strip{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));border:1px solid var(--rule);background:rgba(8,25,44,.65);margin-bottom:20px}
.military-strength-strip>div{padding:14px 18px;border-right:1px solid var(--grid)}
.military-strength-strip>div:last-child{border:0}
.military-stat{font:32px 'Barlow Condensed',sans-serif;color:var(--brass)}
.military-country-body{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:20px;align-items:start;margin-bottom:20px}
.military-country-page .ib{max-width:none}
.military-country-page .ibtitle{text-align:left;font-size:17px}
.military-capacity-content{padding:14px}
.military-capacity .return-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
.military-capacity .return-grid dl>div{align-items:baseline;gap:10px}
.military-capacity .return-grid dd{flex:none}
.military-capacity .return-grid>div:only-child{grid-column:1/-1}
.military-capacity .note:empty{display:none}
.military-inventory .tablewrap{border:0;max-height:none;margin:0}
.military-inventory th:first-child,.military-inventory td:first-child{text-align:left}
.military-rivals .rival-table{min-width:0;width:100%}
.military-help{font-size:12px;color:var(--ink-dim);padding:10px 14px}
.military-help summary{cursor:pointer}.military-help p{margin-bottom:0}
.military-delta{display:block;font-size:10px;color:var(--ink-dim);font-weight:normal}
@media(max-width:900px){.military-country-body{grid-template-columns:1fr}.military-strength-strip{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:550px){.military-capacity .return-grid{grid-template-columns:1fr}.military-strength-strip{grid-template-columns:repeat(2,minmax(0,1fr))}.military-country-header h2{font-size:19px}}
.military-forces-column{display:flex;flex-direction:column;gap:20px;min-width:0}
.military-forces-column .military-rivals{margin-bottom:0}
.military-forces-column .rival-table{font-size:11px}
.military-forces-column .rival-table td,.military-forces-column .rival-table th{padding:8px 6px}
.military-forces-column .rival-table button{font-size:11px;padding:5px 7px}
.military-forces-column .military-delta{white-space:normal}
.military-composition-history{margin-top:6px}
.nation-identity{display:inline-flex;align-items:center;gap:10px;text-align:left}
#poptable .nation-identity{font-size:14px}
#poptable th:nth-child(2),#poptable td:nth-child(2){text-align:left}
#popcountryfacts .ibtitle .military-flag{width:42px;height:28px}
#popcountryfacts .ibtitle .nation-identity{justify-content:center}
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
    <button class="tab" role="tab" id="tab-nations" aria-controls="panel-nations" aria-selected="true">World</button>
    <button class="tab" role="tab" id="tab-compare" aria-controls="panel-compare" aria-selected="false">Compare</button>
    <button class="tab" role="tab" id="tab-pops" aria-controls="panel-pops" aria-selected="false">Population</button>
    <button class="tab" role="tab" id="tab-military" aria-controls="panel-military" aria-selected="false">Military</button>
    <button class="tab" role="tab" id="tab-wars" aria-controls="panel-wars" aria-selected="false">Wars</button>
    <button class="tab" role="tab" id="tab-tech" aria-controls="panel-tech" aria-selected="false">Technology</button>
    <button class="tab" role="tab" id="tab-market" aria-controls="panel-market" aria-selected="false">Market</button>
  </div>

  <!-- ============ NATIONS ============ -->
  <div role="tabpanel" id="panel-nations" aria-labelledby="tab-nations">
    <section>
      <figure class="world-atlas">
        <div class="mapwrap"><canvas id="mapcanvas" role="img"
             aria-label="Political map with army positions"></canvas></div>
        <div class="map-caption map-overlay">
          <h2>World at <span id="mapdate"></span><span id="mapworld" class="rk"></span></h2>
        </div>
        <details class="map-inspection">
          <summary>Map readout</summary>
          <div class="readout" id="mapreadout"></div>
        </details>
        <details class="gpstrip map-overlay" id="gpstrip" open hidden>
          <summary>Great Powers</summary>
          <div class="gpbody">
            <div class="gplabel">In-game rank · colours match the map</div>
            <div class="gpgrid" id="gpgrid" role="list" aria-label="Great powers in rank order"></div>
          </div>
        </details>
        <details class="map-console map-overlay" open>
          <summary>Playback &amp; map controls</summary>
          <div class="chart-toolbar map-toolbar" role="group" aria-label="World date and playback">
            <select id="mapsave" aria-label="Save" title="Save"></select>
            <button id="mapplay" aria-pressed="false" title="Play through the campaign saves">Play</button>
            <input type="range" id="mapstep" class="timeline" min="0" step="1" value="0"
                   aria-label="Move through the campaign save by save">
          </div>
          <details class="map-options">
            <summary>Map options</summary>
            <div class="chart-toolbar" role="group" aria-label="Map display and playback settings">
              <span class="toolbar-group"><label for="mapspeed">Speed</label>
                <input type="range" id="mapspeed" class="timeline narrow" min="0" max="8" step="1" value="3" title="Playback speed">
                <span class="rk" id="mapspeedout"></span></span>
              <button id="mapocc" aria-pressed="true" title="Hatch occupied land in the occupier's colour">Occupation</button>
              <button id="mapborders" aria-pressed="false">Province borders</button>
              <button id="mapreset" title="Back to the whole world">Reset</button>
              <span class="rk" id="mapzoom">1.0&times;</span>
              <span id="pick-map"></span>
            </div>
            <p class="note">Scroll to zoom; drag to pan. Open Map readout for land and army details; click an army to pin them.</p>
          </details>
        </details>
      </figure>
    </section>
  </div>

  <!-- ============ COMPARE ============ -->
  <div role="tabpanel" id="panel-compare" aria-labelledby="tab-compare" hidden>
    <div class="controls segments" role="group" aria-label="Comparison view">
      <button id="compare-trends-button" aria-pressed="true" aria-controls="compare-trends">Trends</button>
      <button id="compare-head-button" aria-pressed="false" aria-controls="compare-head">Head-to-head</button>
    </div>
    <div id="compare-trends">
    <section>
      <h2 id="chart-title">Population over time</h2>
      <figure>
        <div class="chart-toolbar" role="group" aria-label="Graph controls">
          <div class="metric-browser">
            <select id="metric-category" aria-label="Category" title="Category"></select>
            <select id="metric-family" aria-label="Measure" aria-describedby="metric-description" title="Measure"></select>
            <span id="metric-variant"><select id="metric" aria-label="View" title="View"></select></span>
            <span id="ship-variant" hidden><select id="shiptype" aria-label="Hull" title="Hull"></select></span>
          </div>
          <span id="pick-nations"></span>
          <button id="scale" aria-pressed="false" title="Switch between linear and logarithmic vertical scale">Linear</button>
          <button id="worldline" aria-pressed="false" title="Add the world population as a separate line">World</button>
          <span id="metric-description" hidden></span>
        </div>
        <svg id="chart" viewBox="0 0 1000 460" role="img" aria-label="Metric plotted over time by nation"></svg>
        <div class="readout" id="readout"></div>
      </figure>
      <p class="note" id="fleetspan" hidden></p>
      <p class="note" id="ratenote" hidden></p>
      <p class="note" id="succnote"></p>
    </section>


    </div>
    <div id="compare-head" hidden>
      <h2>Head to head at <span id="mildate"></span></h2>
      <figure>
      <div class="chart-toolbar head-toolbar" role="group" aria-label="Head-to-head controls">
        <select id="milsave" aria-label="Save" title="Save"></select>
        <div class="segments" role="group" aria-label="Head-to-head branch"><button id="head-army" aria-pressed="true">Army</button><button id="head-navy" aria-pressed="false">Navy</button></div>
        <button id="milmob" aria-pressed="false" title="Show each side's full potential -- everything its soldier pops could raise, plus everything its mobilization ceiling could add on top -- instead of just its brigades right now. Army only.">Current</button>

        <span class="toolbar-group" role="group" aria-label="Left side"><label>Left</label><span id="pick-milA"></span></span>
        <span class="toolbar-group" role="group" aria-label="Right side"><label>Right</label><span id="pick-milB"></span></span>
        <button id="milswap" title="Swap the two sides">Swap</button>
        <button id="milview" aria-pressed="false" title="Totals compares the two sides as one pie; composition breaks each side down by unit type">Totals</button>
      </div>
        <svg id="milpies" viewBox="0 0 1000 400" role="img" aria-label="Force composition compared between two nations"></svg>
        <div class="readout" id="milreadout"></div>
        <div class="stackwrap" id="millegend"></div>
      </figure>
      <p class="note">Pick nations for each side. Switch Army/Navy and Totals/Composition; hover a slice to compare counts. Potential includes unbuilt and mobilizable brigades.</p>
      <p class="note">Fleet power shows full-strength and current-strength estimates.</p>
    </div>

  </div>

  <!-- ============ MILITARY ============ -->
  <div role="tabpanel" id="panel-military" aria-labelledby="tab-military" hidden>
    <section id="miloverview">
      <div class="ledger-heading"><div><p class="tb-label">War Office · strength return</p>
      <h2>Military establishment</h2></div><button id="mil-compare">Head-to-head →</button></div>
      <p class="note">Forces fielded at the selected save. Click a row to open its military dossier, composition, and potential rivals.</p>
      <div class="controls ledger-toolbar">
        <div class="segments" role="group" aria-label="Military branch">
          <button id="overview-army" aria-pressed="true" aria-controls="overview-army-view">Army</button>
          <button id="overview-navy" aria-pressed="false" aria-controls="overview-navy-view">Navy</button>
        </div>
        <label for="fleetsave">Save</label><select id="fleetsave"></select>
        <span id="pick-military"></span>
      </div>
      <div id="military-browse">
      <div id="overview-army-view">
        <div class="tablewrap military-ledger-wrap"><table id="miltable" class="strength-ledger"><thead><tr></tr></thead><tbody></tbody></table></div>
        <p class="note">Counts are brigades, not troop headcounts. Fielded = professional + mobilized. Unbuilt capacity is additional professional recruitment capacity.</p>
      </div>
      <div id="overview-navy-view" hidden>
        <div class="tablewrap military-ledger-wrap"><table id="fleettable" class="strength-ledger"><thead><tr></tr></thead><tbody></tbody></table></div>
        <p class="note">Counts are ships. Heavy hull classification and power estimates require naval unit data. Other hulls include light ships and transports.</p>
      </div>
      </div>
      <div id="military-country" hidden></div>
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
      <p class="note">Choose a nation and save. Click a technology for effects and inventions; search to highlight matching technologies across categories.</p>
    </section>
  </div>


  <!-- ============ WARS ============ -->
  <div role="tabpanel" id="panel-wars" aria-labelledby="tab-wars" hidden>
    <section id="warlist">
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
      <button id="warback" hidden style="margin-bottom:14px">&larr; Back to wars</button>
      <div id="wardetail"></div>
    </section>
  </div>

  <!-- ============ POPULATION ============ -->
  <div role="tabpanel" id="panel-pops" aria-labelledby="tab-pops" hidden>
    <section>
      <h2>Population at <span id="popdate"></span></h2>
      <div class="table-frame">
        <div class="chart-toolbar" role="group" aria-label="Population table controls">
          <select id="popsave" aria-label="Save" title="Save"></select>
          <input id="popfind" type="search" aria-label="Find country" placeholder="Find country or tag" autocomplete="off">
          <select id="popcountry" aria-label="Country" title="Country"><option value="">Choose a country</option></select>
          <button id="popshare" aria-pressed="false" title="Switch between population counts and shares">Counts</button>
          <button id="popback" hidden>&larr; All countries</button>
        </div>
        <div id="popbrowse">
          <div id="poptableview"><div class="tablewrap"><table id="poptable"><thead><tr></tr></thead><tbody></tbody></table></div>
            <p class="note">Click a heading to sort; choose a country for details.</p></div>
        </div>
      </div>
    </section>
    <div id="popcountrydetail" hidden>
      <div class="popcountrylayout">
        <div>
          <div id="popcountryfacts" class="ib"></div>
        </div>
        <div>
          <figure>
            <div class="chart-toolbar" role="group" aria-label="Population map controls"><select id="popregion" aria-label="State" title="State"><option value="">Choose a state</option></select>
              <button id="popallland" aria-pressed="false">All possessions</button></div>
            <canvas id="popcountrymap" class="popatlas" role="img" aria-label="Selected country; click a state for population and literacy"></canvas>
            <div id="popstatefacts" class="readout">Click a state or choose one above.</div></figure>
          <p class="note">Highlighted land belongs to this country at the selected save. State figures cover its owned portion.</p>
        </div>
      </div>
    <div hidden><select id="cultagsel"></select><span id="cultag"></span><table id="cultable"><thead><tr></tr></thead><tbody></tbody></table></div>

    <section>
      <h2>Population evolution · <span id="popscope"></span></h2>
      <div class="controls" hidden>
        <label class="tb-label" for="poptag" style="margin:0">Nation</label>
        <select id="poptag"></select>
      </div>
      <figure>
        <div class="chart-toolbar" role="group" aria-label="Population evolution controls"></div>
        <svg id="popchart" viewBox="0 0 1000 360" role="img" aria-label="Pop sizes by type over time"></svg>
      </figure>
      <div class="stackwrap" id="poplegend"></div>
      <p class="note">Click a colored section of a bar to show only that pop type; click a bar again to restore all types. Hover a bar for its population and share of the selected country or state. State history follows the country’s owned portion at each save. Each bar shows the last save of that year.</p>
    </section>
    </div>
  </div>

  <!-- ============ MARKET ============ -->
  <div role="tabpanel" id="panel-market" aria-labelledby="tab-market" hidden>
    <section>
      <h2>World prices &middot; <span>__PRICESPAN__</span></h2>
      <figure>
      <div class="chart-toolbar" role="group" aria-label="Price chart controls">
        <span id="pick-goods"></span>
        <button id="topmovers">Top movers</button>
        <button id="pscale" aria-pressed="false">Linear</button>
        <button id="pindex" aria-pressed="false" title="Rebase every good to 100 at its first reading so goods at different price levels can be compared">Absolute</button>
      </div>
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
      <p class="note">Choose a save; click a good to plot its price and see its producers below. Click a heading to sort. Unsold shows the share of supply that found no buyer.</p>
    </section>

    <section>
      <h2>Who produces it at <span id="proddate"></span></h2>
      <figure>
      <div class="chart-toolbar" role="group" aria-label="Producer chart controls">
        <select id="prodsave" aria-label="Save" title="Save"></select>
        <select id="prodgood" aria-label="Good" title="Good"></select>
      </div>
        <svg id="prodchart" viewBox="0 0 1000 430" role="img"
             aria-label="Supply of one good by nation"></svg>
        <div class="readout" id="prodreadout"></div>
      </figure>
      <p class="note" id="prodnote"></p>
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
/* The payload is JSON, gzipped, then base64'd, because the uncompressed shape
   of a long campaign is a hundred megabytes of repeated key names and columns
   of similar numbers -- a file nobody can send anybody. Compressed it is about
   a ninth of that, and the page opens faster for it: inflating a megabyte
   costs less than reading nine off a disk and parsing them.

   `DecompressionStream` is asynchronous and there is no synchronous gzip in a
   browser, which is why everything below runs inside one async function rather
   than at the top level. Nothing else about the page changes. */
const PACKED = "__DATA__";

/* Empty in an ordinary report, which carries its own payload. `--split` puts
   the payload in a file beside this one instead and names it here: the page
   then weighs a few hundred kilobytes, the data is fetched as raw gzip with no
   base64 third on top, and the browser inflates it as it arrives. The cost is
   that two files have to travel together and be served, which is why it is not
   the default -- a report is usually something somebody was sent. */
const PACKED_URL = "__DATAURL__";

/* The map's state snapshots, [date, base64 gzip] each, when the payload is in
   this page. Each is compressed already, so they sit beside the payload
   rather than being gzipped a second time inside it; `--split` keeps them in
   the payload file and leaves this empty. */
const STATE_CHUNKS = __STATES__;

async function unpackFrom(url) {
  let res;
  try {
    res = await fetch(url);
  } catch (err) {
    throw new Error('this report keeps its data in ' + url + ' beside it, and '
      + 'a browser will not read that from a plain file path. Put both files '
      + 'on a web server -- GitHub Pages will do -- and open the page from '
      + 'there');
  }
  if (!res.ok) throw new Error('could not read ' + url + ': ' + res.status);
  if (typeof DecompressionStream !== 'function')
    throw new Error('this browser has no DecompressionStream; Chrome 80, '
      + 'Firefox 113, Safari 16.4 or newer will open this file');
  const stream = res.body.pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(stream).text());
}

async function unpack(text) {
  if (typeof DecompressionStream !== 'function')
    throw new Error('this browser has no DecompressionStream; Chrome 80, '
      + 'Firefox 113, Safari 16.4 or newer will open this file');
  const bin = atob(text);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const stream = new Blob([bytes]).stream()
    .pipeThrough(new DecompressionStream('gzip'));
  return JSON.parse(await new Response(stream).text());
}

/* A report is a file somebody was sent, so a failure has to say so on the page
   rather than only in a console the reader will never open. */
function bootNote(text) {
  let box = document.getElementById('bootnote');
  if (!box) {
    box = document.createElement('p');
    box.id = 'bootnote';
    box.className = 'note';
    box.style.cssText = 'margin:1.5rem 2rem;color:var(--ink)';
    document.body.prepend(box);
  }
  box.textContent = text;
  return box;
}

function bootFailed(err) {
  bootNote('This report could not be unpacked: '
    + (err && err.message ? err.message : err) + '.');
  throw err;
}

(async () => {
/* A campaign of a few dozen saves unpacks in well under a tenth of a second and
   should say nothing at all; one autosaved every month for a century takes long
   enough that a page of empty tables needs explaining. Hence the delay: the
   notice only ever appears when there is something to wait for. */
const slow = setTimeout(() => bootNote('Unpacking the campaign\u2026'), 200);
const DATA = PACKED_URL ? await unpackFrom(PACKED_URL) : await unpack(PACKED);
if (STATE_CHUNKS.length && DATA.map) DATA.map.populationStateChunks = STATE_CHUNKS;
// Workers pack self-contained state snapshots. Restore the same records the
// views have always read, with a bounded number of inflaters alive at once.
if (DATA.map && DATA.map.populationStateChunks) {
  const chunks = DATA.map.populationStateChunks;
  const states = DATA.map.populationStates || (DATA.map.populationStates = {});
  for (let at = 0; at < chunks.length; at += 8) {
    const batch = chunks.slice(at, at + 8);
    const decoded = await Promise.all(batch.map(([, text]) => unpack(text)));
    for (let i = 0; i < batch.length; i++) {
      const [words, layouts, nations] = decoded[i];
      const snapshot = Object.create(null);
      for (const [tag, rows] of Object.entries(nations)) {
        const regions = snapshot[tag] = Object.create(null);
        for (const [region, size, literacy, provinces, layout, counts] of rows) {
          const [types, cultures] = layouts[layout];
          regions[words[region]] = [size, literacy,
            Object.fromEntries(types.map((t, j) => [words[t], counts[j]])),
            cultures.map((c, j) => [words[Math.floor(c / 2)], counts[types.length + j], !!(c % 2)]),
            provinces];
        }
      }
      states[batch[i][0]] = snapshot;
    }
  }
  delete DATA.map.populationStateChunks;
}
clearTimeout(slow);
const said = document.getElementById('bootnote');
if (said) said.remove();

/* `facts` and `series` are the same numbers in two orientations: series is
   by nation then measure then date, facts is by date then nation then
   measure. Charts want the first, tables want the second, and shipping both
   whole meant saying everything twice -- two megabytes of an eleven megabyte
   payload, a seventh of the finished file. Only what series cannot supply
   travels now, and the rest is put back here, which takes a few milliseconds
   on a century of monthly saves.

   Only the measures `factKeys` names, which are the ones that were taken
   out. `series` holds a dozen more that facts never carried, and putting
   those in too would hand the tables values they have never had -- harmless
   today, because nothing reads them off a fact, and a silent change in what
   the page shows the first time something does.

   `thin_facts` and `rebuild_facts` in report.py are this same operation,
   kept there so a test can hold the two to being inverses. Change one and
   change the other. */
for (const tag in DATA.series) {
  const metrics = DATA.series[tag];
  for (const key of (DATA.factKeys || [])) {
    const column = metrics[key];
    if (!column) continue;
    for (let i = 0; i < column.length; i++) {
      const value = column[i];
      if (value === null) continue;
      const date = DATA.dates[i];
      const at = DATA.facts[date] || (DATA.facts[date] = {});
      (at[tag] || (at[tag] = {}))[key] = value;
    }
  }
}

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

/* A nation the report does not chart has no place in DATA.tags, and every one
   of them used to fall back to the palette's first colour: Austria, Baden and
   Sweden came out the same gold in one war's list. Most nations in a
   campaign's wars are like that -- gone before its first save -- so the tag
   picks a slot past the palette instead, the same one on every report. */
function tagSlot(t) {
  let h = 0;
  for (const ch of String(t)) h = (h * 31 + ch.charCodeAt(0)) % 9973;
  return C.length + h % 360;
}
const colourFor = t => NATION_INK[t] || seriesColour(tagSlot(t));
/* A save names a culture by its key. The mod's localisation has the name the
   game shows; without a mod folder there is none, so the key stands in, tidied
   the way every other raw key here is. */
const cultureName = c => (DATA.cultureNames || {})[c] || (c || '').replace(/_/g, ' ');
/* Same again for the other bare keys a save writes down -- goods, unit types,
   pop types, technologies, casus belli. The mod's localisation holds the name
   the game shows, so `cattle` reads Livestock in IGoR and Cattle in vanilla;
   with no mod folder there is nothing to look it up in and the key stands in,
   tidied. */
const gameName = k => (DATA.names || {})[k] || (k || '').replace(/_/g, ' ');
// Any list a reader scans for a name has to be in the order of the names it
// shows, not of the keys behind them: IGoR calls `barrels` Tanks and `cattle`
// Livestock, and sorted by key those land under B and C.
const byGameName = (a, b) => gameName(a).localeCompare(gameName(b));
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
  // Every tick the caller gave, gridline and label together. The callers hand
  // over round years spaced far enough apart to read, so there is nothing left
  // here to thin out.
  cfg.xTicks.forEach(({v, label: txt}) => {
    const x = xOf(v);
    axis.appendChild(el('line', {x1: x, x2: x, y1: M.t, y2: H - M.b, class: 'gridline'}));
    const label = el('text', {x, y: H - M.b + 17, 'text-anchor': 'middle'});
    label.textContent = txt;
    axis.appendChild(label);
  });
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
    // A marker on every reading is a row of boxes with a line threaded
    // through it once the saves come monthly, and it says nothing the line has
    // not already said. Only the two ends carry one, which is the one thing
    // the line cannot show on its own: where this nation's run of data starts
    // and where it stops.
    // A series with a single reading has no line, so its one marker is the
    // whole of it; drawing the same box twice would only thicken its edge.
    if (cfg.markers)
      (xy.length > 1 ? [xy[0], xy[xy.length - 1]] : [xy[0]]).forEach(p => svg.appendChild(el('rect', {
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
      if (hit) return [s, hit[1], false];
      // Series that share their dates -- every chart but the cross-campaign
      // one -- want an exact hit and nothing else, so this stays off by
      // default. Two campaigns saved on different days never share an x, and
      // an exact match would show whichever one happens to own the line and
      // hide the other, which is the opposite of a comparison. With `carry`
      // the last reading at or before the line stands in.
      if (!cfg.carry) return null;
      let prev = null;
      for (const p of s.pts) { if (p[0] > at.v) break; prev = p; }
      return prev ? [s, prev[1], true] : null;
    }).filter(Boolean).sort((a, b) => b[1] - a[1])
      .map(([s, v, carried]) => `<span><span class="rk">${s.name}</span> `
        + `<b style="color:${s.colour}"${carried
            ? ' title="its last reading at or before this date"' : ''}>`
        + `${cfg.fmt(v)}${carried ? ' ·' : ''}</b></span>`);
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
  // A column whose text is a localised name still sorts on the key underneath
  // unless it says otherwise, which would put Livestock under C for cattle.
  const sortCol = cols.find(c => c.key === state.key);
  const readSort = sortCol && sortCol.sortBy ? sortCol.sortBy : r => r[state.key];
  [...rows].sort((a, b) => {
    const x = readSort(a), y = readSort(b);
    if (x === undefined) return 1;
    if (y === undefined) return -1;
    return state.dir * (typeof x === 'string' ? x.localeCompare(y) : x - y);
  }).forEach(row => {
    const tr = document.createElement('tr');
    cols.forEach(col => {
      const td = document.createElement('td');
      const v = row[col.key];
      if (col.render) td.appendChild(col.render(row));
      else td.textContent = col.fmt ? col.fmt(v, row) : (v === undefined ? '—' : v);
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
/* Vertical rules at round years, evenly spaced.
   They used to mark the saves themselves, one gridline and one label each,
   which reads as a calendar when a campaign is thirty hand-made saves and as
   a picket fence the moment it is monthly autosaves -- a rule every few
   pixels behind the very lines it is there to help read. Years do not care
   how the campaign was saved: the spacing stays even and the count stays
   the same whether the run holds thirty saves or nine hundred.
   The step is the first of the usual round numbers that leaves the labels
   room to breathe, so they never need thinning out afterwards. */
const TICK_STEPS = [1, 2, 5, 10, 20, 25, 50, 100, 200];
function yearTicks(lo, hi) {
  const room = Math.max(2, Math.floor((W - M.l - M.r) / 74));
  const step = TICK_STEPS.find(v => (hi - lo) / v <= room)
            || TICK_STEPS[TICK_STEPS.length - 1];
  const out = [];
  for (let y = Math.ceil(lo / step) * step; y <= hi; y += step)
    out.push({v: y, label: String(y)});
  return out;
}
const saveTicks = yearTicks(xMin, xMax);
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

/* Every country somebody was playing. Each carries `human=yes` in its own
   block of the save, so a multiplayer campaign names all of its players rather
   than only whoever pressed save -- which is what the report used to have to
   assume. A nation counts if it was played at any point in the run: the tags
   worth picking out of a hundred and twenty are the ones a person steered,
   whether or not they were still steering it at the end. */
const PLAYER_TAGS = DATA.tags.filter(t =>
  DATA.dates.some(d => ((DATA.facts[d] || {})[t] || {}).is_player));
const isPlayer = t => PLAYER_TAGS.includes(t);

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
      ...(PLAYER_TAGS.length ? [['Players', () => dateOf
        ? PLAYER_TAGS.filter(t => tagsAt(dateOf()).includes(t)) : PLAYER_TAGS]] : []),
      ['Great powers', () => greatPowersNear(dateOf ? dateOf() : DATA.lastDate)],
      ['Top 8 by pop', () => dateOf ? biggestAt(dateOf(), 'total_pop', 8)
        : [...DATA.tags].sort((a, b) =>
            (DATA.series[b].total_pop[DATA.dates.length - 1] || 0) -
            (DATA.series[a].total_pop[DATA.dates.length - 1] || 0)).slice(0, 8)],
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

/* =============== fleet power ===============
   How much a hull is worth in a fight, after Boltun's reading of the naval
   combat code. Two ships trading fire deal damage in proportion to their own
   gun power and in inverse proportion to the other's hull, and evasion throws
   away a share of the ticks aimed at it -- so asking "who out-damages whom"
   and moving each ship's terms to its own side of the comparison leaves

       power = gun power x hull / (1 - evasion)

   which is a number that can be added up over a fleet and compared. Torpedoes
   count only against a big ship, so they are a second power level rather than
   part of the first. The stats are the mod's own, upgraded by the inventions
   each nation actually rolled; without a mod folder there are no unit files
   and the whole measure is unavailable. */
const NAVAL = DATA.naval || null;
const navalStats = (tag, date) => {
  if (!NAVAL) return null;
  const idx = (NAVAL.of[tag] || {})[date];
  return idx === undefined ? null : NAVAL.profiles[idx];
};
const shipPower = (stats, vsHeavy) => !stats ? 0
  : (stats.gun_power + (vsHeavy ? stats.torpedo_attack : 0))
    * stats.hull / (1 - stats.evasion);
/** What one hull of this type is worth to this nation at this date. */
function shipPowerOf(tag, date, type, vsHeavy) {
  const stats = navalStats(tag, date);
  return stats && stats[type] ? shipPower(stats[type], vsHeavy) : 0;
}
/** Every hull a side has, added up.

    `atStrength` asks for the fleet as it stands rather than as it was drawn:
    the damage formula multiplies by the firing ship's strength and divides by
    one minus the target's experience, and rearranging the duel leaves both on
    their owner's side. Boltun holds them equal because he is ranking ship
    designs -- "all ships have the same experience... strength is maxed at
    100%" -- which is right for that question and not for this one. A fleet at
    half strength fights at half strength, and a veteran one above its paper
    figure; `crews` carries the sum of `strength / (1 - experience)` over the
    hulls of each type, and is absent wherever it comes to the count. */
function fleetPower(tags, date, vsHeavy, atStrength) {
  let total = 0;
  tags.forEach(tag => {
    const at = (DATA.ships[tag] || {})[date] || {};
    const crew = atStrength ? ((DATA.crews || {})[tag] || {})[date] || {} : null;
    for (const type in at) {
      const hulls = crew && crew[type] !== undefined ? crew[type] : at[type];
      total += shipPowerOf(tag, date, type, vsHeavy) * hulls;
    }
  });
  return total;
}
/** Whether any hull on either side carries a torpedo, which is the only thing
    that makes the second power level differ from the first. */
function torpedoesAbout(tags, date) {
  return tags.some(tag => {
    const stats = navalStats(tag, date);
    const at = (DATA.ships[tag] || {})[date] || {};
    return stats && Object.keys(at).some(t => stats[t] && stats[t].torpedo_attack > 0);
  });
}
const fmtPower = v => !v ? '0'
  : v >= 100 ? Math.round(v).toLocaleString()
  : v >= 10 ? v.toFixed(1) : v.toFixed(2);

/* =============== NATIONS =============== */
let natTags = defaultTags.slice();
let logScale = false;

const metricSel = document.getElementById('metric');
// Families keep related readings together without changing the underlying data.
const metricGroups = [
  ['Population', [
    ['Population', ['total_pop','accepted_pop','primary_culture_pop'], 'People living in the nation, with culture-specific views.'],
    ['Accepted share', ['accepted_pct'], 'Percentage of the population belonging to an accepted culture.'],
    ['Literacy', ['avg_literacy','avg_literacy_stated'], 'Average literacy, across the nation or its own states.'],
    ['Population growth', ['pop_growth','accepted_growth'], 'Annualized percentage change between saves.'],
    ['Population gain', ['pop_gain','accepted_gain'], 'People added or lost between saves, including border changes.'],
    ['Social strata', ['pop_poor','pop_middle','pop_rich'], 'Population by social stratum.']]],
  ['Living conditions', [
    ['Life needs unmet', ['life_unmet','life_unmet_pct'], 'People whose life needs are not fully met.'],
    ['Starvation', ['starving','starving_pct'], 'Starving population, shown as a count or population share.']]],
  ['Army', [
    ['Brigades', ['brigades','regular_brigades','mobilized_brigades','mobilizing'], 'Fielded brigades or units queued for mobilization.'],
    ['Recruitment capacity', ['brigade_cap'], 'Professional brigade capacity supported by soldier populations.'],
    ['Mobilizable population', ['mobilization_pool'], 'Population eligible to support mobilization.'],
    ['Mobilization ceiling', ['mobilization_brigades'], 'Total population-based mobilization capacity, including already mobilized brigades.']]],
  ['Navy', [
    ['Ships', ['ships'], 'Ship counts over time. Choose a hull to inspect a specific ship type.'],
    ['Naval bases', ['naval_base_levels','ports','max_naval_base'], 'Total base levels, provinces with bases, or the largest individual base.']]],
  ['Economy', [
    ['Treasury', ['treasury'], 'National treasury balance.'],
    ['Tax base', ['tax_base'], 'The nation’s tax base.'],
    ['Factories', ['factory_count','factory_levels'], 'Number of factories or their combined levels.'],
    ['Railroads', ['railroad_levels'], 'Combined railroad levels.']]],
  ['Society', [
    ['Consciousness', ['avg_consciousness'], 'Average political consciousness.'],
    ['Militancy', ['avg_militancy'], 'Average population militancy.']]],
  ['Nation', [
    ['Prestige', ['prestige'], 'National prestige over time.'],
    ['Infamy', ['infamy'], 'National infamy over time.'],
    ['Technologies', ['techs'], 'Number of researched technologies.'],
    ['Territory', ['provinces','states'], 'Territory measured in provinces or states.']]],
];
const availableMetrics = new Map(DATA.metrics.map(m => [m.key, m]));
const groupedKeys = new Set(metricGroups.flatMap(([, families]) => families.flatMap(([, keys]) => keys)));
const extraMetrics = DATA.metrics.filter(m => !groupedKeys.has(m.key));
if (extraMetrics.length) metricGroups.push(['Other', extraMetrics.map(m => [m.label, [m.key], m.label])]);
const categories = metricGroups.map(([name, families]) => [name,
  families.map(([label, keys, description]) => [label, keys.filter(k => availableMetrics.has(k)), description])
    .filter(([, keys]) => keys.length)]).filter(([, families]) => families.length);
const categorySel = document.getElementById('metric-category');
const familySel = document.getElementById('metric-family');
const metricMemory = new Map();
const familyMemory = new Map();
const variantLabels = {
  total_pop:'Total', accepted_pop:'Accepted culture', primary_culture_pop:'Primary culture',
  avg_literacy:'All population', avg_literacy_stated:'Own states',
  brigades:'All fielded', regular_brigades:'Standing', mobilized_brigades:'Mobilized', mobilizing:'Queued',
  life_unmet:'People', life_unmet_pct:'% of population', starving:'People', starving_pct:'% of population',
  pop_growth:'Total population', accepted_growth:'Accepted culture', pop_gain:'Total population', accepted_gain:'Accepted culture',
  pop_poor:'Poor', pop_middle:'Middle', pop_rich:'Rich', factory_count:'Count', factory_levels:'Total levels',
  naval_base_levels:'Total levels', ports:'Provinces with bases', max_naval_base:'Largest base',
};
function selectMetricFamily() {
  const family = categories.find(([name]) => name === categorySel.value)[1].find(([name]) => name === familySel.value);
  const [label, keys, description] = family;
  familyMemory.set(categorySel.value, label);
  metricSel.replaceChildren(...keys.map(key => new Option(variantLabels[key] || availableMetrics.get(key).label, key)));
  metricSel.value = metricMemory.get(label) || keys[0];
  document.getElementById('metric-variant').hidden = keys.length < 2;
  document.getElementById('ship-variant').hidden = metricSel.value !== 'ships';
  document.getElementById('metric-description').textContent = description;
  familySel.title = description;
}
function selectMetricCategory() {
  const families = categories.find(([name]) => name === categorySel.value)[1];
  familySel.replaceChildren(...families.map(([name]) => new Option(name, name)));
  familySel.value = familyMemory.get(categorySel.value) || families[0][0];
  selectMetricFamily();
}
categories.forEach(([name]) => categorySel.add(new Option(name, name)));
selectMetricCategory();
categorySel.onchange = () => { selectMetricCategory(); drawChart(); };
familySel.onchange = () => { selectMetricFamily(); drawChart(); };
const fmtFor = key => {
  const m = DATA.metrics.find(m => m.key === key);
  return formatters[m ? m.fmt : 'count'] || fmtCount;
};
metricSel.onchange = () => { metricMemory.set(familySel.value, metricSel.value); drawChart(); };

const nationsPicker = makePicker(document.getElementById('pick-nations'),
  tagPickerCfg(natTags, sel => { natTags = sel; drawChart(); }));

const scaleBtn = document.getElementById('scale');
scaleBtn.onclick = () => {
  logScale = !logScale;
  scaleBtn.setAttribute('aria-pressed', logScale);
  scaleBtn.textContent = logScale ? 'Logarithmic' : 'Linear';
  drawChart();
};

const worldBtn = document.getElementById('worldline');
worldBtn.onclick = () => {
  worldLine = !worldLine;
  worldBtn.setAttribute('aria-pressed', worldLine);
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

/* Growth is not a quantity a save holds; it is the difference between two of
   them. That makes it read differently from every other measure here, so the
   chart says so, and draws the line that separates growing from shrinking. */
const isRate = key => (DATA.metrics.find(m => m.key === key) || {}).rate === 1;

/* Everyone alive, as a series the chart can draw beside the nations.

   It is not a nation and cannot be one: it counts pops on land nobody owns,
   which belong to no tag at all -- 6.4% of the world in 1836 and none of it by
   1908 -- so it comes from its own total rather than from adding the nations
   up. Offered only against population, since nothing else on the measure list
   has a world figure behind it. */
let worldLine = false;
function worldSeries(key) {
  if (!worldLine || key !== 'total_pop' || !DATA.worldPop) return [];
  const pts = DATA.dates
    .map((d, i) => [years[i], DATA.worldPop[d]])
    .filter(p => p[1] !== undefined);
  return pts.length ? [{name: 'World', colour: 'var(--ink-dim)', pts}] : [];
}

function drawChart() {
  const key = metricSel.value;
  document.getElementById('chart-title').textContent = availableMetrics.get(key).label + ' over time';
  document.getElementById('chart').setAttribute('aria-label', availableMetrics.get(key).label + ' over time by nation');
  document.getElementById('fleetspan').hidden = true;
  const shown = DATA.tags.filter(t => natTags.includes(t));
  const rate = isRate(key);
  const worldBtn = document.getElementById('worldline');
  // Nothing else on the list has a world total behind it, so the button says
  // so by going quiet rather than drawing a line that would be a guess. Being
  // switched on does not survive that: a measure with no world figure cannot
  // be showing one, so the button gives up the state as well as the colour.
  worldBtn.disabled = key !== 'total_pop' || !DATA.worldPop;
  if (worldBtn.disabled && worldLine) {
    worldLine = false;
    worldBtn.setAttribute('aria-pressed', 'false');
  }
  if (key === 'ships') {
    document.getElementById('ratenote').hidden = true;
    drawFleetChart();
    return;
  }
  plot(document.getElementById('chart'), {
    series: shown.map(tag => ({
      name: tag, colour: colourFor(tag),
      // `!= null` rather than `!== undefined`: a measure a nation has no
      // reading for in a save is a null in its column, not a gap.
      pts: DATA.dates.map((d, i) => [years[i], DATA.series[tag][key][i]])
                     .filter(p => p[1] != null),
    })).concat(worldSeries(key)),
    xOf: xOfSave, xTicks: saveTicks, hoverXs: saveHovers,
    fmt: fmtFor(key), log: logScale, markers: true,
    links: SUCCESSIONS,
    baseline: rate ? 0 : null,
    readout: document.getElementById('readout'),
    idle: 'Hover the plot to read values at a date.',
    emptyMsg: shown.length || worldSeries(key).length
      ? 'No data for this measure.' : 'Select a nation.',
  });
  const note = document.getElementById('ratenote');
  note.hidden = !rate;
  if (rate) note.innerHTML = 'Compounded yearly, between one save and the one '
    + 'before it: a nation that grew 3% over six months plots at about 6%. '
    + `Two saves less than ${(DATA.growthSpan * 12).toFixed(0)} months apart are `
    + 'measured across the gap to the next one far enough away instead &mdash; a '
    + 'fortnight of ordinary growth annualises into hundreds of percent and would '
    + 'bury everything else on the chart. Conquest, annexation and independence '
    + 'move population as surely as births do, so the sharp spikes and drops are '
    + 'usually a border moving rather than a demographic event.';
}

/* =============== MILITARY =============== */
let milTags = defaultTags.slice(0, 6);
let milMode = 'army';       // army | navy
let milView = 'totals';     // totals | composition
let milPotential = false;    // true = standing + mobilization ceiling, false = brigades right now
// Horizon blue against field grey: the two uniforms the period ended in, and
// far enough apart on a burgundy ground to read at a glance. Mobilization is
// the same blue and grey held back to a khaki, so an added ceiling reads as
// part of the same army rather than a third force.
const MOB_COLOUR = '#B79B6E';
// Brigades the cap allows that nobody has raised. Kept clearly apart from the
// mobilization brass, since the two are different kinds of "not yet".
const CAP_COLOUR = '#6B7C8C';
const SIDE_COLOUR = ['#5E8CB8', '#9DA08D'];

const milSave = document.getElementById('milsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  milSave.appendChild(o);
});
milSave.value = DATA.lastDate;

const fleetSave = document.getElementById('fleetsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  fleetSave.appendChild(o);
});
fleetSave.value = DATA.lastDate;
fleetSave.onchange = () => {
  milPicker.refresh();
  drawMilTable(); drawFleetTable();
};

let overviewBranch = 'army';
function showMilitaryOverview(branch) {
  for (const kind of ['army', 'navy']) {
    const selected = kind === branch;
    document.getElementById('overview-' + kind).setAttribute('aria-pressed', selected);
    document.getElementById('overview-' + kind + '-view').hidden = !selected;
  }
  overviewBranch = branch;
  if (branch === 'navy') { drawFleetTable(); }
  else { drawMilTable(); }
}
for (const branch of ['army', 'navy']) {
  document.getElementById('overview-' + branch).onclick = () => showMilitaryOverview(branch);
}



const byBrigades = [...DATA.tags].sort((a, b) =>
  (((DATA.facts[DATA.lastDate] || {})[b] || {}).brigades || 0) -
  (((DATA.facts[DATA.lastDate] || {})[a] || {}).brigades || 0));
let sideA = [byBrigades[0]].filter(Boolean);
let sideB = [byBrigades[1]].filter(Boolean);

const pickerA = makePicker(document.getElementById('pick-milA'),
  tagPickerCfg(sideA, sel => { sideA = sel; drawMilPies(); }, () => milSave.value));
const pickerB = makePicker(document.getElementById('pick-milB'),
  tagPickerCfg(sideB, sel => { sideB = sel; drawMilPies(); }, () => milSave.value));

function setHeadBranch(branch) {
  milMode = branch;
  for (const kind of ['army', 'navy']) document.getElementById('head-' + kind).setAttribute('aria-pressed', kind === branch);
  document.getElementById('milmob').hidden = branch === 'navy';
  drawMilPies();
}
for (const branch of ['army', 'navy']) document.getElementById('head-' + branch).onclick = () => setHeadBranch(branch);
function showCompareView(view) {
  for (const kind of ['trends', 'head']) {
    document.getElementById('compare-' + kind).hidden = kind !== view;
    document.getElementById('compare-' + kind + '-button').setAttribute('aria-pressed', kind === view);
  }
}
for (const view of ['trends', 'head']) document.getElementById('compare-' + view + '-button').onclick = () => showCompareView(view);
document.getElementById('mil-compare').onclick = () => {
  milSave.value = fleetSave.value;
  pickerA.refresh(); pickerB.refresh();
  setHeadBranch(overviewBranch);
  selectTab('tab-compare'); showCompareView('head');
  document.getElementById('compare-head-button').focus();
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
  pickerA.refresh(); pickerB.refresh();
  drawMilPies();
};

const milPicker = makePicker(document.getElementById('pick-military'),
  tagPickerCfg(milTags, sel => { milTags = sel; drawMilTable(); drawFleetTable(); },
               () => fleetSave.value));

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
/**
 * The standing brigades a side's soldier pops could support.
 *
 * Potential used to mean the brigades already standing plus the mobilization
 * ceiling, which understated a nation that had not recruited its soldier pops
 * out -- and nations differ enormously there. This is the other half: what
 * could be raised without mobilizing at all.
 */
function groupCap(tags, date) {
  if (milMode !== 'army') return groupTotal(tags, date);
  const at = DATA.facts[date] || {};
  return tags.reduce((sum, t) => sum + ((at[t] || {}).brigade_cap || 0), 0);
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
    ? groupCap(tags, date) + groupMob(tags, date)
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
  const caps = [groupCap(sideA, date), groupCap(sideB, date)];
  // The cap counts brigades that do not exist yet, so they have no unit type to
  // be drawn as; they get a slice of their own, and the slices then still add
  // up to the headline -- standing + mobilized + unbuilt + remaining ceiling is
  // the cap plus the ceiling. Declared here with the other side arrays because
  // the labels under each donut read it well before the slices are built.
  const unbuilt = milPotential
    ? [0, 1].map(i => Math.max(0, caps[i] - standing[i])) : [0, 0];
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
  // Hulls are not interchangeable: five frigates are not a cruiser. Fleet power
  // is what a side's ships are worth in a fight, so it sits beside the count
  // rather than replacing it -- the two disagreeing is the interesting part.
  const powers = NAVAL && milMode === 'navy'
    ? [fleetPower(sideA, date, false), fleetPower(sideB, date, false)] : null;
  const heavyPowers = powers && torpedoesAbout(sideA.concat(sideB), date)
    ? [fleetPower(sideA, date, true), fleetPower(sideB, date, true)] : null;
  // The same fleets at the strength and experience the save records. Shown
  // under the design figure rather than instead of it, so a fleet somebody has
  // stopped paying for still appears at what it could be worth again.
  const nowPowers = powers
    ? [fleetPower(sideA, date, false, true), fleetPower(sideB, date, false, true)]
    : null;
  const powersDiffer = nowPowers && [0, 1].some(i =>
    Math.abs(nowPowers[i] - powers[i]) > Math.max(0.5, powers[i] * 0.005));
  const powerRatio = powers && powers[1]
    ? (powers[0] / powers[1]).toFixed(2) + '×' : '—';
  const powerBits = !powers ? ''
    : `<span><span class="rk">fleet power</span> `
      + `<b style="color:${SIDE_COLOUR[0]}">${fmtPower(powers[0])}</b>`
      + ` <span class="rk">v</span> `
      + `<b style="color:${SIDE_COLOUR[1]}">${fmtPower(powers[1])}</b></span>`
      + `<span><span class="rk">power ratio</span> <b>${powerRatio}</b></span>`
      + (powersDiffer ? `<span><span class="rk">at current strength</span> `
        + `<b>${fmtPower(nowPowers[0])}</b> <span class="rk">v</span> `
        + `<b>${fmtPower(nowPowers[1])}</b></span>` : '')
      + (heavyPowers ? `<span><span class="rk">vs heavy</span> `
        + `<b>${fmtPower(heavyPowers[0])}</b> <span class="rk">v</span> `
        + `<b>${fmtPower(heavyPowers[1])}</b></span>` : '');
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
      + (milPotential && (caps[0] || caps[1])
          ? `<span title="The standing brigades each side's soldier pops can `
            + `support, never read below what it already has."><span `
            + `class="rk">brigade cap</span> `
            + `<b>${caps[0].toLocaleString()}</b> <span class="rk">v</span> `
            + `<b>${caps[1].toLocaleString()}</b></span>` : '')
      + `<span><span class="rk">${milPotential ? 'mob ceiling' : 'mobilized'}</span> `
      + `<b>${(milPotential ? mobs[0] : mobilized[0]).toLocaleString()}</b>`
      + ` <span class="rk">v</span> <b>${(milPotential ? mobs[1] : mobilized[1]).toLocaleString()}</b></span>`
    : '';
  const idle = `<span class="rk">left</span> <b style="color:${SIDE_COLOUR[0]}">`
    + `${totals[0].toLocaleString()}</b>`
    + `<span><span class="rk">right</span> <b style="color:${SIDE_COLOUR[1]}">`
    + `${totals[1].toLocaleString()}</b></span>`
    + `<span><span class="rk">ratio</span> <b>${ratioText}</b></span>` + split
    + powerBits
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
      if (milMode === 'army'
          && (milPotential ? (mobs[side] || unbuilt[side]) : mobilized[side])) {
        const breakdown = el('text', {x, y: 122, 'text-anchor': 'middle',
          fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
        breakdown.textContent = milPotential
          ? `${standing[side].toLocaleString()} standing `
            + (unbuilt[side] ? `+ ${unbuilt[side].toLocaleString()} unbuilt ` : '')
            + `+ ${mobs[side].toLocaleString()} mob ceiling`
          : `${standing[side].toLocaleString()} standing `
            + `+ ${mobilized[side].toLocaleString()} mobilized`;
        svg.appendChild(breakdown);
      }
      // The same slot under the navy's count carries what those hulls are
      // worth, which is the number that actually decides a battle.
      if (powers) {
        const worth = el('text', {x, y: 122, 'text-anchor': 'middle',
          fill: 'var(--brass)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
        worth.textContent = `${fmtPower(powers[side])} fleet power`;
        svg.appendChild(worth);
        let line = 138;
        if (powersDiffer) {
          const now = el('text', {x, y: line, 'text-anchor': 'middle',
            fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
          const pct = powers[side]
            ? Math.round(100 * nowPowers[side] / powers[side]) : 100;
          now.textContent = `${fmtPower(nowPowers[side])} at current strength `
            + `(${pct}%)`;
          svg.appendChild(now);
          line += 15;
        }
        if (heavyPowers && heavyPowers[side] > powers[side] + 0.5) {
          const vs = el('text', {x, y: line, 'text-anchor': 'middle',
            fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
          vs.textContent = `${fmtPower(heavyPowers[side])} against heavy ships`;
          svg.appendChild(vs);
        }
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
        const n = type === '__mob' ? remainingMob[i]
              : type === '__unbuilt' ? unbuilt[i] : (counts[i][type] || 0);
        const pct = totals[i] ? (n / totals[i] * 100).toFixed(1) : '0.0';
        return `<span><span class="rk">${i ? 'right' : 'left'}</span> `
             + `<b style="color:${SIDE_COLOUR[i]}">${n.toLocaleString()}</b> `
             + `<span class="rk">(${pct}%)</span></span>`;
      });
      const [x, y] = type === '__mob' ? remainingMob
                   : type === '__unbuilt' ? unbuilt
                   : [counts[0][type] || 0, counts[1][type] || 0];
      const r = y ? (x / y).toFixed(2) + '×' : (x ? '—' : '');
      const label = type === '__mob' ? 'still mobilizable'
                  : type === '__unbuilt' ? 'cap not yet raised' : gameName(type);
      // What one of these hulls is worth, side by side. The two sides can
      // differ on the same hull type: inventions upgrade guns and armour, so
      // one nation's cruiser is not another's.
      let worth = '';
      if (powers && type !== '__mob' && type !== '__unbuilt') {
        const each = [0, 1].map(i => {
          const per = sideCount[i] ? shipPowerOf(sideCount[i], date, type, false) : 0;
          return `<span><span class="rk">${i ? 'right' : 'left'} each</span> `
               + `<b style="color:${SIDE_COLOUR[i]}">${fmtPower(per)}</b> `
               + `<span class="rk">x${(counts[i][type] || 0).toLocaleString()} `
               + `= ${fmtPower(per * (counts[i][type] || 0))}</span></span>`;
        });
        worth = `<span class="rk">power</span>` + each.join('');
      }
      readout.innerHTML = `<span class="rk">${label}</span>` + parts.join('')
        + (r ? `<span><span class="rk">ratio</span> <b>${r}</b></span>` : '')
        + worth;
    };
    // A side is one nation or several. Power per hull belongs to a nation, so
    // the readout quotes the side's largest fleet rather than pretending a
    // coalition of nations on different technology shares one cruiser.
    const shipsOf = t => ((DATA.facts[date] || {})[t] || {}).ships || 0;
    const sideCount = [sideA, sideB].map(
      tags => tags.slice().sort((a, b) => shipsOf(b) - shipsOf(a))[0]);

    [[sideA, 0, 268], [sideB, 1, 732]].forEach(([tags, side, cx]) => {
      const head = el('text', {x: cx, y: 34, 'text-anchor': 'middle', fill: SIDE_COLOUR[side],
        'font-family': 'IBM Plex Mono, monospace', 'font-size': 13});
      head.textContent = sideLabel(tags);
      svg.appendChild(head);
      const slices = present.map(type => ({
        label: `${sideLabel(tags)} · ${gameName(type)}`, value: counts[side][type] || 0,
        colour: milColour(type), type,
      }));
      if (unbuilt[side]) slices.push({
        label: `${sideLabel(tags)} · cap not yet raised`, value: unbuilt[side],
        colour: CAP_COLOUR, type: '__unbuilt',
      });
      if (remainingMob[side]) slices.push({
        label: `${sideLabel(tags)} · still mobilizable`, value: remainingMob[side],
        colour: MOB_COLOUR, type: '__mob',
      });
      donut(svg, cx, 196, 74, 122, slices, slice => setType(slice.type));
      centreText(svg, cx, 196, totals[side].toLocaleString(), noun);
      if (powers) {
        const worth = el('text', {x: cx, y: 348, 'text-anchor': 'middle',
          fill: 'var(--brass)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 13});
        worth.textContent = fmtPower(powers[side]);
        svg.appendChild(worth);
        const cap = el('text', {x: cx, y: 364, 'text-anchor': 'middle',
          fill: 'var(--ink-dim)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 10});
        cap.textContent = 'fleet power';
        svg.appendChild(cap);
      }
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
      item.innerHTML = `<i style="background:${milColour(type)}"></i>${gameName(type)}`;
      item.style.cursor = 'pointer';
      item.onmouseenter = () => setType(type);
      legend.appendChild(item);
    });
    if (unbuilt[0] || unbuilt[1]) {
      const item = document.createElement('span');
      item.className = 'slegend';
      item.innerHTML = `<i style="background:${CAP_COLOUR}"></i>cap not yet raised`;
      item.style.cursor = 'pointer';
      item.onmouseenter = () => setType('__unbuilt');
      legend.appendChild(item);
    }
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

let militaryCountry = null;
const militaryLedgers = {};
const strengthValue = value => value == null ? '—'
  : typeof value === 'number' ? value.toLocaleString() : value;

function strengthDetails(sections, note) {
  const grid = document.createElement('div');
  grid.className = 'return-grid';
  sections.forEach(([title, entries]) => {
    const section = document.createElement('div');
    const heading = document.createElement('h3');
    const list = document.createElement('dl');
    heading.textContent = title;
    const shown = entries.length ? entries : [['No units recorded', '—']];
    shown.forEach(([label, value]) => {
      const line = document.createElement('div');
      const term = document.createElement('dt');
      const definition = document.createElement('dd');
      term.textContent = label;
      definition.textContent = strengthValue(value);
      line.append(term, definition);
      list.appendChild(line);
    });
    section.append(heading, list);
    grid.appendChild(section);
  });
  const help = document.createElement('p');
  help.className = 'note';
  help.textContent = note;
  return [grid, help];
}

// Use the report's embedded flags; a nation-colour swatch is the honest fallback.
function nationFlag(tag) {
  const src = (DATA.flags || {})[tag + '|'];
  const flag = document.createElement(src ? 'img' : 'span');
  flag.className = 'military-flag' + (src ? '' : ' blank');
  if (src) { flag.src = src; flag.alt = ''; }
  else { flag.style.backgroundColor = colourFor(tag); flag.setAttribute('aria-hidden', 'true'); }
  return flag;
}

function nationIdentity(tag) {
  const identity = document.createElement('span'); identity.className = 'nation-identity';
  const name = document.createElement('span'); name.textContent = nameOf(tag);
  name.style.color = colourFor(tag);
  identity.append(nationFlag(tag),name);
  return identity;
}

function compareMilitaryNations(tag, rival, branch) {
  milSave.value = fleetSave.value;
  pickerA.set([tag]); pickerB.set([rival]);
  pickerA.refresh(); pickerB.refresh();
  setHeadBranch(branch);
  selectTab('tab-compare'); showCompareView('head');
  document.getElementById('compare-head-button').focus();
}

// Keep this a transparent shortlist, not an invented battle or diplomacy score.
// Candidates come from all nations present in this save, independent of filters.
function militaryRivalRows(tag, branch, metric, date) {
  const facts = DATA.facts[date] || {};
  const value = (t, key) => {
    const f = facts[t] || {};
    if (key === 'size') return branch === 'army' ? f.brigades || 0 : shipCount(t, date, '__all') || 0;
    if (key === 'tech') return f[branch + '_techs'] ?? null;
    if (key === 'power') {
      const stats = navalStats(t,date), counts = (DATA.ships[t] || {})[date] || {};
      return stats && Object.keys(counts).every(type => stats[type]) ? fleetPower([t],date,false,true) : null;
    }
    return f.mobilization_brigades ?? null;
  };
  const own = value(tag, 'size');
  const rows = Object.keys(facts).filter(t => t !== tag && value(t, 'size') > 0)
    .map(t => ({tag:t, size:value(t, 'size'), tech:value(t, 'tech'), mob:value(t, 'mob'), power:metric === 'power' ? value(t,'power') : null}));
  const key = metric === 'closest' ? 'size' : metric;
  return rows.filter(r => r[key] != null).sort((a,b) => {
    const order = metric === 'closest' ? Math.abs(a.size-own) - Math.abs(b.size-own) : b[key]-a[key];
    return order || b.size-a.size || a.tag.localeCompare(b.tag);
  }).slice(0,3);
}

function militaryRivals(tag, branch, date) {
  const box = document.createElement('div'); box.className = 'ib military-rivals';
  const title = document.createElement('div'); title.className = 'ibtitle';
  title.textContent = 'Who challenges ' + nameOf(tag) + '’s might?';
  const controls = document.createElement('div'); controls.className = 'controls';
  const label = document.createElement('label'); label.textContent = 'Scout rivals by ';
  const select = document.createElement('select'); select.setAttribute('aria-label', 'Rank potential rivals');
  [['closest','Closest in force size'], ['size',branch === 'army' ? 'Largest armies' : 'Largest navies'],
   ['tech',branch === 'army' ? 'Highest army technology' : 'Highest naval technology'],
   ...(branch === 'army' ? [['mob','Largest mobilization ceiling']] : [['power','Highest fleet power']])]
    .forEach(([value,text]) => select.add(new Option(text,value)));
  label.appendChild(select); controls.appendChild(label);
  const wrap = document.createElement('div'); wrap.className = 'tablewrap';
  const table = document.createElement('table'); table.className = 'rival-table'; wrap.appendChild(table);
  const note = document.createElement('p'); note.className = 'note';
  note.textContent = 'Three other nations at this save, ranked by the selected measure. Force size means '
    + (branch === 'army' ? 'fielded brigades' : 'ship count, not fighting power')
    + '. These are global strength comparisons, not geographic neighbours or confirmed enemies. Tech is researched technology count.';
  const draw = () => {
    table.replaceChildren();
    const head = table.createTHead().insertRow();
    ['Nation',branch === 'army' ? 'Brigades' : 'Ships','Tech',branch === 'army' ? 'Mob ceiling' : 'Power · est.',''].forEach(text => {
      const th = document.createElement('th'); th.scope = 'col'; th.textContent = text; head.appendChild(th);
    });
    const body = table.createTBody();
    const rows = militaryRivalRows(tag,branch,select.value,date);
    rows.forEach(r => {
      const tr = body.insertRow();
      const name = document.createElement('span'); name.className = 'rival-name'; name.style.color = colourFor(r.tag);
      name.append(nationFlag(r.tag), document.createTextNode(nameOf(r.tag))); tr.insertCell().appendChild(name);
      const own = (DATA.facts[date] || {})[tag] || {};
      const difference = (cell,value,baseline) => {
        cell.textContent = strengthValue(value);
        if (value == null || baseline == null) return;
        const delta = document.createElement('small'); delta.className = 'military-delta';
        const n = value-baseline;
        delta.textContent = n === 0 ? 'Equal to yours' : strengthValue(Math.abs(n))+(n > 0 ? ' more than yours' : ' fewer than yours');
        cell.appendChild(delta);
      };
      difference(tr.insertCell(),r.size,branch === 'army' ? own.brigades : shipCount(tag,date,'__all'));
      difference(tr.insertCell(),r.tech,own[branch+'_techs']);
      const stats = navalStats(r.tag,date), counts = (DATA.ships[r.tag] || {})[date] || {};
      const known = stats && Object.keys(counts).every(type => stats[type]);
      const measure = tr.insertCell();
      if (branch === 'army') difference(measure,r.mob,own.mobilization_brigades);
      else {
        measure.textContent = known ? fmtPower(fleetPower([r.tag],date,false,true)) : '—';
        const ownStats = navalStats(tag,date), ownCounts = (DATA.ships[tag] || {})[date] || {};
        if (known && ownStats && Object.keys(ownCounts).every(type => ownStats[type])) {
          const delta = document.createElement('small'); delta.className = 'military-delta';
          const n = fleetPower([r.tag],date,false,true)-fleetPower([tag],date,false,true);
          delta.textContent = n === 0 ? 'Equal to yours' : fmtPower(Math.abs(n))+(n > 0 ? ' above yours' : ' below yours');
          measure.appendChild(delta);
        }
      }
      const compare = document.createElement('button'); compare.textContent = 'Compare →';
      compare.setAttribute('aria-label', 'Compare ' + nameOf(tag) + ' with ' + nameOf(r.tag));
      compare.onclick = () => compareMilitaryNations(tag,r.tag,branch);
      tr.insertCell().appendChild(compare);
    });
    if (!rows.length) { const td = body.insertRow().insertCell(); td.colSpan = 5; td.textContent = 'No other nations with recorded forces for this measure.'; }
  };
  select.onchange = draw; draw();
  const help = militaryHelp(note.textContent);
  box.append(title,controls,wrap,help);
  return box;
}

function militaryHelp(text) {
  const help = document.createElement('details'); help.className = 'military-help';
  const summary = document.createElement('summary'); summary.textContent = 'How these figures are calculated';
  const body = document.createElement('p'); body.textContent = text;
  help.append(summary,body); return help;
}

function militaryInventory(row, branch, date) {
  const box = document.createElement('div'); box.className = 'ib military-inventory';
  const title = document.createElement('div'); title.className = 'ibtitle';
  title.textContent = branch === 'army' ? 'Fielded composition' : 'Hull inventory';
  const wrap = document.createElement('div'); wrap.className = 'tablewrap fit';
  const table = document.createElement('table');
  const head = table.createTHead().insertRow();
  const labels = ['Unit type','Count','Share', ...(branch === 'navy' ? ['Current power'] : [])];
  labels.forEach(label => { const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; head.appendChild(th); });
  const counts = branch === 'army' ? (DATA.brigades[row.tag] || {})[date] || {} : row.counts;
  const total = Object.values(counts).reduce((sum,n) => sum+n,0);
  const stats = navalStats(row.tag,date), crew = ((DATA.crews || {})[row.tag] || {})[date] || {};
  const body = table.createTBody();
  Object.entries(counts).filter(([,count]) => count > 0).sort((a,b) => b[1]-a[1]).forEach(([type,count]) => {
    const tr = body.insertRow(); tr.insertCell().textContent = gameName(type);
    tr.insertCell().textContent = strengthValue(count);
    tr.insertCell().textContent = total ? (100*count/total).toFixed(1)+'%' : '—';
    if (branch === 'navy') tr.insertCell().textContent = stats?.[type]
      ? fmtPower(shipPower(stats[type],false)*(crew[type] ?? count)) : '—';
  });
  if (!body.rows.length) { const td = body.insertRow().insertCell(); td.colSpan = labels.length; td.textContent = 'No units recorded at this save.'; }
  wrap.appendChild(table); box.append(title,wrap); return box;
}

function militaryDossier(row, branch, sections, note) {
  const date = fleetSave.value, facts = (DATA.facts[date] || {})[row.tag] || {};
  const page = document.createElement('div'); page.className = 'military-country-page';
  const header = document.createElement('div'); header.className = 'military-country-header';
  const back = document.createElement('button'); back.id = 'military-back'; back.textContent = '← All countries';
  back.onclick = () => {
    const tag = militaryCountry; militaryCountry = null; refreshMilitaryCountry();
    const id = overviewBranch === 'army' ? 'miltable' : 'fleettable';
    [...document.querySelectorAll('#'+id+' .strength-row')].find(tr => tr.dataset.tag === tag)?.querySelector('button').focus();
  };
  const name = document.createElement('h2'); name.textContent = row.name; name.style.color = colourFor(row.tag);
  const stamp = document.createElement('span'); stamp.className = 'note'; stamp.textContent = date;
  header.append(back,nationFlag(row.tag),name,stamp);
  const strip = document.createElement('div'); strip.className = 'military-strength-strip';
  const metrics = branch === 'army'
    ? [['Fielded brigades',row.brigades],['Professional',row.regular_brigades],['Mobilized',row.mobilized_brigades],['Unbuilt capacity',row.cap_headroom],['Total potential · est.',row.total_military_potential]]
    : [['Ships',row.total],['Heavy hulls',row.heavy],['Other hulls',row.other],['Current power · est.',row.power == null ? null : fmtPower(row.power)],['Full-strength power',row.design == null ? null : fmtPower(row.design)]];
  metrics.forEach(([label,value]) => {
    const tile = document.createElement('div'), caption = document.createElement('div'), number = document.createElement('div');
    caption.className = 'tb-label'; caption.textContent = label;
    number.className = 'military-stat'; number.textContent = strengthValue(value); tile.append(caption,number); strip.appendChild(tile);
  });
  const main = document.createElement('div'); main.className = 'military-country-body';
  const capacity = document.createElement('div'); capacity.className = 'ib military-capacity';
  const title = document.createElement('div'); title.className = 'ibtitle';
  title.textContent = branch === 'army' ? 'Recruitment & mobilization' : 'Fleet capability';
  const content = document.createElement('div'); content.className = 'military-capacity-content';
  const entries = branch === 'army' ? [[sections[0][0],sections[0][1].filter(([label]) => !['Unbuilt capacity','Total potential (estimate)'].includes(label))],sections[1]]
    : [['Naval establishment',[['Naval technologies',facts.navy_techs ?? null],['Current power',row.power == null ? null : fmtPower(row.power)],['Full-strength power',row.design == null ? null : fmtPower(row.design)]]]];
  content.append(...strengthDetails(entries,''));
  if (branch === 'army') {
    const tech = document.createElement('p'); tech.className = 'note'; tech.textContent = 'Army technologies researched: '+strengthValue(facts.army_techs);
    content.appendChild(tech);
  }
  content.appendChild(militaryHelp(note)); capacity.append(title,content);
  const forces = document.createElement('div'); forces.className = 'military-forces-column';
  forces.append(militaryInventory(row,branch,date),militaryRivals(row.tag,branch,date));
  main.append(forces,capacity);
  const history = document.createElement('section'); history.className = 'military-composition-history';
  const heading = document.createElement('h2');
  heading.textContent = branch === 'army' ? 'Army composition over time' : 'Fleet composition over time';
  const figure = document.createElement('figure');
  const svg = document.createElementNS(SVGNS,'svg'); svg.id = 'military-composition';
  svg.setAttribute('viewBox','0 0 1000 360'); svg.setAttribute('role','img');
  svg.setAttribute('aria-label',nameOf(row.tag)+' · '+heading.textContent);
  figure.appendChild(svg);
  const legend = document.createElement('div'); legend.id = 'military-composition-legend'; legend.className = 'stackwrap';
  const hint = document.createElement('p'); hint.className = 'note';
  hint.textContent = 'Full campaign history for this country. Each bar uses the last save of that year. Hover a band for its '+(branch === 'army' ? 'brigade' : 'ship')+' count.';
  history.append(heading,figure,legend,hint);
  page.append(header,strip,main,history);
  return page;
}

function refreshMilitaryCountry() {
  const host = document.getElementById('military-country');
  const ledger = militaryLedgers[overviewBranch];
  const row = ledger?.rows.find(row => row.tag === militaryCountry);
  if (militaryCountry && !row) militaryCountry = null;
  document.getElementById('military-browse').hidden = !!militaryCountry;
  document.getElementById('miloverview').classList.toggle('country-open',!!militaryCountry);
  host.hidden = !militaryCountry;
  host.replaceChildren();
  if (row) {
    host.appendChild(militaryDossier(row,overviewBranch,ledger.sections(row),ledger.note));
    const army = overviewBranch === 'army';
    stackedBars('military-composition','military-composition-legend',
      (army ? DATA.brigades : DATA.ships)[row.tag] || {},
      army ? DATA.regimentTypes : DATA.shipTypes,
      row.name+' has no '+(army ? 'brigades' : 'ships')+' in these saves.');
  }
}

// Preserve the selected country while rebuilding either branch at a new save.
// Native buttons provide keyboard activation without making every cell focusable.
function renderStrengthLedger(id, cols, rows, state, sections, note) {
  const branch = id === 'miltable' ? 'army' : 'navy';
  militaryLedgers[branch] = {rows, sections, note};
  if (branch === overviewBranch) refreshMilitaryCountry();
  const table = document.getElementById(id);
  const head = table.querySelector('thead tr'), body = table.querySelector('tbody');
  head.replaceChildren(); body.replaceChildren();
  cols.forEach((col, index) => {
    const th = document.createElement('th');
    th.scope = 'col';
    th.setAttribute('aria-sort', state.key === col.key
      ? (state.dir < 0 ? 'descending' : 'ascending') : 'none');
    const button = document.createElement('button');
    button.textContent = col.label;
    button.onclick = () => {
      state.dir = state.key === col.key ? -state.dir : -1;
      state.key = col.key;
      renderStrengthLedger(id, cols, rows, state, sections, note);
      head.children[index].querySelector('button').focus();
    };
    th.appendChild(button); head.appendChild(th);
  });
  const ordered = [...rows].sort((a, b) => {
    const x = a[state.key], y = b[state.key];
    if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
    return state.dir * (typeof x === 'string' ? x.localeCompare(y) : x - y);
  });
  ordered.forEach(row => {
    const tr = document.createElement('tr');
    tr.className = 'strength-row'; tr.dataset.tag = row.tag;
    cols.forEach((col, index) => {
      const td = document.createElement('td');
      if (index === 0) {
        const button = document.createElement('button');
        button.className = 'nation-toggle';
        const arrow = document.createElement('span'); arrow.setAttribute('aria-hidden','true');
        const name = document.createElement('span'); name.textContent = row.name; name.style.color = colourFor(row.tag);
        button.append(arrow,nationFlag(row.tag),name);
        arrow.textContent = '▸';
        button.setAttribute('aria-controls','military-country');
        tr.onclick = () => {
          militaryCountry = row.tag; refreshMilitaryCountry();
          document.getElementById('military-back').focus();
        };
        td.appendChild(button);
      } else {
        const value = row[col.key];
        td.textContent = col.fmt ? col.fmt(value) : strengthValue(value);
      }
      tr.appendChild(td);
    });
    body.appendChild(tr);
  });
  if (!rows.length) {
    const tr = document.createElement('tr'), td = document.createElement('td');
    td.colSpan = cols.length;
    td.textContent = 'Select nations to view their strength returns.';
    tr.appendChild(td); body.appendChild(tr);
  }
}

const milState = {key: 'brigades', dir: -1};
function drawMilTable() {
  const date = fleetSave.value;
  const facts = DATA.facts[date] || {};
  const usedReg = DATA.regimentTypes;
  const cols = [
    {key:'name', label:'Nation'},
    {key:'brigades', label:'Fielded brigades'},
    {key:'regular_brigades', label:'Professional'},
    {key:'mobilized_brigades', label:'Mobilized'},
    {key:'cap_headroom', label:'Unbuilt capacity'},
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
      brigade_cap: f.brigade_cap || 0,
      cap_headroom: Math.max(0, (f.brigade_cap || 0) - (f.regular_brigades || 0)),
      total_military_potential: (f.brigade_cap || 0)
                              + (f.mobilization_brigades || 0),
      mobilisation_size: f.mobilisation_size || 0,
      mobilization_pool: f.mobilization_pool || 0,
      ships: f.ships || 0,
      soldiers,
      soldier_pct: f.total_pop ? soldiers / f.total_pop * 100 : 0,
      noncol_soldier_pct: f.total_pop
        ? (f.soldiers_noncolonial || 0) / f.total_pop * 100 : 0,
    };
    usedReg.forEach(rt => row[rt] = at[rt] || 0);
    return row;
  });
  renderStrengthLedger('miltable', cols, rows, milState, row => [
    ['Recruitment potential', [
      ['Professional brigade cap', row.brigade_cap], ['Unbuilt capacity', row.cap_headroom],
      ['Mobilization ceiling (estimate)', row.mobilization_brigades], ['Mobilization queued', row.mobilizing],
      ['Total potential (estimate)', row.total_military_potential]]],
    ['Recruitment base', [['Soldier population', row.soldiers], ['Soldier share', row.soldier_pct.toFixed(2) + '%'],
      ['Non-colonial soldier share', row.noncol_soldier_pct.toFixed(2) + '%'],
      ['Mobilizable population', row.mobilization_pool], ['Mobilization rate', (row.mobilisation_size * 100).toFixed(2) + '%']]],
    ['Fielded composition', usedReg.filter(type => row[type]).map(type => [gameName(type), row[type]])],
  ], 'Potential combines the professional brigade cap and population-based mobilization ceiling. Mobilized brigades are already included in that ceiling; it is not the remaining in-game mobilization count.');
}

/* =============== FLEETS =============== */

const shipSel = document.getElementById('shiptype');
[['__all', 'All ships'],
 ...[...DATA.shipTypes].sort(byGameName).map(s => [s, gameName(s)])].forEach(([v, label]) => {
  const o = document.createElement('option'); o.value = v; o.textContent = label;
  shipSel.appendChild(o);
});
shipSel.onchange = drawChart;

const shipCount = (tag, date, type) => {
  const at = (DATA.ships[tag] || {})[date];
  if (!at) return undefined;
  if (type === '__all') return Object.values(at).reduce((a, b) => a + b, 0);
  return at[type];
};

function drawFleetChart() {
  const type = shipSel.value;
  document.getElementById('chart-title').textContent = (type === '__all' ? 'Ships' : gameName(type)) + ' over time';
  document.getElementById('chart').setAttribute('aria-label', document.getElementById('chart-title').textContent + ' by nation');
  const shown = DATA.tags.filter(t => natTags.includes(t));
  const series = shown.map(tag => ({
    name: tag, colour: colourFor(tag),
    pts: DATA.dates.map((d, i) => [years[i], shipCount(tag, d, type)])
                   .filter(p => p[1] !== undefined),
  }));
  /* A hull nobody had before 1882 spent two thirds of this chart as empty
     floor, with the years that actually had ships crushed into the last
     third. The axis starts where the first one was launched and stops where
     the last one was still afloat, so the span the hull existed for is the
     span the chart draws. Doing it off the plotted points rather than off a
     date in the tech tree also covers the other end: a hull every navy has
     since scrapped stops the axis there instead of trailing off flat. */
  const seen = [].concat(...series.map(x => x.pts.map(pt => pt[0])));
  const lo = seen.length ? Math.min(...seen) : xMin;
  const hi = seen.length ? Math.max(...seen) : xMax;
  // No padding either side: the first reading sits on the vertical axis and
  // the last on the right edge, the way it does on every other chart here.
  const a = lo, b = hi;
  const xOf = y => M.l + (b === a ? 0.5 : (y - a) / (b - a)) * (W - M.l - M.r);
  plot(document.getElementById('chart'), {
    series,
    xOf, xTicks: yearTicks(a, b),
    hoverXs: saveHovers.filter(h => h.v >= a && h.v <= b),
    fmt: fmtCount, log: logScale, markers: true,
    readout: document.getElementById('readout'),
    idle: 'Hover the plot to read fleet sizes at a date.',
    emptyMsg: shown.length ? 'No ships of this type in these saves.' : 'Select a nation.',
  });
  const note = document.getElementById('fleetspan');
  const whole = !seen.length || (lo <= years[0] && hi >= years[years.length - 1]);
  note.hidden = whole;
  if (!whole) {
    const at = v => DATA.dates[years.indexOf(v)] || '';
    // Mods name hulls, so the article cannot be baked into the sentence.
    const name = type === '__all' ? 'ship' : gameName(type);
    const one = (/^[aeiou]/i.test(name) ? 'an ' : 'a ') + name;
    note.textContent = lo === hi
      ? `The ${at(lo)} save is the only one with ${one} in it.`
      : `Nobody in these saves held ${one} outside `
        + `${at(lo)} – ${at(hi)}, so the chart stops there.`;
  }
}

const fleetState = {key: 'total', dir: -1};
function drawFleetTable() {
  const date = fleetSave.value;
  const cols = [{key:'name', label:'Nation'}, {key:'total', label:'Ships'},
    {key:'heavy', label:'Heavy hulls'}, {key:'other', label:'Other hulls'},
    {key:'power', label:'Current power · est.', fmt: v => v == null ? '—' : fmtPower(v)}];
  const rows = milTags.map(tag => {
    const counts = (DATA.ships[tag] || {})[date] || {};
    const stats = navalStats(tag, date);
    const known = stats && Object.keys(counts).every(type => stats[type]);
    const total = shipCount(tag, date, '__all') || 0;
    const heavy = known ? Object.entries(counts).reduce((n, [type, count]) => n + (stats[type].heavy ? count : 0), 0) : null;
    return {tag, name:nameOf(tag), total, heavy, other:known ? total - heavy : null,
      power:known ? fleetPower([tag], date, false, true) : null,
      design:known ? fleetPower([tag], date, false, false) : null, counts};
  });
  renderStrengthLedger('fleettable', cols, rows, fleetState, row => [
    ['Fleet estimates', [['Current power', row.power == null ? 'Unavailable' : fmtPower(row.power)],
      ['Full-strength power', row.design == null ? 'Unavailable' : fmtPower(row.design)]]],
    ['Hull inventory', Object.entries(row.counts).filter(([,n]) => n).map(([type,n]) => [gameName(type),n])],
  ], 'Power estimates use hull and gun statistics. Current power incorporates recorded strength and experience where available, otherwise full-strength hull counts. These are comparative estimates, not predicted battle outcomes.');
}

/* One bar per save is one bar per year while a campaign is saved by hand, and
   a thicket the moment it is saved every month: nine hundred columns four
   pixels wide with their totals printed over each other. A year is the unit
   anyone reads a population by, so these charts keep the last save in each
   year and drop the rest. The run has the same shape and the bars have room
   to be labelled. */
const YEAR_DATES = (() => {
  const last = new Map();
  DATA.dates.forEach(d => last.set(d.split('.')[0], d));
  return [...last.values()];
})();

/* Which bars can carry a label without colliding with the one before: greedy
   from the left, and the final bar always gets one, since a chart whose last
   column is unlabelled asks the reader to count. Anything the greedy pass put
   too close to that final label gives way to it. */
function labelSlots(xs, gap) {
  const keep = [];
  for (let i = 0; i < xs.length - 1; i++)
    if (!keep.length || xs[i] - xs[keep[keep.length - 1]] >= gap) keep.push(i);
  if (xs.length) {
    while (keep.length && xs[xs.length - 1] - xs[keep[keep.length - 1]] < gap) keep.pop();
    keep.push(xs.length - 1);
  }
  return new Set(keep);
}

function stackedBars(svgId, legendId, byDate, keys, emptyMsg, populationTag = null, scopeTotals = null, filter = null) {
  const svg = document.getElementById(svgId);
  svg.textContent = '';
  const legend = document.getElementById(legendId);
  legend.textContent = '';
  const NW = 1000, NH = 360, NM = {t: 16, r: 20, b: 38, l: 70};
  const dates = YEAR_DATES;
  const available = keys.filter(k => dates.some(d => (byDate[d] || {})[k]));
  const used = filter?.key ? available.filter(k => k === filter.key) : available;
  const fullTotals = dates.map(d => available.reduce((sum, k) => sum + (byDate[d]?.[k] || 0), 0));
  const totals = dates.map(d =>
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

  const slot = (NW - NM.l - NM.r) / dates.length;
  const barW = Math.min(56, slot * 0.62);
  const mids = dates.map((d, i) => NM.l + slot * (i + 0.5));
  const yearSlots = labelSlots(mids, 30);
  const totalSlots = labelSlots(mids, 42);
  dates.forEach((d, i) => {
    const x = mids[i] - barW / 2;
    let y = NH - NM.b;
    used.forEach((k, si) => {
      const count = (byDate[d] || {})[k] || 0;
      if (!count) return;
      const h = count / peak * (NH - NM.t - NM.b);
      y -= h;
      const rect = el('rect', {x, y, width: barW, height: h,
        fill: seriesColour(populationTag ? DATA.popTypes.indexOf(k) : si), 'fill-opacity': .82,
        stroke: 'var(--ground)', 'stroke-width': .5});
      const title = document.createElementNS(SVGNS, 'title');
      title.textContent = `${d} · ${gameName(k)}: ${count.toLocaleString()}`;
      if (populationTag) {
        const total = scopeTotals ? scopeTotals[d] : DATA.facts[d]?.[populationTag]?.total_pop ?? fullTotals[i];
        title.textContent += total > 0 ? ` · ${(100 * count / total).toFixed(1)}% of ${scopeTotals ? "state" : "country"} population` : '';
      }
      rect.appendChild(title);
      if (filter) {
        rect.dataset.popType = k; rect.dataset.date = d;
        rect.setAttribute('tabindex', '0'); rect.setAttribute('role', 'button');
        rect.setAttribute('aria-pressed', filter.key === k);
        rect.setAttribute('aria-label', title.textContent + (filter.key === k ? '. Show all pop types.' : '. Show only this pop type.'));
        const select = () => filter.onSelect(filter.key === k ? null : k, k, d);
        rect.onclick = select;
        rect.onkeydown = event => {
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); }
        };
      }
      svg.appendChild(rect);
    });
    const mk = (txt, yy, size, fill) => {
      const t = el('text', {x: mids[i], y: yy, 'text-anchor': 'middle'});
      t.setAttribute('font-family', 'IBM Plex Mono, monospace');
      t.setAttribute('font-size', size); t.setAttribute('fill', fill);
      t.textContent = txt; svg.appendChild(t);
    };
    if (yearSlots.has(i)) mk(d.split('.')[0], NH - NM.b + 17, 10, '#C9AC80');
    if (totals[i] && totalSlots.has(i)) mk(fmtCount(totals[i]), y - 6, 10.5, '#F4E7CC');
  });

  available.forEach((k, si) => {
    const item = document.createElement('span');
    item.className = 'slegend';
    item.innerHTML = `<i style="background:${seriesColour(populationTag ? DATA.popTypes.indexOf(k) : si)}"></i>${gameName(k)}`;
    legend.appendChild(item);
  });
}

let focusedPopType = null;
function populationHistory(byDate, keys, emptyMsg, tag, totals = null) {
  if (focusedPopType && !YEAR_DATES.some(d => byDate[d]?.[focusedPopType])) focusedPopType = null;
  const svg = document.getElementById('popchart');
  svg.setAttribute('aria-label', focusedPopType ? gameName(focusedPopType) + ' population over time' : 'Pop sizes by type over time');
  stackedBars('popchart', 'poplegend', byDate, keys, emptyMsg, tag, totals, {
    key: focusedPopType,
    onSelect: (key, clicked, date) => {
      focusedPopType = key;
      populationHistory(byDate, keys, emptyMsg, tag, totals);
      const bars = [...svg.querySelectorAll('rect[data-pop-type]')];
      bars.find(bar => bar.dataset.popType === clicked && bar.dataset.date === date)?.focus({preventScroll:true});
    },
  });
}

/* =============== POPS =============== */
const popSave = document.getElementById('popsave');
DATA.dates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  popSave.appendChild(o);
});
popSave.value = DATA.lastDate;
popSave.onchange = () => { drawPopTable(); refreshPopulation(); };

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
    {key: 'name', label: 'Nation', render: r => nationIdentity(r.tag)},
    {key: 'total', label: 'Total pop', fmt: v => v.toLocaleString()},
    {key: 'accepted_pct', label: 'Accepted', fmt: v => v.toFixed(1) + '%'},
    /* The nation's own states, not its empire. A colony's pops are in the
       national average and drag it down without saying anything about the
       metropole -- Britain reads 52.5% with India in the figure and rather
       higher without. The column keeps the plain name because this is the
       reading somebody means by "how literate is this country"; the whole-
       empire figure is still on the chart above, as Average literacy. */
    {key: 'avg_literacy_stated', label: 'Literacy',
     fmt: v => (v * 100).toFixed(1) + '%',
     title: 'Literacy across the pops in this nation\u2019s own states, with '
          + 'its colonies left out. The same states the soldier counts use, so '
          + 'the two agree about what counts as our own. Average literacy on '
          + 'the chart above is the whole empire.'},
    {key: 'avg_militancy', label: 'Mil', fmt: v => v.toFixed(2)},
    {key: 'avg_consciousness', label: 'Con', fmt: v => v.toFixed(2)},
    ...used.map(pt => ({key: pt, label: gameName(pt), fmt: cell})),
  ];
  const rows = DATA.tags.map(tag => {
    const at = (DATA.pops[tag] || {})[date] || {};
    const f = facts[tag] || {};
    const row = {
      tag, name: nameOf(tag),
      total: f.total_pop || 0,
      accepted_pct: f.accepted_pct || 0,
      avg_literacy_stated: f.avg_literacy_stated || 0,
      avg_militancy: f.avg_militancy || 0,
      avg_consciousness: f.avg_consciousness || 0,
    };
    used.forEach(pt => row[pt] = at[pt] || 0);
    return row;
  }).filter(r => r.total > 0 && populationMatches(r.tag));
  renderTable(document.getElementById('poptable'), cols, rows, popState,
              row => openPopulationCountry(row.tag));
  filterPopulationTable();
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
    culture: cultureName(culture), key: culture, size, accepted,
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

const drawPopChart = () => populationHistory(
  DATA.pops[popTag.value] || {}, DATA.popTypes,
  nameOf(popTag.value) + ' has no pops in these saves.', popTag.value);

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
  items: [...DATA.goods].sort(byGameName),
  labelFor: g => gameName(g),
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
  const by = DATA.prices[good] || [];
  const pts = [];
  let base = null;
  for (let i = 0; i < PD.length; i++) {
    let v = by[i];
    if (v == null) continue;
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
  plot(document.getElementById('pricechart'), {
    series: shown.map(g => ({name: gameName(g), colour: goodColour(g),
                             pts: priceSeries(g)})),
    xOf: pxOf, xTicks: yearTicks(pxMin, pxMax),
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

/* A good that records no sale in any save is not traded on the market at all.
   Precious metal is the standing example: the engine turns it straight into
   money at the mint rather than putting it up for sale, so its supply is real
   and its sales are always nil. Reading that as "100% unsold, for ever" would
   put it at the top of every glut list and say nothing. */
const NEVER_SOLD = new Set(DATA.goods.filter(g =>
  DATA.snapshotDates.every(d => !(((DATA.snapshot[d] || {})[g]) || {}).actual_sold)));
const unsoldShare = (good, snap) =>
  (!snap || !snap.supply || NEVER_SOLD.has(good)) ? null
    : Math.max(0, (snap.supply - snap.actual_sold) / snap.supply * 100);

const snapSel = document.getElementById('snapsel');
DATA.snapshotDates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  snapSel.appendChild(o);
});
if (DATA.snapshotDates.length)
  snapSel.value = DATA.snapshotDates[DATA.snapshotDates.length - 1];
snapSel.onchange = drawMarketTable;

const MARKET_COLS = [
  {key: 'good', label: 'Good', fmt: gameName, sortBy: r => gameName(r.good),
   colour: r => goodColour(r.good)},
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
  {key: 'unsold', label: 'Unsold', fmt: v => v == null ? '—' : v.toFixed(0) + '%',
   title: "The share of the day's supply nobody bought. A good left on the "
        + 'quayside is being overproduced whatever its demand figure says, '
        + 'which matters in a mod where one nation stands ready to buy the '
        + "world's surplus.",
   cls: r => r.unsold == null ? '' : r.unsold > 25 ? 'down' : r.unsold < 2 ? 'up' : ''},
  {key: 'pegged', label: 'Pegged', fmt: v => v ? 'yes' : '—',
   title: 'A buyer with no limit is standing in this good\'s market: demand is '
        + 'recorded as something on the order of a billion, which no economy '
        + 'produces. Every pegged reading in these saves sits at exactly five '
        + "times the good's base cost, the engine's price ceiling -- so the price "
        + 'says nothing about whether the good is scarce or drowning.',
   cls: r => r.pegged ? 'down' : ''},
];
const marketState = {key: 'change', dir: -1};
function drawMarketTable() {
  const date = snapSel.value;
  document.getElementById('snapdate').textContent = date || '—';
  const snap = DATA.snapshot[date] || {};
  const rows = Object.keys(snap).map(good => {
    const by = DATA.prices[good] || [];
    const seen = [];
    for (let i = 0; i < PD.length; i++) if (by[i] != null) seen.push(i);
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
      unsold: unsoldShare(good, snap[good]),
      pegged: snap[good].pegged,
      discovered: snap[good].discovered,
    };
  }).filter(r => r.discovered);
  renderTable(document.getElementById('market'), MARKET_COLS, rows, marketState,
              row => { goodsPicker.set([row.good]); showProducers(row.good, date); });
}

/* =============== WHO PRODUCES IT ===============
   Each country block carries `saved_country_supply`: what that nation put on
   the world market. Added up over every nation it comes back to the market's
   own supply pool, which is what makes it production as the market sees it
   rather than a stockpile or an income.

   Overproduction is the thing worth finding here, and demand is a poor guide
   to it. A mod with a nation that stands ready to buy any surplus -- IGoR's
   world bank -- keeps demand permanently above supply for goods that are
   plainly drowning, so the honest signals are elsewhere: how much of the day's
   supply went unsold, and how far the price has sunk below the good's own base
   cost. Both are in the table above; this names who is doing it. */
const SUPPLY = DATA.supply || {};

const prodSave = document.getElementById('prodsave');
const prodGood = document.getElementById('prodgood');
const prodDates = DATA.dates.filter(d => Object.values(SUPPLY).some(by => by[d]));
prodDates.forEach(d => {
  const o = document.createElement('option'); o.value = d; o.textContent = d;
  prodSave.appendChild(o);
});
if (prodDates.length) prodSave.value = prodDates[prodDates.length - 1];
prodSave.onchange = drawSupply;

const prodGoods = DATA.goods.filter(g => SUPPLY[g]).sort(byGameName);
prodGoods.forEach(g => {
  const o = document.createElement('option'); o.value = g;
  o.textContent = gameName(g);
  prodGood.appendChild(o);
});
prodGood.onchange = drawSupply;
// Open on whatever the world makes most of, which is a good with enough
// suppliers to be worth a chart rather than whatever sorts first.
if (prodGoods.length) {
  const at = prodDates[prodDates.length - 1];
  prodGood.value = prodGoods.slice().sort((a, b) =>
    ((SUPPLY[b][at] || {}).t || 0) - ((SUPPLY[a][at] || {}).t || 0))[0];
}

/* Jump the panel to one good -- a click in the market table means that good. */
function showProducers(good, date) {
  if (!SUPPLY[good]) return;
  prodGood.value = good;
  if (date && prodDates.includes(date)) prodSave.value = date;
  drawSupply();
}

function drawSupply() {
  const svg = document.getElementById('prodchart');
  svg.textContent = '';
  const note = document.getElementById('prodnote');
  const readout = document.getElementById('prodreadout');
  const date = prodSave.value, good = prodGood.value;
  document.getElementById('proddate').textContent = date || '\u2014';
  const rec = (SUPPLY[good] || {})[date];
  const PW = 1000, PH = 430;
  if (!rec || !rec.t) {
    const t = el('text', {x: PW / 2, y: PH / 2, 'text-anchor': 'middle', fill: '#C9AC80',
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 14});
    t.textContent = prodDates.length
      ? `Nobody supplied ${good ? gameName(good) : 'this good'} at ${date}.`
      : 'These saves carry no per-nation supply.';
    svg.appendChild(t);
    readout.textContent = '';
    note.textContent = '';
    return;
  }

  const named = rec.n.reduce((sum, pair) => sum + pair[1], 0);
  const rest = rec.t - named;
  const bars = rec.n.map(pair => ({tag: pair[0], value: pair[1], colour: colourFor(pair[0])}));
  // Everyone the payload did not name, kept as one bar so the shares still add
  // up to the world's supply instead of quietly to less than it.
  if (rest > rec.t * 0.005)
    bars.push({tag: '', value: rest, colour: 'var(--grid)', rest: true});

  const snap = (DATA.snapshot[date] || {})[good] || {};
  const base = (DATA.basePrices || {})[good];
  const unsold = unsoldShare(good, snap);

  const left = 132, right = 156, top = 58, bottom = 14;
  const rowH = Math.min(26, (PH - top - bottom) / Math.max(1, bars.length));
  const barH = Math.max(6, rowH - 7);
  const peak = Math.max(...bars.map(b => b.value));
  const spanX = PW - left - right;
  const at = v => v / (peak || 1) * spanX;

  const head = el('text', {x: left, y: 28, fill: 'var(--ink)',
    'font-family': 'Barlow Condensed, sans-serif', 'font-size': 22, 'font-weight': 600});
  head.textContent = gameName(good);
  svg.appendChild(head);
  const sub = el('text', {x: left, y: 47, fill: 'var(--ink-dim)',
    'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
  sub.textContent = `world supply ${fmtCount(rec.t)}`
    + (snap.actual_sold !== undefined ? ` \u00b7 sold ${fmtCount(snap.actual_sold)}` : '')
    + (unsold !== null ? ` \u00b7 ${unsold.toFixed(0)}% unsold` : '')
    + (snap.price !== undefined ? ` \u00b7 price ${snap.price.toFixed(2)}` : '')
    + (base ? ` \u00b7 ${((snap.price - base) / base * 100).toFixed(0)}% vs base` : '')
    + (snap.pegged ? ' \u00b7 price pegged at its ceiling' : '');
  svg.appendChild(sub);

  const tell = bar => {
    const share = bar.value / rec.t * 100;
    readout.innerHTML =
      `<span class="rk">${bar.rest ? 'everyone else' : nameOf(bar.tag)}</span>`
      + `<span><b style="color:${bar.rest ? 'var(--ink)' : colourFor(bar.tag)}">`
      + `${fmtCount(bar.value)}</b> <span class="rk">of ${fmtCount(rec.t)}</span></span>`
      + `<span><span class="rk">share</span> <b>${share.toFixed(1)}%</b></span>`
      + (bar.rest ? '<span class="rk">every supplier outside the top '
                    + `${rec.n.length}</span>` : '');
  };

  bars.forEach((bar, i) => {
    const y = top + i * rowH;
    const w = Math.max(1, at(bar.value));
    const label = el('text', {x: left - 10, y: y + barH * 0.5 + 4, 'text-anchor': 'end',
      fill: bar.rest ? 'var(--ink-dim)' : colourFor(bar.tag),
      'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
    label.textContent = bar.rest ? 'everyone else' : bar.tag;
    svg.appendChild(label);

    const rect = el('rect', {x: left, y, width: w, height: barH,
      fill: bar.colour, 'fill-opacity': bar.rest ? .35 : .82,
      stroke: 'var(--ground)', 'stroke-width': .5});
    rect.style.cursor = 'pointer';
    rect.onpointerenter = () => { rect.setAttribute('fill-opacity', 1); tell(bar); };
    rect.onpointerleave = () => rect.setAttribute('fill-opacity', bar.rest ? .35 : .82);
    const title = document.createElementNS(SVGNS, 'title');
    title.textContent = `${bar.rest ? 'everyone else' : nameOf(bar.tag)}: `
      + `${fmtCount(bar.value)} (${(bar.value / rec.t * 100).toFixed(1)}%)`;
    rect.appendChild(title);
    svg.appendChild(rect);

    const value = el('text', {x: left + w + 8, y: y + barH * 0.5 + 4,
      fill: 'var(--ink)', 'font-family': 'IBM Plex Mono, monospace', 'font-size': 11});
    value.textContent =
      `${fmtCount(bar.value)}   ${(bar.value / rec.t * 100).toFixed(1)}%`;
    svg.appendChild(value);
  });

  const three = rec.n.slice(0, 3).reduce((sum, pair) => sum + pair[1], 0);
  const idle = `<span class="rk">${bars.length} bars</span>`
    + `<span><span class="rk">largest</span> <b style="color:${colourFor(rec.n[0][0])}">`
    + `${rec.n[0][0]}</b> <span class="rk">`
    + `${(rec.n[0][1] / rec.t * 100).toFixed(1)}%</span></span>`
    + `<span><span class="rk">top three</span> <b>${(three / rec.t * 100).toFixed(1)}%</b></span>`
    + (unsold !== null ? `<span><span class="rk">unsold</span> <b>${unsold.toFixed(0)}%</b></span>` : '');
  svg.onpointerleave = () => readout.innerHTML = idle;
  readout.innerHTML = idle;

  note.textContent = 'Choose a good and save; hover a bar to see a nation’s contribution to world supply.';
}

/* =============== MAP =============== */
const MAP = DATA.map;
let mapTags = null;          // null means every nation
let mapHatchOccupied = true;
let mapShowProvinceBorders = false;
/* Contested tiles are always marked. It was a toggle while the rule was a
   guess about recent battles and worth being able to switch off; now that it
   is simply "enemies are standing here", there is nothing to disbelieve. */
const mapShowBattles = true;
let mapProv = null;          // province id for every pixel
let mapOwners = null;        // date -> {own: Map, occ: Map}
let mapDots = [];            // what is currently drawn, for hit testing
let mapCrowded = 0;          // counters held back because one was already there
let mapOccAny = false;
let mapStopPlay = () => {};  // set once the controls exist
let mapZoom = 1;             // 1 fits the whole world to the panel width
let mapOX = 0, mapOY = 0;    // map coordinate sitting at the panel's top left
let mapPinned = null;        // a marker clicked, so the readout stays put

function mapDecoded() {
  if (!mapProv) { mapProv = mapDecode(); mapOwners = mapOwnerTables(); }
}

/* A colour in the byte order `putImageData` actually reads.

   The canvas buffer is bytes R,G,B,A, so on a little-endian machine one 32-bit
   store must carry them reversed. Every machine this runs on is little-endian,
   but the order is derived rather than assumed: a single pixel is written
   through the byte view and read back through the word view, once. */
let mapEndian = 0;
function mapWord(rgb) {
  if (!mapEndian) {
    const probe = new Uint8ClampedArray(4);
    probe[0] = 1;
    mapEndian = new Uint32Array(probe.buffer)[0] === 1 ? 1 : 2;
  }
  return mapEndian === 1
    ? (0xFF000000 | ((rgb & 255) << 16) | (rgb & 0xFF00) | ((rgb >> 16) & 255))
    : (((rgb & 0xFFFFFF) << 8) | 0xFF);
}

/* A palette converted once, with the unclaimed-land colour on the end. */
function mapWords(table, wild) {
  const out = new Uint32Array(table.length + 1);
  for (let i = 0; i < table.length; i++) out[i] = mapWord(table[i]);
  out[table.length] = mapWord(wild);
  return out;
}

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
const MAP_WATER = [30, 47, 61], MAP_WILD = [112, 108, 88], MAP_EDGE = [35, 32, 28];
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

// Match the theatre map's softer land colours without changing marker colours.
function mapLandColour(hex) {
  const rgb = parseInt(hex.slice(1), 16);
  const soften = v => Math.round(v * .65 + 45);
  return (soften((rgb >> 16) & 255) << 16)
    | (soften((rgb >> 8) & 255) << 8) | soften(rgb & 255);
}

function mapPalette(date) {
  const book = mapOwners[date] || {own: new Map(), occ: new Map()};
  const owners = new Map(book.own);
  let top = 0;
  mapSea.forEach(p => { if (p > top) top = p; });
  owners.forEach((_i, p) => { if (p > top) top = p; });
  const table = new Int32Array(top + 1);
  const wild = (MAP_WILD[0] << 16) | (MAP_WILD[1] << 8) | MAP_WILD[2];
  const water = (MAP_WATER[0] << 16) | (MAP_WATER[1] << 8) | MAP_WATER[2];
  for (let p = 0; p <= top; p++) table[p] = mapSea.has(p) ? water : wild;
  owners.forEach((idx, pid) => {
    const hex = MAP.colours[MAP.tags[idx]];
    if (hex) table[pid] = mapLandColour(hex);
  });
  return table;
}

/* Who is holding land that belongs to somebody else, as a colour per province
   and -1 for everywhere nobody is. Kept apart from the owner table because
   occupation is drawn over the top rather than instead: shading occupied ground
   in the occupier's colour made a siege and an annexation look identical. */
function mapOccPalette(date) {
  const book = mapOwners[date] || {own: new Map(), occ: new Map()};
  let top = 0;
  book.occ.forEach((_i, p) => { if (p > top) top = p; });
  const table = new Int32Array(top + 1).fill(-1);
  book.occ.forEach((idx, pid) => {
    const hex = MAP.colours[MAP.tags[idx]];
    if (hex) table[pid] = parseInt(hex.slice(1), 16);
  });
  return table;
}

/* Fixed province-index levels never depend on the date or the camera. Each
   level halves both dimensions; a 2x2 majority keeps coastlines and small
   provinces steadier than sampling one pixel. Odd raster edges are retained. */
const mapLevels = [];
let mapMaxProvince = 0;
function mapLevel(level) {
  if (!mapLevels.length) {
    mapDecoded();
    for (const p of mapProv) if (p > mapMaxProvince) mapMaxProvince = p;
    mapLevels.push({w:MAP.w, h:MAP.h, prov:mapProv, step:1});
  }
  while (mapLevels.length <= level) {
    const prev = mapLevels[mapLevels.length - 1];
    const w = Math.ceil(prev.w / 2), h = Math.ceil(prev.h / 2);
    const prov = new Int32Array(w * h);
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = y * 2 * prev.w + x * 2;
      const right = x * 2 + 1 < prev.w, down = y * 2 + 1 < prev.h;
      const a = prev.prov[i], b = right ? prev.prov[i+1] : a;
      const c = down ? prev.prov[i+prev.w] : a;
      const d = down ? (right ? prev.prov[i+prev.w+1] : c) : b;
      prov[y*w+x] = b === c || b === d ? b : c === d ? c : a;
    }
    mapLevels.push({w,h,prov,step:prev.step*2});
  }
  return mapLevels[level];
}

/* Only visible tiles are coloured. A bounded LRU holds both layers across
   pans and zoom steps; ownership changes discard coloured tiles, not geometry.
   Borders read neighbouring province owners directly, including across tile
   seams: playback never scans the full world to find political boundaries. */
const MAP_TILE_SIZE = 256, MAP_TILE_LIMIT = 128;
const mapTiles = new Map();
let mapTileDate = null, mapTilePalette = null;
function mapSameValues(a,b) {
  if (!a || a.length!==b.length) return false;
  for (let i=0;i<a.length;i++) if (a[i]!==b[i]) return false;
  return true;
}
function mapTileState(date) {
  if (mapTileDate === date) return mapTilePalette;
  mapLevel(0);
  const colours = mapPalette(date), occupation = mapOccPalette(date);
  const owners = (mapOwners[date] || {own:new Map()}).own;
  const identity = new Int32Array(mapMaxProvince + 1).fill(-1);
  for (const p of mapSea) identity[p] = -2;
  for (const [p, owner] of owners) if (!mapSea.has(p)) identity[p] = owner;
  // Most saves move armies without changing the political raster. Retain the
  // tiles when ownership and occupation are identical, using exact comparison
  // rather than a hash that could leave a stale border after a collision.
  if (!mapTilePalette || !mapSameValues(mapTilePalette.identity,identity)
      || !mapSameValues(mapTilePalette.occupation,occupation)) mapTiles.clear();
  mapTilePalette = {
    colours:mapWords(colours, (MAP_WILD[0]<<16)|(MAP_WILD[1]<<8)|MAP_WILD[2]),
    colourCount:colours.length, occupation,
    occupied:mapWords(occupation,0), identity,
    edge:mapWord((MAP_EDGE[0]<<16)|(MAP_EDGE[1]<<8)|MAP_EDGE[2]),
  };
  mapOccAny = occupation.some(c => c >= 0);
  mapTileDate = date;
  return mapTilePalette;
}

function mapTile(level, tx, ty, palette, occupied) {
  const key = `${level}|${tx}|${ty}|${mapShowProvinceBorders}|${occupied}`;
  let tile = mapTiles.get(key);
  if (tile) { mapTiles.delete(key); mapTiles.set(key,tile); return tile; }
  const idx = mapLevel(level), x0 = tx*MAP_TILE_SIZE, y0 = ty*MAP_TILE_SIZE;
  const w = Math.min(MAP_TILE_SIZE,idx.w-x0), h = Math.min(MAP_TILE_SIZE,idx.h-y0);
  const base = document.createElement('canvas'); base.width=w; base.height=h;
  const ctx = base.getContext('2d'), img = ctx.createImageData(w,h);
  const pixels = new Uint32Array(img.data.buffer);
  const occImg = occupied ? ctx.createImageData(w,h) : null;
  const occPixels = occImg ? new Uint32Array(occImg.data.buffer) : null;
  const {identity,colours,colourCount,occupation} = palette;
  for (let y=0; y<h; y++) for (let x=0; x<w; x++) {
    const i=(y0+y)*idx.w+x0+x, dst=y*w+x, p=idx.prov[i];
    const right=x0+x+1<idx.w ? idx.prov[i+1] : p;
    const down=y0+y+1<idx.h ? idx.prov[i+idx.w] : p;
    const boundary=p!==right || p!==down;
    const edge=boundary && (mapShowProvinceBorders
      || identity[p]!==identity[right] || identity[p]!==identity[down]);
    pixels[dst]=edge ? palette.edge : colours[p<colourCount ? p : colourCount];
    if (occPixels && !edge && p<occupation.length && occupation[p]>=0) occPixels[dst]=palette.occupied[p];
  }
  ctx.putImageData(img,0,0);
  let occ=null;
  if (occImg) {
    occ=document.createElement('canvas'); occ.width=w; occ.height=h;
    occ.getContext('2d').putImageData(occImg,0,0);
  }
  tile={base,occ}; mapTiles.set(key,tile);
  if (mapTiles.size>MAP_TILE_LIMIT) mapTiles.delete(mapTiles.keys().next().value);
  return tile;
}

function mapPaintTiles(ctx, sc, date, s, cw, ch, dpr) {
  // Choose a stable resolution near physical screen pixels, not an arbitrary
  // zoom=1 special case. Cap density at 2 for bounded work on high-DPI screens.
  let level=Math.max(0,Math.floor(Math.log2(1/(s*Math.min(dpr,2)))));
  const maxLevel=Math.ceil(Math.log2(Math.max(MAP.w,MAP.h)));
  level=Math.min(level,maxLevel);
  const x0=Math.max(0,mapOX), y0=Math.max(0,mapOY);
  const x1=Math.min(MAP.w,mapOX+cw/s), y1=Math.min(MAP.h,mapOY+ch/s);
  if (x1<=x0 || y1<=y0) return;
  // Keep the visible working set below the cache limit even on huge displays.
  while (level<maxLevel) {
    const span=MAP_TILE_SIZE*2**level;
    const count=(Math.ceil(x1/span)-Math.floor(x0/span))*(Math.ceil(y1/span)-Math.floor(y0/span));
    if (count<=MAP_TILE_LIMIT/2) break;
    level++;
  }
  const idx=mapLevel(level), step=idx.step;
  const palette=mapTileState(date);
  const firstX=Math.floor(x0/step/MAP_TILE_SIZE), firstY=Math.floor(y0/step/MAP_TILE_SIZE);
  const endX=Math.ceil(x1/step/MAP_TILE_SIZE), endY=Math.ceil(y1/step/MAP_TILE_SIZE);
  // Align shared edges to device pixels and use nearest sampling. This avoids
  // translucent hairlines between tiles and keeps boundaries crisp at any zoom.
  ctx.imageSmoothingEnabled=false;
  if(sc) sc.imageSmoothingEnabled=false;
  for(let ty=firstY;ty<endY;ty++) for(let tx=firstX;tx<endX;tx++) {
    const tile=mapTile(level,tx,ty,palette,!!sc);
    const lx=tx*MAP_TILE_SIZE, ly=ty*MAP_TILE_SIZE;
    const sx=Math.max(0,x0/step-lx), sy=Math.max(0,y0/step-ly);
    const ex=Math.min(tile.base.width,x1/step-lx), ey=Math.min(tile.base.height,y1/step-ly);
    const dx=Math.round(((lx+sx)*step-mapOX)*s*dpr)/dpr;
    const dy=Math.round(((ly+sy)*step-mapOY)*s*dpr)/dpr;
    const dw=Math.round(((lx+ex)*step-mapOX)*s*dpr)/dpr-dx;
    const dh=Math.round(((ly+ey)*step-mapOY)*s*dpr)/dpr-dy;
    ctx.drawImage(tile.base,sx,sy,ex-sx,ey-sy,dx,dy,dw,dh);
    if(sc) sc.drawImage(tile.occ,sx,sy,ex-sx,ey-sy,dx,dy,dw,dh);
  }
}

/* One tile of diagonal stripes, built once and used as a mask on the screen
   rather than painted into the map. On the screen the hatching keeps the same
   width however far the map is zoomed; baked into a 5,616-pixel raster, one
   stripe would be a hair at zoom 1 and half a province at zoom 24. */
let mapHatchTile = null;
let mapHatchFill = null;     // the CanvasPattern, which outlives the frame
function mapHatchPattern(ctx) {
  if (mapHatchFill) return mapHatchFill;
  if (!mapHatchTile) {
    const p = 9, ink = 3;
    mapHatchTile = document.createElement('canvas');
    mapHatchTile.width = mapHatchTile.height = p;
    const t = mapHatchTile.getContext('2d');
    const img = t.createImageData(p, p);
    for (let y = 0; y < p; y++) {
      for (let x = 0; x < p; x++) {
        const o = (y * p + x) * 4;
        img.data[o] = img.data[o + 1] = img.data[o + 2] = 255;
        // x + y wraps cleanly at the tile edge, so the stripes join up.
        // Three pixels on and six off, rather than the five and four it began
        // as: the occupier has to be legible, but it is the owner's province
        // and the owner's colour should still be the one the eye lands on.
        img.data[o + 3] = ((x + y) % p) < ink ? 255 : 0;
      }
    }
    t.putImageData(img, 0, 0);
  }
  // Held rather than remade each frame. A pattern is bound to the canvas that
  // created it, and the scratch canvas is kept, so one lasts as long as it.
  mapHatchFill = ctx.createPattern(mapHatchTile, 'repeat');
  return mapHatchFill;
}

/* A screen-sized canvas to build the hatched layer in, since masking with
   `destination-in` eats whatever else is on the canvas it runs on. */
let mapScratchCanvas = null;
function mapScratch(w, h) {
  if (!mapScratchCanvas) mapScratchCanvas = document.createElement('canvas');
  if (mapScratchCanvas.width !== w || mapScratchCanvas.height !== h) {
    mapScratchCanvas.width = w;
    mapScratchCanvas.height = h;
    // Resizing a canvas resets its context, so the pattern made from the old
    // one is no longer usable and has to be made again.
    mapHatchFill = null;
  }
  return mapScratchCanvas;
}

function mapFit(cw) {        // screen pixels per map pixel at zoom 1
  if (cw === undefined) {
    const canvas = document.getElementById('mapcanvas');
    cw = canvas.clientWidth || MAP.w;
  }
  return cw / MAP.w;
}

function mapClamp(cw, ch) {
  const canvas = document.getElementById('mapcanvas');
  // Reading `clientWidth` makes the browser settle the layout before it can
  // answer. The render already knows the size, so it passes it in rather than
  // asking again twice.
  if (cw === undefined) cw = canvas.clientWidth || MAP.w;
  if (ch === undefined) ch = canvas.clientHeight || MAP.h;
  const s = mapFit(cw) * mapZoom;
  const viewW = cw / s;
  const viewH = ch / s;
  mapOX = viewW >= MAP.w ? (MAP.w - viewW) / 2
                         : Math.min(Math.max(mapOX, 0), MAP.w - viewW);
  mapOY = viewH >= MAP.h ? (MAP.h - viewH) / 2
                         : Math.min(Math.max(mapOY, 0), MAP.h - viewH);
}

/* Provinces the last mapStacks() could not place, so the readout can own up
   to an under-drawn map instead of quietly showing a fraction of the army.
   With the base-game fallback in the mod loader this should stay at zero. */
let mapUnplaced = 0, mapUnplacedBrigades = 0;

/* The dots do not move when the map does. Panning changes where each one is
   drawn, not which ones there are or what is in them, so the grouping is kept
   until the save or the nation picker changes it -- the two things that can. */
let mapStackCache = null;
/* Who was at war with whom on a given date.

   The first version of this marked provinces where a *battle* was recorded in
   the interval before the save, which was wrong in both directions: a battle
   fought last month leaves nobody on the tile today, so peaceful garrisons got
   crossed swords, and a siege that has been grinding for a year without a
   pitched battle in that particular fortnight got nothing.

   What the map can say honestly is who is standing where. Two nations on one
   tile who are on opposite sides of a war that is running are fighting -- that
   is what being on the same tile as an enemy means in this game. It needs no
   guess about timing, and it cannot mark an empty province.

   Built once, since the wars do not depend on the view. */
let mapWarBook = null;
function mapEnemiesAt(date) {
  if (!mapWarBook) {
    const num = d => {
      const p = String(d).split('.');
      return (+p[0]) * 10000 + (+(p[1] || 1)) * 100 + (+(p[2] || 1));
    };
    mapWarBook = [];
    for (const w of (DATA.wars || [])) {
      if (!w.attackers.length || !w.defenders.length) continue;
      mapWarBook.push({
        from: w.start ? num(w.start) : 0,
        to: w.active || !w.end ? Infinity : num(w.end),
        a: new Set(w.attackers), d: new Set(w.defenders),
      });
    }
    mapWarBook.num = num;
  }
  const n = mapWarBook.num(date);
  return mapWarBook.filter(w => w.from <= n && n <= w.to);
}

/* The stacks on a contested tile, split into the two armies facing each other.

   Blending them was the thing that made a contested counter useless: "138k"
   over a province where 82k are besieging 56k says nothing anyone wants to
   know, and the band across the counter put the two sides' colours next to
   each other with no line between what they meant. Each side gets its own
   box and its own total; whoever is not in the war at all -- a neutral with
   troops parked in the middle -- keeps a box of their own on the end. */
function mapSides(stacks, fight) {
  if (!fight) return null;
  const bag = t => fight.a.includes(t) ? 0 : fight.d.includes(t) ? 1 : 2;
  const out = [[], [], []];
  for (const st of stacks) out[bag(st.tag)].push(st);
  return out.filter(g => g.length).map(g => ({
    stacks: g,
    men: g.reduce((n, a) => n + a.men, 0),
    n: g.reduce((n, a) => n + a.n, 0),
  }));
}

/* Are any two of these nations on opposite sides of a war running now? */
function mapContested(tags, wars) {
  if (tags.length < 2) return null;
  for (const w of wars) {
    const left = tags.filter(t => w.a.has(t));
    const right = tags.filter(t => w.d.has(t));
    if (left.length && right.length) return {a: left, d: right, war: w};
  }
  return null;
}

function mapStacks(date) {
  const stamp = date + '|' + (mapTags === null ? '*' : mapTags.join(','));
  if (mapStackCache && mapStackCache.stamp === stamp) {
    mapUnplaced = mapStackCache.unplaced;
    mapUnplacedBrigades = mapStackCache.unplacedBrigades;
    return mapStackCache.dots;
  }
  const armies = (MAP.armies || {})[date] || {};
  const wars = mapEnemiesAt(date);
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
      .map(a => ({tag: MAP.tags[a[0]], n: a[1], mix: a[2],
                  // Reports written before strength was carried have three
                  // entries and no men in them; those fall back to regiments
                  // at full strength rather than reading as empty.
                  men: a.length > 3 ? a[3] : a[1] * 1000,
                  menMix: a.length > 4 ? a[4] : ''}))
      .filter(a => !wanted || wanted.has(a.tag));
    if (!stacks.length) continue;
    stacks.sort((a, b) => b.men - a.men);
    const fight = mapContested(stacks.map(a => a.tag), wars);
    dots.push({x: spot[0], y: spot[1], pid: +pid, stacks,
               total: stacks.reduce((s, a) => s + a.n, 0),
               men: stacks.reduce((s, a) => s + a.men, 0),
               fighting: fight,
               sides: mapSides(stacks, fight)});
  }
  dots.sort((a, b) => b.total - a.total);   // small stacks draw last, on top
  mapStackCache = {stamp, dots, unplaced: mapUnplaced,
                   unplacedBrigades: mapUnplacedBrigades};
  return dots;
}

/* A pointer or a wheel reports far more often than the screen redraws -- a
   120Hz trackpad or a high-rate mouse will fire several times between frames,
   and each one used to repaint. Every repaint past the first was thrown away
   unseen, and with occupation on each costs a second scaled blit of the raster
   plus a full-canvas mask, so the queue fell behind and the map dragged.

   Coalescing to one repaint per animation frame draws exactly what gets shown.
   The one-off callers -- picking a save, toggling a layer, clicking a marker --
   still call `mapRender` directly, since there is no storm to smooth there. */
let mapFrame = 0;
function mapRenderSoon() {
  if (mapFrame) return;
  mapFrame = requestAnimationFrame(() => { mapFrame = 0; mapRender(); });
}

/* Everyone alive at this save, land nobody owns included.

   Summing the nations would have been easier and would have been wrong: pops
   on land nobody has colonised yet belong to no nation, and they are 6.4% of
   the world in 1836 and none of it by 1908. A total built that way would climb
   as the map was carved up and read as people being born. */
function mapWorldPop(date) {
  const el = document.getElementById('mapworld');
  if (!el) return;
  const n = (DATA.worldPop || {})[date];
  if (!n) { el.textContent = ''; return; }
  const first = (DATA.worldPop || {})[DATA.dates[0]] || 0;
  const since = first && n !== first
    ? '  ' + (n > first ? '+' : '−')
      + Math.abs((n / first - 1) * 100).toFixed(1) + '% since ' + DATA.dates[0]
    : '';
  el.textContent = '·  world population ' + n.toLocaleString() + since;
}

function mapRender() {
  if (!MAP) return;
  const canvas = document.getElementById('mapcanvas');
  const date = document.getElementById('mapsave').value || DATA.lastDate;
  document.getElementById('mapdate').textContent = date;
  mapWorldPop(date);          // beside the date it was counted on
  mapTileState(date);

  const dpr = window.devicePixelRatio || 1;
  const cw = canvas.clientWidth || MAP.w, ch = canvas.clientHeight || MAP.h;
  if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) {
    canvas.width = Math.round(cw * dpr);
    canvas.height = Math.round(ch * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  // Extend the ocean into the space around the fitted map in a tall atlas.
  ctx.fillStyle = `rgb(${MAP_WATER.join(',')})`;
  ctx.fillRect(0, 0, cw, ch);

  mapClamp(cw, ch);
  const s = mapFit(cw) * mapZoom;
  const scratch = mapHatchOccupied && mapOccAny ? mapScratch(canvas.width,canvas.height) : null;
  const sc = scratch ? scratch.getContext('2d') : null;
  if (sc) {
    sc.setTransform(dpr,0,0,dpr,0,0);
    sc.clearRect(0,0,cw,ch);
  }
  mapPaintTiles(ctx,sc,date,s,cw,ch,dpr);
  if (sc) {
    sc.globalCompositeOperation='destination-in';
    sc.fillStyle=mapHatchPattern(sc);
    sc.fillRect(0,0,cw,ch);
    sc.globalCompositeOperation='source-over';
    ctx.drawImage(scratch,0,0,cw,ch);
  }

  mapDots = mapStacks(date);
  // markers grow with zoom, but slower than the map, so a dense theatre thins
  // out as you go in instead of turning into one blob
  const grow = Math.pow(mapZoom, 0.45);
  const labelled = [];
  /* Province anchors in a dense theatre are closer together than a counter is
     wide, so two of them land on top of each other and neither number can be
     read -- which is what made the map look broken rather than busy. The
     stacks are drawn biggest first, and one that would cover a counter already
     placed is held back rather than drawn over it. Nothing is lost: the count
     of what is holding back is put on the readout, and zooming separates the
     anchors until they all fit, since counters grow slower than the map. */
  const placed = [];
  mapCrowded = 0;
  for (const dot of mapDots) {
    dot.sx = (dot.x - mapOX) * s;
    dot.sy = (dot.y - mapOY) * s;
    /* Every counter the same size -- sizing them by strength meant a big army
       drew a block several times the width of its neighbours, which buried
       them and made adjacent provinces collide. The number inside says how
       big the stack is, and says it exactly rather than by area.

       What the size does carry is how much detail there is room for. Zoomed
       out the counter is a small mark that answers "who has troops, and
       where"; zoomed in it grows into a block with the strength written in
       it. So it starts smaller than it used to and grows faster. */
    const half = Math.max(2.2, Math.min(14, 2.9 * Math.pow(mapZoom, 0.72)));
    dot.sr = half;                      // hit testing still works in radii
    const hw = half * 1.7, hh = half * 0.95;
    dot.hw = hw; dot.hh = hh;
    if (dot.sx < -30 || dot.sy < -30 || dot.sx > cw + 30 || dot.sy > ch + 30) continue;
    // Overlapping by more than half in both directions is the point at which
    // the number underneath stops being readable.
    // A contested tile draws a counter a side, so it needs the room of both
    // before anything else is allowed to sit next to it.
    const boxes = dot.sides ? dot.sides.length : 1;
    /* A contested tile draws a box a side, but not two full-width ones: at
       full width the pair was two and a half times a plain counter and buried
       whatever province sat next to it. Each side is drawn at four fifths,
       touching, so the pair comes to about 1.6 counters rather than 2.4. */
    const sideNarrow = boxes > 1 ? 0.8 : 1;
    const reach = half * 1.7 * boxes * sideNarrow;
    /* Two counters overlap when the distance between their centres is less
       than their half-widths added together. The first version halved that
       sum, which let them sit half on top of each other and still pass -- so
       the map still had counters with their numbers half buried. */
    /* A hair of overlap is allowed -- a counter clipping a neighbour's frame
       by a few per cent costs nothing, while demanding perfect separation hid
       four times as many. */
    let hidden = false;
    for (const p of placed) {
      if (Math.abs(p.x - dot.sx) < (reach + p.reach) * 0.72
          && Math.abs(p.y - dot.sy) < hh * 1.5) {
        hidden = true;
        break;
      }
    }
    /* A held-back counter still leaves a pip where it stands.

       Dropping it entirely was worse than the overlap it was avoiding: fifty
       brigades in Udine were simply not on the map, and the only way to find
       them was to hover apparently empty ground. A pip says "troops here, the
       number is a hover away", which is what the zoomed-out view is for. It
       reserves no space of its own, so it cannot push a third counter out in
       turn. */
    if (hidden) {
      mapCrowded++;
      const r = Math.max(1.6, half * 0.42);
      ctx.beginPath();
      ctx.arc(dot.sx, dot.sy, r, 0, Math.PI * 2);
      ctx.fillStyle = mapDim(MAP.colours[dot.stacks[0].tag] || '#ffffff');
      ctx.fill();
      ctx.lineWidth = Math.min(1.2, .5 * grow);
      ctx.strokeStyle = dot.fighting ? '#ff5c33' : 'rgba(255,240,214,.75)';
      ctx.stroke();
      continue;
    }
    placed.push({x: dot.sx, y: dot.sy, reach});
    const ink = t => mapDim(MAP.colours[t] || '#ffffff');
    const x0 = dot.sx - hw, y0 = dot.sy - hh, ww = hw * 2, hgt = hh * 2;

    /* Somewhere fought over since the last save gets a burst behind its
       counter -- spikes radiating past the corners, the way a fight is drawn
       on a map. Behind rather than over, so it never touches the number; a
       shape rather than a colour, because the map is already made of colour
       and an orange edge was lost against whichever nation owned the ground.
       The first go put small sabres above the counter, which collided with
       whatever was drawn north of it and vanished at anything but full zoom. */
    const inFight = mapShowBattles && dot.fighting;
    // Below this the diamond is smaller than the counter it sits behind
    // and only its tips show, so the counter's own edge carries it instead.
    const burstFits = half >= 4.5;

    /* One box, or one box a side where two armies are facing each other.
       Each is banded by the nations in it, in proportion to their men. */
    const groups = dot.sides || [{stacks: dot.stacks, men: dot.men, n: dot.total}];
    const gap = 0;               // the sides touch; a rule marks the join
    const bw = ww * sideNarrow;
    const boxW = bw * groups.length;
    let bx = dot.sx - boxW / 2;
    dot.boxes = [];
    /* The diamond goes behind the pair, which is where it read best -- but
       sized so it stays a diamond. The version that scaled its width with the
       box count and left its height alone came out a flattened lozenge with
       points jutting out either side; giving it height in proportion keeps it
       near 1.4:1, which reads as a shape rather than a smear. */
    if (inFight && burstFits) {
      const rx = boxW / 2 + half * 0.6, ry = hh + half * 1.35;
      ctx.beginPath();
      ctx.moveTo(dot.sx, dot.sy - ry);
      ctx.lineTo(dot.sx + rx, dot.sy);
      ctx.lineTo(dot.sx, dot.sy + ry);
      ctx.lineTo(dot.sx - rx, dot.sy);
      ctx.closePath();
      ctx.fillStyle = '#a82c14';
      ctx.fill();
      ctx.lineWidth = Math.min(1.3, .55 * grow);
      ctx.strokeStyle = 'rgba(255,196,150,.9)';
      ctx.stroke();
    }
    groups.forEach((g, gi) => {
      ctx.fillStyle = ink(g.stacks[0].tag);
      ctx.fillRect(bx, y0, bw, hgt);
      if (g.stacks.length > 1 && bw >= 8) {
        let at = bx;
        for (const part of g.stacks) {
          const seg = bw * (part.men / Math.max(1, g.men));
          ctx.fillStyle = ink(part.tag);
          ctx.fillRect(at, y0, seg, hgt);
          at += seg;
        }
        if (bw >= 16) {
          ctx.lineWidth = Math.min(1.1, .45 * grow);
          ctx.strokeStyle = 'rgba(0,0,0,.6)';
          at = bx;
          for (const part of g.stacks) {
            at += bw * (part.men / Math.max(1, g.men));
            ctx.beginPath();
            ctx.moveTo(at, y0); ctx.lineTo(at, y0 + hgt);
            ctx.stroke();
          }
        }
      }
      dot.boxes.push({x: bx + bw / 2, y: dot.sy, men: g.men, w: bw});
      bx += bw;
      // A bright rule where two sides meet, so the join is not read as one
      // nation's colour running into the next.
      if (gi < groups.length - 1) {
        ctx.lineWidth = Math.max(1, Math.min(2, .9 * grow));
        ctx.strokeStyle = 'rgba(255,232,200,.95)';
        ctx.beginPath();
        ctx.moveTo(bx, y0); ctx.lineTo(bx, y0 + hgt);
        ctx.stroke();
      }
    });
    /* A pale edge, which is what survives on a dark nation's land -- unless
       this province is being fought over and the counter is too small for the
       burst to show around it, in which case the edge itself carries it. At
       twelve pixels across there is no room for a symbol, but there is room
       for a colour. */
    ctx.lineWidth = inFight && !burstFits
      ? Math.max(1.4, Math.min(2.2, 1.1 * grow)) : Math.min(1.6, .7 * grow);
    ctx.strokeStyle = inFight && !burstFits
      ? '#ff5c33' : 'rgba(255,240,214,.7)';
    for (const b of dot.boxes) ctx.strokeRect(b.x - b.w / 2, y0, b.w, hgt);

    if (mapPinned && mapPinned.pid === dot.pid) {
      ctx.lineWidth = 2.4;
      ctx.strokeStyle = '#ffffff';
      for (const b of dot.boxes) ctx.strokeRect(b.x - b.w / 2, y0, b.w, hgt);
    }
    labelled.push(dot);
  }
  // Numerals last, so a small stack drawn over a big one cannot have its
  // count half-covered. Only where the circle can hold the digits: below
  // that the number would be a smudge, and the count is a hover away.
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  for (const dot of labelled) {
    for (const box of dot.boxes) {
      // Men, not regiments: it is what the counter is sized on and what
      // changes when a stack takes casualties. Rounded to thousands past 10k,
      // where the exact figure is neither readable at this size nor what
      // anyone is asking of a glance. On a contested tile each side carries
      // its own, so the counter reads as the matchup it is.
      const text = box.men >= 10000
        ? Math.round(box.men / 1000).toLocaleString() + 'k'
        : box.men.toLocaleString();
      // Fitted to the box rather than a radius: monospace digits run about
      // 0.6em wide, so the width test is against the count of them.
      const size = Math.min(dot.hh * 1.6, box.w * 1.4 / text.length);
      if (size < 7) continue;
      ctx.font = `600 ${size.toFixed(1)}px "IBM Plex Mono", monospace`;
      ctx.lineWidth = Math.max(1.6, size / 5);
      ctx.strokeStyle = 'rgba(0,0,0,.55)';
      ctx.strokeText(text, box.x, box.y);
      ctx.fillStyle = '#F6ECD8';
      ctx.fillText(text, box.x, box.y);
    }
  }
  document.getElementById('mapzoom').textContent = mapZoom.toFixed(1) + '×';
  mapShow(mapPinned);
}

function mapIdle() {
  const shown = mapDots.reduce((s, d) => s + d.total, 0);
  document.getElementById('mapreadout').innerHTML =
    `<span class="rk">stacks</span> <b>${mapDots.length.toLocaleString()}</b>`
    + (mapCrowded
        ? `<span><span class="rk">drawn as pips, too close to label</span> `
          + `<b>${mapCrowded.toLocaleString()}</b> <span class="rk">\u2014 zoom in`
          + `</span></span>` : '')
    + `<span><span class="rk">brigades shown</span> <b>${shown.toLocaleString()}</b></span>`
    + `<span><span class="rk">shading</span> <b>owner</b>`
    + `<span class="rk">${mapHatchOccupied
        ? (mapOccAny ? ', occupied land hatched' : ', nothing occupied') : ''}</span></span>`
    + (mapUnplaced
        ? `<span><span class="rk">no map position</span> `
          + `<b>${mapUnplaced.toLocaleString()}</b>`
          + `<span class="rk"> provinces, ${mapUnplacedBrigades.toLocaleString()} brigades</span></span>`
        : '')
    + `<span class="rk">hover the land for its owner, a marker for its armies</span>`;
}

/* The province under the cursor, which is the painting's own lookup run
   backwards: `mapProv` holds a province id per raster pixel. */
function mapProvinceAt(p) {
  if (!mapProv) return -1;
  const s = mapFit() * mapZoom;
  const x = Math.floor(mapOX + p.x / s), y = Math.floor(mapOY + p.y / s);
  if (x < 0 || y < 0 || x >= MAP.w || y >= MAP.h) return -1;
  return mapProv[y * MAP.w + x];
}

/* Who owns a province and who is standing on it, as readout spans. Hatching
   says a province is held by somebody else, but no pattern can say *which*
   nation owns the ground under it once a stripe is across it -- so the readout
   names both outright, which is the one answer that is never ambiguous. */
function landBits(pid) {
  const date = document.getElementById('mapsave').value || DATA.lastDate;
  const book = (mapOwners || {})[date] || {own: new Map(), occ: new Map()};
  const tagOf = idx => (idx === undefined ? null : MAP.tags[idx]);
  const own = tagOf(book.own.get(pid)), occ = tagOf(book.occ.get(pid));
  const chip = (label, tag) => `<span><span class="rk">${label}</span> `
    + `<b style="color:${MAP.colours[tag] || '#fff'}">${tag}</b>`
    + (nameOf(tag) === tag ? '' : ` <span class="rk">${nameOf(tag)}</span>`)
    + `</span>`;
  if (!own) return [`<span class="rk">unclaimed</span>`];
  return occ ? [chip('owned by', own), chip('held by', occ)]
             : [chip('owned by', own)];
}

/* Land with no army on it still has an owner worth naming. */
function mapShowLand(pid) {
  if (pid < 0 || mapSea.has(pid)) return mapIdle();
  const name = (MAP.names && MAP.names[pid]) || ('province ' + pid);
  document.getElementById('mapreadout').innerHTML =
    `<span class="rk">${name}</span>` + landBits(pid).join('');
}

function mapShow(dot) {
  if (!dot) return mapIdle();
  const name = (MAP.names && MAP.names[dot.pid]) || ('province ' + dot.pid);
  const row = s => {
    const mix = s.mix.split(';').map(part => {
      const c = part.lastIndexOf(':');
      return `${part.slice(0, c)} ${part.slice(c + 1)}`;
    }).join(', ');
    // A brigade at less than full strength is the whole point of showing men,
    // so the share is quoted where it is not a round hundred per cent.
    const full = s.n * (MAP.regimentSize || 3000);
    const pct = full ? Math.round(s.men / full * 100) : 100;
    return `<b style="color:${MAP.colours[s.tag] || '#fff'}">${s.tag}</b>`
         + `<b class="num">${s.men.toLocaleString()}</b>`
         + `<span class="rk num">${s.n.toLocaleString()} `
         + `${s.n === 1 ? 'bde' : 'bdes'}</span>`
         + `<span class="rk num">${pct}%</span>`
         + `<span class="mix">${mix}</span>`;
  };
  /* Contested tiles are listed side by side rather than as one run of
     nations, with each side's total above its members -- which is the
     comparison the province is actually posing. */
  const bits = [];
  if (dot.sides && dot.sides.length > 1) {
    const label = ['attacking', 'defending', 'neither side'];
    dot.sides.forEach((g, i) => {
      const who = g.stacks.map(a => a.tag).join(' + ');
      bits.push(`<div class="sidehead"><b>${who}</b> `
        + `<span class="rk">${label[dot.fighting.a.includes(g.stacks[0].tag) ? 0
             : dot.fighting.d.includes(g.stacks[0].tag) ? 1 : 2]}</span> `
        + `<b>${g.men.toLocaleString()}</b> <span class="rk">men in `
        + `${g.n.toLocaleString()} ${g.n === 1 ? 'brigade' : 'brigades'}</span>`
        + `</div>`);
      bits.push(`<div class="natgrid">${g.stacks.map(row).join('')}</div>`);
    });
  } else {
    bits.push(`<div class="natgrid">${dot.stacks.map(row).join('')}</div>`);
  }
  const fight = dot.fighting
    ? `<span><b style="color:#ff7043">contested</b> <span class="rk">`
      + `${dot.fighting.a.join(' + ')} against ${dot.fighting.d.join(' + ')}`
      + `</span></span>`
    : '';

  document.getElementById('mapreadout').innerHTML =
    `<span class="rk">${name}</span>`
    + landBits(dot.pid).join('')
    + `<span><b>${dot.men.toLocaleString()}</b> <span class="rk">men, `
    + `${dot.total.toLocaleString()} ${dot.total === 1 ? 'brigade' : 'brigades'}`
    + `</span></span>`
    + fight
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
    mapStep.value = DATA.dates.indexOf(mapSave.value);
    mapPinned = null; mapPicker.refresh(); mapRender(); drawGreatPowers();
  };

  /* A run of saves is a campaign in the order it happened, and until now the
     only way to see it move was to pick each date in turn. The slider is the
     same choice as the dropdown -- both set the save -- and Play walks it. */
  const mapStep = document.getElementById('mapstep');
  const playBtn = document.getElementById('mapplay');
  mapStep.max = Math.max(0, DATA.dates.length - 1);
  mapStep.value = DATA.dates.length - 1;
  mapStep.disabled = DATA.dates.length < 2;
  playBtn.disabled = DATA.dates.length < 2;

  const goToSave = i => {
    mapStep.value = i;
    mapSave.value = DATA.dates[i];
    mapSave.onchange();
  };
  mapStep.oninput = () => { mapStopPlay(); goToSave(+mapStep.value); };

  /* How long a frame is held. A quarter of a second is about as slow as
     anyone wants to watch a campaign that has thirty saves in it, and the
     multipliers are there for the one that has nine hundred. */
  /* How long Play holds each save, in milliseconds.

     One number cannot suit every campaign: a folder of monthly autosaves runs
     to about a thousand saves and a folder of yearly ones to about a hundred,
     and a pace that reads well at one is unwatchable at the other. The button
     this replaced started at 250ms -- four saves a second, faster than anything
     can actually be read -- and could only go up from there. */
  const HOLD = [4000, 3000, 2000, 1500, 1000, 750, 500, 350, 250, 125,
                50, 25];
  const holdText = ms => ms >= 1000
    ? (ms / 1000) + 's a save' : ms + 'ms a save';
  const speedBtn = document.getElementById('mapspeed');
  const speedOut = document.getElementById('mapspeedout');
  speedBtn.disabled = DATA.dates.length < 2;
  speedBtn.max = HOLD.length - 1;
  /* Longer campaigns open faster, so the run is watchable rather than starting
     at the same pace whether there are twenty saves or a thousand. The reader
     can move it either way from there. */
  const wantHold = DATA.dates.length > 400 ? 125
                 : DATA.dates.length > 150 ? 250
                 : DATA.dates.length > 60 ? 500
                 : DATA.dates.length > 25 ? 750 : 1000;
  speedBtn.value = HOLD.indexOf(wantHold);
  const showSpeed = () => { speedOut.textContent = holdText(HOLD[+speedBtn.value]); };
  speedBtn.oninput = showSpeed;
  showSpeed();
  const frameDelay = () => HOLD[+speedBtn.value];

  let mapTimer = null;
  mapStopPlay = () => {
    if (!mapTimer) return;
    clearTimeout(mapTimer);
    mapTimer = null;
    playBtn.setAttribute('aria-pressed', 'false');
    playBtn.textContent = 'Play';
  };
  playBtn.onclick = () => {
    if (mapTimer) return mapStopPlay();
    // Pressing Play while sitting on the last save means "again from the top",
    // which is what anyone who has just watched it to the end wants next.
    if (+mapStep.value >= DATA.dates.length - 1) goToSave(0);
    playBtn.setAttribute('aria-pressed', 'true');
    playBtn.textContent = 'Pause';
    /* Each frame schedules the next one after it has finished drawing, rather
       than every frame being booked in advance on an interval. A repaint is
       about a tenth of a second of work and the picker refresh doubles it, so
       an interval would keep firing while the last frame was still drawing
       and the queue would run away with itself; this way a slow machine plays
       back slower instead of falling behind.
       What is waited is the rest of the frame's slot, not the whole slot on
       top of the work, so 1x really is a quarter of a second a frame rather
       than a quarter of a second plus however long the drawing took. */
    const tick = () => {
      const next = +mapStep.value + 1;
      if (next > DATA.dates.length - 1) return mapStopPlay();
      const started = performance.now();
      goToSave(next);
      const left = frameDelay() - (performance.now() - started);
      mapTimer = setTimeout(tick, Math.max(16, left));
    };
    mapTimer = setTimeout(tick, frameDelay());
  };

  const borderBtn = document.getElementById('mapborders');
  borderBtn.onclick = () => {
    mapShowProvinceBorders = !mapShowProvinceBorders;
    borderBtn.setAttribute('aria-pressed', mapShowProvinceBorders);
    mapRender();
  };

  const occBtn = document.getElementById('mapocc');
  occBtn.onclick = () => {
    mapHatchOccupied = !mapHatchOccupied;
    occBtn.setAttribute('aria-pressed', mapHatchOccupied);
    occBtn.textContent = mapHatchOccupied ? 'Occupation' : 'Ownership';
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
    /* 24x used to be the ceiling, which is where a dense theatre still had
       counters shouldering each other: they stop growing at their cap while
       the map keeps magnifying, so every further doubling of zoom pulls the
       province anchors twice as far apart and crowding halves. 48x shows
       about 117 map pixels across a panel -- blocky, since that is the
       resolution the raster has, but it is the view where a front with a
       dozen stacks on it can be read one counter at a time. */
    mapZoom = Math.min(48, Math.max(1, mapZoom * factor));
    const after = mapFit() * mapZoom;
    mapOX = mx - at.x / after;
    mapOY = my - at.y / after;
    mapRenderSoon();
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
      mapRenderSoon();
      return;
    }
    if (mapPinned) return;
    const hit = mapPick(p);
    if (hit) mapShow(hit); else mapShowLand(mapProvinceAt(p));
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
  window.addEventListener('resize', () => { if (MAP) mapRenderSoon(); });
} else {
  // No --mod-path, so there is no province bitmap and no country order: hide the
  // map and the great power ranking rather than showing empty frames.
  document.getElementById('mapcanvas').closest('section').hidden = true;
}


/* =============== GREAT POWERS =============== */
function drawGreatPowers() {
  const grid = document.getElementById('gpgrid');
  const date = document.getElementById('mapsave').value || DATA.lastDate;
  const list = (DATA.greatPowers || {})[date] || [];
  document.getElementById('gpstrip').hidden = !list.length;
  grid.replaceChildren();
  list.forEach((entry, i) => {
    const [tag, flagKey] = Array.isArray(entry) ? entry : [entry, ''];
    const card = document.createElement('div'); card.className = 'gpcard';
    card.setAttribute('role', 'listitem');
    card.style.setProperty('--nation-colour', (DATA.map?.colours || {})[tag] || colourFor(tag));
    const identity = document.createElement('div'); identity.className = 'gpidentity';
    const rank = document.createElement('span'); rank.className = 'gprank'; rank.textContent = i + 1;
    let flag = nationFlag(tag); flag.className = 'gpflag';
    if ((DATA.flags || {})[flagKey]) {
      flag = document.createElement('img'); flag.src = DATA.flags[flagKey]; flag.alt = ''; flag.className = 'gpflag';
    }
    const name = document.createElement('button'); name.className = 'gpname'; name.textContent = nameOf(tag);
    name.title = 'View trends for ' + nameOf(tag);
    name.onclick = () => {
      nationsPicker.set([tag]); selectTab('tab-compare'); showCompareView('trends');
      document.getElementById('metric-category').focus();
    };
    identity.append(rank, flag, name);
    const stats = document.createElement('div'); stats.className = 'gpstats';
    const f = (DATA.facts[date] || {})[tag] || {};
    for (const [label, value] of [['Prestige', f.prestige == null ? null : Math.round(f.prestige)],
      ['Factory levels', f.factory_levels], ['Brigades', f.brigades], ['Ships', f.ships]]) {
      const stat = document.createElement('span'); stat.textContent = label;
      const amount = document.createElement('b'); amount.textContent = value == null ? '—' : value.toLocaleString();
      stat.append(amount); stats.append(stat);
    }
    card.append(identity, stats); grid.append(card);
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
/* What to write in a war's "to" column.

   Victoria 2 wars do not always end. Two AIs that cannot reach each other
   never agree a peace, and the war sits in the save as an active_war until
   the campaign stops -- the German-French War in one campaign had its last
   battle in 1872 and was still open in 1881, nine years without a shot
   fired. The save is not wrong and neither was this column, but "ongoing"
   for a war nobody has fought since the last decade reads as a mistake in
   the report rather than a fact about the game. So a war still open at the
   last save says so, and one that has been open and quiet for over a year
   says that instead, with the date it went quiet. */
function warEnd(w) {
  if (!w.active) return w.end || '—';
  const quiet = warQuietSince(w);
  return quiet ? `<b>unresolved</b> <span class="rk">quiet since ${quiet}</span>`
               : '<b>ongoing</b>';
}
// The date an open war last saw a battle, if that was over a year before the
// last save; '' while it is still being fought.
function warQuietSince(w) {
  /* Years as a number, because these are `1872.9.1` strings and sorting them
     as text puts October before September. */
  const when = d => {
    const p = String(d).split('.');
    return (+p[0]) + ((+(p[1] || 1)) - 1) / 12;
  };
  let last = 0, shown = w.start;
  for (const b of w.battles) {
    if (b.date && when(b.date) > last) { last = when(b.date); shown = b.date; }
  }
  if (!last && w.start) last = when(w.start);
  let finish = 0;
  for (const d of (DATA.dates || [])) finish = Math.max(finish, when(d));
  return last && finish && finish - last > 1 ? shown : '';
}

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
      + `<td class="num">${warEnd(w)}</td>`
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
      drawWarTable();
      document.getElementById('warback').focus();
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
/* =============== THE WAR INFOBOX =============== */

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December'];
// `1845.12.23` the way a reader writes it: 23 December 1845.
function longDate(d) {
  const p = String(d || '').split('.');
  const month = MONTHS[+p[1] - 1];
  return p.length === 3 && month ? `${+p[2]} ${month} ${p[0]}` : (d || '—');
}
// How long from one date to another: years and months, and the days as well
// for anything under a year. The game's calendar has no leap years.
const MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
function warSpan(from, to) {
  const a = String(from || '').split('.').map(Number);
  const b = String(to || '').split('.').map(Number);
  if (a.length !== 3 || b.length !== 3 || a.concat(b).some(isNaN)) return '';
  let y = b[0] - a[0], m = b[1] - a[1], d = b[2] - a[2];
  if (d < 0) { m -= 1; d += MONTH_DAYS[(b[1] + 10) % 12]; }
  if (m < 0) { y -= 1; m += 12; }
  if (y < 0) return '';
  const unit = (n, what) => `${n} ${what}${n === 1 ? '' : 's'}`;
  if (!y && !m) return unit(d, 'day');
  return [y ? unit(y, 'year') : '', m ? unit(m, 'month') : '',
          !y && d ? unit(d, 'day') : ''].filter(Boolean).join(', ');
}
const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th'
  : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');
// The same year axis as DATA.years, which Python's `year_fraction` fills.
const dateYear = d => {
  const p = String(d).split('.');
  return (+p[0]) + (+p[1] - 1) / 12 + (+p[2] - 1) / 365;
};

/* Which side of the war a nation fought on: 1 attacking, -1 defending, 0 when
   the two lists cannot say -- the same tag on both, as in a civil war. The two
   nations in a battle are on opposite sides, so an unclear one takes the
   opposite of its opponent. That is wars.py's `_side_losses` rule, which is
   what makes the casualties here add up to the coalition totals it ships. */
function warSides(w) {
  const att = new Set(w.attackers), dfd = new Set(w.defenders);
  const which = t => {
    const a = att.has(t), d = dfd.has(t);
    return a && !d ? 1 : d && !a ? -1 : 0;
  };
  const battle = b => {
    let x = which(b.a[0]), y = which(b.d[0]);
    if (!x && y) x = -y;
    if (!y && x) y = -x;
    return [x, y];
  };
  return {which, battle};
}

/* The save that shows a war going in: the last one taken before it began, if
   that was within a year, or else the first one taken while it was fought. A
   war of eight days between two monthly saves has none of its own, and the
   save three weeks before it says who was a great power as well as any would.
   None for a war over before the first save: then nothing here can say who
   was great at the time, or what anybody had. */
function warOpening(w) {
  if (!w.start || !DATA.dates.length) return null;
  const from = dateYear(w.start);
  const to = w.active ? Infinity : dateYear(w.end || w.start);
  let before = -1;
  DATA.years.forEach((y, i) => { if (y <= from) before = i; });
  if (before >= 0 && from - DATA.years[before] <= 1)
    return {date: DATA.dates[before], what: 'the last save before the war'};
  const during = DATA.years.findIndex(y => y > from && y <= to);
  return during < 0 ? null
    : {date: DATA.dates[during], what: 'the first save taken during the war'};
}
// {tag: rank} for the great powers at one save.
function warGreatPowers(opening) {
  const rank = {};
  if (!opening) return rank;
  ((DATA.greatPowers || {})[opening.date] || []).forEach((e, i) => {
    rank[Array.isArray(e) ? e[0] : e] = i + 1;
  });
  return rank;
}

/* A flag at one of three sizes: '' in a list, 'big' for a principal
   belligerent, 'hero' across the top. */
function ibFlag(tag, size) {
  const src = (DATA.flags || {})[tag + '|'];
  const cls = 'ibflag' + (size ? ' ' + size : '');
  if (src) return `<img class="${cls}" src="${src}" alt="">`;
  return `<span class="${cls} blank" style="background-color:${colourFor(tag)}">`
    + `${size ? tag : ''}</span>`;
}
const ibName = t => t
  ? `${warFlag(t)}<b style="color:${colourFor(t)}">${nameOf(t)}</b>`
  : '<span class="rk">unknown</span>';

/* One side's nations, the principal ones first: its war leader, then any
   great power, in rank order. A side the data marks no leader for -- a report
   built before leaders were marked -- lets its first nation stand in, so each
   side has a flag in the picture. */
function ibParties(w, side, gp) {
  const parties = belParties(w, side).map((p, i) => ({...p, i, gp: gp[p.tag] || 0}));
  const weight = p => p.leads ? 0 : p.gp ? 1 : 2;
  parties.sort((a, b) => weight(a) - weight(b)
    || (a.gp || 99) - (b.gp || 99) || a.i - b.i);
  parties.forEach(p => { p.major = !!(p.leads || p.gp); });
  if (parties.length && !parties.some(p => p.major)) parties[0].major = true;
  return parties;
}

function ibNation(p) {
  const ink = colourFor(p.tag);
  const late = !p.original && p.joined;
  if (p.major) {
    /* A nation can be knocked out years before the war ends -- a separate
       peace, or annexation -- and a join date on its own reads as though it
       fought to the finish. */
    const meta = [p.leads ? 'War leader' : '',
                  p.gp ? `Great power, ${ordinal(p.gp)}` : '',
                  late ? `joined ${p.joined}` : '',
                  p.left ? `left ${p.left}` : ''].filter(Boolean).join(' &middot; ');
    return `<div class="ibnat major">${ibFlag(p.tag, 'big')}<div class="ibwho">`
      + `<b style="color:${ink}">${nameOf(p.tag)}</b>`
      + (meta ? `<span class="ibmeta">${meta}</span>` : '') + `</div></div>`;
  }
  const aside = [late ? p.joined : '', p.left ? `left ${p.left}` : '']
    .filter(Boolean).join(' &middot; ');
  return `<div class="ibnat">${ibFlag(p.tag)}<div class="ibwho">`
    + `<b style="color:${ink}">${nameOf(p.tag)}</b></div>`
    + (aside ? `<span class="ibaside">${aside}</span>` : '') + `</div>`;
}
function ibBelligerents(label, parties) {
  const first = parties.filter(p => p.original);
  const later = parties.filter(p => !p.original);
  return `<div class="ibside">${label}</div>` + first.map(ibNation).join('')
    + (later.length ? `<div class="ibgroup">Joined later</div>`
        + later.map(ibNation).join('') : '');
}
// Province centres from the same raster as the deployment map. Army anchors
// cover only garrisoned provinces, so historical battles cannot rely on them.
let warCentres = null;
const warTheatreCache = new Map();
function warBattleSites(w) {
  if (!MAP) return [];
  mapDecoded();
  if (!warCentres) {
    warCentres = new Map();
    for (let y = 0; y < MAP.h; y++) for (let x = 0; x < MAP.w; x++) {
      const p = mapProv[y * MAP.w + x];
      if (!p) continue;
      let c = warCentres.get(p);
      if (!c) { c = [0, 0, 0]; warCentres.set(p, c); }
      c[0] += x; c[1] += y; c[2]++;
    }
    for (const c of warCentres.values()) { c[0] /= c[2]; c[1] /= c[2]; }
  }
  const sites = new Map();
  for (const b of w.battles) {
    const c = warCentres.get(+b.province);
    if (!c) continue;
    let site = sites.get(+b.province);
    if (!site) {
      site = {x:c[0], y:c[1], name:b.name, losses:0, count:0, date:''};
      sites.set(+b.province, site);
    }
    site.losses += Math.max(0, b.a[2]) + Math.max(0, b.d[2]);
    site.count++;
    if (b.date && (!site.date || dateYear(b.date) > dateYear(site.date))) site.date = b.date;
  }
  return [...sites.values()];
}

function warTheatre(w) {
  if (warTheatreCache.has(w)) return warTheatreCache.get(w);
  const sites = warBattleSites(w);
  if (!sites.length) { warTheatreCache.set(w, null); return null; }
  // Score neighbouring battles, not an average of distant fronts that could
  // put the camera in an empty ocean. Wrap longitude across the map seam.
  const dx = (a,b) => ((a-b + MAP.w * 1.5) % MAP.w) - MAP.w / 2;
  const radius = Math.min(MAP.w * .055, MAP.h * .18);
  const hasLosses = sites.some(p => p.losses > 0);
  let centre = sites[0], best = -1;
  for (const p of sites) {
    const score = sites.reduce((n,q) => n + (Math.hypot(dx(q.x,p.x),q.y-p.y) <= radius
      ? (hasLosses ? q.losses : q.count) : 0), 0);
    if (score > best || (score === best && p.losses > centre.losses)) { centre = p; best = score; }
  }
  const nearby = sites.filter(p => Math.hypot(dx(p.x,centre.x),p.y-centre.y) <= radius);
  const xs = nearby.map(p => centre.x + dx(p.x,centre.x)), ys = nearby.map(p => p.y);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  let width = Math.max(maxX-minX + radius*.65, (maxY-minY + radius*.65)*2, MAP.w*.075);
  width = Math.min(width, MAP.w, MAP.h*2);
  const height = width/2, x0 = (minX+maxX-width)/2;
  const y0 = Math.max(0, Math.min(MAP.h-height, (minY+maxY-height)/2));
  const target = centre.date || (w.active ? DATA.lastDate : w.end) || w.start;
  const dates = Object.keys(mapOwners);
  const date = dates.reduce((best,d) => !best || Math.abs(dateYear(d)-dateYear(target))
    < Math.abs(dateYear(best)-dateYear(target)) ? d : best, '');
  if (!date) { warTheatreCache.set(w,null); return null; }
  const own = mapOwners[date].own, palette = mapPalette(date);
  const fighters = new Set(w.attackers.concat(w.defenders));
  const canvas = document.createElement('canvas'); canvas.width = 720; canvas.height = 360;
  const ctx = canvas.getContext('2d'), img = ctx.createImageData(720,360);
  const wrap = x => ((Math.floor(x)%MAP.w)+MAP.w)%MAP.w;
  const province = (x,y) => mapProv[Math.min(MAP.h-1,Math.max(0,Math.floor(y)))*MAP.w+wrap(x)];
  const owner = p => own.has(p) ? own.get(p) : -1;
  const isBoundary = (p,q) => mapSea.has(p) !== mapSea.has(q) || owner(p) !== owner(q);
  for (let y=0; y<360; y++) for (let x=0; x<720; x++) {
    const mx=x0+x*width/720, my=y0+y*height/360, p=province(mx,my);
    let rgb = mapSea.has(p) ? [30,47,61] : [112,108,88];
    if (!mapSea.has(p) && fighters.has(MAP.tags[owner(p)])) {
      const colour=palette[p]; rgb=[(colour>>16)&255,(colour>>8)&255,colour&255];
      // mapPalette already applies the shared softer land colours.
    }
    if (isBoundary(p,province(mx+width/720,my)) || isBoundary(p,province(mx,my+height/360))) rgb=[35,32,28];
    const i=(y*720+x)*4; img.data.set([...rgb,255],i);
  }
  ctx.putImageData(img,0,0);
  const visible = sites.map(p=>({...p,px:(centre.x+dx(p.x,centre.x)-x0)*720/width,py:(p.y-y0)*360/height}))
    .filter(p=>p.px>=0 && p.px<=720 && p.py>=0 && p.py<=360).sort((a,b)=>a.losses-b.losses);
  const peak = Math.max(1,...visible.map(p=>p.losses));
  for (const p of visible) {
    ctx.beginPath(); ctx.arc(p.px,p.py,3+9*Math.sqrt(p.losses/peak),0,Math.PI*2);
    ctx.fillStyle='rgba(239,186,77,.75)'; ctx.fill(); ctx.strokeStyle='#2a1714'; ctx.lineWidth=1.5; ctx.stroke();
  }
  // Label only a few major sites; leave overlapping labels out.
  const labels=[]; ctx.font='bold 13px sans-serif';
  for (const p of [...visible].reverse()) {
    if (labels.length>=3) break;
    const label=p.name || 'Battle site', tw=ctx.measureText(label).width;
    const x=Math.max(6,Math.min(714-tw,p.px+12)), y=Math.max(18,Math.min(350,p.py-14));
    if (labels.some(q=>Math.abs(y-q.y)<22 && x<q.x+q.w+8 && x+tw+8>q.x)) continue;
    ctx.fillStyle='rgba(21,29,33,.85)'; ctx.fillRect(x-4,y-14,tw+8,20);
    ctx.fillStyle='#fff0cd'; ctx.fillText(label,x,y); labels.push({x,y,w:tw});
  }
  const n=visible.reduce((n,p)=>n+p.count,0), losses=visible.reduce((n,p)=>n+p.losses,0);
  const outside = dateYear(date)<dateYear(w.start) || (!w.active && w.end && dateYear(date)>dateYear(w.end));
  const caption=`Fighting around ${centre.name || 'the main battle sites'} · ${n} recorded battle${n===1?'':'s'}, ${losses.toLocaleString()} casualties in view. `
    + `Ownership: ${longDate(date)}${outside?' (outside the war’s dates)':''}. `
    + 'Gold circles show battle sites across the war, sized by casualties; borders show ownership, not a reconstructed frontline.';
  // Bound retained canvas memory when browsing a long campaign.
  if (warTheatreCache.size >= 8) warTheatreCache.delete(warTheatreCache.keys().next().value);
  const result={canvas,caption}; warTheatreCache.set(w,result); return result;
}

function drawWarTheatre(w) {
  const slot=document.getElementById('wartheatre');
  if (!slot) return;
  const view=warTheatre(w);
  if (!view) { slot.remove(); return; }
  const canvas=document.createElement('canvas'); canvas.width=720; canvas.height=360;
  canvas.setAttribute('role','img'); canvas.setAttribute('aria-label',view.caption);
  canvas.getContext('2d').drawImage(view.canvas,0,0);
  const caption=document.createElement('figcaption'); caption.textContent=view.caption;
  slot.append(canvas,caption);
}

// Past a handful, the rest of a list folds away behind a count.
function ibList(rows, keep) {
  if (rows.length <= keep + 1) return rows.join('');
  return rows.slice(0, keep).join('')
    + `<details><summary>and ${rows.length - keep} more</summary>`
    + rows.slice(keep).join('') + `</details>`;
}

/* What each nation lost, counted from the battles it fought. The two totals
   are the coalition split the war table's casualties figure divides into. */
function ibLosses(w, sides) {
  const by = {1: new Map(), '-1': new Map()};
  let unplaced = 0;
  for (const b of w.battles) {
    const marks = sides.battle(b);
    [b.a, b.d].forEach((s, k) => {
      if (!marks[k]) { unplaced += s[2]; return; }
      by[marks[k]].set(s[0], (by[marks[k]].get(s[0]) || 0) + s[2]);
    });
  }
  const column = side => {
    const rows = [...by[side]].sort((x, y) => y[1] - x[1]);
    const total = rows.reduce((sum, [, n]) => sum + n, 0);
    return ibList(rows.map(([t, n]) => `<div class="ibnat">${ibFlag(t)}`
        + `<div class="ibwho">${t ? `<b style="color:${colourFor(t)}">${nameOf(t)}</b>`
                               : '<span class="rk">unknown</span>'}</div>`
        + `<span class="ibnum">${n.toLocaleString()}</span></div>`), 8)
      + `<div class="ibtotal"><div class="ibwho">Total</div>`
      + `<span class="ibnum">${total.toLocaleString()}</span></div>`;
  };
  return {cols: [column(-1), column(1)], unplaced};
}

/* Brigades and ships at the first save taken during the war. Only the nations
   the report charts have figures; the rest are counted, not guessed at. */
function ibStrength(parties, date) {
  const at = DATA.facts[date] || {};
  const rows = parties.filter(p => at[p.tag])
    .map(p => [p.tag, at[p.tag].brigades || 0, at[p.tag].ships || 0])
    .sort((x, y) => y[1] - x[1] || y[2] - x[2]);
  const pair = (b, s) => `<span class="ibnum pair"><span>${b.toLocaleString()}</span>`
    + `<span>${s.toLocaleString()}</span></span>`;
  const missing = parties.length - rows.length;
  if (!rows.length)
    return `<span class="rk">No figures for ${missing === 1 ? 'this nation' : `these ${missing} nations`}</span>`;
  return `<div class="ibhead"><span>brigades</span><span>ships</span></div>`
    + ibList(rows.map(([t, b, s]) => `<div class="ibnat">${ibFlag(t)}<div class="ibwho">`
        + `<b style="color:${colourFor(t)}">${nameOf(t)}</b></div>${pair(b, s)}</div>`), 8)
    + `<div class="ibtotal"><div class="ibwho">Total</div>`
    + pair(rows.reduce((n, r) => n + r[1], 0), rows.reduce((n, r) => n + r[2], 0))
    + `</div>`
    + (missing ? `<div class="ibmeta" style="margin-top:4px">and ${missing} with no `
        + `figures at that save</div>` : '');
}

/* What the peace did, in as many words as the saves can back. A war goal is
   judged by who held its state either side of the war (see the goals table),
   so a war nothing saw going in, or one still open, is not given a verdict. */
function ibResult(w, sides) {
  if (w.active) {
    const quiet = warQuietSince(w);
    return quiet ? `Unresolved: still open at the last save, with no battle since ${quiet}`
                 : 'Still being fought at the last save';
  }
  if (!w.goals.length) return '<span class="rk">No war goal was recorded</span>';
  const judged = w.goals.filter(g => g.checkable);
  if (!judged.length) {
    const first = DATA.dates.length ? DATA.years[0] : 0;
    return '<span class="rk">Not known: '
      + (w.end && first && dateYear(w.end) <= first
          ? 'the war was over before the first save'
          : 'no war goal could be checked against who held what') + '</span>';
  }
  const lines = [];
  for (const [side, who] of [[-1, 'Defenders'], [1, 'Attackers'], [0, 'Others']]) {
    const mine = judged.filter(g => sides.which(g.actor) === side);
    if (!mine.length) continue;
    const full = mine.filter(g => g.met).length;
    const part = mine.filter(g => g.part).length;
    const cls = full === mine.length ? 'up' : full + part ? '' : 'down';
    const text = mine.length === 1
      ? `${who}' war goal ${full ? 'taken' : part ? 'taken in part' : 'not taken'}`
      : `${who} took ${full + part} of ${mine.length} war goals`
        + (part ? `, ${part} in part` : '');
    lines.push(`<span class="${cls}">${text}</span>`);
  }
  return lines.join('<br>');
}

function warInfobox(w) {
  const sides = warSides(w);
  const opening = warOpening(w);
  const gp = warGreatPowers(opening);
  const dfd = ibParties(w, 'defender', gp);
  const att = ibParties(w, 'attacker', gp);
  const cols = (left, right, named) => {
    const side = label => named ? '' : `<div class="ibside stacked">${label}</div>`;
    return `<div class="ibcols"><div class="ibcol">${side('Defenders')}${left}</div>`
      + `<div class="ibcol">${side('Attackers')}${right}</div></div>`;
  };
  const band = title => `<div class="ibband" data-war-section="${title}">${title}</div>`;

  const facts = [];
  const fact = (label, html) => facts.push(`<dt>${label}</dt><dd>${html}</dd>`);
  const span = warSpan(w.start, w.active ? DATA.lastDate : w.end);
  fact('Date', `${longDate(w.start)} &ndash; ${w.active ? 'ongoing' : longDate(w.end)}`
    + (span ? `<br><span class="rk">${span}${w.active ? ' by the last save' : ''}</span>` : ''));
  fact('Result', ibResult(w, sides));
  if (w.transfers.length) {
    fact('Territorial changes', `<ul>${w.transfers.map(t =>
      `<li>${ibName(t[2])} ceded ${t[1] || t[0] || 'a state'} to ${ibName(t[3])}`
      + (t[4] < t[5] ? ` <span class="rk">(${t[4]} of ${t[5]} provinces)</span>`
         : !(t[1] || t[0]) ? ` <span class="rk">(${t[4]} province${t[4] === 1 ? '' : 's'})</span>`
         : '')
      + `</li>`).join('')}</ul>`);
  }
  if (w.battles.length) {
    const naval = w.battles.filter(b => b.sea).length;
    const land = w.battles.length - naval;
    const won = {1: 0, '-1': 0};
    for (const b of w.battles) {
      const side = sides.battle(b)[b.won ? 0 : 1];
      if (side) won[side]++;
    }
    fact('Battles', [land ? `${land} on land` : '', naval ? `${naval} at sea` : '']
      .filter(Boolean).join(', ')
      + `<br><span class="rk">defenders won ${won[-1]}, attackers ${won[1]}</span>`);
  } else {
    fact('Battles', '<span class="rk">None recorded</span>');
  }

  const notes = [];
  let body = band('Belligerents')
    + cols(ibBelligerents('Defenders', dfd), ibBelligerents('Attackers', att), true);
  if (opening && DATA.facts[opening.date]) {
    body += band('Strength')
      + `<div class="ibcaption">At ${opening.date}, ${opening.what}</div>`
      + cols(ibStrength(dfd, opening.date), ibStrength(att, opening.date));
  }
  if (w.battles.length) {
    const lost = ibLosses(w, sides);
    body += band('Casualties and losses') + cols(lost.cols[0], lost.cols[1])
      + `<div class="ibcaption" style="padding:10px 14px;border-top:1px solid var(--grid)">Total casualties: <b>${w.battles.reduce((n, b) => n + b.a[2] + b.d[2], 0).toLocaleString()}</b></div>`;
    notes.push('Casualties are each battle&rsquo;s losses, under the one nation '
      + 'the save names for each side of it.');
    if (lost.unplaced)
      notes.push(`${lost.unplaced.toLocaleString()} more were lost by nations `
        + `neither side&rsquo;s list could place.`);
  }
  if (!w.battles.length) body += band('Casualties and losses') + '<div class="ibcaption" style="padding-bottom:10px">No battle casualties recorded.</div>';
  if (Object.keys(DATA.greatPowers || {}).length) {
    notes.push(opening
      ? `Great-power ranks as of ${opening.date}, ${opening.what}.`
      : 'No save shows this war going in, so great powers are not marked: '
        + 'the saves cannot say who was one then.');
  }

  return `<div class="ib"><div class="ibtitle"><span>${w.name}</span><button type="button" class="war-export" title="Export war summary as PNG" aria-label="Export war summary as PNG"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M14 3H4v18h16V11M15 3h6v6M21 3l-9 9M4 17l5-5 5 5 3-3 3 3"/><circle cx="8" cy="7" r="1"/></svg></button><span class="war-export-status" role="status"></span></div>`
    + (MAP && w.battles.length ? '<figure id="wartheatre" class="wartheatre"></figure>' : '')
    + `<dl class="ibfacts">${facts.join('')}</dl>`
    + body
    + (notes.length ? `<div class="ibnote">${notes.map(n => `<p>${n}</p>`).join('')}</div>` : '')
    + `</div>`;
}

// A side's unit string is "kind:n;kind:n", largest first. Parsed once here for
// both the (unused in the row) army total and the expanded composition list.
function sideUnits(s) {
  const units = s[3] ? s[3].split(';').map(p => {
    const [kind, n] = p.split(':');
    return [gameName(kind), +n];
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
  const widths = [12, 20, 9, 11, 10, 11, 10, 17];
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

// Render a styled copy of the infobox, rather than redraw its flags and text.
async function warSummaryPNG(source) {
  await document.fonts.ready;
  const clone = source.cloneNode(true);
  const originals = [source, ...source.querySelectorAll('*')];
  const copies = [clone, ...clone.querySelectorAll('*')];
  originals.forEach((node, index) => {
    const style = getComputedStyle(node);
    copies[index].style.cssText = Array.from(style).map(key => key + ':' + style.getPropertyValue(key) + ';').join('');
  });
  let section = '';
  for (const child of [...clone.children]) {
    if (child.classList.contains('ibband')) section = child.dataset.warSection;
    if (child.classList.contains('ibtitle') || child.classList.contains('ibnote')) continue;
    if (child.classList.contains('ibfacts')) {
      [...child.children].slice(2).forEach(node => node.remove());
      child.style.height = 'auto';
      continue;
    }
    if (section === 'Belligerents' || section === 'Casualties and losses') continue;
    child.remove();
  }
  clone.querySelectorAll('.war-export, .war-export-status').forEach(node => node.remove());
  clone.querySelectorAll('details').forEach(node => {
    node.open = true; node.style.height = 'auto';
    node.querySelector('summary')?.remove();
  });
  // Computed pixel heights describe the original collapsed layout. Let the
  // selected sections reflow at the same width after removing other content.
  clone.querySelectorAll('div,dl,dd').forEach(node => {
    node.style.height = 'auto';
    if (node.style.display === 'grid') node.style.gridTemplateRows = 'none';
  });
  const width = Math.ceil(source.getBoundingClientRect().width);
  clone.style.width = width + 'px'; clone.style.maxWidth = 'none'; clone.style.height = 'auto';
  clone.style.margin = '0';
  const stage = document.createElement('div');
  stage.style.cssText = 'position:fixed;left:-100000px;top:0;pointer-events:none;';
  stage.appendChild(clone); document.body.appendChild(stage);
  try {
    await Promise.all([...clone.querySelectorAll('img')].map(img => img.decode()));
    const height = Math.ceil(clone.getBoundingClientRect().height);
    // SVG images have their own font context. Embed the report's webfonts so
    // the exported text keeps the same metrics and appearance.
    const fontRules = [];
    const loadedFonts = [...document.fonts].filter(font => font.status === 'loaded');
    for (const sheet of loadedFonts.length ? document.styleSheets : []) {
      let css;
      try { css = [...sheet.cssRules].map(rule => rule.cssText).join('\n'); }
      catch { if (!sheet.href) continue; const response = await fetch(sheet.href); if (!response.ok) throw new Error('Could not load report fonts.'); css = await response.text(); }
      for (const rule of css.match(/@font-face\s*\{[^}]*\}/g) || []) {
        if (!loadedFonts.some(font => rule.includes(font.family.replace(/[\"']/g, '')))) continue;
        let embedded = rule;
        for (const match of rule.matchAll(/url\(["']?([^"')]+)["']?\)/g)) {
          const response = await fetch(new URL(match[1], sheet.href || location.href));
          if (!response.ok) throw new Error('Could not load report fonts.');
          const data = await new Promise((resolve, reject) => {
            const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject;
            response.blob().then(blob => reader.readAsDataURL(blob), reject);
          });
          embedded = embedded.replace(match[0], 'url("' + data + '")');
        }
        fontRules.push(embedded);
      }
    }
    const root = document.createElementNS('http://www.w3.org/1999/xhtml', 'div');
    const sheet = source.closest('.sheet');
    const sheetStyle = getComputedStyle(sheet);
    const sheetBox = sheet.getBoundingClientRect(), sourceBox = source.getBoundingClientRect();
    root.style.cssText = 'width:' + width + 'px;background-color:' + getComputedStyle(document.body).backgroundColor + ';';
    root.style.backgroundImage = sheetStyle.backgroundImage;
    root.style.backgroundSize = sheetBox.width + 'px ' + sheetBox.height + 'px';
    root.style.backgroundPosition = (sheetBox.left - sourceBox.left) + 'px ' + (sheetBox.top - sourceBox.top) + 'px';
    const style = document.createElement('style'); style.textContent = fontRules.join('\n'); root.append(style, clone);
    const xml = new XMLSerializer().serializeToString(root);
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="' + width + '" height="' + height + '"><foreignObject width="100%" height="100%">' + xml + '</foreignObject></svg>';
    const img = new Image();
    await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = () => reject(new Error('Could not render the war summary.')); img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg); });
    const canvas = document.createElement('canvas'); canvas.width = width * 2; canvas.height = height * 2;
    const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Could not encode the war summary.')), 'image/png'));
  } finally { stage.remove(); }
}

function attachWarExport(box, war) {
  const button = box.querySelector('.war-export');
  button.onclick = async () => {
    const status = box.querySelector('.war-export-status');
    button.disabled = true; status.textContent = 'Preparing image…';
    try {
      const blob = await warSummaryPNG(box.querySelector('.ib'));
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url;
      link.download = (war.name.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'war') + '-summary.png';
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      status.textContent = 'PNG ready.';
    } catch (error) { status.textContent = 'Export failed: ' + error.message; }
    finally { button.disabled = false; }
  };
}

function drawWarDetail() {
  const box = document.getElementById('wardetail');
  const selected = warPick !== null && !!WARS[warPick];
  document.getElementById('warlist').hidden = selected;
  document.getElementById('warback').hidden = !selected;
  if (warPick === null || !WARS[warPick]) {
    box.innerHTML = '';
    return;
  }
  const w = WARS[warPick];
  const goals = w.goals.length
    ? `<table class="mini fitmini"><thead><tr><th>Demand</th><th>By</th><th>On</th>`
      + `<th>State</th><th>Taken at the peace</th><th>Occupied mid-war</th>`
      + `</tr></thead><tbody>`
      + w.goals.map(g =>
          `<tr><td>${gameName(g.cb)}</td>`
          + `<td>${warTag(g.actor)}</td><td>${warTag(g.receiver)}</td>`
          + `<td>${g.state || '—'}</td>`
          + `<td class="${g.met ? 'up' : g.part ? '' : g.checkable ? 'down' : ''}">`
          +   (!g.checkable ? '<span class="rk">not checkable</span>'
               : g.met ? `all ${g.of}` : g.part ? `${g.took} of ${g.of}` : 'none')
          + `</td>`
          + `<td class="rk">${g.sieged === null ? '—' : g.sieged ? 'yes' : 'no'}</td></tr>`)
        .join('')
      + `</tbody></table>`
      + `<p class="note">Taken at the peace shows territorial gains; occupied mid-war shows recorded occupation.</p>`
    : `<p class="note">No war goal was recorded for this war.</p>`;

  // What changed hands is the infobox's "Territorial changes" row now.
  const sea = w.battles.filter(b => b.sea), dry = w.battles.filter(b => !b.sea);
  const undated = w.battles.length - w.dated;
  box.innerHTML =
    `<div class="warlayout">${warInfobox(w)}<div class="warmain">`
    + `<div class="techsub">War goals</div>${goals}`
    + warBattleTable(dry, 'Land battles', 'land')
    + warBattleTable(sea, 'Naval battles', 'sea')
    + (undated ? `<p class="note">${undated} battle${undated === 1 ? ' has' : 's have'} no recorded date.</p>` : '')
    + `</div></div>`;

  drawWarTheatre(w);
  attachWarExport(box, w);

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

document.getElementById('warback').onclick = () => {
  const previous = warPick;
  warPick = null;
  drawWarTable();
  const row = document.querySelector(`#wartable tr[data-war="${previous}"]`);
  if (row) { row.tabIndex = -1; row.focus({preventScroll:true}); row.scrollIntoView({block:'nearest'}); }
  else document.getElementById('warfind').focus();
};

if (WARS.length) {
  document.getElementById('warfind').oninput = () => { warPick = null; drawWarTable(); };
} else {
  const tab = document.getElementById('tab-wars');
  if (tab) tab.hidden = true;
}

// Population navigation is independent of deployment and head-to-head.
let populationCountry = '', populationAllLand = false;
let populationRegion = '';
let populationBoundsDate = '', populationBounds = new Map();
const populationCountrySelect = document.getElementById('popcountry');
const populationRegionSelect = document.getElementById('popregion');
const populationRegionOf = p => String((MAP.provinceRegions || {})[p] || ('province:' + p));
const populationRegionName = r => (MAP.stateNames || {})[r] || r.replace('province:', 'Province ').replace(/_/g,' ');
// Province bounds and land neighbours are fixed across saves.
let populationProvinces = null;
function populationGeometry(date) {
  mapDecoded();
  if (!populationProvinces) {
    populationProvinces = new Map();
    for (let y=0;y<MAP.h;y++) for(let x=0;x<MAP.w;x++) {
      const p=mapProv[y*MAP.w+x];
      if(mapSea.has(p))continue;
      let box=populationProvinces.get(p);
      if(!box){box={x0:x,x1:x,y0:y,y1:y,area:0,neighbours:new Set()};populationProvinces.set(p,box);}
      box.x0=Math.min(box.x0,x);box.x1=Math.max(box.x1,x);box.y1=y;box.area++;
      for(const q of [x?mapProv[y*MAP.w+x-1]:p,y?mapProv[(y-1)*MAP.w+x]:p]) {
        if(q===p || mapSea.has(q))continue;
        box.neighbours.add(q);populationProvinces.get(q)?.neighbours.add(p);
      }
    }
  }
  if (populationBoundsDate === date) return;
  populationBoundsDate = date; populationBounds = new Map();
  const owners = mapOwners[date].own;
  const seen=new Set();
  for(const [p,start] of populationProvinces) {
    const owner=owners.get(p);
    if(owner===undefined || seen.has(p))continue;
    const part={x0:start.x0,x1:start.x1,y0:start.y0,y1:start.y1,area:0,provinces:new Set()};
    const todo=[p];seen.add(p);
    while(todo.length) {
      const q=todo.pop(), box=populationProvinces.get(q);
      part.provinces.add(q);part.area+=box.area;
      part.x0=Math.min(part.x0,box.x0);part.x1=Math.max(part.x1,box.x1);
      part.y0=Math.min(part.y0,box.y0);part.y1=Math.max(part.y1,box.y1);
      for(const n of box.neighbours)if(!seen.has(n) && owners.get(n)===owner){seen.add(n);todo.push(n);}
    }
    let country=populationBounds.get(owner);
    if(!country){country={...part,parts:[]};populationBounds.set(owner,country);}
    country.x0=Math.min(country.x0,part.x0);country.x1=Math.max(country.x1,part.x1);
    country.y0=Math.min(country.y0,part.y0);country.y1=Math.max(country.y1,part.y1);
    country.parts.push(part);
  }
}
function populationHome(box, tag, date) {
  const capital=Number(MAP.capitals?.[date]?.[tag]);
  const part=box.parts.find(p=>p.provinces.has(capital)) || box.parts.reduce((a,b)=>a.area>b.area?a:b);
  const capitalBox=part.provinces.has(capital)?populationProvinces.get(capital):null;
  // Include nearby islands across narrow seas, but keep overseas colonies out.
  const near=box.parts.filter(p=>Math.hypot(Math.max(0,part.x0-p.x1,p.x0-part.x1),Math.max(0,part.y0-p.y1,p.y0-part.y1))<MAP.w*.055);
  const home={x0:Math.min(...near.map(p=>p.x0)),x1:Math.max(...near.map(p=>p.x1)),
    y0:Math.min(...near.map(p=>p.y0)),y1:Math.max(...near.map(p=>p.y1))};
  return {part:home, cx:capitalBox?(capitalBox.x0+capitalBox.x1)/2:(part.x0+part.x1)/2,
    cy:capitalBox?(capitalBox.y0+capitalBox.y1)/2:(part.y0+part.y1)/2};
}
function drawPopulationAtlas(canvas, tag) {
  if (!MAP) return;
  const date=popSave.value; populationGeometry(date);
  const owners=mapOwners[date].own, index=MAP.tags.indexOf(tag), box=populationBounds.get(index);
  let x0=0,y0=0,width=MAP.w,height=MAP.h;
  if (box) {
    let a=box.x0,b=box.x1,c=box.y0,d=box.y1;
    let home=null;
    if(!populationAllLand && !populationRegion){
      home=populationHome(box,tag,date);
      ({x0:a,x1:b,y0:c,y1:d}=home.part);
    }
    // Selecting a state also brings distant possessions into view.
    if(populationRegion){
      let found=false;a=MAP.w;b=0;c=MAP.h;d=0;
      for(let y=0;y<MAP.h;y++) for(let x=0;x<MAP.w;x++){
        const p=mapProv[y*MAP.w+x];
        if(owners.get(p)===index && populationRegionOf(p)===populationRegion){found=true;a=Math.min(a,x);b=Math.max(b,x);c=Math.min(c,y);d=Math.max(d,y);}
      }
      if(!found){a=box.x0;b=box.x1;c=box.y0;d=box.y1;}
    }
    let cx=(a+b)/2,cy=(c+d)/2;
    width=Math.max((b-a+1)*1.16,(d-c+1)*2.32,MAP.w*.055);
    if(home && width>MAP.w*.35){width=MAP.w*.35;cx=home.cx;cy=home.cy;}
    // Keep the required span even at world edges; ocean margins letterbox it.
    height=width/2;x0=cx-width/2;y0=cy-height/2;
  }
  canvas.width=960;canvas.height=Math.round(960*height/width);
  const ctx=canvas.getContext('2d'),img=ctx.createImageData(canvas.width,canvas.height),pal=mapPalette(date);
  const regionIds=new Map(); let next=0;
  const group=new Map();
  for(const [p,owner] of owners){const r=populationRegionOf(p);if(!regionIds.has(r))regionIds.set(r,++next);group.set(p,regionIds.get(r));}
  const get=(x,y)=>x<0||y<0||x>=MAP.w||y>=MAP.h?-1:mapProv[Math.floor(y)*MAP.w+Math.floor(x)];
  const sea=p=>p===-1||mapSea.has(p);
  for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++){
    const mx=x0+x*width/canvas.width,my=y0+y*height/canvas.height,p=get(mx,my),o=owners.get(p);
    let rgb=sea(p)?[30,47,61]:[112,108,88];
    if(!sea(p) && o!==undefined && (!tag || o===index)){
      const v=pal[p];rgb=[(v>>16)&255,(v>>8)&255,v&255];
      if(tag && populationRegion && populationRegionOf(p)===populationRegion)rgb=[224,191,103];
    }
    const edge=q=>sea(p)!==sea(q)||owners.get(q)!==o||(tag&&o===index&&group.get(p)!==group.get(q));
    if(edge(get(mx+width/canvas.width,my))||edge(get(mx,my+height/canvas.height)))rgb=[35,32,28];
    img.data.set([...rgb,255],(y*canvas.width+x)*4);
  }
  ctx.putImageData(img,0,0);
  const hit=e=>{const r=canvas.getBoundingClientRect();return get(x0+(e.clientX-r.left)/r.width*width,y0+(e.clientY-r.top)/r.height*height);};
  canvas.onclick=e=>{
    const p=hit(e),t=MAP.tags[owners.get(p)];if(!t||sea(p))return;
    if(!tag)openPopulationCountry(t);
    else if(t===tag){populationAllLand=false;populationRegion=populationRegionOf(p);populationRegionSelect.value=populationRegion;refreshPopulation();}
  };
  canvas.onmousemove=e=>{
    const p=hit(e),t=MAP.tags[owners.get(p)];
    canvas.title=t?(tag?populationRegionName(populationRegionOf(p))+' · ':'')+nameOf(t):'Sea / unowned land';
  };
}
function renderPopulationState(){
  const panel=document.getElementById('popstatefacts');
  if(!populationRegion){panel.textContent='Click a state or choose one above.';return;}
  const row=((((MAP||{}).populationStates||{})[popSave.value]||{})[populationCountry]||{})[populationRegion];
  panel.textContent=populationRegionName(populationRegion)+(row?' · '+row[0].toLocaleString()+' population · '+(row[1]===null?'literacy unavailable':(row[1]*100).toFixed(1)+'% literacy'):' · State population data is unavailable in this report.');
}
function openPopulationCountry(tag){
  populationCountry=tag;populationRegion='';populationAllLand=false;refreshPopulation();
  document.getElementById('popback').focus();
}
function refreshPopulation(){
  const date=popSave.value,facts=DATA.facts[date]||{};
  document.getElementById('popcountrymap').hidden=!MAP;
  populationRegionSelect.disabled=!MAP;
  document.getElementById('popallland').disabled=!MAP;
  const tags=new Set(Object.keys(facts));
  if(MAP){mapDecoded();for(const owner of mapOwners[date].own.values())tags.add(MAP.tags[owner]);}
  populationCountrySelect.replaceChildren(new Option('Choose a country',''));
  [...tags].filter(t=>t && (t===populationCountry || populationMatches(t))).sort((a,b)=>nameOf(a).localeCompare(nameOf(b))).forEach(t=>populationCountrySelect.add(new Option(nameOf(t),t)));
  if(populationCountry&&!tags.has(populationCountry))populationCountry='';
  populationCountrySelect.value=populationCountry;
  const selected=!!populationCountry;
  document.getElementById('popbrowse').hidden=selected;
  document.getElementById('popshare').hidden=selected;
  document.getElementById('popcountrydetail').hidden=!selected;
  document.getElementById('popback').hidden=!selected;
  filterPopulationTable();
  if(!selected)return;
  populationRegionSelect.replaceChildren(new Option('Choose a state',''));
  if(MAP){
    const index=MAP.tags.indexOf(populationCountry), regions=new Set();
    for(const [p,owner] of mapOwners[date].own)if(owner===index)regions.add(populationRegionOf(p));
    [...regions].sort((a,b)=>populationRegionName(a).localeCompare(populationRegionName(b))).forEach(r=>populationRegionSelect.add(new Option(populationRegionName(r),r)));
    if(!regions.has(populationRegion))populationRegion='';
    populationRegionSelect.value=populationRegion;
    drawPopulationAtlas(document.getElementById('popcountrymap'),populationCountry);renderPopulationState();
  }else document.getElementById('popstatefacts').textContent='Geographic view requires map data. Country totals and breakdowns are available below.';
  renderPopulationDetails();
  document.getElementById('popallland').setAttribute('aria-pressed',populationAllLand);
}
function populationMatches(tag){
  const query=document.getElementById('popfind').value.trim().toLocaleLowerCase();
  return (tag+' '+nameOf(tag)).toLocaleLowerCase().includes(query);
}
function filterPopulationTable(){
  for(const row of document.querySelectorAll('#poptable tbody tr')){
    row.hidden=!row.textContent.toLocaleLowerCase().includes(document.getElementById('popfind').value.trim().toLocaleLowerCase());
  }
}
document.getElementById('popfind').oninput=()=>{drawPopTable();refreshPopulation();};
function populationStateAt(date){return MAP?.populationStates?.[date]?.[populationCountry]?.[populationRegion];}
function populationSliceColour(key,culture){
  if(!culture)return seriesColour(Math.max(0,DATA.popTypes.indexOf(key)));
  const hash=[...key].reduce((n,c)=>(n*31+c.charCodeAt(0))>>>0,0);
  return `hsl(${hash%360} 52% ${hash%2?62:49}%)`;
}
function renderPopulationPie(id, entries, total, culture=false){
  const host=document.getElementById(id);
  const rows=entries.filter(r=>r[1]>0).sort((a,b)=>b[1]-a[1]);
  const remainder=(total||0)-rows.reduce((n,r)=>n+r[1],0);
  if(rows.length && remainder>0)rows.push(['__unreported',remainder,false]);
  if(!rows.length){host.textContent='Breakdown unavailable for this selection.';return;}
  const svg=el('svg',{viewBox:'0 0 240 240',role:'img','aria-label':culture?'Culture composition':'Population composition'});
  const legend=document.createElement('div');legend.className='poppielegend';
  const readout=document.createElement('div');readout.className='poppiehint';readout.textContent='Hover a slice or focus a label for details.';
  const sum=rows.reduce((n,r)=>n+r[1],0);let angle=-Math.PI/2;
  for(const [i,[key,size,accepted]] of rows.entries()){
    const end=angle+size/sum*Math.PI*2,colour=populationSliceColour(key,culture);
    const point=a=>[120+108*Math.cos(a),120+108*Math.sin(a)];
    const start=point(angle),finish=point(end);
    const shape=rows.length===1?el('circle',{cx:120,cy:120,r:108}):el('path',{d:`M120,120 L${start} A108,108 0 ${end-angle>Math.PI?1:0},1 ${finish} Z`});
    shape.setAttribute('fill',colour);shape.setAttribute('stroke','#211b20');shape.setAttribute('stroke-width','1');
    const label=key==='__unreported'?'Unreported':culture?cultureName(key):gameName(key);
    const detail=label+' · '+size.toLocaleString()+' · '+(total?100*size/total:0).toFixed(1)+'%'+(culture&&accepted?' · Accepted':'');
    const title=el('title',{});title.textContent=detail;shape.append(title);svg.append(shape);
    const button=document.createElement('button');button.className='poppiekey';button.textContent=label;button.title=detail;button.setAttribute('aria-label',detail);
    const swatch=document.createElement('i');swatch.style.background=colour;button.prepend(swatch);
    const show=()=>{readout.textContent=detail;shape.setAttribute('stroke','#ffe4a0');shape.setAttribute('stroke-width','3');};
    const hide=()=>{shape.setAttribute('stroke','#211b20');shape.setAttribute('stroke-width','1');};
    shape.onmouseenter=show;shape.onmouseleave=hide;button.onmouseenter=show;button.onfocus=show;button.onclick=show;button.onmouseleave=hide;button.onblur=hide;
    legend.append(button);angle=end;
  }
  host.append(svg,legend,readout);
}
function renderPopulationDetails(){
  const date=popSave.value, f=DATA.facts[date]?.[populationCountry], row=populationRegion?populationStateAt(date):null;
  const types=populationRegion?(row?.[2]||{}):(DATA.pops[populationCountry]?.[date]||{});
  const cultures=populationRegion?(row?.[3]||[]):(DATA.cultures[populationCountry]?.[date]||[]);
  const total=populationRegion?row?.[0]:f?.total_pop;
  const scope=populationRegion?populationRegionName(populationRegion):nameOf(populationCountry);
  const count=v=>v==null?'Unavailable':v.toLocaleString();
  const percent=v=>v==null?'Unavailable':(v*100).toFixed(1)+'%';
  const accepted=populationRegion?(row?.[3]?.length&&total?cultures.reduce((n,c)=>n+(c[2]?c[1]:0),0)/total:null):f?.accepted_pct==null?null:f.accepted_pct/100;
  const entries=[['Population',count(total)],...(populationRegion? [['Literacy',percent(row?.[1])]]:[['Literacy · states excluding colonies',percent(f?.avg_literacy_stated)],['Literacy · whole country',percent(f?.avg_literacy)]]),['Accepted cultures',percent(accepted)],[populationRegion?'Provinces with population':'Provinces',count(populationRegion?row?.[4]:f?.provinces)],['Date',longDate(date)]];
  const host=document.getElementById('popcountryfacts');
  host.innerHTML='<div class="ibtitle"></div><dl class="ibfacts">'+entries.map(([k,v])=>'<dt>'+k+'</dt><dd>'+v+'</dd>').join('')+'</dl>';
  host.querySelector('.ibtitle').appendChild(nationIdentity(populationCountry));
  if(populationRegion){const heading=document.createElement('div');heading.className='popscope';heading.textContent=scope;host.insertBefore(heading,host.children[1]);}
  for(const [id,label] of [['poptypesnapshot','Population Composition'],['popculturesnapshot','Cultures']]){
    const section=document.createElement('section'),h=document.createElement('h2'),chart=document.createElement('div');h.textContent=label;chart.id=id;chart.className='poppie';section.append(h,chart);host.append(section);
  }
  renderPopulationPie('poptypesnapshot',Object.entries(types),total);
  renderPopulationPie('popculturesnapshot',cultures,total,true);
  document.getElementById('popscope').textContent=scope;
  if(populationRegion){
    const series={},totals={};
    for(const d of DATA.dates){const r=populationStateAt(d);if(r?.[2]){series[d]=r[2];totals[d]=r[0];}}
    const keys=[...new Set([...DATA.popTypes,...Object.values(series).flatMap(v=>Object.keys(v))])];
    populationHistory(series,keys,'State history is unavailable in these saves.',populationCountry,totals);
  }else{popTag.value=populationCountry;drawPopChart();}
}
populationCountrySelect.onchange=()=>openPopulationCountry(populationCountrySelect.value);
populationRegionSelect.onchange=()=>{populationAllLand=false;populationRegion=populationRegionSelect.value;refreshPopulation();};
document.getElementById('popback').onclick=()=>{populationCountry='';populationRegion='';refreshPopulation();populationCountrySelect.focus();};
document.getElementById('popallland').onclick=()=>{populationAllLand=!populationAllLand;populationRegion='';refreshPopulation();};

/* =============== TABS =============== */
const tabs = [...document.querySelectorAll('.tab')];
function selectTab(id) {
  if (id !== 'tab-nations') mapStopPlay();
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
    // Past the ones that have taken themselves off the row. Arrowing onto a
    // tab that is not there selects a panel nobody can see their way back
    // from.
    let at = i;
    for (let n = 0; n < tabs.length; n++) {
      at = (at + d + tabs.length) % tabs.length;
      if (!tabs[at].hidden) break;
    }
    const next = tabs[at];
    next.focus(); selectTab(next.id);
  };
});

goodsPicker.set(topMovers(6));
drawChart();
drawMilPies(); drawMilTable();
drawFleetTable();
drawPopTable(); drawCultureTable(); drawPopChart();
refreshPopulation();
searchSelect(document.getElementById('cultagsel'), 'search nations');
searchSelect(document.getElementById('poptag'), 'search nations');
drawMarketTable();
drawSupply();
searchSelect(document.getElementById('prodgood'), 'search goods');
if (TECH) drawTechTree();
if (WARS.length) drawWarTable();
searchSelect(document.getElementById('techtag'), 'search nations');
if (MAP) mapRender();
drawGreatPowers();

/* A tab with nothing behind it is worse than no tab. Technology and Wars
   already take themselves off the row when the campaign has none; the map
   and the great power ranking hide their own sections without a mod and
   left Nations on the row, selected, with an empty panel under it -- so a
   report built without a mod opened on a blank page and looked broken.
   Done here rather than beside the map because it has to run after
   everything that hides a section, and it is the same rule for all of
   them: a panel whose sections are all hidden is a tab not worth showing. */
tabs.forEach(t => {
  if (t.hidden) return;
  const panel = document.getElementById(t.getAttribute('aria-controls'));
  const sections = panel ? [...panel.querySelectorAll(':scope > section')] : [];
  if (sections.length && sections.every(s => s.hidden)) t.hidden = true;
});
const firstShown = tabs.find(t => !t.hidden);
if (firstShown) selectTab(firstShown.id);

/* Export the visible view; inline SVG styles so downloaded plots retain their
   colours without the report stylesheet. Canvas maps already contain pixels. */
async function graphPNG(source, title, subtitle, legend) {
  const isMap = source instanceof HTMLCanvasElement;
  const width = 1200;
  const box = isMap ? {width: source.width, height: source.height} : source.viewBox.baseVal;
  if (!box.width || !box.height) throw new Error('This view has not been drawn yet.');
  const height = Math.round(width * box.height / box.width);
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  // Wrap headings and legend entries before sizing; long coalition names and
  // modded unit lists must not be clipped from the exported image.
  function lines(text, font, limit) {
    ctx.font = font;
    const result = []; let line = '';
    for (const word of text.split(/\s+/)) {
      const next = line ? line + ' ' + word : word;
      if (line && ctx.measureText(next).width > limit) { result.push(line); line = word; }
      else line = next;
    }
    if (line) result.push(line);
    return result;
  }
  const titles = lines(title, 'bold 24px sans-serif', width - 48);
  const subtitles = lines(subtitle, '16px sans-serif', width - 48);
  const entries = legend.map(item => ({...item, lines: lines(item.text, '15px sans-serif', width - 76)}));
  const top = 24 + titles.length * 30 + subtitles.length * 23 + 18;
  const bottom = entries.reduce((n, item) => n + item.lines.length * 21 + 7, 0);
  canvas.width = width * 2;
  canvas.height = (top + height + bottom + 24) * 2;
  ctx.scale(2, 2);
  ctx.fillStyle = '#2A0F17'; ctx.fillRect(0, 0, canvas.width / 2, canvas.height / 2);
  let y = 30;
  ctx.fillStyle = '#E7C464'; ctx.font = 'bold 24px sans-serif';
  titles.forEach(line => { ctx.fillText(line, 24, y); y += 30; });
  ctx.fillStyle = '#C9AC80'; ctx.font = '16px sans-serif';
  subtitles.forEach(line => { ctx.fillText(line, 24, y); y += 23; });
  if (isMap) ctx.drawImage(source, 0, top, width, height);
  else {
    const clone = source.cloneNode(true);
    const originalNodes = [source, ...source.querySelectorAll('*')];
    const clonedNodes = [clone, ...clone.querySelectorAll('*')];
    const properties = ['fill','fill-opacity','stroke','stroke-width','stroke-opacity','stroke-dasharray',
      'stroke-linecap','stroke-linejoin','opacity','font-family','font-size','font-weight','font-style',
      'text-anchor','dominant-baseline','letter-spacing','visibility','display','paint-order'];
    originalNodes.forEach((node, i) => {
      const style = getComputedStyle(node);
      properties.forEach(property => clonedNodes[i].style.setProperty(property, style.getPropertyValue(property)));
    });
    clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    clone.setAttribute('width', width); clone.setAttribute('height', height);
    clone.style.width = width + 'px'; clone.style.height = height + 'px';
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], {type:'image/svg+xml'}));
    try {
      const img = new Image();
      await new Promise((resolve, reject) => { img.onload = resolve; img.onerror = () => reject(new Error('Could not render this graph.')); img.src = url; });
      ctx.drawImage(img, 0, top, width, height);
    } finally { URL.revokeObjectURL(url); }
  }
  y = top + height + 18;
  ctx.font = '15px sans-serif';
  entries.forEach(item => {
    ctx.fillStyle = item.colour; ctx.fillRect(24, y - 11, 12, 12);
    ctx.fillStyle = '#F4E7CC';
    item.lines.forEach(line => { ctx.fillText(line, 46, y); y += 21; });
    y += 7;
  });
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Could not create the PNG.')), 'image/png'));
}

// Figures share one export path, including the fleet view in the visualizer.
for (const source of document.querySelectorAll('figure > svg, #mapcanvas')) {
  const figure = source.closest('figure');
  const controls = document.createElement('div'); controls.className = 'controls export-controls';
  const button = document.createElement('button'); button.textContent = 'Export PNG';
  button.type = 'button'; button.setAttribute('aria-label', 'Export ' + (source.getAttribute('aria-label') || 'graph') + ' as PNG');
  const status = document.createElement('span'); status.className = 'note'; status.setAttribute('role', 'status');
  button.dataset.exportTarget = source.id;
  controls.append(button, status);
  const toolbar = figure.querySelector('.chart-toolbar');
  if (toolbar) toolbar.appendChild(controls);
  else figure.before(controls);
  button.onclick = async () => {
    button.disabled = true; status.textContent = 'Preparing PNG…';
    try {
      if (source.id === 'mapcanvas') mapStopPlay();
      const container = source.closest('section') || source.closest('[id^="compare-"]');
      const title = container?.querySelector('h2')?.textContent.trim() || source.getAttribute('aria-label') || 'Campaign graph';
      let subtitle = DATA.dates[0] + ' – ' + DATA.dates[DATA.dates.length - 1];
      let legend = [];
      if (source.id === 'popchart') subtitle += ' · ' + (focusedPopType ? gameName(focusedPopType) : 'All pop types');
      if (source.id === 'chart') subtitle += ' · ' + scaleBtn.textContent + (worldLine ? ' · World total included' : '');
      if (source.id === 'milpies') {
        subtitle = (milMode === 'army' ? 'Army' : 'Navy') + ' · ' + milView
          + (milMode === 'army' ? (milPotential ? ' · Potential' : ' · Current') : '')
          + ' · ' + sideLabel(sideA) + ' versus ' + sideLabel(sideB);
        legend = [...document.querySelectorAll('#millegend .slegend')].map(item => ({
          text: item.textContent.trim(), colour: getComputedStyle(item.querySelector('i')).backgroundColor}));
      }
      if (source.id === 'mapcanvas') subtitle = 'Current map view · ' + document.getElementById('mapzoom').textContent
        + ' · Occupation ' + (document.getElementById('mapocc').getAttribute('aria-pressed') === 'true' ? 'on' : 'off')
        + ' · Province borders ' + (document.getElementById('mapborders').getAttribute('aria-pressed') === 'true' ? 'on' : 'off');
      const blob = await graphPNG(source, title, subtitle, legend);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url;
      link.download = (title + (source.id === 'milpies' ? '-' + milMode + '-' + milView : '')).replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').slice(0, 120) + '.png';
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      status.textContent = 'PNG ready.';
    } catch (error) { status.textContent = 'Export failed: ' + error.message; }
    finally { button.disabled = false; }
  };
}

window.campaign = DATA;
})().catch(bootFailed);
</script>
</body>
</html>
"""
