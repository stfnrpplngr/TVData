(() => {
const tableSelect = document.getElementById('tableSelect');
const baselineSelect = document.getElementById('baselineSelect');
const targetSelect = document.getElementById('targetSelect');
const loadBtn = document.getElementById('loadBtn');

const metricsEl = document.getElementById('metrics');
const pairKpisEl = document.getElementById('pairKpis');
const heatmapEl = document.getElementById('heatmap');
const groupBarsEl = document.getElementById('groupBars');
const graphEl = document.getElementById('graph');
const histEl = document.getElementById('hist');
const logicEl = document.getElementById('logic');
const allowancesEl = document.getElementById('allowances');

const cache = new Map();

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function githubReposFromLocation() {
  const repos = [];
  const { hostname, pathname } = window.location;

  if (hostname.endsWith('github.io')) {
    const owner = hostname.split('.')[0];
    const [repo] = pathname.split('/').filter(Boolean);
    if (owner && repo) repos.push({ owner, repo });
  }

  const pathSegments = pathname.split('/').filter(Boolean);
  if (pathSegments.length >= 2) {
    const [repo] = pathSegments;
    ['stfnrpplngr', 'Tekergo-T'].forEach((owner) => repos.push({ owner, repo }));
  }

  repos.push({ owner: 'stfnrpplngr', repo: 'TVData' });
  repos.push({ owner: 'Tekergo-T', repo: 'TVData' });

  return unique(repos.map(({ owner, repo }) => `${owner}/${repo}`));
}

var tablesBaseCandidates = globalThis.__tvdataTablesBaseCandidates || (() => {
  const candidates = [
    '../tables',
    '../../tables',
    '/tables',
    './remote/tables',
    '../remote/tables',
    '/remote/tables',
  ];
  const branches = ['Comparing-Remuneration-Tables', 'main', 'master'];
  githubReposFromLocation().forEach((repoPath) => {
    branches.forEach((branch) => {
      candidates.push(`https://cdn.jsdelivr.net/gh/${repoPath}@${branch}/tables`);
      candidates.push(`https://raw.githubusercontent.com/${repoPath}/${branch}/tables`);
    });
  });
  return unique(candidates);
})();
globalThis.__tvdataTablesBaseCandidates = tablesBaseCandidates;
var tablesBase = globalThis.__tvdataTablesBase || null;
var tablesList = globalThis.__tvdataTablesList || null;

const toNum = (v) => {
  if (v == null || `${v}`.trim() === '') return null;
  return Number.parseFloat(`${v}`.replace(',', '.'));
};

const fmt = (n, unit = '') => (n == null || Number.isNaN(n) ? '—' : `${n.toFixed(2)}${unit}`);

function parseCSV(text) {
  return text.trim().split(/\r?\n/).map((line) => line.split(','));
}

function kvObject(rows) {
  const obj = {};
  rows.slice(1).forEach((r) => { if (r.length > 1) obj[r[0]] = r[1]; });
  return obj;
}

function gridObject(rows) {
  const headers = rows[0].slice(1);
  const out = {};
  rows.slice(1).forEach((r) => {
    const row = {};
    headers.forEach((h, i) => { row[h] = r[i + 1] ?? ''; });
    out[r[0]] = row;
  });
  return out;
}

async function fetchCSV(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Fehler beim Laden: ${path}`);
  return parseCSV(await res.text());
}

async function fetchJSON(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`Fehler beim Laden: ${path}`);
  return await res.json();
}

async function fetchJSONWithTimeout(path, timeoutMs = 2000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, { signal: ctrl.signal });
    if (!res.ok) throw new Error(`Fehler beim Laden: ${path}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

function normalizeTableList(data) {
  if (!Array.isArray(data)) return [];
  return data
    .map((item) => {
      if (typeof item === 'string') return item;
      if (item && typeof item === 'object') return item.name || item.id || item.table || '';
      return '';
    })
    .map((x) => `${x}`.trim())
    .filter(Boolean);
}

async function probeTableIndex(candidate) {
  try {
    const isRemote = /^https?:\/\//.test(candidate);
    const data = isRemote
      ? await fetchJSONWithTimeout(`${candidate}/index.json`, 2000)
      : await fetchJSON(`${candidate}/index.json`);
    const list = normalizeTableList(data);
    if (list.length > 0) return list;
  } catch (_) {
    // try next candidate
  }
  return null;
}

async function resolveTablesBase() {
  if (tablesBase && tablesList) return tablesBase;

  for (const candidate of tablesBaseCandidates) {
    const list = await probeTableIndex(candidate);
    if (list) {
      tablesBase = candidate;
      tablesList = list;
      globalThis.__tvdataTablesBase = tablesBase;
      globalThis.__tvdataTablesList = tablesList;
      return tablesBase;
    }
  }

  throw new Error(`tables/index.json fehlt oder ist leer. Geprüfte Pfade: ${tablesBaseCandidates.join(', ')}`);
}

async function listTables() {
  await resolveTablesBase();
  return tablesList;
}

async function loadTable(name) {
  if (cache.has(name)) return cache.get(name);
  const tableBase = await resolveTablesBase();
  const base = `${tableBase}/${encodeURIComponent(name)}`;
  const [tableRows, advRows, metaRows] = await Promise.all([
    fetchCSV(`${base}/Table.csv`),
    fetchCSV(`${base}/Adv.csv`),
    fetchCSV(`${base}/Meta.csv`),
  ]);
  const data = { name, table: gridObject(tableRows), adv: gridObject(advRows), meta: kvObject(metaRows) };
  cache.set(name, data);
  return data;
}

function selectedValues(select) {
  return [...select.selectedOptions].map((o) => o.value);
}

function quantile(sortedVals, q) {
  if (!sortedVals.length) return null;
  const pos = (sortedVals.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  const next = sortedVals[base + 1] ?? sortedVals[base];
  return sortedVals[base] + rest * (next - sortedVals[base]);
}

function stddev(vals, m) {
  if (!vals.length) return 0;
  const v = vals.reduce((acc, x) => acc + (x - m) ** 2, 0) / vals.length;
  return Math.sqrt(v);
}

function collectSalaries(data) {
  const vals = [];
  Object.values(data.table).forEach((row) => Object.values(row).forEach((v) => {
    const n = toNum(v);
    if (n != null) vals.push(n);
  }));
  vals.sort((a, b) => a - b);
  return vals;
}

function metrics(data) {
  const vals = collectSalaries(data);
  const sum = vals.reduce((a, b) => a + b, 0);
  const mean = sum / vals.length;
  const median = quantile(vals, 0.5);
  const p10 = quantile(vals, 0.1);
  const p90 = quantile(vals, 0.9);
  const q1 = quantile(vals, 0.25);
  const q3 = quantile(vals, 0.75);
  const sd = stddev(vals, mean);
  return {
    count: vals.length,
    mean,
    median,
    min: vals[0],
    max: vals[vals.length - 1],
    spread: vals[vals.length - 1] - vals[0],
    p10,
    p90,
    iqr: q3 - q1,
    stddev: sd,
    cv: mean ? sd / mean : 0,
  };
}

function pairedCells(base, target) {
  const pairs = [];
  Object.keys(base.table).forEach((group) => {
    if (!target.table[group]) return;
    Object.keys(base.table[group]).forEach((stage) => {
      const a = toNum(base.table[group][stage]);
      const b = toNum(target.table[group]?.[stage]);
      if (a == null || b == null) return;
      const delta = b - a;
      const pct = a ? (delta / a) * 100 : 0;
      pairs.push({ group, stage, base: a, target: b, delta, pct });
    });
  });
  return pairs;
}

function correlation(xs, ys) {
  const n = xs.length;
  if (n === 0) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0; let dx = 0; let dy = 0;
  for (let i = 0; i < n; i += 1) {
    const xv = xs[i] - mx;
    const yv = ys[i] - my;
    num += xv * yv;
    dx += xv * xv;
    dy += yv * yv;
  }
  return dx && dy ? num / Math.sqrt(dx * dy) : null;
}

function renderMetrics(rows) {
  metricsEl.innerHTML = `<table><thead><tr><th>Tabelle</th><th>Anzahl</th><th>Mittelwert</th><th>Median</th><th>P10</th><th>P90</th><th>Min</th><th>Max</th><th>Spreizung</th><th>IQR</th><th>StdAbw</th><th>CV</th></tr></thead><tbody>${rows.map((r) =>
    `<tr><td>${r.name}</td><td>${r.m.count}</td><td>${fmt(r.m.mean)}</td><td>${fmt(r.m.median)}</td><td>${fmt(r.m.p10)}</td><td>${fmt(r.m.p90)}</td><td>${fmt(r.m.min)}</td><td>${fmt(r.m.max)}</td><td>${fmt(r.m.spread)}</td><td>${fmt(r.m.iqr)}</td><td>${fmt(r.m.stddev)}</td><td>${fmt(r.m.cv * 100, '%')}</td></tr>`).join('')}</tbody></table>`;
}

function renderPairKpis(base, target) {
  const pairs = pairedCells(base, target);
  const deltas = pairs.map((p) => p.delta);
  const pcts = pairs.map((p) => p.pct).sort((a, b) => a - b);
  const avgDelta = deltas.reduce((a, b) => a + b, 0) / deltas.length;
  const avgPct = pcts.reduce((a, b) => a + b, 0) / pcts.length;
  const medPct = quantile(pcts, 0.5);
  const maxUp = deltas.length ? Math.max(...deltas) : null;
  const maxDown = deltas.length ? Math.min(...deltas) : null;
  const corr = correlation(pairs.map((p) => p.base), pairs.map((p) => p.target));

  const cards = [
    ['Gemeinsame Zellen', `${pairs.length}`],
    ['Ø Differenz', fmt(avgDelta, ' €')],
    ['Ø Differenz %', fmt(avgPct, '%')],
    ['Median Differenz %', fmt(medPct, '%')],
    ['Max. Anstieg', fmt(maxUp, ' €')],
    ['Max. Rückgang', fmt(maxDown, ' €')],
    ['Korrelation', fmt(corr)],
  ];

  pairKpisEl.innerHTML = cards.map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');
}

function heatColor(deltaPct) {
  const v = Math.max(-10, Math.min(10, deltaPct));
  if (v >= 0) return `hsl(5 ${50 + v * 4}% ${95 - v * 3}%)`;
  return `hsl(210 ${50 + Math.abs(v) * 4}% ${95 - Math.abs(v) * 3}%)`;
}

function renderHeatmap(base, target) {
  const groups = Object.keys(base.table).filter((g) => target.table[g]);
  const stages = Object.keys(base.table[groups[0]] || {});
  let body = '';
  for (const g of groups) {
    body += `<tr><td>${g}</td>`;
    for (const s of stages) {
      const a = toNum(base.table[g][s]);
      const b = toNum(target.table[g]?.[s]);
      if (a == null || b == null) { body += '<td></td>'; continue; }
      const d = b - a;
      const p = (d / a) * 100;
      body += `<td class="heat" style="background:${heatColor(p)}" title="${d.toFixed(2)} EUR">${p.toFixed(2)}%</td>`;
    }
    body += '</tr>';
  }
  heatmapEl.innerHTML = `<table><thead><tr><th>Gruppe</th>${stages.map((s) => `<th>Stufe ${s}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderGroupBars(base, target) {
  const pairs = pairedCells(base, target);
  const agg = new Map();
  pairs.forEach((p) => {
    const curr = agg.get(p.group) || { sum: 0, n: 0 };
    curr.sum += p.pct;
    curr.n += 1;
    agg.set(p.group, curr);
  });
  const rows = [...agg.entries()].map(([group, v]) => ({ group, avgPct: v.sum / v.n }));
  rows.sort((a, b) => b.avgPct - a.avgPct);
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.avgPct)), 1);
  const bar = (v) => `${(Math.abs(v) / maxAbs) * 45}%`;

  groupBarsEl.innerHTML = `<table><thead><tr><th>Gruppe</th><th>Ø Differenz %</th><th>Visualisierung</th></tr></thead><tbody>${rows.map((r) => {
    const positive = r.avgPct >= 0;
    const color = positive ? '#dc2626' : '#2563eb';
    return `<tr><td>${r.group}</td><td>${fmt(r.avgPct, '%')}</td><td><div style="display:flex;align-items:center;gap:6px;"><div style="width:45%;display:flex;justify-content:flex-end;"><div style="height:10px;background:${positive ? 'transparent' : color};width:${positive ? '0' : bar(r.avgPct)}"></div></div><div style="width:2px;height:14px;background:#9ca3af"></div><div style="width:45%;"><div style="height:10px;background:${positive ? color : 'transparent'};width:${positive ? bar(r.avgPct) : '0'}"></div></div></div></td></tr>`;
  }).join('')}</tbody></table>`;
}

function progressionSeries(data, group) {
  const row = data.table[group] || {};
  const adv = data.adv[group] || {};
  let year = 0;
  const points = [];
  Object.keys(row).forEach((stage) => {
    const salary = toNum(row[stage]);
    if (salary == null) return;
    const duration = toNum(adv[stage]) ?? 0;
    points.push({ stage, x: year, duration, y: salary });
    year += duration;
  });
  return points;
}

function renderGraph(base, target) {
  const groups = Object.keys(base.table).filter((g) => target.table[g]).slice(0, 8);
  const colors = ['#2563eb', '#dc2626', '#059669', '#7c3aed', '#ea580c', '#0891b2', '#4f46e5', '#65a30d'];
  const series = groups.map((g) => ({ group: g, base: progressionSeries(base, g), target: progressionSeries(target, g) }));
  const all = series.flatMap((s) => [...s.base, ...s.target]);
  if (!all.length) { graphEl.textContent = 'Keine gemeinsamen Daten.'; return; }

  const maxX = Math.max(...all.map((p) => p.x)) || 1;
  const minY = Math.min(...all.map((p) => p.y));
  const maxY = Math.max(...all.map((p) => p.y));
  const sx = (x) => 50 + (x / maxX) * 900;
  const sy = (y) => 330 - ((y - minY) / (maxY - minY || 1)) * 280;

  let paths = '';
  let legend = '<div class="legend">';
  series.forEach((s, i) => {
    const c = colors[i % colors.length];
    const toPath = (pts) => pts.map((p, idx) => `${idx ? 'L' : 'M'}${sx(p.x)},${sy(p.y)}`).join(' ');
    paths += `<path d="${toPath(s.base)}" stroke="${c}" stroke-width="2" fill="none" />`;
    paths += `<path d="${toPath(s.target)}" stroke="${c}" stroke-dasharray="6 4" stroke-width="2" fill="none" />`;
    legend += `<span><span class="swatch" style="background:${c}"></span>${s.group} (voll=Baseline / gestrichelt=Vergleich)</span>`;
  });
  legend += '</div>';

  graphEl.innerHTML = `${legend}<div class="graph-wrap"><svg viewBox="0 0 980 360"><line x1="50" y1="330" x2="950" y2="330" stroke="#9ca3af"/><line x1="50" y1="40" x2="50" y2="330" stroke="#9ca3af"/>${paths}</svg></div>`;
}

function renderHistogram(tables) {
  const allVals = tables.map((t) => collectSalaries(t));
  const min = Math.min(...allVals.flat());
  const max = Math.max(...allVals.flat());
  const bins = 12;
  const width = (max - min) / bins || 1;
  const palette = ['#2563eb', '#dc2626', '#059669', '#7c3aed', '#ea580c', '#0891b2'];

  const countsByTable = allVals.map((vals) => {
    const c = Array.from({ length: bins }, () => 0);
    vals.forEach((v) => {
      const idx = Math.min(bins - 1, Math.floor((v - min) / width));
      c[idx] += 1;
    });
    return c;
  });

  const maxCount = Math.max(...countsByTable.flat(), 1);
  let rects = '';
  countsByTable.forEach((counts, ti) => {
    counts.forEach((count, bi) => {
      const x = 60 + bi * 70 + ti * (50 / countsByTable.length);
      const w = 48 / countsByTable.length;
      const h = (count / maxCount) * 260;
      rects += `<rect x="${x}" y="${320 - h}" width="${w}" height="${h}" fill="${palette[ti % palette.length]}" opacity="0.65"/>`;
    });
  });

  const legend = `<div class="legend">${tables.map((t, i) => `<span><span class="swatch" style="background:${palette[i % palette.length]}"></span>${t.name}</span>`).join('')}</div>`;
  histEl.innerHTML = `${legend}<div class="chart-wrap"><svg viewBox="0 0 980 360"><line x1="50" y1="320" x2="940" y2="320" stroke="#9ca3af"/>${rects}</svg></div>`;
}

function renderLogic(base, target) {
  const groups = Object.keys(base.adv).filter((g) => target.adv[g]);
  const rows = [];
  groups.forEach((g) => {
    let a = 0; let b = 0;
    Object.keys(base.adv[g]).forEach((s) => {
      const av = toNum(base.adv[g][s]);
      const bv = toNum(target.adv[g]?.[s]);
      if (av != null) a += av;
      if (bv != null) b += bv;
    });
    rows.push({ g, a, b, d: b - a });
  });
  logicEl.innerHTML = `<table><thead><tr><th>Gruppe</th><th>Gesamtjahre Baseline</th><th>Gesamtjahre Vergleich</th><th>Differenz</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${r.g}</td><td>${fmt(r.a)}</td><td>${fmt(r.b)}</td><td>${fmt(r.d)}</td></tr>`).join('')}</tbody></table>`;
}

function allowanceBaseFromTablesBase() {
  if (!tablesBase) return '../../allowances';
  return tablesBase.replace(/\/tables$/, '/allowances');
}

async function loadAllowanceMeta(name) {
  const [metaRows, tableRows] = await Promise.all([
    fetchCSV(`${allowanceBaseFromTablesBase()}/${name}/Meta.csv`),
    fetchCSV(`${allowanceBaseFromTablesBase()}/${name}/Table.csv`),
  ]);
  const meta = kvObject(metaRows);
  const values = tableRows.slice(1).flatMap((r) => r.slice(1)).map(toNum).filter((x) => x != null);
  return {
    name,
    label: meta.label_de || meta.label_en || name,
    addingType: meta.adding_type || '',
    min: values.length ? Math.min(...values) : null,
    max: values.length ? Math.max(...values) : null,
  };
}

async function renderAllowances(tables) {
  const lists = {};
  for (const t of tables) {
    const names = (t.meta.allowances || '').split(';').map((x) => x.trim()).filter(Boolean);
    lists[t.name] = await Promise.all(names.map(loadAllowanceMeta));
  }
  const all = [...new Set(Object.values(lists).flat().map((a) => a.name))];
  allowancesEl.innerHTML = `<table><thead><tr><th>Zulage</th>${tables.map((t) => `<th>${t.name}</th>`).join('')}</tr></thead><tbody>${all.map((name) => {
    return `<tr><td>${name}</td>${tables.map((t) => {
      const item = lists[t.name].find((x) => x.name === name);
      return `<td>${item ? `${item.label}<br><small>${item.addingType}, ${fmt(item.min)}..${fmt(item.max)}</small>` : '—'}</td>`;
    }).join('')}</tr>`;
  }).join('')}</tbody></table>`;
}

async function runComparison() {
  const selected = selectedValues(tableSelect);
  if (selected.length < 2) return;
  const baseline = baselineSelect.value;
  const target = targetSelect.value;
  const data = await Promise.all(selected.map(loadTable));
  const byName = Object.fromEntries(data.map((d) => [d.name, d]));

  renderMetrics(data.map((d) => ({ name: d.name, m: metrics(d) })));
  renderPairKpis(byName[baseline], byName[target]);
  renderHeatmap(byName[baseline], byName[target]);
  renderGroupBars(byName[baseline], byName[target]);
  renderGraph(byName[baseline], byName[target]);
  renderHistogram(data);
  renderLogic(byName[baseline], byName[target]);
  await renderAllowances(data);
}

function syncSelectors() {
  const selected = selectedValues(tableSelect);
  baselineSelect.innerHTML = selected.map((x) => `<option value="${x}">${x}</option>`).join('');
  targetSelect.innerHTML = selected.map((x) => `<option value="${x}">${x}</option>`).join('');
  if (selected.length > 1) targetSelect.value = selected[1];
}

async function init() {
  tableSelect.innerHTML = '<option>Lade Tabellen ...</option>';
  const tables = await listTables();
  if (!tables.length) throw new Error('Keine Tabellen gefunden (index.json enthält keine Einträge).');
  tableSelect.innerHTML = tables.map((t) => `<option value="${t}">${t}</option>`).join('');
  [...tableSelect.options].slice(0, 3).forEach((o) => { o.selected = true; });
  syncSelectors();
}

tableSelect.addEventListener('change', syncSelectors);
loadBtn.addEventListener('click', runComparison);

init().catch((err) => {
  document.body.innerHTML = `<pre>Fehler: ${err.message}</pre>`;
});
})();
