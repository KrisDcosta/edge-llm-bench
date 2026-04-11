<<<<<<< HEAD
/**
 * charts.js — All interactive Chart.js components
 *
 * Charts:
 *   1. initTpsChart      — Throughput bar (device × variant, model toggle, error bars)
 *   2. initCliffChart    — KV-cache collapse lines (context vs TPS, per-variant checkboxes)
 *   3. initQualityChart  — Accuracy grouped bar (benchmark select, calib toggle, device toggle)
 *   4. initHeatmap       — Cross-device TPS heatmap (context slider, model toggle)
 *   5. initThreadChart   — Thread count impact bar (bonus)
 *   6. initPplChart      — Perplexity bar (bonus)
 *
 * Cross-chart linking via State.highlight(variant) / State.onChange(fn)
 */

// ── Shared helpers ────────────────────────────────────────────────────────────

function vc(variant) { return VARIANT_COLORS[variant] || { line: '#9CA3AF', fill: 'rgba(148,163,184,0.15)' }; }

function gridColor() {
  return document.documentElement.classList.contains('dark')
    ? 'rgba(255,255,255,0.05)'
    : 'rgba(0,0,0,0.07)';
}

function tickColor() {
  return document.documentElement.classList.contains('dark') ? '#9CA3AF' : '#374151';
}

function tooltipDefaults() {
  return {
    backgroundColor: document.documentElement.classList.contains('dark') ? '#1F2937' : '#FFFFFF',
    titleColor:      document.documentElement.classList.contains('dark') ? '#F9FAFB' : '#111827',
    bodyColor:       document.documentElement.classList.contains('dark') ? '#D1D5DB' : '#374151',
    borderColor:     document.documentElement.classList.contains('dark') ? '#374151' : '#E5E7EB',
    borderWidth: 1, padding: 10,
  };
}

function scaleDefaults(yLabel = 'Decode TPS (tok/s)') {
  return {
    x: { grid: { color: gridColor() }, ticks: { color: tickColor(), font: { size: 11 } } },
    y: {
      grid:  { color: gridColor() },
      ticks: { color: tickColor(), font: { size: 11 } },
      title: { display: true, text: yLabel, color: tickColor(), font: { size: 11 } },
      beginAtZero: true,
    },
  };
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 1 — Throughput Bar
// ══════════════════════════════════════════════════════════════════════════════

let _tpsChart = null;
let _tpsData  = null;

function initTpsChart(data) {
  _tpsData = data;

  bindToggleGroup('tps-model-toggle',  () => renderTpsChart());
  bindToggleGroup('tps-device-toggle', () => renderTpsChart());

  renderTpsChart();
}

function renderTpsChart() {
  const model  = getToggleValue('tps-model-toggle')  || 'Llama';
  const device = getToggleValue('tps-device-toggle') || 'all';
  const modelData = _tpsData.data[model] || {};

  const devices = device === 'all'
    ? DEVICE_COLORS
    : { [device]: DEVICE_COLORS[device] };

  const datasets = Object.entries(devices).map(([dev, color]) => {
    const devData = modelData[dev] || {};
    return {
      label: dev === 'Pixel6a' ? 'Pixel 6a' : dev === 'M4Mac' ? 'M4 Mac' : 'x86',
      backgroundColor: color + 'CC',
      borderColor:     color,
      borderWidth: 1.5,
      borderRadius: 4,
      data: VARIANT_ORDER.map(v => devData[v]?.mean ?? null),
      // Error bar data stored as custom property, drawn manually
      _errPos: VARIANT_ORDER.map(v => devData[v]?.std ?? null),
      _errNeg: VARIANT_ORDER.map(v => devData[v]?.std ?? null),
    };
  });

  const ctx = document.getElementById('chart-tps');
  if (!ctx) return;

  if (_tpsChart) _tpsChart.destroy();

  _tpsChart = new Chart(ctx, {
    type: 'bar',
    data: { labels: VARIANT_ORDER, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      onClick(event, elements) {
        if (!elements.length) { State.clear(); return; }
        const variant = VARIANT_ORDER[elements[0].index];
        State.highlighted === variant ? State.clear() : State.highlight(variant);
      },
      plugins: {
        legend: { labels: { color: tickColor(), boxWidth: 12, padding: 16, font: { size: 11 } } },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => items[0].label,
            label(item) {
              const ds  = item.dataset;
              const val = ds.data[item.dataIndex];
              const std = ds._errPos?.[item.dataIndex];
              if (val == null) return `${ds.label}: no data`;
              return std != null
                ? `${ds.label}: ${val.toFixed(2)} ± ${std.toFixed(2)} tok/s`
                : `${ds.label}: ${val.toFixed(2)} tok/s`;
            },
            afterLabel(item) {
              const ds = item.dataset;
              const n  = _tpsData.data[
                getToggleValue('tps-model-toggle') || 'Llama'
              ]?.[Object.keys(devices)[item.datasetIndex]]?.[VARIANT_ORDER[item.dataIndex]]?.n;
              return n != null ? `n = ${n} trials` : '';
            },
          },
        },
      },
      scales: scaleDefaults('Decode TPS (tok/s)'),
    },
    plugins: [{
      // Manual error bar rendering
      id: 'errorbars',
      afterDatasetsDraw(chart) {
        const { ctx: c, scales: { x, y } } = chart;
        chart.data.datasets.forEach((ds, di) => {
          if (!ds._errPos) return;
          ds._errPos.forEach((std, i) => {
            if (std == null) return;
            const mean = ds.data[i];
            if (mean == null) return;
            const meta = chart.getDatasetMeta(di);
            const bar  = meta.data[i];
            if (!bar) return;
            const cx   = bar.x;
            const yTop = y.getPixelForValue(mean + std);
            const yBot = y.getPixelForValue(Math.max(0, mean - std));
            const hw   = 5;

            c.save();
            c.beginPath();
            c.strokeStyle = document.documentElement.classList.contains('dark') ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.45)';
            c.lineWidth   = 1.5;
            c.globalAlpha = 1;
            // Vertical line
            c.moveTo(cx, yTop); c.lineTo(cx, yBot);
            // Top cap
            c.moveTo(cx - hw, yTop); c.lineTo(cx + hw, yTop);
            // Bot cap
            c.moveTo(cx - hw, yBot); c.lineTo(cx + hw, yBot);
            c.stroke();
            c.restore();
          });
        });
      },
    }],
  });
}

function highlightTpsChart(variant) {
  if (!_tpsChart) return;
  _tpsChart.data.datasets.forEach(ds => {
    ds.borderWidth = 1.5;
    ds.borderColor = Object.values(DEVICE_COLORS).find(
      c => ds.backgroundColor.startsWith(c)
    ) || ds.borderColor;
  });
  if (variant) {
    const idx = VARIANT_ORDER.indexOf(variant);
    if (idx >= 0) {
      _tpsChart.data.datasets.forEach(ds => {
        ds.data.forEach((_, i) => {
          if (i !== idx) {
            const orig = ds.backgroundColor;
            ds.borderWidth = i === idx ? 3 : 1;
          }
        });
      });
    }
  }
  _tpsChart.update('none');
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 2 — KV-Cache Collapse Lines
// ══════════════════════════════════════════════════════════════════════════════

let _cliffChart   = null;
let _cliffData    = null;
let _kvQuantData  = null;
let _activeVariants = new Set(VARIANT_ORDER);

function initCliffChart(cliffData, kvQuantData) {
  _cliffData   = cliffData;
  _kvQuantData = kvQuantData;

  // Build variant checkboxes
  buildVariantCheckboxes('cliff-variant-checkboxes', v => {
    _activeVariants.has(v) ? _activeVariants.delete(v) : _activeVariants.add(v);
    renderCliffChart();
  });

  bindToggleGroup('cliff-source-toggle', () => renderCliffChart());

  document.getElementById('cliff-show-kv-quant')?.addEventListener('change', renderCliffChart);
  document.getElementById('cliff-show-threshold')?.addEventListener('change', renderCliffChart);

  renderCliffChart();
}

function buildVariantCheckboxes(containerId, onChange) {
  const el = document.getElementById(containerId);
  if (!el) return;
  VARIANT_ORDER.forEach(v => {
    const color = vc(v).line;
    const label = document.createElement('label');
    label.className = 'variant-checkbox-label checked';
    label.innerHTML = `<input type="checkbox" checked /><span style="color:${color}">${v}</span>`;
    label.querySelector('input').addEventListener('change', e => {
      label.classList.toggle('checked', e.target.checked);
      onChange(v);
    });
    el.appendChild(label);
  });
}

function renderCliffChart() {
  const source     = getToggleValue('cliff-source-toggle') || 'Pixel6a_Llama';
  const showKV     = document.getElementById('cliff-show-kv-quant')?.checked ?? false;
  const showBand   = document.getElementById('cliff-show-threshold')?.checked ?? true;
  const curves     = _cliffData.curves[source] || {};
  const threshold  = _cliffData.collapse_threshold;

  const datasets = [];

  VARIANT_ORDER.forEach(variant => {
    if (!_activeVariants.has(variant)) return;
    const points = curves[variant] || [];
    if (!points.length) return;

    const color    = vc(variant);
    const isHL     = State.highlighted === variant;
    const isCliff  = CLIFF_PRONE_VARIANTS.has(variant);

    datasets.push({
      label:           isCliff ? `⚠ ${variant}` : variant,
      data:            points.map(p => ({ x: p.context, y: p.mean })),
      borderColor:     color.line,
      backgroundColor: color.fill,
      borderWidth:     isHL ? 3 : (isCliff ? 2.4 : 1.8),
      pointRadius:     isHL ? 5 : (isCliff ? 4 : 3),
      pointHoverRadius: 6,
      tension:         0.3,
      fill:            false,
      _variant:        variant,
      _std:            points.map(p => p.std),
      _n:              points.map(p => p.n),
    });
  });

  // KV-cache quant overlay
  if (showKV && _kvQuantData?.series) {
    Object.entries(_kvQuantData.series).forEach(([variant, points]) => {
      if (!_activeVariants.has(variant)) return;
      const color = vc(variant);
      datasets.push({
        label:       `${variant} (kv=q8_0)`,
        data:        points.map(p => ({ x: p.context, y: p.mean })),
        borderColor: color.line,
        borderWidth: 2,
        borderDash:  [6, 3],
        pointRadius: 3,
        tension:     0.3,
        fill:        false,
        _variant:    variant,
      });
    });
  }

  const ctx = document.getElementById('chart-cliff');
  if (!ctx) return;
  if (_cliffChart) _cliffChart.destroy();

  // Collapse threshold annotation plugin (inline)
  const thresholdPlugin = {
    id: 'thresholdBand',
    beforeDraw(chart) {
      if (!showBand) return;
      const { ctx: c, chartArea, scales: { x } } = chart;
      if (!x || !chartArea) return;
      const x0 = x.getPixelForValue(threshold.start);
      const x1 = x.getPixelForValue(threshold.end);
      c.save();
      c.fillStyle = 'rgba(239,68,68,0.08)';
      c.fillRect(x0, chartArea.top, x1 - x0, chartArea.height);
      c.strokeStyle = 'rgba(239,68,68,0.3)';
      c.lineWidth   = 1;
      c.setLineDash([4, 4]);
      c.beginPath(); c.moveTo(x0, chartArea.top); c.lineTo(x0, chartArea.bottom); c.stroke();
      c.beginPath(); c.moveTo(x1, chartArea.top); c.lineTo(x1, chartArea.bottom); c.stroke();
      c.setLineDash([]);
      c.fillStyle = 'rgba(239,68,68,0.7)';
      c.font      = '10px sans-serif';
      c.fillText('collapse zone', x0 + 4, chartArea.top + 14);
      c.restore();
    },
  };

  _cliffChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      parsing: false,
      onClick(event, elements) {
        if (!elements.length) { State.clear(); return; }
        const variant = elements[0].dataset._variant;
        if (!variant) return;
        State.highlighted === variant ? State.clear() : State.highlight(variant);
      },
      plugins: {
        legend: {
          labels: { color: tickColor(), boxWidth: 12, padding: 12, font: { size: 11 } },
        },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => `Context: ${items[0].parsed.x} tokens`,
            label(item) {
              const ds  = item.dataset;
              const idx = item.dataIndex;
              const std = ds._std?.[idx];
              const n   = ds._n?.[idx];
              const val = item.parsed.y;
              let s = `${ds.label}: ${val.toFixed(2)} tok/s`;
              if (std != null) s += ` ± ${std.toFixed(2)}`;
              if (n   != null) s += ` (n=${n})`;
              return s;
            },
          },
        },
      },
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: 'Context Length (tokens)', color: tickColor(), font: { size: 11 } },
          grid:  { color: gridColor() },
          ticks: { color: tickColor(), font: { size: 11 } },
        },
        y: {
          ...scaleDefaults('Decode TPS (tok/s)').y,
        },
      },
    },
    plugins: [thresholdPlugin],
  });
}

function highlightCliffChart(variant) {
  if (!_cliffChart) return;
  _cliffChart.data.datasets.forEach(ds => {
    const isCliff = CLIFF_PRONE_VARIANTS.has(ds._variant);
    if (!variant) {
      ds.borderWidth  = isCliff ? 2.4 : 1.8;
      ds.pointRadius  = isCliff ? 4 : 3;
      ds.borderDash   = ds.label.includes('kv=') ? [6, 3] : [];
    } else if (ds._variant === variant) {
      ds.borderWidth  = 3.5;
      ds.pointRadius  = 6;
    } else {
      ds.borderWidth  = 1;
      ds.pointRadius  = 2;
    }
  });
  _cliffChart.update('none');
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 3 — Quality Benchmarks
// ══════════════════════════════════════════════════════════════════════════════

let _qualityChart = null;
let _qualityData  = null;

function initQualityChart(data) {
  _qualityData = data;

  document.getElementById('quality-benchmark-select')?.addEventListener('change', renderQualityChart);
  bindToggleGroup('quality-device-toggle', () => renderQualityChart());
  bindToggleGroup('quality-calib-toggle',  () => renderQualityChart());

  renderQualityChart();
}

function renderQualityChart() {
  const bm    = document.getElementById('quality-benchmark-select')?.value || 'boolq';
  const dev   = getToggleValue('quality-device-toggle') || 'Pixel6a';
  const calib = getToggleValue('quality-calib-toggle')  || 'standard';

  // M4 quality is hardware-independent — use Pixel6a data and show note
  const isM4 = dev === 'M4Mac';
  const dataKey = isM4 ? 'Pixel6a' : dev;
  document.getElementById('quality-m4-note')?.classList.toggle('hidden', !isM4);

  // Show imatrix partial note when imatrix selected (only BoolQ has data)
  const showImatrixNote = (calib === 'imatrix' || calib === 'both') && bm !== 'boolq';
  document.getElementById('quality-imatrix-note')?.classList.toggle('hidden', !showImatrixNote);

  const devData = _qualityData.data[dataKey] || {};
  const datasets = [];

  if (calib === 'both') {
    ['standard', 'imatrix'].forEach((c, ci) => {
      const bmData = devData[c]?.[bm] || {};
      datasets.push({
        label:           c === 'standard' ? 'Standard' : 'imatrix',
        backgroundColor: VARIANT_ORDER.map(v => {
          const col = vc(v).line;
          return col + (ci === 0 ? 'CC' : '66');
        }),
        borderColor:     VARIANT_ORDER.map(v => vc(v).line),
        borderWidth: 1.5,
        borderRadius: 4,
        data:            VARIANT_ORDER.map(v => bmData[v]?.accuracy ?? null),
        _details:        VARIANT_ORDER.map(v => bmData[v]),
      });
    });
  } else {
    const bmData = devData[calib]?.[bm] || {};
    datasets.push({
      label:           calib === 'imatrix' ? 'imatrix calibration' : 'Standard quantization',
      backgroundColor: VARIANT_ORDER.map(v => vc(v).line + 'CC'),
      borderColor:     VARIANT_ORDER.map(v => vc(v).line),
      borderWidth: 1.5,
      borderRadius: 4,
      data:            VARIANT_ORDER.map(v => bmData[v]?.accuracy ?? null),
      _details:        VARIANT_ORDER.map(v => bmData[v]),
    });
  }

  const bmLabel = (_qualityData.benchmark_labels?.[bm] || bm) +
    (isM4 ? '  (Pixel 6a values — hardware-independent)' : '');
  const ctx = document.getElementById('chart-quality');
  if (!ctx) return;
  if (_qualityChart) _qualityChart.destroy();

  _qualityChart = new Chart(ctx, {
    type: 'bar',
    data: { labels: VARIANT_ORDER, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      onClick(event, elements) {
        if (!elements.length) { State.clear(); return; }
        const variant = VARIANT_ORDER[elements[0].index];
        State.highlighted === variant ? State.clear() : State.highlight(variant);
      },
      plugins: {
        legend: {
          labels: { color: tickColor(), boxWidth: 12, padding: 16, font: { size: 11 } },
        },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => `${items[0].label} — ${bmLabel}`,
            label(item) {
              const acc = item.parsed.y;
              const det = item.dataset._details?.[item.dataIndex];
              if (acc == null) return `${item.dataset.label}: no data`;
              let s = `${item.dataset.label}: ${acc.toFixed(1)}%`;
              if (det?.correct != null) s += ` (${det.correct}/${det.total})`;
              return s;
            },
          },
        },
      },
      scales: {
        ...scaleDefaults('Accuracy (%)'),
        y: {
          ...scaleDefaults('Accuracy (%)').y,
          min: 0, max: 100,
          ticks: {
            ...scaleDefaults().y.ticks,
            callback: v => `${v}%`,
          },
        },
      },
    },
  });
}

function highlightQualityChart(variant) {
  if (!_qualityChart) return;
  _qualityChart.data.datasets.forEach(ds => {
    ds.backgroundColor = VARIANT_ORDER.map((v, i) => {
      const base = vc(v).line;
      if (!variant)            return base + 'CC';
      if (v === variant)       return base + 'FF';
      return base + '33';
    });
  });
  _qualityChart.update('none');
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 4 — Cross-Device Heatmap
// ══════════════════════════════════════════════════════════════════════════════

let _heatmapData     = null;
let _heatmapContexts = [];
let _heatmapCtxIdx   = 0;

function initHeatmap(data) {
  _heatmapData     = data;
  _heatmapContexts = data.context_lens;

  // Slider
  const slider = document.getElementById('heatmap-ctx-slider');
  if (slider) {
    slider.max   = _heatmapContexts.length - 1;
    slider.value = 0;
    slider.addEventListener('input', () => {
      _heatmapCtxIdx = +slider.value;
      renderHeatmap();
    });
  }

  bindToggleGroup('heatmap-model-toggle', () => {
    _heatmapCtxIdx = 0;
    if (slider) slider.value = 0;
    renderHeatmap();
  });

  renderHeatmap();
}

function renderHeatmap() {
  const model   = getToggleValue('heatmap-model-toggle') || 'Llama';
  const ctx     = _heatmapContexts[_heatmapCtxIdx];
  const ctxKey  = String(ctx);
  const modelData = _heatmapData.data[model] || {};
  const ctxData   = modelData[ctxKey] || {};
  const x86Tps    = _heatmapData.x86_tps?.[model] || {};

  // Update slider label
  const label = document.getElementById('heatmap-ctx-label');
  if (label) label.textContent = ctx ? `ctx=${ctx}` : 'ctx=–';

  const devices  = ['Pixel6a', 'M4Mac', 'x86'];
  const devLabel = { Pixel6a: 'Pixel 6a', M4Mac: 'M4 Mac', x86: 'x86' };

  // Collect all values for colour scaling
  const allVals = [];
  VARIANT_ORDER.forEach(v => {
    devices.forEach(d => {
      const val = d === 'x86'
        ? (ctxData.x86?.[v]?.mean ?? x86Tps[v])
        : ctxData[d]?.[v]?.mean;
      if (val != null) allVals.push(val);
    });
  });
  const minVal = Math.min(...allVals);
  const maxVal = Math.max(...allVals);

  function heatColor(val) {
    if (val == null) return 'transparent';
    const t = (val - minVal) / (maxVal - minVal || 1);
    // Red → amber → green
    if (t < 0.5) {
      const r = 239, g = Math.round(68 + (158 - 68) * (t * 2));
      return `rgba(${r},${g},68,0.35)`;
    } else {
      const g2 = Math.round(158 + (185 - 158) * ((t - 0.5) * 2));
      return `rgba(16,${g2},130,0.35)`;
    }
  }

  // Build thead
  const thead = document.getElementById('heatmap-thead');
  if (thead) {
    thead.innerHTML = `<tr>
      <th>Variant</th>
      ${devices.map(d => `<th style="color:${DEVICE_COLORS[d]}">${devLabel[d]}</th>`).join('')}
    </tr>`;
  }

  // Build tbody
  const tbody = document.getElementById('heatmap-tbody');
  if (!tbody) return;

  const isHL = State.highlighted;
  tbody.innerHTML = VARIANT_ORDER.map(v => {
    const color  = vc(v).line;
    const rowHL  = isHL === v ? 'highlighted' : '';
    const cells  = devices.map(d => {
      const val = d === 'x86'
        ? (ctxData.x86?.[v]?.mean ?? x86Tps[v])
        : ctxData[d]?.[v]?.mean;
      const bg  = heatColor(val);
      const n   = d === 'x86' ? ctxData.x86?.[v]?.n : ctxData[d]?.[v]?.n;
      const tt  = n != null ? `title="n=${n} trials"` : '';
      return `<td style="background:${bg}" ${tt}>
        ${val != null ? val.toFixed(1) : '—'}
        ${n != null ? `<span class="text-gray-600 text-xs"> tok/s</span>` : ''}
      </td>`;
    }).join('');

    return `<tr class="${rowHL}" data-variant="${v}" style="cursor:pointer">
      <td><span style="color:${color};font-family:monospace;font-weight:600">${v}</span></td>
      ${cells}
    </tr>`;
  }).join('');

  // Row click → cross-chart highlight
  tbody.querySelectorAll('tr[data-variant]').forEach(row => {
    row.addEventListener('click', () => {
      const v = row.dataset.variant;
      State.highlighted === v ? State.clear() : State.highlight(v);
    });
  });
}

function highlightHeatmapRow(variant) {
  document.querySelectorAll('#heatmap-tbody tr[data-variant]').forEach(row => {
    if (!variant) {
      row.classList.remove('highlighted');
    } else {
      row.classList.toggle('highlighted', row.dataset.variant === variant);
    }
  });
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 5 — Thread Sweep (bonus)
// ══════════════════════════════════════════════════════════════════════════════

function initThreadChart(data) {
  const ctx = document.getElementById('chart-threads');
  if (!ctx) return;

  const series  = data.series || [];
  const labels  = series.map(p => `${p.threads} thread${p.threads > 1 ? 's' : ''}`);
  const means   = series.map(p => p.mean);
  const stds    = series.map(p => p.std);

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label:           'Decode TPS',
        data:            means,
        backgroundColor: series.map((_, i) => i === 2 ? '#10B981CC' : '#4F8EF766'),
        borderColor:     series.map((_, i) => i === 2 ? '#10B981'   : '#4F8EF7'),
        borderWidth: 1.5,
        borderRadius: 4,
        _std: stds,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => items[0].label,
            label(item) {
              const val = item.parsed.y;
              const std = item.dataset._std?.[item.dataIndex];
              return std != null
                ? `${val.toFixed(2)} ± ${std.toFixed(2)} tok/s`
                : `${val.toFixed(2)} tok/s`;
            },
            afterLabel: item => item.dataIndex === 2 ? '← optimal' : '',
          },
        },
      },
      scales: scaleDefaults('Decode TPS (tok/s)'),
    },
    plugins: [{
      id: 'threadErrorBars',
      afterDatasetsDraw(chart) {
        const { ctx: c, scales: { x, y } } = chart;
        const ds = chart.data.datasets[0];
        if (!ds._std) return;
        ds._std.forEach((std, i) => {
          if (std == null) return;
          const mean = ds.data[i];
          const meta = chart.getDatasetMeta(0);
          const bar  = meta.data[i];
          if (!bar) return;
          const cx   = bar.x;
          const yTop = y.getPixelForValue(mean + std);
          const yBot = y.getPixelForValue(Math.max(0, mean - std));
          c.save();
          c.beginPath();
          c.strokeStyle = document.documentElement.classList.contains('dark') ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.45)'; c.lineWidth = 1.5; c.globalAlpha = 1;
          c.moveTo(cx, yTop); c.lineTo(cx, yBot);
          c.moveTo(cx - 4, yTop); c.lineTo(cx + 4, yTop);
          c.moveTo(cx - 4, yBot); c.lineTo(cx + 4, yBot);
          c.stroke(); c.restore();
        });
      },
    }],
  });
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 6 — Perplexity (bonus)
// ══════════════════════════════════════════════════════════════════════════════

function initPplChart(data) {
  const ctx = document.getElementById('chart-ppl');
  if (!ctx) return;

  const rows    = data.data || [];
  const labels  = rows.map(r => r.variant);
  const values  = rows.map(r => r.perplexity);          // null if not_evaluated
  const colors  = labels.map(v => vc(v).line);
  const corpuses = rows.map(r => r.corpus);

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label:           'Perplexity (lower = better)',
        data:            values,
        backgroundColor: colors.map((c, i) => values[i] == null ? '#374151' : c + '99'),
        borderColor:     colors.map((c, i) => values[i] == null ? '#4B5563' : c),
        borderWidth: 1.5,
        borderRadius: 4,
        _corpus: corpuses,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => items[0].label,
            label(item) {
              const val    = item.parsed.y;
              const corpus = item.dataset._corpus?.[item.dataIndex];
              if (val == null) return 'Not evaluated';
              const corpusLabel = corpus === 'wikitext2_full'
                ? 'full corpus (~285K tokens)'
                : corpus === 'wikitext2_sample'
                ? 'sample (~12K tokens)'
                : corpus || '';
              return [`PPL: ${val.toFixed(4)}`, `Corpus: ${corpusLabel}`];
            },
          },
        },
      },
      scales: {
        ...scaleDefaults('Perplexity'),
        y: {
          ...scaleDefaults('Perplexity').y,
          beginAtZero: false,
          min: 8,
          suggestedMax: 15,
        },
      },
    },
  });
}
=======
/**
 * charts.js — All interactive Chart.js components
 *
 * Charts:
 *   1. initTpsChart      — Throughput bar (device × variant, model toggle, error bars)
 *   2. initCliffChart    — KV-cache collapse lines (context vs TPS, per-variant checkboxes)
 *   3. initQualityChart  — Accuracy grouped bar (benchmark select, calib toggle, device toggle)
 *   4. initHeatmap       — Cross-device TPS heatmap (context slider, model toggle)
 *   5. initThreadChart   — Thread count impact bar (bonus)
 *   6. initPplChart      — Perplexity bar (bonus)
 *
 * Cross-chart linking via State.highlight(variant) / State.onChange(fn)
 */

// ── Shared helpers ────────────────────────────────────────────────────────────

function vc(variant) { return VARIANT_COLORS[variant] || { line: '#9CA3AF', fill: 'rgba(148,163,184,0.15)' }; }

function gridColor() {
  return document.documentElement.classList.contains('dark')
    ? 'rgba(255,255,255,0.05)'
    : 'rgba(0,0,0,0.07)';
}

function tickColor() {
  return document.documentElement.classList.contains('dark') ? '#9CA3AF' : '#374151';
}

function tooltipDefaults() {
  return {
    backgroundColor: document.documentElement.classList.contains('dark') ? '#1F2937' : '#FFFFFF',
    titleColor:      document.documentElement.classList.contains('dark') ? '#F9FAFB' : '#111827',
    bodyColor:       document.documentElement.classList.contains('dark') ? '#D1D5DB' : '#374151',
    borderColor:     document.documentElement.classList.contains('dark') ? '#374151' : '#E5E7EB',
    borderWidth: 1, padding: 10,
  };
}

function scaleDefaults(yLabel = 'Decode TPS (tok/s)') {
  return {
    x: { grid: { color: gridColor() }, ticks: { color: tickColor(), font: { size: 11 } } },
    y: {
      grid:  { color: gridColor() },
      ticks: { color: tickColor(), font: { size: 11 } },
      title: { display: true, text: yLabel, color: tickColor(), font: { size: 11 } },
      beginAtZero: true,
    },
  };
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 1 — Throughput Bar
// ══════════════════════════════════════════════════════════════════════════════

let _tpsChart = null;
let _tpsData  = null;

function initTpsChart(data) {
  _tpsData = data;

  bindToggleGroup('tps-model-toggle',  () => renderTpsChart());
  bindToggleGroup('tps-device-toggle', () => renderTpsChart());

  renderTpsChart();
}

function renderTpsChart() {
  const model  = getToggleValue('tps-model-toggle')  || 'Llama';
  const device = getToggleValue('tps-device-toggle') || 'all';
  const modelData = _tpsData.data[model] || {};

  const devices = device === 'all'
    ? DEVICE_COLORS
    : { [device]: DEVICE_COLORS[device] };

  const datasets = Object.entries(devices).map(([dev, color]) => {
    const devData = modelData[dev] || {};
    return {
      label: dev === 'Pixel6a' ? 'Pixel 6a' : dev === 'M4Mac' ? 'M4 Mac' : 'x86',
      backgroundColor: color + 'CC',
      borderColor:     color,
      borderWidth: 1.5,
      borderRadius: 4,
      data: VARIANT_ORDER.map(v => devData[v]?.mean ?? null),
      // Error bar data stored as custom property, drawn manually
      _errPos: VARIANT_ORDER.map(v => devData[v]?.std ?? null),
      _errNeg: VARIANT_ORDER.map(v => devData[v]?.std ?? null),
    };
  });

  const ctx = document.getElementById('chart-tps');
  if (!ctx) return;

  if (_tpsChart) _tpsChart.destroy();

  _tpsChart = new Chart(ctx, {
    type: 'bar',
    data: { labels: VARIANT_ORDER, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      onClick(event, elements) {
        if (!elements.length) { State.clear(); return; }
        const variant = VARIANT_ORDER[elements[0].index];
        State.highlighted === variant ? State.clear() : State.highlight(variant);
      },
      plugins: {
        legend: { labels: { color: tickColor(), boxWidth: 12, padding: 16, font: { size: 11 } } },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => items[0].label,
            label(item) {
              const ds  = item.dataset;
              const val = ds.data[item.dataIndex];
              const std = ds._errPos?.[item.dataIndex];
              if (val == null) return `${ds.label}: no data`;
              return std != null
                ? `${ds.label}: ${val.toFixed(2)} ± ${std.toFixed(2)} tok/s`
                : `${ds.label}: ${val.toFixed(2)} tok/s`;
            },
            afterLabel(item) {
              const ds = item.dataset;
              const n  = _tpsData.data[
                getToggleValue('tps-model-toggle') || 'Llama'
              ]?.[Object.keys(devices)[item.datasetIndex]]?.[VARIANT_ORDER[item.dataIndex]]?.n;
              return n != null ? `n = ${n} trials` : '';
            },
          },
        },
      },
      scales: scaleDefaults('Decode TPS (tok/s)'),
    },
    plugins: [{
      // Manual error bar rendering
      id: 'errorbars',
      afterDatasetsDraw(chart) {
        const { ctx: c, scales: { x, y } } = chart;
        chart.data.datasets.forEach((ds, di) => {
          if (!ds._errPos) return;
          ds._errPos.forEach((std, i) => {
            if (std == null) return;
            const mean = ds.data[i];
            if (mean == null) return;
            const meta = chart.getDatasetMeta(di);
            const bar  = meta.data[i];
            if (!bar) return;
            const cx   = bar.x;
            const yTop = y.getPixelForValue(mean + std);
            const yBot = y.getPixelForValue(Math.max(0, mean - std));
            const hw   = 5;

            c.save();
            c.beginPath();
            c.strokeStyle = document.documentElement.classList.contains('dark') ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.45)';
            c.lineWidth   = 1.5;
            c.globalAlpha = 1;
            // Vertical line
            c.moveTo(cx, yTop); c.lineTo(cx, yBot);
            // Top cap
            c.moveTo(cx - hw, yTop); c.lineTo(cx + hw, yTop);
            // Bot cap
            c.moveTo(cx - hw, yBot); c.lineTo(cx + hw, yBot);
            c.stroke();
            c.restore();
          });
        });
      },
    }],
  });
}

function highlightTpsChart(variant) {
  if (!_tpsChart) return;
  _tpsChart.data.datasets.forEach(ds => {
    ds.borderWidth = 1.5;
    ds.borderColor = Object.values(DEVICE_COLORS).find(
      c => ds.backgroundColor.startsWith(c)
    ) || ds.borderColor;
  });
  if (variant) {
    const idx = VARIANT_ORDER.indexOf(variant);
    if (idx >= 0) {
      _tpsChart.data.datasets.forEach(ds => {
        ds.data.forEach((_, i) => {
          if (i !== idx) {
            const orig = ds.backgroundColor;
            ds.borderWidth = i === idx ? 3 : 1;
          }
        });
      });
    }
  }
  _tpsChart.update('none');
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 2 — KV-Cache Collapse Lines
// ══════════════════════════════════════════════════════════════════════════════

let _cliffChart   = null;
let _cliffData    = null;
let _kvQuantData  = null;
let _activeVariants = new Set(VARIANT_ORDER);

function initCliffChart(cliffData, kvQuantData) {
  _cliffData   = cliffData;
  _kvQuantData = kvQuantData;

  // Build variant checkboxes
  buildVariantCheckboxes('cliff-variant-checkboxes', v => {
    _activeVariants.has(v) ? _activeVariants.delete(v) : _activeVariants.add(v);
    renderCliffChart();
  });

  bindToggleGroup('cliff-source-toggle', () => renderCliffChart());

  document.getElementById('cliff-show-kv-quant')?.addEventListener('change', renderCliffChart);
  document.getElementById('cliff-show-threshold')?.addEventListener('change', renderCliffChart);

  renderCliffChart();
}

function buildVariantCheckboxes(containerId, onChange) {
  const el = document.getElementById(containerId);
  if (!el) return;
  VARIANT_ORDER.forEach(v => {
    const color = vc(v).line;
    const label = document.createElement('label');
    label.className = 'variant-checkbox-label checked';
    label.innerHTML = `<input type="checkbox" checked /><span style="color:${color}">${v}</span>`;
    label.querySelector('input').addEventListener('change', e => {
      label.classList.toggle('checked', e.target.checked);
      onChange(v);
    });
    el.appendChild(label);
  });
}

function renderCliffChart() {
  const source     = getToggleValue('cliff-source-toggle') || 'Pixel6a_Llama';
  const showKV     = document.getElementById('cliff-show-kv-quant')?.checked ?? false;
  const showBand   = document.getElementById('cliff-show-threshold')?.checked ?? true;
  const curves     = _cliffData.curves[source] || {};
  const threshold  = _cliffData.collapse_threshold;

  const datasets = [];

  VARIANT_ORDER.forEach(variant => {
    if (!_activeVariants.has(variant)) return;
    const points = curves[variant] || [];
    if (!points.length) return;

    const color = vc(variant);
    const isHL  = State.highlighted === variant;

    datasets.push({
      label:           variant,
      data:            points.map(p => ({ x: p.context, y: p.mean })),
      borderColor:     color.line,
      backgroundColor: color.fill,
      borderWidth:     isHL ? 3 : 1.8,
      pointRadius:     isHL ? 5 : 3,
      pointHoverRadius: 6,
      tension:         0.3,
      fill:            false,
      _variant:        variant,
      _std:            points.map(p => p.std),
      _n:              points.map(p => p.n),
    });
  });

  // KV-cache quant overlay
  if (showKV && _kvQuantData?.series) {
    Object.entries(_kvQuantData.series).forEach(([variant, points]) => {
      if (!_activeVariants.has(variant)) return;
      const color = vc(variant);
      datasets.push({
        label:       `${variant} (kv=q8_0)`,
        data:        points.map(p => ({ x: p.context, y: p.mean })),
        borderColor: color.line,
        borderWidth: 2,
        borderDash:  [6, 3],
        pointRadius: 3,
        tension:     0.3,
        fill:        false,
        _variant:    variant,
      });
    });
  }

  const ctx = document.getElementById('chart-cliff');
  if (!ctx) return;
  if (_cliffChart) _cliffChart.destroy();

  // Collapse threshold annotation plugin (inline)
  const thresholdPlugin = {
    id: 'thresholdBand',
    beforeDraw(chart) {
      if (!showBand) return;
      const { ctx: c, chartArea, scales: { x } } = chart;
      if (!x || !chartArea) return;
      const x0 = x.getPixelForValue(threshold.start);
      const x1 = x.getPixelForValue(threshold.end);
      c.save();
      c.fillStyle = 'rgba(239,68,68,0.08)';
      c.fillRect(x0, chartArea.top, x1 - x0, chartArea.height);
      c.strokeStyle = 'rgba(239,68,68,0.3)';
      c.lineWidth   = 1;
      c.setLineDash([4, 4]);
      c.beginPath(); c.moveTo(x0, chartArea.top); c.lineTo(x0, chartArea.bottom); c.stroke();
      c.beginPath(); c.moveTo(x1, chartArea.top); c.lineTo(x1, chartArea.bottom); c.stroke();
      c.setLineDash([]);
      c.fillStyle = 'rgba(239,68,68,0.7)';
      c.font      = '10px sans-serif';
      c.fillText('collapse zone', x0 + 4, chartArea.top + 14);
      c.restore();
    },
  };

  _cliffChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      parsing: false,
      onClick(event, elements) {
        if (!elements.length) { State.clear(); return; }
        const variant = elements[0].dataset._variant;
        if (!variant) return;
        State.highlighted === variant ? State.clear() : State.highlight(variant);
      },
      plugins: {
        legend: {
          labels: { color: tickColor(), boxWidth: 12, padding: 12, font: { size: 11 } },
        },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => `Context: ${items[0].parsed.x} tokens`,
            label(item) {
              const ds  = item.dataset;
              const idx = item.dataIndex;
              const std = ds._std?.[idx];
              const n   = ds._n?.[idx];
              const val = item.parsed.y;
              let s = `${ds.label}: ${val.toFixed(2)} tok/s`;
              if (std != null) s += ` ± ${std.toFixed(2)}`;
              if (n   != null) s += ` (n=${n})`;
              return s;
            },
          },
        },
      },
      scales: {
        x: {
          type: 'linear',
          title: { display: true, text: 'Context Length (tokens)', color: tickColor(), font: { size: 11 } },
          grid:  { color: gridColor() },
          ticks: { color: tickColor(), font: { size: 11 } },
        },
        y: {
          ...scaleDefaults('Decode TPS (tok/s)').y,
        },
      },
    },
    plugins: [thresholdPlugin],
  });
}

function highlightCliffChart(variant) {
  if (!_cliffChart) return;
  _cliffChart.data.datasets.forEach(ds => {
    if (!variant) {
      ds.borderWidth  = 1.8;
      ds.pointRadius  = 3;
      ds.borderDash   = ds.label.includes('kv=') ? [6, 3] : [];
    } else if (ds._variant === variant) {
      ds.borderWidth  = 3.5;
      ds.pointRadius  = 6;
    } else {
      ds.borderWidth  = 1;
      ds.pointRadius  = 2;
    }
  });
  _cliffChart.update('none');
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 3 — Quality Benchmarks
// ══════════════════════════════════════════════════════════════════════════════

let _qualityChart = null;
let _qualityData  = null;

function initQualityChart(data) {
  _qualityData = data;

  document.getElementById('quality-benchmark-select')?.addEventListener('change', renderQualityChart);
  bindToggleGroup('quality-device-toggle', () => renderQualityChart());
  bindToggleGroup('quality-calib-toggle',  () => renderQualityChart());

  renderQualityChart();
}

function renderQualityChart() {
  const bm    = document.getElementById('quality-benchmark-select')?.value || 'boolq';
  const dev   = getToggleValue('quality-device-toggle') || 'Pixel6a';
  const calib = getToggleValue('quality-calib-toggle')  || 'standard';

  // M4 quality is hardware-independent — use Pixel6a data and show note
  const isM4 = dev === 'M4Mac';
  const dataKey = isM4 ? 'Pixel6a' : dev;
  document.getElementById('quality-m4-note')?.classList.toggle('hidden', !isM4);

  // Show imatrix partial note when imatrix selected (only BoolQ has data)
  const showImatrixNote = (calib === 'imatrix' || calib === 'both') && bm !== 'boolq';
  document.getElementById('quality-imatrix-note')?.classList.toggle('hidden', !showImatrixNote);

  const devData = _qualityData.data[dataKey] || {};
  const datasets = [];

  if (calib === 'both') {
    ['standard', 'imatrix'].forEach((c, ci) => {
      const bmData = devData[c]?.[bm] || {};
      datasets.push({
        label:           c === 'standard' ? 'Standard' : 'imatrix',
        backgroundColor: VARIANT_ORDER.map(v => {
          const col = vc(v).line;
          return col + (ci === 0 ? 'CC' : '66');
        }),
        borderColor:     VARIANT_ORDER.map(v => vc(v).line),
        borderWidth: 1.5,
        borderRadius: 4,
        data:            VARIANT_ORDER.map(v => bmData[v]?.accuracy ?? null),
        _details:        VARIANT_ORDER.map(v => bmData[v]),
      });
    });
  } else {
    const bmData = devData[calib]?.[bm] || {};
    datasets.push({
      label:           calib === 'imatrix' ? 'imatrix calibration' : 'Standard quantization',
      backgroundColor: VARIANT_ORDER.map(v => vc(v).line + 'CC'),
      borderColor:     VARIANT_ORDER.map(v => vc(v).line),
      borderWidth: 1.5,
      borderRadius: 4,
      data:            VARIANT_ORDER.map(v => bmData[v]?.accuracy ?? null),
      _details:        VARIANT_ORDER.map(v => bmData[v]),
    });
  }

  const bmLabel = (_qualityData.benchmark_labels?.[bm] || bm) +
    (isM4 ? '  (Pixel 6a values — hardware-independent)' : '');
  const ctx = document.getElementById('chart-quality');
  if (!ctx) return;
  if (_qualityChart) _qualityChart.destroy();

  _qualityChart = new Chart(ctx, {
    type: 'bar',
    data: { labels: VARIANT_ORDER, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      onClick(event, elements) {
        if (!elements.length) { State.clear(); return; }
        const variant = VARIANT_ORDER[elements[0].index];
        State.highlighted === variant ? State.clear() : State.highlight(variant);
      },
      plugins: {
        legend: {
          labels: { color: tickColor(), boxWidth: 12, padding: 16, font: { size: 11 } },
        },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => `${items[0].label} — ${bmLabel}`,
            label(item) {
              const acc = item.parsed.y;
              const det = item.dataset._details?.[item.dataIndex];
              if (acc == null) return `${item.dataset.label}: no data`;
              let s = `${item.dataset.label}: ${acc.toFixed(1)}%`;
              if (det?.correct != null) s += ` (${det.correct}/${det.total})`;
              return s;
            },
          },
        },
      },
      scales: {
        ...scaleDefaults('Accuracy (%)'),
        y: {
          ...scaleDefaults('Accuracy (%)').y,
          min: 0, max: 100,
          ticks: {
            ...scaleDefaults().y.ticks,
            callback: v => `${v}%`,
          },
        },
      },
    },
  });
}

function highlightQualityChart(variant) {
  if (!_qualityChart) return;
  _qualityChart.data.datasets.forEach(ds => {
    ds.backgroundColor = VARIANT_ORDER.map((v, i) => {
      const base = vc(v).line;
      if (!variant)            return base + 'CC';
      if (v === variant)       return base + 'FF';
      return base + '33';
    });
  });
  _qualityChart.update('none');
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 4 — Cross-Device Heatmap
// ══════════════════════════════════════════════════════════════════════════════

let _heatmapData     = null;
let _heatmapContexts = [];
let _heatmapCtxIdx   = 0;

function initHeatmap(data) {
  _heatmapData     = data;
  _heatmapContexts = data.context_lens;

  // Slider
  const slider = document.getElementById('heatmap-ctx-slider');
  if (slider) {
    slider.max   = _heatmapContexts.length - 1;
    slider.value = 0;
    slider.addEventListener('input', () => {
      _heatmapCtxIdx = +slider.value;
      renderHeatmap();
    });
  }

  bindToggleGroup('heatmap-model-toggle', () => {
    _heatmapCtxIdx = 0;
    if (slider) slider.value = 0;
    renderHeatmap();
  });

  renderHeatmap();
}

function renderHeatmap() {
  const model   = getToggleValue('heatmap-model-toggle') || 'Llama';
  const ctx     = _heatmapContexts[_heatmapCtxIdx];
  const ctxKey  = String(ctx);
  const modelData = _heatmapData.data[model] || {};
  const ctxData   = modelData[ctxKey] || {};
  const x86Tps    = _heatmapData.x86_tps?.[model] || {};

  // Update slider label
  const label = document.getElementById('heatmap-ctx-label');
  if (label) label.textContent = ctx ? `ctx=${ctx}` : 'ctx=–';

  const devices  = ['Pixel6a', 'M4Mac', 'x86'];
  const devLabel = { Pixel6a: 'Pixel 6a', M4Mac: 'M4 Mac', x86: 'x86' };

  // Collect all values for colour scaling
  const allVals = [];
  VARIANT_ORDER.forEach(v => {
    devices.forEach(d => {
      const val = d === 'x86'
        ? (ctxData.x86?.[v]?.mean ?? x86Tps[v])
        : ctxData[d]?.[v]?.mean;
      if (val != null) allVals.push(val);
    });
  });
  const minVal = Math.min(...allVals);
  const maxVal = Math.max(...allVals);

  function heatColor(val) {
    if (val == null) return 'transparent';
    const t = (val - minVal) / (maxVal - minVal || 1);
    // Red → amber → green
    if (t < 0.5) {
      const r = 239, g = Math.round(68 + (158 - 68) * (t * 2));
      return `rgba(${r},${g},68,0.35)`;
    } else {
      const g2 = Math.round(158 + (185 - 158) * ((t - 0.5) * 2));
      return `rgba(16,${g2},130,0.35)`;
    }
  }

  // Build thead
  const thead = document.getElementById('heatmap-thead');
  if (thead) {
    thead.innerHTML = `<tr>
      <th>Variant</th>
      ${devices.map(d => `<th style="color:${DEVICE_COLORS[d]}">${devLabel[d]}</th>`).join('')}
    </tr>`;
  }

  // Build tbody
  const tbody = document.getElementById('heatmap-tbody');
  if (!tbody) return;

  const isHL = State.highlighted;
  tbody.innerHTML = VARIANT_ORDER.map(v => {
    const color  = vc(v).line;
    const rowHL  = isHL === v ? 'highlighted' : '';
    const cells  = devices.map(d => {
      const val = d === 'x86'
        ? (ctxData.x86?.[v]?.mean ?? x86Tps[v])
        : ctxData[d]?.[v]?.mean;
      const bg  = heatColor(val);
      const n   = d === 'x86' ? ctxData.x86?.[v]?.n : ctxData[d]?.[v]?.n;
      const tt  = n != null ? `title="n=${n} trials"` : '';
      return `<td style="background:${bg}" ${tt}>
        ${val != null ? val.toFixed(1) : '—'}
        ${n != null ? `<span class="text-gray-600 text-xs"> tok/s</span>` : ''}
      </td>`;
    }).join('');

    return `<tr class="${rowHL}" data-variant="${v}" style="cursor:pointer">
      <td><span style="color:${color};font-family:monospace;font-weight:600">${v}</span></td>
      ${cells}
    </tr>`;
  }).join('');

  // Row click → cross-chart highlight
  tbody.querySelectorAll('tr[data-variant]').forEach(row => {
    row.addEventListener('click', () => {
      const v = row.dataset.variant;
      State.highlighted === v ? State.clear() : State.highlight(v);
    });
  });
}

function highlightHeatmapRow(variant) {
  document.querySelectorAll('#heatmap-tbody tr[data-variant]').forEach(row => {
    if (!variant) {
      row.classList.remove('highlighted');
    } else {
      row.classList.toggle('highlighted', row.dataset.variant === variant);
    }
  });
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 5 — Thread Sweep (bonus)
// ══════════════════════════════════════════════════════════════════════════════

function initThreadChart(data) {
  const ctx = document.getElementById('chart-threads');
  if (!ctx) return;

  const series  = data.series || [];
  const labels  = series.map(p => `${p.threads} thread${p.threads > 1 ? 's' : ''}`);
  const means   = series.map(p => p.mean);
  const stds    = series.map(p => p.std);

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label:           'Decode TPS',
        data:            means,
        backgroundColor: series.map((_, i) => i === 2 ? '#10B981CC' : '#4F8EF766'),
        borderColor:     series.map((_, i) => i === 2 ? '#10B981'   : '#4F8EF7'),
        borderWidth: 1.5,
        borderRadius: 4,
        _std: stds,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => items[0].label,
            label(item) {
              const val = item.parsed.y;
              const std = item.dataset._std?.[item.dataIndex];
              return std != null
                ? `${val.toFixed(2)} ± ${std.toFixed(2)} tok/s`
                : `${val.toFixed(2)} tok/s`;
            },
            afterLabel: item => item.dataIndex === 2 ? '← optimal' : '',
          },
        },
      },
      scales: scaleDefaults('Decode TPS (tok/s)'),
    },
    plugins: [{
      id: 'threadErrorBars',
      afterDatasetsDraw(chart) {
        const { ctx: c, scales: { x, y } } = chart;
        const ds = chart.data.datasets[0];
        if (!ds._std) return;
        ds._std.forEach((std, i) => {
          if (std == null) return;
          const mean = ds.data[i];
          const meta = chart.getDatasetMeta(0);
          const bar  = meta.data[i];
          if (!bar) return;
          const cx   = bar.x;
          const yTop = y.getPixelForValue(mean + std);
          const yBot = y.getPixelForValue(Math.max(0, mean - std));
          c.save();
          c.beginPath();
          c.strokeStyle = document.documentElement.classList.contains('dark') ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.45)'; c.lineWidth = 1.5; c.globalAlpha = 1;
          c.moveTo(cx, yTop); c.lineTo(cx, yBot);
          c.moveTo(cx - 4, yTop); c.lineTo(cx + 4, yTop);
          c.moveTo(cx - 4, yBot); c.lineTo(cx + 4, yBot);
          c.stroke(); c.restore();
        });
      },
    }],
  });
}


// ══════════════════════════════════════════════════════════════════════════════
// Chart 6 — Perplexity (bonus)
// ══════════════════════════════════════════════════════════════════════════════

function initPplChart(data) {
  const ctx = document.getElementById('chart-ppl');
  if (!ctx) return;

  const rows    = data.data || [];
  const labels  = rows.map(r => r.variant);
  const values  = rows.map(r => r.perplexity);          // null if not_evaluated
  const colors  = labels.map(v => vc(v).line);
  const corpuses = rows.map(r => r.corpus);

  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label:           'Perplexity (lower = better)',
        data:            values,
        backgroundColor: colors.map((c, i) => values[i] == null ? '#374151' : c + '99'),
        borderColor:     colors.map((c, i) => values[i] == null ? '#4B5563' : c),
        borderWidth: 1.5,
        borderRadius: 4,
        _corpus: corpuses,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 300 },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...tooltipDefaults(),
          callbacks: {
            title: items => items[0].label,
            label(item) {
              const val    = item.parsed.y;
              const corpus = item.dataset._corpus?.[item.dataIndex];
              if (val == null) return 'Not evaluated';
              const corpusLabel = corpus === 'wikitext2_full'
                ? 'full corpus (~285K tokens)'
                : corpus === 'wikitext2_sample'
                ? 'sample (~12K tokens)'
                : corpus || '';
              return [`PPL: ${val.toFixed(4)}`, `Corpus: ${corpusLabel}`];
            },
          },
        },
      },
      scales: {
        ...scaleDefaults('Perplexity'),
        y: {
          ...scaleDefaults('Perplexity').y,
          beginAtZero: false,
          min: 8,
          suggestedMax: 15,
        },
      },
    },
  });
}
>>>>>>> 6e8752a (Updated Qwen 2.5 Benchmark on x86 Intel i5 device)
