'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../assets/share-redirect.js'), 'utf8');

function follow(query, linkHref = '../../?graf=rmMainChart#graf-rmMainChart', currentPath = 'del/rmMainChart/') {
  const current = new URL('https://ai-michelklos.github.io/A-kasseindsigt-dashboard/' + currentPath + query);
  let destination = null;
  const link = { getAttribute: () => linkHref, href: linkHref };
  vm.runInNewContext(source, {
    URL, URLSearchParams,
    document: { getElementById: () => link },
    window: { location: { href: current.href, origin: current.origin, search: current.search, replace(value) { destination = value; } } }
  });
  return { destination: destination && new URL(destination), link };
}

const state = { v: 5, fund: '31', region: 'hovedstaden', period: '24', comparisonFund: 'TOT', comparisonRegion: 'all', rmHorizon: 'six', hidden: ['section-3'] };
const encoded = Buffer.from(JSON.stringify(state)).toString('base64url');
const filtered = follow('?pv=' + encoded + '&v=abc&redirect=https%3A%2F%2Fexample.com');
assert.equal(filtered.destination.pathname, '/A-kasseindsigt-dashboard/');
assert.equal(filtered.destination.searchParams.get('graf'), 'rmMainChart');
assert.equal(filtered.destination.searchParams.get('pv'), encoded);
assert.equal(filtered.destination.hash, '#graf-rmMainChart');
assert.equal(filtered.destination.searchParams.has('redirect'), false);
assert.equal(filtered.destination.searchParams.has('v'), false);
assert.equal(filtered.link.href, filtered.destination.href);
const legacy = follow('?pv=' + encoded, '../?graf=rmMainChart#graf-rmMainChart', 'share/rmMainChart.html');
assert.equal(legacy.destination.href, filtered.destination.href);
assert.equal(legacy.link.href, filtered.link.href);

for (const query of ['', '?pv=%3Cscript%3E', '?pv=' + 'a'.repeat(12001)]) {
  const { destination } = follow(query);
  assert.equal(destination.searchParams.has('pv'), false);
  assert.equal(destination.searchParams.get('graf'), 'rmMainChart');
  assert.equal(destination.hash, '#graf-rmMainChart');
}
assert.equal(follow('?pv=' + encoded, 'https://example.com/').destination, null);
console.log('OK: landing redirects keep filters and graph, reject unexpected destinations and malformed state');
