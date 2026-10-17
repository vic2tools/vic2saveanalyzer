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
