/* =============== POPULATION =============== */
const popSave = document.getElementById('popsave');
fillSelect(popSave, DATA.dates);
popSave.value = DATA.lastDate;
popSave.onchange = () => { drawPopTable(); refreshPopulation(); };

let popShare = false;
toggleButton(document.getElementById('popshare'), () => (popShare = !popShare),
             () => drawPopTable(), ['Counts', 'Shares']);

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

// The nation the population history chart is drawn for.
let popChartTag = largestBy('total_pop');

const drawPopChart = () => populationHistory(
  DATA.pops[popChartTag] || {}, DATA.popTypes,
  nameOf(popChartTag) + ' has no pops in these saves.', popChartTag);


/* ---- one country's population ---- */
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
  // The land provinces' boxes, areas and land neighbours, in the order the
  // map first meets them.
  if (!populationProvinces)
    populationProvinces = new Map([...provinceGeometry()].filter(([p]) => !mapSea.has(p)));
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
    let rgb=sea(p)?MAP_WATER:MAP_WILD;
    if(!sea(p) && o!==undefined && (!tag || o===index)){
      const v=pal[p];rgb=[(v>>16)&255,(v>>8)&255,v&255];
      if(tag && populationRegion && populationRegionOf(p)===populationRegion)rgb=[224,191,103];
    }
    const edge=q=>sea(p)!==sea(q)||owners.get(q)!==o||(tag&&o===index&&group.get(p)!==group.get(q));
    if(edge(get(mx+width/canvas.width,my))||edge(get(mx,my+height/canvas.height)))rgb=MAP_EDGE;
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
    const shape=rows.length===1?el('circle',{cx:120,cy:120,r:108}):el('path',{d:arcPath(120,120,0,108,angle,end)});
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
  }else{popChartTag=populationCountry;drawPopChart();}
}
populationCountrySelect.onchange=()=>openPopulationCountry(populationCountrySelect.value);
populationRegionSelect.onchange=()=>{populationAllLand=false;populationRegion=populationRegionSelect.value;refreshPopulation();};
document.getElementById('popback').onclick=()=>{populationCountry='';populationRegion='';refreshPopulation();populationCountrySelect.focus();};
document.getElementById('popallland').onclick=()=>{populationAllLand=!populationAllLand;populationRegion='';refreshPopulation();};

registerTab('tab-pops', {init() { drawPopTable(); drawPopChart(); refreshPopulation(); }});
exportNotes.popchart = base => ({
  subtitle: base + ' · ' + (focusedPopType ? gameName(focusedPopType) : 'All pop types')});
