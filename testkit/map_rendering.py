#!/usr/bin/env python3
"""Check map tile pixels, seams, cache reuse and date changes in a built report.

    python3 testkit/map_rendering.py /path/to/report.html

Uses a temporary copy to access renderer internals; the shipped report exposes
no testing API. Needs a report with a map and at least two saves.
"""
import json
from pathlib import Path
import sys
import tempfile

import boots

PROBE = r"""
window.checkMapRendering = function () {
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  check(MAP && DATA.dates.length > 1, 'Fixture needs a map and multiple saves');
  let pixelsChecked=0;
  const dates=[DATA.dates[0],DATA.dates[DATA.dates.length-1]];
  for (const date of dates) {
    const palette=mapTileState(date);
    const owners=mapOwners[date].own, occupations=mapOwners[date].occ;
    const owner = p => mapSea.has(p) ? -2 : (owners.get(p) ?? -1);
    for (const borders of [false,true]) {
      mapShowProvinceBorders=borders;
      for (const level of [0,1,2]) {
        const idx=mapLevel(level);
        const positions=[[0,0],[Math.floor((idx.w-1)/256),Math.floor((idx.h-1)/256)],
          [Math.floor(idx.w/512),Math.floor(idx.h/512)]];
        for (const [tx,ty] of positions) {
          const tile=mapTile(level,tx,ty,palette,true);
          check(mapTile(level,tx,ty,palette,true)===tile,'Unchanged tile was rebuilt');
          const base=tile.base.getContext('2d').getImageData(0,0,tile.base.width,tile.base.height).data;
          const occ=tile.occ.getContext('2d').getImageData(0,0,tile.occ.width,tile.occ.height).data;
          const w=tile.base.width,h=tile.base.height;
          // Sample the entire tile perimeter, especially neighbours across
          // the right/bottom seams, plus regularly spaced interior pixels.
          for(let y=0;y<h;y++) for(let x=0;x<w;x++) {
            if(x!==0 && y!==0 && x!==w-1 && y!==h-1 && (x%31 || y%31)) continue;
            const gx=tx*256+x,gy=ty*256+y,p=idx.prov[gy*idx.w+gx];
            const neighbours=[];
            if(gx+1<idx.w) neighbours.push(idx.prov[gy*idx.w+gx+1]);
            if(gy+1<idx.h) neighbours.push(idx.prov[(gy+1)*idx.w+gx]);
            const edge=neighbours.some(n=>borders ? n!==p : owner(n)!==owner(p));
            let expected=MAP_WILD;
            if(mapSea.has(p)) expected=MAP_WATER;
            const hex=MAP.colours[MAP.tags[owners.get(p)]];
            if(hex) {
              const n=parseInt(hex.slice(1),16);
              expected=[n>>16,(n>>8)&255,n&255].map(v=>Math.round(v*.65+45));
            }
            if(edge) expected=MAP_EDGE;
            const at=(y*w+x)*4;
            check(expected.every((v,c)=>base[at+c]===v) && base[at+3]===255,'Wrong ownership/border pixel');
            const occupying=MAP.colours[MAP.tags[occupations.get(p)]];
            check(occ[at+3]===(!edge && occupying ? 255 : 0),'Stale or missing occupation pixel');
            if(!edge && occupying) {
              const n=parseInt(occupying.slice(1),16);
              check(occ[at]===(n>>16) && occ[at+1]===((n>>8)&255) && occ[at+2]===(n&255),'Wrong occupier colour');
            }
            pixelsChecked++;
          }
        }
      }
    }
  }
  // Transparent gaps at tile joins must not expose the ocean underneath land.
  mapShowProvinceBorders=false;
  const oldX=mapOX,oldY=mapOY;
  for(const dpr of [1,2]) for(const scale of [.24,.251,.49,.51,1.01,4]) {
    const canvas=document.createElement('canvas');
    const cw=317,ch=193;canvas.width=cw*dpr;canvas.height=ch*dpr;
    const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
    mapOX=MAP.w*.3+.37;mapOY=MAP.h*.2+.61;
    mapPaintTiles(ctx,null,dates[0],scale,cw,ch,dpr);
    const bytes=ctx.getImageData(0,0,canvas.width,canvas.height).data;
    // The fixture must be large enough for the viewport to stay on the raster.
    check(mapOX+cw/scale<MAP.w && mapOY+ch/scale<MAP.h,'Fixture map is too small for seam check');
    for(let i=3;i<bytes.length;i+=4) check(bytes[i]===255,'Gap between rendered tiles');
    check(mapTiles.size<=MAP_TILE_LIMIT,'Tile cache exceeded its bound');
  }
  mapOX=oldX;mapOY=oldY;
  mapRender();
  return {pixelsChecked};
};
"""


def main():
    html = Path(sys.argv[1]).read_text()
    anchor = '/* Export the visible view;'
    if anchor not in html:
        raise RuntimeError('Report does not contain the expected renderer')
    html = html.replace(anchor, PROBE + '\n' + anchor, 1)
    boots.WATCHER = boots.WATCHER.replace(
        'tourWars(verdict);',
        "try { say('mapRendering', JSON.stringify(window.checkMapRendering())); } "
        "catch(e) { bad.push('mapRendering: '+e.message); } verdict();")
    with tempfile.TemporaryDirectory(prefix='vic2-map-rendering-') as folder:
        report = Path(folder) / 'report.html'
        report.write_text(html)
        result = boots.looked(str(report))
    print(json.dumps(result))
    return 0 if result and not result['error'] and result.get('mapRendering') else 1


if __name__ == '__main__':
    sys.exit(main())
