/**
 * main.js — Boot sequence, data loading, theme toggle, nav highlighting
 */

// ── Data cache ───────────────────────────────────────────────────────────────
const DATA = {};

async function loadJSON(name) {
  if (DATA[name]) return DATA[name];
  const r = await fetch(`data/${name}.json`);
  if (!r.ok) throw new Error(`Failed to load ${name}.json: ${r.status}`);
  DATA[name] = await r.json();
  return DATA[name];
}

// ── Boot ─────────────────────────────────────────────────────────────────────
async function boot() {
  // Load all data in parallel
  const [tps, cliff, quality, crossDevice, threads, kvQuant, ppl, rawTable] =
    await Promise.all([
      loadJSON('tps_by_variant'),
      loadJSON('cliff_curves'),
      loadJSON('quality_scores'),
      loadJSON('cross_device'),
      loadJSON('thread_sweep'),
      loadJSON('kv_quant'),
      loadJSON('perplexity'),
      loadJSON('raw_table'),
    ]);

  // Init all charts and table
  initTpsChart(tps);
  initCliffChart(cliff, kvQuant);
  initQualityChart(quality);
  initHeatmap(crossDevice);
  initThreadChart(threads);
  initPplChart(ppl);
  initTable(rawTable);

  // Cross-chart highlight sync
  State.onChange(variant => {
    highlightTpsChart(variant);
    highlightCliffChart(variant);
    highlightQualityChart(variant);
    highlightHeatmapRow(variant);
    highlightTableRows(variant);
  });
}

// ── Theme toggle ─────────────────────────────────────────────────────────────
function initTheme() {
  const html   = document.documentElement;
  const btn    = document.getElementById('theme-toggle');
  const moon   = document.getElementById('icon-moon');
  const sun    = document.getElementById('icon-sun');

  // Default dark
  html.classList.add('dark');

  btn.addEventListener('click', () => {
    const isDark = html.classList.toggle('dark');
    moon.classList.toggle('hidden', !isDark);
    sun.classList.toggle('hidden', isDark);
    // Re-render charts with updated grid colours
    Chart.instances && Object.values(Chart.instances).forEach(c => c.update());
  });
}

// ── Active nav link on scroll ────────────────────────────────────────────────
function initScrollSpy() {
  const sections = document.querySelectorAll('section[id]');
  const links    = document.querySelectorAll('.nav-link');

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const id = entry.target.id;
        links.forEach(l => {
          l.classList.toggle(
            'text-white',
            l.getAttribute('href') === `#${id}`
          );
        });
      }
    });
  }, { rootMargin: '-40% 0px -55% 0px' });

  sections.forEach(s => observer.observe(s));
}

// ── Entry point ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initScrollSpy();
  boot().catch(err => {
    console.error('Dashboard boot error:', err);
    document.body.insertAdjacentHTML('afterbegin',
      `<div class="fixed top-4 left-1/2 -translate-x-1/2 z-[999] bg-red-900 text-white text-sm px-4 py-2 rounded-lg shadow-lg">
        Failed to load data: ${err.message}
      </div>`
    );
  });
});
