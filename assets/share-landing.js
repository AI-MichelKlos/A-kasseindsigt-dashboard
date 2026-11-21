(function () {
  'use strict';

  // The graph id comes from generated HTML, never from a destination URL in input.
  // Keep only the bounded, URL-safe personal-view token. The dashboard validates
  // its contents against known controls after the available data have loaded.
  const chart = document.body.dataset.chart;
  const link = document.getElementById('open-chart');
  if (!chart || !/^[A-Za-z][A-Za-z0-9]*$/.test(chart) || !link) return;

  const destination = new URL('../../', location.href);
  const params = new URLSearchParams(location.search);
  const view = params.get('pv');
  if (view && view.length <= 12000 && /^[A-Za-z0-9_-]+$/.test(view)) {
    destination.searchParams.set('pv', view);
  } else if (params.has('pv')) {
    // Preserve an explicitly invalid shared view as an empty token. Omitting
    // it would let the dashboard restore an unrelated local saved view.
    destination.searchParams.set('pv', '');
    const note = document.getElementById('share-note');
    if (note) note.textContent = 'Linkets filtre kunne ikke læses. Grafen åbnes med standardvisningen.';
  }
  destination.searchParams.set('chart', chart);
  destination.hash = 'graf-' + chart;
  link.href = destination.href;

  // No meta-refresh: it would lose the visitor's query parameters. Keep the
  // visible link as a fallback if automatic navigation is blocked.
  const openDashboard = function () { location.replace(destination.href); };
  if (document.readyState === 'complete') openDashboard();
  else window.addEventListener('load', openDashboard, { once: true });
})();
