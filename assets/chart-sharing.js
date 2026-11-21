(function () {
  'use strict';

  const baseURL = new URL('./', document.baseURI);
  const chartMap = new Map();
  const nextFrame = () => new Promise(resolve => requestAnimationFrame(resolve));
  const domReady = document.readyState === 'loading'
    ? new Promise(resolve => document.addEventListener('DOMContentLoaded', resolve, { once: true }))
    : Promise.resolve();
  let definitions = [];
  let dialog;
  let returnFocus;

  // Lazy section activation redraws existing graphs. Preserve a user's legend
  // selections across those redraws, including selections restored from a link.
  const legendSelections = new Map();
  const pendingLegendSelections = new WeakMap();
  if (window.Chart) Chart.register({
    id: 'dakSharedLegend',
    beforeDestroy(chart) {
      if (!chart.canvas?.id) return;
      legendSelections.set(chart.canvas.id, chart.data.datasets.flatMap((dataset, index) =>
        chart.isDatasetVisible(index) ? [] : [{ index, label: String(dataset.label || '') }]));
    },
    beforeUpdate(chart) {
      if (!pendingLegendSelections.has(chart)) {
        pendingLegendSelections.set(chart, [...(legendSelections.get(chart.canvas?.id) || [])]);
      }
      // Geography labels and comparison datasets may arrive in a later update.
      // Remove only matches, so later user legend clicks remain free.
      const pending = pendingLegendSelections.get(chart).filter(item => {
        const dataset = chart.data.datasets[item.index];
        if (!dataset || String(dataset.label || '') !== item.label) return true;
        chart.setDatasetVisibility(item.index, false);
        return false;
      });
      pendingLegendSelections.set(chart, pending);
    }
  });

  function chartInstance(id) {
    const canvas = document.getElementById(id);
    return canvas && window.Chart ? Chart.getChart(canvas) : null;
  }

  function stateForChart(id) {
    if (!chartMap.has(id)) throw new Error('Grafen findes ikke.');
    const view = window.DAKPersonalView;
    if (!view || view.isBusy) throw new Error('Vent, mens de valgte filtre indlæses.');
    if (view.status?.state === 'error') throw new Error('Et filter kunne ikke indlæses. Vælg det igen, før du deler.');
    const state = { ...view.getState() };
    const chart = chartInstance(id);
    // Legend selections belong to this graph, not to every graph in the dashboard.
    if (chart) {
      state.chartView = {
        id,
        hiddenDatasets: chart.data.datasets.flatMap((dataset, index) =>
          chart.isDatasetVisible(index) ? [] : [{ index, label: String(dataset.label || '') }])
      };
    }
    return state;
  }

  function getLink(id) {
    const definition = chartMap.get(id);
    const state = stateForChart(id);
    const url = new URL('share/' + definition.slug + '/', baseURL);
    url.searchParams.set('pv', window.DAKPersonalView.encodeState(state));
    return url.href;
  }

  function getDirectLink(id) {
    const state = stateForChart(id);
    const url = new URL(baseURL);
    url.searchParams.set('pv', window.DAKPersonalView.encodeState(state));
    url.searchParams.set('chart', id);
    url.hash = 'graf-' + id;
    return url.href;
  }

  function feedback(card, message) {
    const status = card.querySelector('.chart-share-feedback');
    if (status) status.textContent = message;
  }

  function getDialog() {
    if (dialog) return dialog;
    dialog = document.createElement('dialog');
    dialog.id = 'chartShareDialog';
    dialog.setAttribute('aria-labelledby', 'chartShareTitle');
    dialog.innerHTML = '<h2 id="chartShareTitle">Kopiér link til grafen</h2>' +
      '<p>Linket åbner grafen med dine valgte filtre. Markér og kopiér hele linket.</p>' +
      '<label for="chartShareUrl">Link til grafen</label>' +
      '<input id="chartShareUrl" type="url" readonly>' +
      '<button type="button" data-share-close>Luk</button>';
    dialog.querySelector('[data-share-close]').addEventListener('click', () => {
      if (typeof dialog.close === 'function') dialog.close();
      else dialog.removeAttribute('open');
      returnFocus?.focus();
    });
    dialog.addEventListener('close', () => returnFocus?.focus());
    document.body.appendChild(dialog);
    return dialog;
  }

  async function copyLink(id, card, button) {
    let url;
    try { url = getLink(id); }
    catch (error) { feedback(card, error.message); return; }
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(url);
      feedback(card, 'Link til grafen er kopieret. Dine filtre følger med.');
    } catch (_) {
      const modal = getDialog();
      const input = modal.querySelector('input');
      input.value = url;
      returnFocus = button;
      if (typeof modal.showModal === 'function') modal.showModal();
      else modal.setAttribute('open', '');
      input.focus();
      input.select();
      feedback(card, 'Kopiér linket i det åbne vindue.');
    }
  }

  function updateLinkedInLink(link, id, card, reportError = false) {
    try {
      link.href = 'https://www.linkedin.com/sharing/share-offsite/?url=' + encodeURIComponent(getLink(id));
      link.removeAttribute('aria-disabled');
      return true;
    } catch (error) {
      link.removeAttribute('href');
      link.setAttribute('aria-disabled', 'true');
      if (reportError) feedback(card, error.message);
      return false;
    }
  }

  function installButtons() {
    definitions.forEach(definition => {
      const card = document.getElementById('graf-' + definition.id);
      if (!card || card.querySelector('.share-linkedin')) return;
      let toolbar = card.querySelector('.chart-toolbar');
      if (!toolbar) {
        toolbar = document.createElement('div');
        toolbar.className = 'chart-toolbar';
        (card.querySelector('.chart') || card.querySelector('h3')).insertAdjacentElement('afterend', toolbar);
      }
      const link = document.createElement('a');
      link.className = 'chart-action share-linkedin';
      link.tabIndex = 0;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Del på LinkedIn';
      link.setAttribute('aria-label', 'Del ' + definition.title + ' på LinkedIn');
      link.title = 'LinkedIn viser grafens emne. Linket åbner grafen med dine valgte filtre.';
      // Update synchronously for ordinary clicks, keyboard activation and context menus.
      ['pointerdown', 'focus', 'contextmenu'].forEach(type => link.addEventListener(type, () => updateLinkedInLink(link, definition.id, card)));
      link.addEventListener('click', event => {
        if (!updateLinkedInLink(link, definition.id, card, true)) event.preventDefault();
      });
      const copy = document.createElement('button');
      copy.type = 'button';
      copy.className = 'chart-action copy-chart-link';
      copy.textContent = 'Kopiér link';
      copy.setAttribute('aria-label', 'Kopiér link til ' + definition.title);
      copy.addEventListener('click', () => copyLink(definition.id, card, copy));
      const status = document.createElement('span');
      status.className = 'chart-share-feedback';
      status.setAttribute('role', 'status');
      status.setAttribute('aria-live', 'polite');
      toolbar.append(link, copy, status);
      updateLinkedInLink(link, definition.id, card);
    });
    const refreshLinks = () => {
      definitions.forEach(definition => {
        const card = document.getElementById('graf-' + definition.id);
        const link = card?.querySelector('.share-linkedin');
        if (link) updateLinkedInLink(link, definition.id, card);
      });
    };
    window.addEventListener('dak:personal-view-status', refreshLinks);
    document.getElementById('dashboardFilters')?.addEventListener('change', refreshLinks);
    const bar = document.getElementById('pvControls');
    if (bar && !document.getElementById('chartSharingNote')) {
      const note = document.createElement('p');
      note.id = 'chartSharingNote';
      note.textContent = 'Del en enkelt graf med knapperne under grafen. LinkedIn viser grafens emne; linket åbner dine valgte filtre.';
      bar.appendChild(note);
    }
  }

  function restoreLegend(id) {
    const shared = window.DAKPersonalView.decodeState(new URL(location.href).searchParams.get('pv') || '');
    const selection = shared?.chartView;
    const chart = chartInstance(id);
    if (!chart || selection?.id !== id || !Array.isArray(selection.hiddenDatasets)) return;
    selection.hiddenDatasets.slice(0, 100).forEach(item => {
      if (!item || !Number.isInteger(item.index) || item.index < 0) return;
      const dataset = chart.data.datasets[item.index];
      // Do not hide an unrelated series if source data has changed since sharing.
      if (dataset && String(dataset.label || '') === item.label) chart.setDatasetVisibility(item.index, false);
    });
    chart.update('none');
  }

  async function openChart(id, options = {}) {
    if (!chartMap.has(id)) return false;
    const card = document.getElementById('graf-' + id);
    const section = card?.closest('section');
    if (!card || !section) return false;
    // A direct link must remain reachable even when a saved view hid its section.
    section.hidden = false;
    card.hidden = false;
    section.dataset.expanded = 'true';
    const checkbox = [...document.querySelectorAll('[data-pv-module]')]
      .find(input => input.value === section.dataset.personalViewKey);
    if (checkbox) checkbox.checked = true;
    const reveal = section.querySelector('.section-reveal');
    if (reveal) {
      reveal.setAttribute('aria-expanded', 'true');
      reveal.textContent = 'Skjul analyser';
    }
    await window.DAKDashboard.activateSection(section.dataset.section);
    await nextFrame();
    const chart = chartInstance(id);
    chart?.resize();
    if (options.restoreLegend) restoreLegend(id);
    await nextFrame();
    card.classList.add('shared-chart');
    card.tabIndex = -1;
    const navHeight = document.querySelector('.section-nav')?.getBoundingClientRect().height || 0;
    card.style.scrollMarginTop = Math.ceil(navHeight + 18) + 'px';
    card.scrollIntoView({ block: 'start', behavior: 'instant' });
    card.focus({ preventScroll: true });
    return true;
  }

  function showNotice(text) {
    let notice = document.getElementById('chartShareNotice');
    if (!notice) {
      notice = document.createElement('p');
      notice.id = 'chartShareNotice';
      notice.setAttribute('role', 'status');
      document.getElementById('dashboard')?.prepend(notice);
    }
    notice.textContent = text;
  }

  async function init() {
    const response = await fetch(new URL('config/share-charts.json', baseURL));
    if (!response.ok) throw new Error('Delingsknapperne kunne ikke indlæses. Genindlæs siden for at prøve igen.');
    const manifest = await response.json();
    definitions = (manifest.charts || []).filter(item =>
      /^[A-Za-z][A-Za-z0-9]*$/.test(item.id) && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(item.slug));
    definitions.forEach(item => chartMap.set(item.id, item));
    await domReady;
    await window.DAKDashboard.ready;
    await window.DAKPersonalView.ready;
    installButtons();
    const url = new URL(location.href);
    const id = url.searchParams.get('chart') || (url.hash.startsWith('#graf-') ? url.hash.slice(6) : '');
    if (id && !await openChart(id, { restoreLegend: true })) {
      showNotice('Den delte graf findes ikke. Du kan vælge en graf i dashboardet nedenfor.');
    }
    return { charts: definitions.length };
  }

  window.DAKSharing = {
    getLink,
    getDirectLink,
    openChart,
    get charts() { return definitions; },
    ready: init().catch(async error => {
      await domReady;
      showNotice(error.message);
      console.error('Grafdeling:', error);
      return { error: error.message };
    })
  };
})();
