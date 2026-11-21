(function () {
  'use strict';

  const ROOT = 'https://ai-michelklos.github.io/A-kasseindsigt-dashboard/';

  function selection(id) {
    const el = document.getElementById(id);
    return el && el.selectedOptions && el.selectedOptions[0]
      ? el.selectedOptions[0].textContent.trim() : '';
  }

  function contextLines() {
    const lines = [];
    const fund = selection('fundSelect');
    const region = selection('regionSelect');
    const span = selection('periodSelect');
    const comparison = selection('comparisonFundSelect');
    const compareRegion = selection('comparisonRegionSelect');
    if (fund) lines.push('A-kasse: ' + fund);
    if (region && region !== 'Hele landet') lines.push('Geografi: ' + region);
    if (span) lines.push('Viste periode: ' + span);
    if (comparison && comparison !== 'Ingen') lines.push('Sammenligning: ' + comparison);
    if (compareRegion && compareRegion !== 'Ingen') lines.push('Sammenligningsgeografi: ' + compareRegion);
    return lines;
  }

  function shareLink(id) {
    const page = ROOT + 'share/' + encodeURIComponent(id) + '.html';
    const current = new URL(location.href);
    // The per-figure copy button generates a full, reusable pv URL.
    const button = document.getElementById(id)?.closest('.card')?.querySelector('.dak-share-copy');
    if (button && typeof window.__dakShareLinkForFigure === 'function') {
      return window.__dakShareLinkForFigure(id);
    }
    current.searchParams.set('figure', id);
    return current.href;
  }

  function wrap(ctx, text, x, baseline, width, size, maxLines) {
    ctx.font = '700 ' + size + 'px Arial, sans-serif';
    const words = String(text).split(/\s+/);
    let line = '';
    let count = 0;
    for (const word of words) {
      const next = line ? line + ' ' + word : word;
      if (ctx.measureText(next).width > width && line) {
        ctx.fillText(line, x, baseline);
        baseline += size * 1.25;
        count++;
        line = word;
        if (count >= maxLines - 1) break;
      } else line = next;
    }
    if (line) ctx.fillText(line, x, baseline);
    return baseline + size * 1.28;
  }

  function renderCard(canvas, card) {
    const w = 1200, h = 1200;
    const art = document.createElement('canvas');
    art.width = w;
    art.height = h;
    const c = art.getContext('2d');
    if (!c) throw new Error('Billedgenerering understøttes ikke i browseren.');
    const heading = card.querySelector('h3')?.textContent.replace(/^\s*Figur \d+:\s*/, '').trim() || 'A-kasseindsigt';
    const source = card.querySelector('.source')?.querySelector('span')?.textContent.trim() || 'Kilde: Danmarks Statistik og Jobindsats.dk';

    c.fillStyle = '#f7f1ea';
    c.fillRect(0, 0, w, h);
    c.fillStyle = '#fff';
    c.fillRect(28, 28, 1144, 1144);
    c.fillStyle = '#6B9E78';
    c.fillRect(28, 28, 1144, 12);
    c.fillStyle = '#263E32';
    c.font = '700 26px Arial, sans-serif';
    c.fillText('A-KASSEINDSIGT', 80, 92);
    c.fillStyle = '#2B211B';
    const endTitle = wrap(c, heading, 80, 152, 1020, 46, 2);
    c.font = '22px Arial, sans-serif';
    c.fillStyle = '#6f6258';
    const lines = contextLines();
    let y = Math.max(230, endTitle + 12);
    for (const label of lines.slice(0, 3)) {
      c.fillText(label, 80, y);
      y += 31;
    }

    const frame = {x:65, y: Math.max(355, y + 16), w:1070, h:655};
    c.fillStyle = '#fff';
    c.fillRect(frame.x, frame.y, frame.w, frame.h);
    const sw = canvas.width, sh = canvas.height;
    if (!sw || !sh) throw new Error('Grafen er endnu ikke tegnet. Vis grafen og prøv igen.');
    const factor = Math.min(frame.w / sw, frame.h / sh);
    const drawW = sw * factor, drawH = sh * factor;
    c.drawImage(canvas, frame.x + (frame.w-drawW)/2, frame.y + (frame.h-drawH)/2, drawW, drawH);
    c.fillStyle = '#e8ebe8';
    c.fillRect(80, 1062, 1040, 2);

    c.fillStyle = '#35493B';
    c.font = '700 22px Arial, sans-serif';
    c.fillText('Michel Klos', 80, 1105);
    c.font = '18px Arial, sans-serif';
    c.fillStyle = '#6f6258';
    const src = source.length > 100 ? source.slice(0, 97) + '...' : source;
    c.fillText(src, 80, 1140);
    return art;
  }

  function showInfo(toolbar, text, link, copied) {
    const card = toolbar.closest('.card');
    let box = card.querySelector('.dak-linkedin-image-info');
    if (!box) {
      box = document.createElement('div');
      box.className = 'dak-linkedin-image-info';
      box.setAttribute('role', 'status');
      toolbar.insertAdjacentElement('afterend', box);
    }
    box.replaceChildren();
    const p = document.createElement('p');
    p.textContent = text + (copied ? ' Tekst og link er kopieret.' : ' Kopiér linket herunder og indsæt det i opslaget.');
    box.append(p);
    const row = document.createElement('div');
    row.className = 'dak-linkedin-image-actions';
    const input = document.createElement('input');
    input.type = 'text';
    input.readOnly = true;
    input.setAttribute('aria-label', 'Link til denne graf');
    input.value = link;
    const action = document.createElement('button');
    action.type = 'button';
    action.textContent = 'Kopiér opslagstekst';
    action.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(card.dataset.dakLinkedinText || link);
        action.textContent = 'Kopieret';
      } catch (_) {
        input.focus();
        input.select();
        action.textContent = 'Markér og kopiér linket';
      }
    });
    row.append(input, action);
    box.append(row);
    const a = document.createElement('a');
    a.href = 'https://www.linkedin.com/feed/';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = 'Åbn LinkedIn for at oprette billedopslaget';
    box.append(a);
  }

  function createButton(card) {
    const graph = card.querySelector('canvas[id]');
    const toolbar = card.querySelector('.chart-toolbar');
    if (!graph || !toolbar || toolbar.querySelector('.dak-share-large-image')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chart-action dak-share-large-image';
    button.textContent = 'Hent stort LinkedIn-billede';
    button.setAttribute('aria-label', 'Hent et stort LinkedIn-billede af denne graf');
    toolbar.append(button);
    button.addEventListener('click', async () => {
      button.disabled = true;
      button.textContent = 'Laver billede...';
      try {
        const art = renderCard(graph, card);
        const blob = await new Promise(resolve => art.toBlob(resolve, 'image/png'));
        if (!blob) throw new Error('Kunne ikke oprette PNG-filen.');
        const blobUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = 'a-kasseindsigt-' + graph.id + '-linkedin.png';
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(blobUrl), 15000);

        const title = card.querySelector('h3')?.textContent.replace(/^\s*Figur \d+:\s*/, '').trim() || 'A-kasseindsigt';
        const url = shareLink(graph.id);
        const text = title + '\n\nSe og tilpas grafen i A-kasseindsigt:\n' + url;
        card.dataset.dakLinkedinText = text;
        let copied = false;
        try { await navigator.clipboard.writeText(text); copied = true; } catch (_) {}
        showInfo(toolbar, 'Billedet er hentet. Upload det som billede i dit LinkedIn-opslag.', url, copied);
      } catch (err) {
        showInfo(toolbar, err && err.message ? err.message : 'Kunne ikke hente billedet.', shareLink(graph.id), false);
      } finally {
        button.disabled = false;
        button.textContent = 'Hent stort LinkedIn-billede';
      }
    });
  }

  const style = document.createElement('style');
  style.textContent = '#dashboard .chart-toolbar{flex-wrap:wrap}' +
    '#dashboard .dak-share-large-image{background:#ebf3ee;border-color:#6B9E78;color:#26432f}' +
    '#dashboard .dak-linkedin-image-info{padding:13px 15px;margin:10px 0;border:1px solid #b6d3bd;background:#f3f8f4;border-radius:9px;font-size:.85rem;line-height:1.5}' +
    '#dashboard .dak-linkedin-image-info p{margin:0 0 10px}' +
    '#dashboard .dak-linkedin-image-actions{display:flex;gap:8px;flex-wrap:wrap}' +
    '#dashboard .dak-linkedin-image-actions input{flex:1;min-width:190px;padding:9px;border:1px solid #b9c8bf;border-radius:6px;background:white}' +
    '#dashboard .dak-linkedin-image-actions button{padding:9px;border-radius:7px;background:white;border:1px solid #6B9E78;cursor:pointer}' +
    '#dashboard .dak-linkedin-image-info a{display:inline-block;margin-top:10px;color:#146298}' +
    '@media(max-width:720px){#dashboard .chart-toolbar .chart-action{flex:1 1 42%}}';
  document.head.append(style);
  function init() {
    const dashboard = document.getElementById('dashboard');
    if (!dashboard) return;
    function attach() { dashboard.querySelectorAll('.card').forEach(createButton); }
    attach();
    new MutationObserver(attach).observe(dashboard, {childList:true,subtree:true});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init);
  else init();
})();