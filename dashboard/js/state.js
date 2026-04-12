/**
 * state.js — Global reactive state for cross-chart linking
 *
 * When a variant is highlighted in any chart or table row,
 * all other components react via the onHighlight callbacks.
 */

const State = (() => {
  let _highlighted = null;   // currently highlighted variant (string | null)
  const _listeners = [];

  return {
    /** Get current highlighted variant */
    get highlighted() { return _highlighted; },

    /** Set highlighted variant and notify all listeners */
    highlight(variant) {
      _highlighted = variant;
      _listeners.forEach(fn => fn(variant));
    },

    /** Clear highlight */
    clear() {
      _highlighted = null;
      _listeners.forEach(fn => fn(null));
    },

    /** Register a callback fired on every highlight change */
    onChange(fn) { _listeners.push(fn); },
  };
})();

/** Canonical variant colours — consistent across all charts */
const VARIANT_COLORS = {
  Q2_K:   { line: '#60A5FA', fill: 'rgba(96,165,250,0.15)'  },  // blue
  Q3_K_M: { line: '#34D399', fill: 'rgba(52,211,153,0.15)'  },  // emerald
  Q4_K_S: { line: '#FBBF24', fill: 'rgba(251,191,36,0.15)'  },  // amber
  Q4_K_M: { line: '#F87171', fill: 'rgba(248,113,113,0.15)' },  // red
  Q5_K_M: { line: '#A78BFA', fill: 'rgba(167,139,250,0.15)' },  // violet
  Q6_K:   { line: '#FB923C', fill: 'rgba(251,146,60,0.15)'  },  // orange
  Q8_0:   { line: '#E879F9', fill: 'rgba(232,121,249,0.15)' },  // fuchsia
  F16:    { line: '#94A3B8', fill: 'rgba(148,163,184,0.15)' },  // slate
};

const DEVICE_COLORS = {
  Pixel6a: '#4F8EF7',
  M4Mac:   '#A855F7',
  x86:     '#F59E0B',
};

const VARIANT_ORDER = ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0'];

/**
 * Variants confirmed cliff-prone (≥18% TPS drop at ctx=512 on ARM).
 * Q2_K: −48% cliff at ctx=512 (n=10). Q5_K_M: −18% at ctx=512, −46% at ctx=2048 (n=15).
 * Q6_K: susceptible to collapse at long ctx. Shown with ⚠ in cliff chart legend.
 */
const CLIFF_PRONE_VARIANTS = new Set(['Q2_K', 'Q5_K_M', 'Q6_K']);

/** fmt: round to 2dp for display */
const fmt = v => (v == null ? '—' : (+v).toFixed(2));

/** Make a single-value toggle button group reactive */
function bindToggleGroup(containerId, onChange) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.addEventListener('click', e => {
    const btn = e.target.closest('.btn-toggle');
    if (!btn) return;
    el.querySelectorAll('.btn-toggle').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    onChange(btn.dataset.value);
  });
}

/** Get active value from a toggle group */
function getToggleValue(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return null;
  return el.querySelector('.btn-toggle.active')?.dataset.value ?? null;
}

/** Chart.js default options shared across all charts */
function baseChartOpts(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: true,
    animation: { duration: 300 },
    plugins: {
      legend: {
        position: 'top',
        labels: {
          color: '#9CA3AF',
          boxWidth: 12,
          padding: 16,
          font: { size: 11 },
        },
      },
      tooltip: {
        backgroundColor: '#1F2937',
        titleColor: '#F9FAFB',
        bodyColor: '#D1D5DB',
        borderColor: '#374151',
        borderWidth: 1,
        padding: 10,
        callbacks: {},
      },
    },
    scales: {
      x: {
        grid: { color: 'rgba(255,255,255,0.04)' },
        ticks: { color: '#6B7280', font: { size: 11 } },
      },
      y: {
        grid: { color: 'rgba(255,255,255,0.06)' },
        ticks: { color: '#6B7280', font: { size: 11 } },
        title: { display: true, color: '#6B7280', font: { size: 11 } },
      },
    },
    ...extra,
  };
}
