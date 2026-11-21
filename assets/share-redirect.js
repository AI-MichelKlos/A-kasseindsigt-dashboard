(function () {
  'use strict';

  // The link is generated from the chart registry, never from a user-provided URL.
  const link = document.getElementById('open-dashboard');
  if (!link) return;
  const target = new URL(link.getAttribute('href'), window.location.href);
  if (target.origin !== window.location.origin) return;
  const incoming = new URLSearchParams(window.location.search);
  const state = incoming.get('pv');
  if (state && state.length <= 12000 && /^[A-Za-z0-9_-]+$/.test(state)) {
    target.searchParams.set('pv', state);
  }
  link.href = target.href;
  // Crawlers receive the page-specific Open Graph tags in the original HTML.
  // Browsers retain the complete personal-view state and graph anchor.
  window.location.replace(target.href);
})();
