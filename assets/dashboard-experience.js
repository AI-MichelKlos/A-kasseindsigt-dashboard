(function () {
  'use strict';

  const SECTION_DEFS = [
    ['members', 'Medlemmer'],
    ['unemployment', 'Ledighed'],
    ['benefits', 'Dagpenge'],
    ['results', 'Resultater'],
    ['duration', 'Varighed'],
    ['after-benefits', 'Efter dagpenge'],
    ['talks', 'Samtaler'],
    ['retirement', 'Efterløn'],
    ['sanctions', 'Sanktioner']
  ];
  const COMPARISON_CHARTS = new Set([
    'membersRawChart', 'membersIndexChart', 'ageChart', 'unempChart',
    'longRawChart', 'longIndexChart', 'dagChart', 'gradCountChart',
    'gradChart', 'consChart', 'exhaustedChart', 'survChart',
    'completedDurationChart', 'statusChart', 'afterlonChart',
    'afterlonContribChart', 'sanctionsTotalChart', 'sanctionsShareChart',
    'sanctionsAvgChart', 'rmMainChart'
  ]);
  const PRIMARY = '#3d6b47';
  const COMPARE = '#4a90c4';
  const TOTAL = '#6f6258';

  window.__dakLazySections = new Set(['members']);

  if (window.Chart) {
    Chart.defaults.font.family = '"Segoe UI", Arial, sans-serif';
    Chart.defaults.color = '#445650';
    if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      Chart.defaults.animation = false;
    }
    Chart.register({
      id: 'dakComparisonStyle',
      beforeUpdate(chart) {
        if (!COMPARISON_CHARTS.has(chart.canvas?.id)) return;
        // Grafer med egne serier pr. gruppe (fx opbrugt dagpengeret) styrer selv farverne.
        if (chart.data.datasets.some(dataset => dataset.dakKeepStyle)) return;
        const line = chart.config.type === 'line';
        chart.data.datasets.forEach((dataset, index) => {
          const total = index > 0 && /^(I alt|Total)(?:\s|$)/i.test(String(dataset.label || ''));
          const color = index === 0 ? PRIMARY : total ? TOTAL : COMPARE;
          dataset.borderColor = color;
          dataset.backgroundColor = line ? color : color + (index === 0 ? 'dd' : 'bb');
          dataset.borderWidth = index === 0 ? 3 : 2;
          dataset.borderDash = total ? [7, 5] : [];
          if (line) {
            dataset.pointRadius = context => {
              const data = context.dataset.data || [];
              let last = data.length - 1;
              while (last >= 0 && data[last] == null) last -= 1;
              return context.dataIndex === last ? (index === 0 ? 4 : 3) : 0;
            };
            dataset.pointHoverRadius = 6;
          }
        });
      }
    });
  }

  let rmPromise = null;

  function loadResultSummary() {
    if (typeof RM_DATA !== 'undefined' && RM_DATA) return Promise.resolve(RM_DATA);
    if (rmPromise) return rmPromise;
    const message = document.getElementById('rmMainMessage');
    if (message) {
      message.hidden = false;
      message.textContent = 'Henter den kompakte resultatmåling …';
    }
    rmPromise = fetch('data/rm01ak-summary.json', { cache: 'no-store' })
      .then(response => {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(data => {
        RM_DATA = data;
        return data;
      })
      .catch(error => {
        rmPromise = null;
        if (message) {
          message.hidden = false;
          message.textContent = 'Resultatmålingen kunne ikke indlæses. ' + error.message;
        }
        return null;
      });
    return rmPromise;
  }

  function renderDashboard() {
    if (typeof draw === 'function' && typeof DATA !== 'undefined' && DATA) draw();
  }

  async function activateSection(key) {
    if (window.__dakLazySections.has(key)) return;
    if (key === 'results') await loadResultSummary();
    window.__dakLazySections.add(key);
    renderDashboard();
  }

  function setupSections() {
    const sections = [...document.querySelectorAll('#dashboard > section')];
    sections.forEach((section, index) => {
      const definition = SECTION_DEFS[index];
      if (!definition) return;
      const [key, label] = definition;
      section.id = section.id || 'section-' + key;
      section.dataset.section = key;
      section.dataset.expanded = index === 0 ? 'true' : 'false';

      const intro = section.querySelector(':scope > p');
      const body = document.createElement('div');
      body.className = 'section-body';
      const start = intro ? intro.nextSibling : section.querySelector('h2')?.nextSibling;
      let node = start;
      while (node) {
        const next = node.nextSibling;
        body.appendChild(node);
        node = next;
      }

      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'section-reveal';
      button.setAttribute('aria-expanded', section.dataset.expanded);
      button.textContent = index === 0 ? 'Skjul analyser' : 'Vis analyser';
      button.addEventListener('click', async () => {
        const expanded = section.dataset.expanded !== 'true';
        section.dataset.expanded = String(expanded);
        button.setAttribute('aria-expanded', String(expanded));
        button.textContent = expanded ? 'Skjul analyser' : 'Vis analyser';
        if (expanded) {
          await activateSection(key);
          requestAnimationFrame(() => Object.values(typeof charts === 'undefined' ? {} : charts).forEach(chart => chart?.resize()));
        }
      });

      if (intro) intro.insertAdjacentElement('afterend', button);
      else section.querySelector('h2')?.insertAdjacentElement('afterend', button);
      section.appendChild(body);
      section.dataset.navLabel = label;
    });
    return sections;
  }

  function setupNavigation(sections) {
    const nav = document.createElement('nav');
    nav.className = 'section-nav';
    nav.setAttribute('aria-label', 'Indhold i A-kasseindsigt');
    nav.innerHTML = '<div class="wrap section-nav-inner"><a href="#dashboard" data-nav="overview">Overblik</a>' +
      sections.map(section => '<a href="#' + section.id + '" data-nav="' + section.dataset.section + '">' + section.dataset.navLabel + '</a>').join('') +
      '</div>';
    document.querySelector('.control-band')?.insertAdjacentElement('afterend', nav);

    nav.addEventListener('click', event => {
      const link = event.target.closest('a[data-nav]');
      if (!link || link.dataset.nav === 'overview') return;
      const section = document.querySelector('[data-section="' + link.dataset.nav + '"]');
      if (window.matchMedia('(max-width: 720px)').matches && section) {
        section.dataset.expanded = 'true';
        const button = section.querySelector('.section-reveal');
        if (button) {
          button.setAttribute('aria-expanded', 'true');
          button.textContent = 'Skjul analyser';
        }
      }
      activateSection(link.dataset.nav);
    });

    if ('IntersectionObserver' in window) {
      const navObserver = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return;
          nav.querySelectorAll('a').forEach(link => link.removeAttribute('aria-current'));
          nav.querySelector('[data-nav="' + entry.target.dataset.section + '"]')?.setAttribute('aria-current', 'location');
        });
      }, { rootMargin: '-30% 0px -60% 0px', threshold: 0 });
      sections.forEach(section => navObserver.observe(section));
    }
  }

  function setupLazyRendering(sections) {
    if (!('IntersectionObserver' in window)) {
      sections.forEach(section => activateSection(section.dataset.section));
      return;
    }
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        if (window.matchMedia('(max-width: 720px)').matches && entry.target.dataset.expanded !== 'true') return;
        activateSection(entry.target.dataset.section);
        observer.unobserve(entry.target);
      });
    }, { rootMargin: '420px 0px 420px 0px', threshold: 0.01 });
    sections.forEach(section => observer.observe(section));
  }

  function setupFilters() {
    const band = document.querySelector('.control-band');
    const controls = band?.querySelector('.controls');
    if (!band || !controls) return;

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'filter-toggle';
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-controls', 'dashboardFilters');
    toggle.textContent = 'Vælg visning';
    controls.id = 'dashboardFilters';
    band.querySelector('.wrap')?.prepend(toggle);
    toggle.addEventListener('click', () => {
      const open = !band.classList.contains('filters-open');
      band.classList.toggle('filters-open', open);
      toggle.setAttribute('aria-expanded', String(open));
    });

    const updateHeight = () => {
      const height = band.getBoundingClientRect().height;
      document.documentElement.style.setProperty('--control-height', Math.round(height) + 'px');
    };
    updateHeight();
    if ('ResizeObserver' in window) new ResizeObserver(updateHeight).observe(band);

    const connectComparison = () => {
      const select = document.getElementById('comparisonFundSelect');
      if (!select || select.dataset.experienceBound) return false;
      select.dataset.experienceBound = 'true';
      const update = () => document.body.classList.toggle('has-comparison', Boolean(select.value));
      select.addEventListener('change', update);
      update();
      return true;
    };
    if (!connectComparison()) {
      const observer = new MutationObserver(() => {
        if (connectComparison()) observer.disconnect();
      });
      observer.observe(controls, { childList: true, subtree: true });
    }
  }

  function setupOverview() {
    const dashboard = document.getElementById('dashboard');
    const kpiGrid = dashboard?.querySelector(':scope > .kpis');
    if (!dashboard || !kpiGrid) return;
    const heading = document.createElement('div');
    heading.className = 'overview-heading';
    heading.innerHTML = '<span class="eyebrow">Aktuelt overblik</span><h2 id="overviewTitle">Valgt enhed</h2><p id="overviewContext">De vigtigste bevægelser i de seneste tal.</p>';
    const insight = document.createElement('div');
    insight.className = 'insight-summary';
    insight.id = 'insightSummary';
    insight.setAttribute('role', 'status');
    insight.setAttribute('aria-live', 'polite');
    insight.innerHTML = '<p>Indsigten vises, når data er indlæst.</p>';
    dashboard.insertBefore(insight, kpiGrid);
    dashboard.insertBefore(heading, insight);
    [...kpiGrid.children].forEach((card, index) => card.classList.add(index < 4 ? 'is-primary' : 'is-secondary'));
  }

  function priorPoint(series, key, currentPeriod) {
    if (!series?.labels?.length || !Array.isArray(series[key])) return null;
    const index = series.labels.lastIndexOf(currentPeriod);
    for (let i = index - 1; i >= 0; i -= 1) {
      if (series[key][i] != null) return { period: series.labels[i], value: Number(series[key][i]) };
    }
    return null;
  }

  function deltaMarkup(delta, percent, direction) {
    if (!Number.isFinite(delta)) return '<span class="delta-neutral">Ikke tilgængelig</span>';
    const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '●';
    const formatted = percent ? new Intl.NumberFormat('da-DK', { maximumFractionDigits: 1 }).format(Math.abs(delta)) + ' pct.point' : new Intl.NumberFormat('da-DK', { maximumFractionDigits: 0 }).format(Math.abs(delta));
    let quality = 'delta-neutral';
    if (direction === 'up-good' && delta !== 0) quality = delta > 0 ? 'delta-good' : 'delta-bad';
    if (direction === 'up-bad' && delta !== 0) quality = delta > 0 ? 'delta-bad' : 'delta-good';
    return '<span class="' + quality + '">' + arrow + ' ' + formatted + '</span>';
  }

  function metricDelta(series, key, percent, direction) {
    const current = typeof last === 'function' ? last(series, key) : null;
    if (!current) return null;
    const previous = priorPoint(series, key, current.period);
    const year = typeof previousYear === 'function' ? previousYear(series, key, current.period) : null;
    return {
      current,
      previous,
      year,
      monthDelta: previous ? Number(current.value) - Number(previous.value) : null,
      yearDelta: year ? Number(current.value) - Number(year.value) : null,
      percent,
      direction
    };
  }

  function enhanceKpis(selectedFund) {
    const grid = document.querySelector('#dashboard > .kpis');
    if (!grid || !selectedFund) return;
    const metrics = [
      metricDelta(selectedFund.members, 'values', false, 'up-good'),
      metricDelta(selectedFund.unemploymentRate, 'values', true, 'up-bad'),
      metricDelta(selectedFund.jobindsats?.longTerm, 'persons', false, 'up-bad'),
      metricDelta(selectedFund.jobindsats?.dagpenge, 'fulltime', false, 'up-bad'),
      metricDelta(selectedFund.jobindsats?.graduates, 'share', true, 'up-bad'),
      metricDelta(selectedFund.jobindsats?.talkForms, 'total', false, 'neutral')
    ];
    [...grid.children].forEach((card, index) => {
      let delta = card.querySelector('.kpi-delta');
      if (!delta) {
        delta = document.createElement('div');
        delta.className = 'kpi-delta';
        card.appendChild(delta);
      }
      const metric = metrics[index];
      delta.innerHTML = metric
        ? '<span><strong>Seneste:</strong> ' + deltaMarkup(metric.monthDelta, metric.percent, metric.direction) + '</span><span><strong>År:</strong> ' + deltaMarkup(metric.yearDelta, metric.percent, metric.direction) + '</span>'
        : '<span class="delta-neutral">Udvikling ikke tilgængelig</span>';
    });

    const region = document.getElementById('regionSelect');
    const regionLabel = region?.selectedOptions?.[0]?.textContent || 'Hele landet';
    const title = document.getElementById('overviewTitle');
    if (title) title.textContent = selectedFund.name + ' · ' + regionLabel;
    const context = document.getElementById('overviewContext');
    if (context) context.textContent = 'Seneste niveau, udvikling siden forrige observation og samme periode året før.';
    const member = metrics[0];
    const unemployment = metrics[1];
    const parts = [];
    if (member && Number.isFinite(member.yearDelta)) parts.push('Antallet af forsikringsaktive er ' + (member.yearDelta >= 0 ? 'steget' : 'faldet') + ' med ' + new Intl.NumberFormat('da-DK', { maximumFractionDigits: 0 }).format(Math.abs(member.yearDelta)) + ' siden samme periode sidste år.');
    if (unemployment && Number.isFinite(unemployment.yearDelta)) parts.push('Ledigheden er ' + (unemployment.yearDelta >= 0 ? 'steget' : 'faldet') + ' med ' + new Intl.NumberFormat('da-DK', { maximumFractionDigits: 1 }).format(Math.abs(unemployment.yearDelta)) + ' procentpoint på et år.');
    const insight = document.getElementById('insightSummary');
    if (insight) insight.innerHTML = '<p>' + (parts.join(' ') || 'Der er endnu ikke nok sammenlignelige perioder til en automatisk hovedpointe.') + '</p>';
  }

  function installKpiEnhancement() {
    if (typeof kpis !== 'function') return;
    const base = kpis;
    kpis = function (selectedFund) {
      base(selectedFund);
      enhanceKpis(selectedFund);
    };
    if (typeof DATA !== 'undefined' && DATA && typeof fund === 'function') enhanceKpis(fund());
  }

  function simplifyExplanations() {
    const repeated = [
      ' Hvis der vælges en sammenligning uden I alt, vises den som en ekstra serie.',
      ' Når I alt indgår, vises tydelige sammenligningstal ved grafen.',
      ' Sammenligning er valgfri og kan vælges med en selvstændig geografi.'
    ];
    document.querySelectorAll('.desc').forEach(description => {
      let text = description.textContent;
      repeated.forEach(sentence => { text = text.replace(sentence, ''); });
      description.textContent = text.trim();
    });
    document.querySelectorAll('.explain').forEach(explanation => {
      if (explanation.id === 'rmMainMessage' || explanation.closest('.metric-help') || explanation.textContent.trim().length < 150) return;
      const details = document.createElement('details');
      details.className = 'metric-help';
      const summary = document.createElement('summary');
      summary.textContent = explanation.textContent.includes('datanote') ? 'Læs vigtig datanote' : 'Hvad betyder målingen?';
      explanation.parentNode.insertBefore(details, explanation);
      details.append(summary, explanation);
    });
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  }

  function chartRows(chart) {
    const labels = chart?.data?.labels || [];
    const datasets = chart?.data?.datasets || [];
    return { labels, datasets };
  }

  function buildDataTable(canvas, host) {
    const chart = Chart.getChart(canvas);
    if (!chart) {
      host.innerHTML = '<div class="lazy-message">Grafen indlæses. Prøv igen om et øjeblik.</div>';
      return;
    }
    const { labels, datasets } = chartRows(chart);
    const header = '<tr><th scope="col">Periode/kategori</th>' + datasets.map(dataset => '<th scope="col">' + escapeHtml(dataset.label || 'Værdi') + '</th>').join('') + '</tr>';
    const body = labels.map((label, rowIndex) => '<tr><th scope="row">' + escapeHtml(typeof period === 'function' ? period(label) : label) + '</th>' + datasets.map(dataset => {
      const raw = dataset.data?.[rowIndex];
      const value = raw && typeof raw === 'object' ? (raw.y ?? raw.x ?? '') : raw;
      return '<td>' + escapeHtml(value == null ? '–' : new Intl.NumberFormat('da-DK', { maximumFractionDigits: 2 }).format(Number(value))) + '</td>';
    }).join('') + '</tr>').join('');
    host.innerHTML = '<table><thead>' + header + '</thead><tbody>' + body + '</tbody></table>';
  }

  function downloadCsv(canvas) {
    const chart = Chart.getChart(canvas);
    if (!chart) return;
    const { labels, datasets } = chartRows(chart);
    const quote = value => '"' + String(value ?? '').replace(/"/g, '""') + '"';
    const rows = [["Periode/kategori", ...datasets.map(dataset => dataset.label || 'Værdi')]];
    labels.forEach((label, index) => rows.push([
      typeof period === 'function' ? period(label) : label,
      ...datasets.map(dataset => {
        const raw = dataset.data?.[index];
        return raw && typeof raw === 'object' ? (raw.y ?? raw.x ?? '') : (raw ?? '');
      })
    ]));
    const csv = '\ufeff' + rows.map(row => row.map(quote).join(';')).join('\r\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = (canvas.id || 'graf') + '.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function setupChartAccess() {
    document.querySelectorAll('.card').forEach((card, index) => {
      const canvas = card.querySelector('canvas');
      const chartHost = canvas?.closest('.chart');
      if (!canvas || !chartHost || card.querySelector('.chart-toolbar')) return;
      const title = card.querySelector('h3')?.textContent?.trim() || 'Graf';
      const description = card.querySelector('.desc')?.textContent?.trim();
      canvas.setAttribute('role', 'img');
      canvas.setAttribute('aria-label', title + (description ? '. ' + description : ''));

      const tableId = 'chartData' + index;
      const toolbar = document.createElement('div');
      toolbar.className = 'chart-toolbar';
      toolbar.innerHTML = '<button type="button" class="chart-action show-data" aria-expanded="false" aria-controls="' + tableId + '">Vis data</button><button type="button" class="chart-action download-data">Hent CSV</button>';
      const table = document.createElement('div');
      table.className = 'chart-data';
      table.id = tableId;
      table.hidden = true;
      chartHost.insertAdjacentElement('afterend', toolbar);
      toolbar.insertAdjacentElement('afterend', table);

      toolbar.querySelector('.show-data').addEventListener('click', async event => {
        const section = card.closest('section');
        if (section?.dataset.section) await activateSection(section.dataset.section);
        const open = table.hidden;
        table.hidden = !open;
        event.currentTarget.setAttribute('aria-expanded', String(open));
        event.currentTarget.textContent = open ? 'Skjul data' : 'Vis data';
        if (open) buildDataTable(canvas, table);
      });
      toolbar.querySelector('.download-data').addEventListener('click', async () => {
        const section = card.closest('section');
        if (section?.dataset.section) await activateSection(section.dataset.section);
        downloadCsv(canvas);
      });
    });
  }

  function markSourceState() {
    document.querySelectorAll('.source span:last-child').forEach(status => {
      status.classList.toggle('is-stale', /^Forældet:/i.test(status.textContent));
    });
  }

  function numberFigures() {
    let figure = 0;
    document.querySelectorAll('#dashboard .card').forEach(card => {
      if (!card.querySelector('canvas')) return;
      const heading = card.querySelector(':scope > h3');
      if (!heading) return;
      let label = heading.querySelector('.figure-number');
      if (!label) {
        label = document.createElement('span');
        label.className = 'figure-number';
        heading.prepend(label);
      }
      const visible = !card.closest('section[hidden]') && !card.hidden;
      label.textContent = visible ? 'Figur ' + (++figure) + ': ' : '';
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const skip = document.createElement('a');
    skip.className = 'skip-link';
    skip.href = '#main-content';
    skip.textContent = 'Spring til indhold';
    document.body.prepend(skip);

    setupOverview();
    numberFigures();
    const figureSections = document.querySelectorAll('#dashboard > section');
    const figureObserver = new MutationObserver(numberFigures);
    figureSections.forEach(section => figureObserver.observe(section, { attributes: true, attributeFilter: ['hidden'] }));
    const sections = setupSections();
    setupNavigation(sections);
    setupFilters();
    setupLazyRendering(sections);
    simplifyExplanations();
    setupChartAccess();
    installKpiEnhancement();
    markSourceState();

    const dashboard = document.getElementById('dashboard');
    if (dashboard) new MutationObserver(markSourceState).observe(dashboard, { childList: true, subtree: true, characterData: true });
  });
})();
