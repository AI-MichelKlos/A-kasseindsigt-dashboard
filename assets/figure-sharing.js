(function () {
  'use strict';

  const cards = new Map();
  let resolveReady;
  const ready = new Promise(resolve => { resolveReady = resolve; });
  let navigationToken = 0;

  function viewStatus() {
    return window.DAKPersonalView?.getStatus() || { busy: true, ok: false };
  }

  function chartTitle(card) {
    return (card.querySelector('h3')?.textContent || 'Graf').replace(/^\s*Figur\s+\d+:\s*/, '').trim();
  }

  function getShareUrl(id) {
    if (!cards.has(id)) throw new Error('Ukendt graf');
    const api = window.DAKPersonalView;
    if (!api || !viewStatus().ok) throw new Error('De valgte data er ikke klar til deling.');
    const url = new URL('del/' + encodeURIComponent(id) + '/', new URL('./', location.href));
    url.searchParams.set('pv', api.encodeState(api.getState()));
    url.hash = 'graf-' + id;
    return url.href;
  }

  function linkedinUrl(id) {
    return 'https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(getShareUrl(id));
  }

  function feedback(card, message) {
    const node = card.querySelector('.chart-share-feedback');
    if (node) node.textContent = message;
  }

  function syncButtons() {
    const status = viewStatus();
    cards.forEach((card, id) => {
      card.querySelectorAll('[data-share-action]').forEach(control => {
        const disabled = !status.ok || control.dataset.working === 'true';
        if (control.tagName === 'A') {
          control.setAttribute('aria-disabled', String(disabled));
          if (disabled) control.removeAttribute('href');
          else control.href = linkedinUrl(id);
        } else control.disabled = disabled;
      });
      if (status.busy) feedback(card, 'Henter de valgte data …');
      else if (!status.ok) feedback(card, 'De valgte data kunne ikke indlæses. Vælg filtre igen før deling.');
      else if (/^(Henter de valgte data|De valgte data kunne ikke)/.test(card.querySelector('.chart-share-feedback')?.textContent || '')) feedback(card, '');
    });
  }

  async function copyLink(card, id) {
    try {
      const url = getShareUrl(id);
      try {
        if (!navigator.clipboard?.writeText) throw new Error('Udklipsholder er ikke tilgængelig.');
        await navigator.clipboard.writeText(url);
        feedback(card, 'Link kopieret. Det åbner grafen med dine valgte filtre.');
      } catch (_) {
        window.prompt('Kopiér link til grafen', url);
        feedback(card, 'Linket kan kopieres fra dialogboksen.');
      }
    } catch (error) {
      feedback(card, error.message);
    }
  }

  function textLines(context, text, width) {
    const words = String(text || '').replace(/\s+/g, ' ').trim().split(' ');
    const lines = [];
    let line = '';
    words.forEach(word => {
      const candidate = line ? line + ' ' + word : word;
      if (line && context.measureText(candidate).width > width) {
        lines.push(line);
        line = word;
      } else line = candidate;
    });
    if (line) lines.push(line);
    return lines;
  }

  function selectionText(card, id) {
    const selected = document.getElementById('fundSelect')?.selectedOptions[0]?.textContent || '';
    const geography = card.querySelector('.geography-context')?.textContent?.trim() || '';
    const comparison = card.querySelector('.comparison-context')?.textContent?.trim() || '';
    const horizon = id === 'rmMainChart' ? document.getElementById('rmHorizon')?.selectedOptions[0]?.textContent : '';
    const period = card.querySelector('.period-highlight')?.textContent?.replace(/\s+/g, ' ').trim() || '';
    return [selected, geography, comparison, horizon, period].filter(Boolean).join(' | ');
  }

  function comparisonText(card) {
    // Raw-count graphs can show a selected comparison only in these strips.
    // Keep every displayed value and its period when exporting the canvas.
    return [...card.querySelectorAll('.comparison-strip')].map(strip => {
      const values = [...strip.querySelectorAll('.comparison-chip')].map(chip => chip.textContent.replace(/\s+/g, ' ').trim());
      const period = strip.querySelector('.comparison-period')?.textContent?.replace(/\s+/g, ' ').trim();
      return { values, period: period || '' };
    }).filter(block => block.values.length);
  }

  async function downloadImage(card, id, button) {
    button.dataset.working = 'true';
    syncButtons();
    feedback(card, 'Klargør billede …');
    try {
      await window.DAKPersonalView.whenIdle();
      if (!viewStatus().ok) throw new Error('De valgte data kunne ikke indlæses.');
      const section = card.closest('section');
      await window.DAKDashboardExperience.activateSection(section.dataset.section);
      const canvas = document.getElementById(id);
      const chart = window.Chart?.getChart(canvas);
      if (!chart || !canvas?.width || !canvas?.height) throw new Error('Grafen har ingen data for den valgte visning.');
      chart.stop();
      chart.update('none');

      // Use the rendered chart so the exported values, colours and filters agree
      // with the graph being shared, including any documented national fallback.
      const output = document.createElement('canvas');
      const context = output.getContext('2d');
      if (!context) throw new Error('Browseren kunne ikke oprette billedet.');
      output.width = 1600;
      const padding = 64;
      const contentWidth = output.width - 2 * padding;
      context.font = 'bold 40px Arial, sans-serif';
      const title = textLines(context, chartTitle(card), contentWidth);
      context.font = '25px Arial, sans-serif';
      const selection = textLines(context, selectionText(card, id), contentWidth);
      const chartTop = 116 + title.length * 49 + selection.length * 34;
      const chartHeight = Math.min(1000, Math.max(430, contentWidth * canvas.height / canvas.width));
      context.font = '24px Arial, sans-serif';
      const comparisonBlocks = comparisonText(card).map(block => ({
        values: block.values.map(value => textLines(context, value, contentWidth - 40)),
        period: textLines(context, block.period, contentWidth - 40)
      }));
      const comparisonHeight = comparisonBlocks.length ? 62 + comparisonBlocks.reduce((height, block) => height + block.values.reduce((rows, lines) => rows + lines.length * 32 + 6, 0) + block.period.length * 32 + 16, 0) : 0;
      const source = card.querySelector('.source')?.textContent?.replace(/\s+/g, ' ').trim() || '';
      context.font = '23px Arial, sans-serif';
      const sourceLines = textLines(context, source, contentWidth);
      output.height = Math.ceil(chartTop + chartHeight + comparisonHeight + 128 + sourceLines.length * 30);
      context.fillStyle = '#ffffff';
      context.fillRect(0, 0, output.width, output.height);
      context.fillStyle = '#6B9E78';
      context.fillRect(0, 0, output.width, 12);
      context.fillStyle = '#4a3428';
      context.font = 'bold 25px Arial, sans-serif';
      context.fillText('A-kasseindsigt', padding, 68);
      context.fillStyle = '#2B211B';
      context.font = 'bold 40px Arial, sans-serif';
      title.forEach((line, index) => context.fillText(line, padding, 120 + index * 49));
      context.fillStyle = '#6f6258';
      context.font = '25px Arial, sans-serif';
      selection.forEach((line, index) => context.fillText(line, padding, 137 + title.length * 49 + index * 34));
      const scale = Math.min(contentWidth / canvas.width, chartHeight / canvas.height);
      const width = canvas.width * scale;
      const height = canvas.height * scale;
      context.drawImage(canvas, padding + (contentWidth - width) / 2, chartTop, width, height);
      if (comparisonBlocks.length) {
        const top = chartTop + chartHeight + 20;
        context.fillStyle = '#f2f7fb';
        context.fillRect(padding, top, contentWidth, comparisonHeight - 12);
        context.fillStyle = '#2B211B';
        context.font = 'bold 24px Arial, sans-serif';
        context.fillText('Sammenligningstal', padding + 20, top + 34);
        context.font = '24px Arial, sans-serif';
        let y = top + 72;
        comparisonBlocks.forEach(block => {
          context.fillStyle = '#2B211B';
          block.values.forEach(lines => {
            lines.forEach(line => { context.fillText(line, padding + 20, y); y += 32; });
            y += 6;
          });
          context.fillStyle = '#6f6258';
          block.period.forEach(line => { context.fillText(line, padding + 20, y); y += 32; });
          y += 16;
        });
      }
      context.fillStyle = '#6f6258';
      context.font = '23px Arial, sans-serif';
      const sourceTop = chartTop + chartHeight + comparisonHeight + 48;
      sourceLines.forEach((line, index) => context.fillText(line, padding, sourceTop + index * 30));
      context.font = '21px Arial, sans-serif';
      context.fillText('ai-michelklos.github.io/A-kasseindsigt-dashboard/', padding, output.height - 34);
      const blob = await new Promise(resolve => output.toBlob(resolve, 'image/png'));
      if (!blob) throw new Error('Billedet kunne ikke dannes.');
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = 'A-kasseindsigt-' + id + '.png';
      link.hidden = true;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      feedback(card, 'Billedet er hentet med dine aktuelle filtre. Brug også linket, når du deler.');
    } catch (error) {
      feedback(card, error.message);
    } finally {
      delete button.dataset.working;
      syncButtons();
    }
  }

  function attach(card, id) {
    const toolbar = card.querySelector('.chart-toolbar');
    if (!toolbar || toolbar.querySelector('[data-share-action]')) return;
    toolbar.classList.add('chart-share');
    const linkedin = document.createElement('a');
    linkedin.className = 'chart-action dak-share-linkedin';
    linkedin.dataset.shareAction = 'linkedin';
    linkedin.textContent = 'Del på LinkedIn';
    linkedin.target = '_blank';
    linkedin.rel = 'noopener noreferrer';
    linkedin.setAttribute('aria-label', 'Del ' + chartTitle(card) + ' på LinkedIn (åbner et nyt vindue)');
    linkedin.addEventListener('click', event => {
      if (!viewStatus().ok) {
        event.preventDefault();
        feedback(card, 'Vent med at dele, til de valgte data er indlæst.');
        return;
      }
      // Compute in the user's click event; the native link can open a tab even
      // in browsers that block popups created after asynchronous work.
      linkedin.href = linkedinUrl(id);
    });
    const copy = document.createElement('button');
    copy.type = 'button';
    copy.className = 'chart-action dak-share-copy';
    copy.dataset.shareAction = 'copy';
    copy.textContent = 'Kopiér link';
    copy.setAttribute('aria-label', 'Kopiér link til ' + chartTitle(card));
    copy.addEventListener('click', () => copyLink(card, id));
    const image = document.createElement('button');
    image.type = 'button';
    image.className = 'chart-action dak-share-image';
    image.dataset.shareAction = 'image';
    image.textContent = 'Hent billede';
    image.setAttribute('aria-label', 'Hent billede af ' + chartTitle(card) + ' med de valgte filtre');
    image.addEventListener('click', () => downloadImage(card, id, image));
    toolbar.append(linkedin, copy, image);

    const note = document.createElement('p');
    note.className = 'chart-share-note';
    note.textContent = 'LinkedIn-billedet viser I alt for hele landet. Linket åbner dine valgte filtre.';
    const status = document.createElement('p');
    status.className = 'chart-share-feedback';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    toolbar.insertAdjacentElement('afterend', note);
    note.insertAdjacentElement('afterend', status);
  }

  function requestedChart(useQuery = true) {
    let hash = '';
    try { hash = decodeURIComponent(location.hash.slice(1)); } catch (_) { /* Invalid fragments are ignored. */ }
    if (hash.startsWith('graf-') && cards.has(hash.slice(5))) return hash.slice(5);
    if (!useQuery) return null;
    const params = new URLSearchParams(location.search);
    for (const key of ['graf', 'chart', 'figure']) {
      const id = params.get(key);
      if (cards.has(id)) return id;
    }
    return null;
  }

  async function openChart(id) {
    await ready;
    if (!cards.has(id)) return false;
    const token = ++navigationToken;
    await window.DAKPersonalView.ready;
    await window.DAKPersonalView.whenIdle();
    if (token !== navigationToken) return false;
    const card = await window.DAKDashboardExperience.revealChart(id);
    if (!card || token !== navigationToken) return false;
    cards.forEach(other => other.classList.remove('dak-shared-figure'));
    card.classList.add('dak-shared-figure');
    card.tabIndex = -1;
    card.focus({ preventScroll: true });
    // Measure whichever navigation bands are actually sticky in this layout.
    // An explicit offset avoids combining the page's scroll-padding and the
    // card's scroll-margin, and works when controls wrap on a narrow screen.
    const stickyBottom = [...document.querySelectorAll('.control-band, .section-nav')].reduce((bottom, element) => {
      const style = getComputedStyle(element);
      if (!['sticky', 'fixed'].includes(style.position)) return bottom;
      return Math.max(bottom, (parseFloat(style.top) || 0) + element.getBoundingClientRect().height);
    }, 0);
    window.scrollTo({ top: Math.max(0, window.scrollY + card.getBoundingClientRect().top - stickyBottom - 16), behavior: 'instant' });
    return true;
  }

  async function initialize() {
    await window.DAKDashboardExperience.ready;
    document.querySelectorAll('#dashboard .card[data-share-chart]').forEach(card => {
      const id = card.dataset.shareChart;
      cards.set(id, card);
      attach(card, id);
    });
    window.addEventListener('dak:view-state', syncButtons);
    document.getElementById('dashboardFilters')?.addEventListener('change', () => queueMicrotask(syncButtons));
    window.addEventListener('hashchange', () => {
      const id = requestedChart(false);
      if (id) openChart(id);
    });
    syncButtons();
    resolveReady();
    await window.DAKPersonalView.ready;
    syncButtons();
    const id = requestedChart();
    if (id) await openChart(id);
  }

  window.DAKSharing = Object.freeze({ ready, getShareUrl, openChart });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
