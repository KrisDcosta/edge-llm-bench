/**
 * table.js — Dataset Explorer: filterable, sortable, paginated table
 */

const PAGE_SIZE = 50;

let _allRows    = [];
let _filtered   = [];
let _page       = 0;
let _sortCol    = 'decode_tps';
let _sortDir    = 'desc';   // 'asc' | 'desc'

function initTable(data) {
  _allRows = data.rows;
  const meta = data.meta;

  // Populate filter dropdowns from meta
  populateSelect('table-variant', meta.variants);
  populateSelect('table-model',   meta.models.map(m => m.split('-')[0])); // "Llama", "Qwen"
  populateSelect('table-exptype', meta.experiment_types);

  // Wire filters
  ['table-device','table-variant','table-model','table-exptype'].forEach(id => {
    document.getElementById(id)?.addEventListener('change', () => {
      _page = 0; applyFilters();
    });
  });

  document.getElementById('table-search')?.addEventListener('input', () => {
    _page = 0; applyFilters();
  });

  document.getElementById('table-reset')?.addEventListener('click', resetFilters);
  document.getElementById('table-export')?.addEventListener('click', exportCSV);
  document.getElementById('table-prev')?.addEventListener('click',  () => { _page--; renderTable(); });
  document.getElementById('table-next')?.addEventListener('click',  () => { _page++; renderTable(); });

  // Column sort headers
  document.querySelectorAll('.th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (_sortCol === col) {
        _sortDir = _sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        _sortCol = col;
        _sortDir = col === 'decode_tps' ? 'desc' : 'asc';
      }
      document.querySelectorAll('.th').forEach(h => {
        h.classList.remove('sort-asc','sort-desc');
      });
      th.classList.add(_sortDir === 'asc' ? 'sort-asc' : 'sort-desc');
      _page = 0;
      applyFilters();
    });
  });

  applyFilters();
}

function populateSelect(id, values) {
  const sel = document.getElementById(id);
  if (!sel) return;
  values.forEach(v => {
    const opt = document.createElement('option');
    opt.value = v; opt.textContent = v;
    sel.appendChild(opt);
  });
}

function resetFilters() {
  ['table-device','table-variant','table-model','table-exptype'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const search = document.getElementById('table-search');
  if (search) search.value = '';
  _page = 0;
  applyFilters();
}

function applyFilters() {
  const device  = document.getElementById('table-device')?.value   || '';
  const variant = document.getElementById('table-variant')?.value  || '';
  const model   = document.getElementById('table-model')?.value    || '';
  const exptype = document.getElementById('table-exptype')?.value  || '';
  const search  = (document.getElementById('table-search')?.value  || '').toLowerCase();

  _filtered = _allRows.filter(r => {
    if (device  && r.device  !== device)                          return false;
    if (variant && r.variant !== variant)                         return false;
    if (model   && !r.model?.toLowerCase().includes(model.toLowerCase())) return false;
    if (exptype && r.experiment_type !== exptype)                 return false;
    if (search  && !`${r.variant}${r.device}${r.experiment_type}${r.model}`
                      .toLowerCase().includes(search))            return false;
    return true;
  });

  // Sort
  _filtered.sort((a, b) => {
    const av = a[_sortCol] ?? -Infinity;
    const bv = b[_sortCol] ?? -Infinity;
    const cmp = av < bv ? -1 : av > bv ? 1 : 0;
    return _sortDir === 'asc' ? cmp : -cmp;
  });

  renderTable();
}

function renderTable() {
  const totalPages = Math.max(1, Math.ceil(_filtered.length / PAGE_SIZE));
  _page = Math.min(Math.max(0, _page), totalPages - 1);

  const start   = _page * PAGE_SIZE;
  const pageRows = _filtered.slice(start, start + PAGE_SIZE);

  const tbody = document.getElementById('table-body');
  if (!tbody) return;

  if (pageRows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="text-center py-10 text-gray-600">No records match the current filters.</td></tr>`;
  } else {
    tbody.innerHTML = pageRows.map(r => {
      const isHL = State.highlighted && r.variant === State.highlighted;
      const dc   = deviceColor(r.device);
      const vc   = VARIANT_COLORS[r.variant]?.line || '#9CA3AF';
      return `<tr class="${isHL ? 'highlighted' : ''}" data-variant="${r.variant || ''}">
        <td><span style="color:${dc};font-weight:600">${r.device || '—'}</span></td>
        <td><span style="color:${vc};font-weight:600;font-family:monospace">${r.variant || '—'}</span></td>
        <td class="text-gray-500 text-xs">${shortModel(r.model)}</td>
        <td class="mono">${r.context_len ?? '—'}</td>
        <td class="mono" style="color:#10B981;font-weight:600">${fmt(r.decode_tps)}</td>
        <td class="mono text-gray-400">${fmt(r.prefill_tps)}</td>
        <td class="text-gray-500 text-xs">${r.experiment_type || '—'}</td>
        <td class="mono text-gray-500">${r.threads ?? '—'}</td>
      </tr>`;
    }).join('');
  }

  // Info + pagination
  document.getElementById('table-info').textContent =
    `Showing ${start + 1}–${Math.min(start + PAGE_SIZE, _filtered.length)} of ${_filtered.length.toLocaleString()} records`;
  document.getElementById('table-page').textContent = `${_page + 1} / ${totalPages}`;
  document.getElementById('table-prev').disabled = _page === 0;
  document.getElementById('table-next').disabled = _page >= totalPages - 1;

  // Re-wire row clicks for cross-chart highlight
  tbody.querySelectorAll('tr[data-variant]').forEach(row => {
    row.style.cursor = 'pointer';
    row.addEventListener('click', () => {
      const v = row.dataset.variant;
      if (State.highlighted === v) State.clear();
      else State.highlight(v);
    });
  });
}

function exportCSV() {
  const cols = ['device','backend','model','variant','context_len',
                'trial','threads','decode_tps','prefill_tps','experiment_type','ts'];
  const header = cols.join(',');
  const rows   = _filtered.map(r =>
    cols.map(c => {
      const v = r[c] ?? '';
      return typeof v === 'string' && v.includes(',') ? `"${v}"` : v;
    }).join(',')
  );
  const blob = new Blob([header + '\n' + rows.join('\n')], { type: 'text/csv' });
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = 'edge-llm-bench-filtered.csv';
  a.click();
}

function highlightTableRows(variant) {
  document.querySelectorAll('#table-body tr[data-variant]').forEach(row => {
    if (!variant) {
      row.classList.remove('highlighted');
    } else {
      row.classList.toggle('highlighted', row.dataset.variant === variant);
    }
  });
}

function deviceColor(device) {
  return DEVICE_COLORS[device] || '#9CA3AF';
}

function shortModel(model) {
  if (!model) return '—';
  if (model.includes('Llama')) return 'Llama 3.2 3B';
  if (model.includes('Qwen'))  return 'Qwen 2.5 1.5B';
  return model;
}
