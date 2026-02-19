(() => {
const $ = (id) => document.getElementById(id);

const els = {
  tariffASelect: $('tariffASelect'), tariffBSelect: $('tariffBSelect'), referenceMode: $('referenceMode'),
  validityInfo: $('validityInfo'), versionInfo: $('versionInfo'),
  groupFrom: $('groupFrom'), groupTo: $('groupTo'), stepFrom: $('stepFrom'), stepTo: $('stepTo'),
  selectedGroups: $('selectedGroups'), includeBase: $('includeBase'), includeJsz: $('includeJsz'),
  includeVwl: $('includeVwl'), includeAllowances: $('includeAllowances'),
  timeMode: $('timeMode'), customDuration: $('customDuration'), argumentMode: $('argumentMode'),
  applyBtn: $('applyBtn'),
  kpiTiles: $('kpiTiles'), curvePlot: $('curvePlot'), differenceBand: $('differenceBand'),
  detailGroupSelect: $('detailGroupSelect'), detailTable: $('detailTable'), microChart: $('microChart'),
  detailHoverInfo: $('detailHoverInfo'), heatmapMode: $('heatmapMode'), heatmap: $('heatmap'),
  simGroup: $('simGroup'), simStartStep: $('simStartStep'), simYears: $('simYears'), simWorkFactor: $('simWorkFactor'),
  lifetimeChart: $('lifetimeChart'), lifetimeTable: $('lifetimeTable'), sources: $('sources'), governance: $('governance'),
  exportCsv: $('exportCsv'), exportExcel: $('exportExcel'), exportPng: $('exportPng'),
};

const REMOTE_TABLE_BASE_CANDIDATES = [
  'https://raw.githubusercontent.com/stfnrpplngr/TVData/main/tables',
  'https://raw.githubusercontent.com/stfnrpplngr/TVData/Comparing-Remuneration-Tables/tables',
];
let tablesBase = null;
let tableList = [];
const cache = new Map();
let state = { filtered: [], pair: null, heatmapSvg: '' };

const toNum = (v) => {
  if (v == null || `${v}`.trim() === '') return null;
  return Number.parseFloat(`${v}`.replace(',', '.'));
};
const fmt = (v, unit = ' €') => (v == null || Number.isNaN(v) ? '—' : `${v.toFixed(2)}${unit}`);
const fmtPct = (v) => (v == null || Number.isNaN(v) ? '—' : `${v.toFixed(2)}%`);

function parseCSV(text) { return text.trim().split(/\r?\n/).map((line) => line.split(',')); }
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
function kvObject(rows) { const o = {}; rows.slice(1).forEach((r) => { if (r.length > 1) o[r[0]] = r[1]; }); return o; }

async function fetchJSON(url) { const r = await fetch(url, { cache: 'no-store' }); if (!r.ok) throw new Error(url); return r.json(); }
async function fetchCSV(url) { const r = await fetch(url, { cache: 'no-store' }); if (!r.ok) throw new Error(url); return parseCSV(await r.text()); }

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function localTableBaseCandidates() {
  const origin = window.location.origin;
  const path = window.location.pathname;
  const segments = path.split('/').filter(Boolean);
  const docsIndex = segments.indexOf('docs');
  const repoRoot = docsIndex >= 0 ? `/${segments.slice(0, docsIndex).join('/')}` : '';
  const cwdBase = window.location.href.endsWith('/') ? window.location.href : `${window.location.href}/`;

  return unique([
    new URL('../tables', cwdBase).pathname,
    new URL('../../tables', cwdBase).pathname,
    '/tables',
    `${repoRoot}/tables`,
    `${origin}/tables`,
    `${origin}${repoRoot}/tables`,
  ]);
}

function tableBaseCandidates() {
  return unique([...localTableBaseCandidates(), ...REMOTE_TABLE_BASE_CANDIDATES]);
}

async function resolveTablesBase() {
  if (tablesBase) return tablesBase;
  const attempts = [];
  for (const base of tableBaseCandidates()) {
    try {
      const idx = await fetchJSON(`${base}/index.json`);
      if (Array.isArray(idx) && idx.length) { tableList = idx; tablesBase = base; return base; }
    } catch (err) {
      attempts.push(`${base}/index.json`);
      void err;
    }
  }
  throw new Error(`Konnte tables/index.json nicht laden. Geprüfte Pfade: ${attempts.join(' | ')}`);
}

async function loadTable(name) {
  if (cache.has(name)) return cache.get(name);
  const base = `${await resolveTablesBase()}/${encodeURIComponent(name)}`;
  const [tableRows, advRows, metaRows] = await Promise.all([
    fetchCSV(`${base}/Table.csv`), fetchCSV(`${base}/Adv.csv`), fetchCSV(`${base}/Meta.csv`),
  ]);
  const data = { name, table: gridObject(tableRows), adv: gridObject(advRows), meta: kvObject(metaRows) };
  cache.set(name, data);
  return data;
}

function groupNumber(group) {
  const match = `${group}`.match(/\d+/);
  return match ? Number.parseInt(match[0], 10) : null;
}

function extractRows(a, b) {
  const rows = [];
  Object.keys(a.table).forEach((group) => {
    if (!b.table[group]) return;
    const gNum = groupNumber(group);
    Object.keys(a.table[group]).forEach((step) => {
      const sNum = Number.parseInt(step, 10);
      const av = toNum(a.table[group][step]);
      const bv = toNum(b.table[group]?.[step]);
      if (av == null || bv == null) return;
      rows.push({ group, gNum, step, sNum, a: av, b: bv });
    });
  });
  return rows;
}

function applyFilters(rows) {
  const gFrom = Number(els.groupFrom.value) || 1;
  const gTo = Number(els.groupTo.value) || 99;
  const sFrom = Number(els.stepFrom.value) || 1;
  const sTo = Number(els.stepTo.value) || 99;
  const selected = els.selectedGroups.value.split(',').map((x) => Number.parseInt(x.trim(), 10)).filter(Number.isFinite);
  return rows.filter((r) => {
    const inRange = (r.gNum == null || (r.gNum >= gFrom && r.gNum <= gTo)) && r.sNum >= sFrom && r.sNum <= sTo;
    return selected.length ? inRange && selected.includes(r.gNum) : inRange;
  });
}

function deltaValues(r) {
  const aMinusB = r.a - r.b;
  const base = els.referenceMode.value === 'A_MINUS_B' ? r.b : r.a;
  const signAdjusted = els.referenceMode.value === 'A_MINUS_B' ? aMinusB : -aMinusB;
  return { abs: signAdjusted, rel: base ? (signAdjusted / base) * 100 : 0 };
}

function componentAdjustedMonthly(row, tariff) {
  let total = 0;
  if (els.includeBase.checked) total += tariff === 'A' ? row.a : row.b;
  const meta = tariff === 'A' ? state.pair.a.meta : state.pair.b.meta;
  if (els.includeVwl.checked) total += toNum(meta.vwl_amount_monthly) || 0;
  if (els.includeAllowances.checked) total += toNum(meta.allowance_flat_monthly) || 0;
  if (els.includeJsz.checked) {
    const jszPct = toNum(meta.jsz_percent) || 0;
    total += ((tariff === 'A' ? row.a : row.b) * (jszPct / 100)) / 12;
  }
  return total;
}

function getDuration(group, step, tariffData) {
  const mode = els.timeMode.value;
  if (mode === 'custom') return Number(els.customDuration.value) || 2;
  if (mode === 'standard') return 2;
  return toNum(tariffData.adv[group]?.[step]) || 2;
}

function renderOverview(rows) {
  const deltas = rows.map(deltaValues);
  const maxAbs = deltas.reduce((m, d) => Math.max(m, Math.abs(d.abs)), 0);
  const maxRel = deltas.reduce((m, d) => Math.max(m, Math.abs(d.rel)), 0);
  const byStep = new Map();
  rows.forEach((r) => {
    const item = byStep.get(r.step) || { a: 0, b: 0, n: 0, diff: 0 };
    item.a += r.a; item.b += r.b; item.n += 1; item.diff += deltaValues(r).abs;
    byStep.set(r.step, item);
  });
  const stepRows = [...byStep.entries()].map(([step, v]) => ({ step, a: v.a / v.n, b: v.b / v.n, d: v.diff / v.n }));
  const stepSorted = stepRows.sort((x, y) => Number(x.step) - Number(y.step));
  const last = stepSorted[stepSorted.length - 1];
  const first = stepSorted[0];
  const spreadA = last ? last.a - first.a : 0;
  const spreadB = last ? last.b - first.b : 0;
  const avgIncA = stepSorted.length > 1 ? spreadA / (stepSorted.length - 1) : 0;
  const avgIncB = stepSorted.length > 1 ? spreadB / (stepSorted.length - 1) : 0;

  const arg = argumentInsights(rows);
  els.kpiTiles.innerHTML = [
    ['Max Betrag Tarif A', fmt(Math.max(...rows.map((r) => r.a)))],
    ['Max Betrag Tarif B', fmt(Math.max(...rows.map((r) => r.b)))],
    ['Spreizung Stufe 1 bis Endstufe (A/B)', `${fmt(spreadA)} / ${fmt(spreadB)}`],
    ['Mittlere Steigerung je Stufe (A/B)', `${fmt(avgIncA)} / ${fmt(avgIncB)}`],
    ['Größte Abweichung absolut', fmt(maxAbs)],
    ['Größte Abweichung relativ', fmtPct(maxRel)],
    ...(els.argumentMode.checked ? [['Größte Verlierer EGs', arg.losers], ['Größte Gewinner EGs', arg.winners], ['Einstieg vs Langjährig', arg.entryVsSenior]] : []),
  ].map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');

  const maxY = Math.max(...stepSorted.flatMap((r) => [r.a, r.b])) || 1;
  const minY = Math.min(...stepSorted.flatMap((r) => [r.a, r.b])) || 0;
  const sx = (i) => 60 + (i / Math.max(stepSorted.length - 1, 1)) * 900;
  const sy = (v) => 260 - ((v - minY) / Math.max(maxY - minY, 1)) * 210;
  const path = (key) => stepSorted.map((r, i) => `${i ? 'L' : 'M'}${sx(i)},${sy(r[key])}`).join(' ');
  const circles = (key, c) => stepSorted.map((r, i) => `<circle cx="${sx(i)}" cy="${sy(r[key])}" r="4" fill="${c}"><title>Stufe ${r.step}: ${fmt(r[key])}</title></circle>`).join('');
  els.curvePlot.innerHTML = `<svg viewBox="0 0 980 280"><line x1="50" y1="260" x2="960" y2="260" stroke="#9aaccc"/><path d="${path('a')}" stroke="#1d4ed8" fill="none" stroke-width="3"/><path d="${path('b')}" stroke="#d32f2f" fill="none" stroke-width="3"/>${circles('a', '#1d4ed8')}${circles('b', '#d32f2f')}</svg>`;

  const maxBand = Math.max(...stepSorted.map((r) => Math.abs(r.d)), 1);
  els.differenceBand.innerHTML = `<svg viewBox="0 0 980 220"><line x1="50" y1="110" x2="960" y2="110" stroke="#9aaccc"/>${stepSorted.map((r, i) => {
    const h = (Math.abs(r.d) / maxBand) * 90;
    const y = r.d >= 0 ? 110 - h : 110;
    const c = r.d >= 0 ? '#d32f2f' : '#1d4ed8';
    return `<rect x="${sx(i) - 16}" y="${y}" width="32" height="${h}" fill="${c}"><title>Stufe ${r.step}: ${fmt(r.d)}</title></rect>`;
  }).join('')}</svg>`;
}

function argumentInsights(rows) {
  const byGroup = new Map();
  rows.forEach((r) => {
    const d = deltaValues(r).abs;
    const e = byGroup.get(r.group) || { sum: 0, n: 0, start: null, end: null };
    e.sum += d; e.n += 1;
    if (r.sNum === 1) e.start = d;
    e.end = d;
    byGroup.set(r.group, e);
  });
  const arr = [...byGroup.entries()].map(([g, v]) => ({ group: g, avg: v.sum / v.n, start: v.start ?? 0, end: v.end ?? 0 }));
  arr.sort((a, b) => b.avg - a.avg);
  const winners = arr.slice(0, 3).map((x) => x.group).join(', ') || '—';
  const losers = arr.slice(-3).map((x) => x.group).join(', ') || '—';
  const entryVsSenior = arr.length ? `${fmt(arr[0].start)} vs ${fmt(arr[0].end)}` : '—';
  return { winners, losers, entryVsSenior };
}

function renderDetail(rows) {
  const groups = [...new Set(rows.map((r) => r.group))];
  const current = els.detailGroupSelect.value && groups.includes(els.detailGroupSelect.value) ? els.detailGroupSelect.value : groups[0];
  els.detailGroupSelect.innerHTML = groups.map((g) => `<option value="${g}">${g}</option>`).join('');
  els.detailGroupSelect.value = current;
  els.simGroup.innerHTML = els.detailGroupSelect.innerHTML;
  const groupRows = rows.filter((r) => r.group === current).sort((a, b) => a.sNum - b.sNum);

  els.detailTable.innerHTML = `<table><thead><tr><th>Stufe</th><th>Tarif A</th><th>Tarif B</th><th>Differenz abs.</th><th>Differenz rel.</th></tr></thead><tbody>${groupRows.map((r) => {
    const d = deltaValues(r);
    const yearlyA = componentAdjustedMonthly(r, 'A') * 12;
    const yearlyB = componentAdjustedMonthly(r, 'B') * 12;
    const rounded = (Math.round(r.a) === r.a || Math.round(r.b) === r.b) ? 'Rundungsartefakt möglich' : 'keine auffällige Rundung';
    const tooltip = `${rounded}; Laufzeit A=${getDuration(r.group, r.step, state.pair.a)} Jahre, B=${getDuration(r.group, r.step, state.pair.b)} Jahre; Jahresbrutto A=${fmt(yearlyA, ' €')}, B=${fmt(yearlyB, ' €')}`;
    return `<tr><td>${r.step}</td><td>${fmt(r.a)}</td><td>${fmt(r.b)}</td><td class="${d.abs >= 0 ? 'positive' : 'negative'}" data-tip="${tooltip}">${fmt(d.abs)}</td><td>${fmtPct(d.rel)}</td></tr>`;
  }).join('')}</tbody></table>`;

  els.detailTable.querySelectorAll('[data-tip]').forEach((cell) => {
    cell.addEventListener('mouseenter', () => { els.detailHoverInfo.textContent = cell.dataset.tip; });
  });

  const prog = groupRows.slice(1).map((r, i) => {
    const prev = groupRows[i];
    return { s: r.step, a: ((r.a - prev.a) / prev.a) * 100, b: ((r.b - prev.b) / prev.b) * 100 };
  });
  const sx = (i) => 70 + (i / Math.max(prog.length - 1, 1)) * 860;
  const maxY = Math.max(...prog.flatMap((x) => [x.a, x.b]), 0) + 1;
  const sy = (v) => 230 - (v / maxY) * 180;
  const path = (k) => prog.map((r, i) => `${i ? 'L' : 'M'}${sx(i)},${sy(r[k])}`).join(' ');
  els.microChart.innerHTML = `<svg viewBox="0 0 980 260"><line x1="50" y1="230" x2="950" y2="230" stroke="#9aaccc"/><path d="${path('a')}" stroke="#1d4ed8" fill="none" stroke-width="3"/><path d="${path('b')}" stroke="#d32f2f" fill="none" stroke-width="3"/></svg>`;
}

function renderHeatmap(rows) {
  const groups = [...new Set(rows.map((r) => r.group))];
  const steps = [...new Set(rows.map((r) => r.step))].sort((a, b) => Number(a) - Number(b));
  const mode = els.heatmapMode.value;
  const values = rows.map((r) => (mode === 'abs' ? deltaValues(r).abs : deltaValues(r).rel));
  const range = Math.max(...values.map((v) => Math.abs(v)), 1);
  const cellW = 70; const cellH = 36;
  let rects = '';
  groups.forEach((g, gi) => {
    steps.forEach((s, si) => {
      const row = rows.find((r) => r.group === g && r.step === s);
      if (!row) return;
      const val = mode === 'abs' ? deltaValues(row).abs : deltaValues(row).rel;
      const ratio = Math.abs(val) / range;
      const hue = val >= 0 ? 5 : 215;
      const fill = `hsl(${hue} ${55 + ratio * 35}% ${94 - ratio * 35}%)`;
      const x = 120 + si * cellW;
      const y = 30 + gi * cellH;
      rects += `<rect class="heatcell" data-group="${g}" x="${x}" y="${y}" width="${cellW - 2}" height="${cellH - 2}" fill="${fill}"/><text x="${x + (cellW / 2)}" y="${y + 21}" text-anchor="middle" font-size="11">${val.toFixed(mode === 'abs' ? 0 : 1)}</text>`;
    });
  });
  const labels = groups.map((g, gi) => `<text x="8" y="${54 + gi * cellH}" font-size="12">${g}</text>`).join('') + steps.map((s, si) => `<text x="${145 + si * cellW}" y="20" font-size="12">St ${s}</text>`).join('');
  const width = 160 + steps.length * cellW;
  const height = 60 + groups.length * cellH;
  const svg = `<svg viewBox="0 0 ${width} ${height}">${labels}${rects}</svg>`;
  state.heatmapSvg = svg;
  els.heatmap.innerHTML = svg;
  els.heatmap.querySelectorAll('.heatcell').forEach((c) => c.addEventListener('click', () => {
    els.detailGroupSelect.value = c.dataset.group;
    renderDetail(rows);
    document.getElementById('detailSection').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));
}

function simulate(rows) {
  const group = els.simGroup.value || rows[0]?.group;
  const years = Number(els.simYears.value) || 10;
  const startStep = Number(els.simStartStep.value) || 1;
  const factor = Number(els.simWorkFactor.value) || 1;
  const groupRows = rows.filter((r) => r.group === group).sort((a, b) => a.sNum - b.sNum);
  let stepIndex = Math.max(0, startStep - 1);
  let cumA = 0; let cumB = 0; let acc = [];
  let remaining = getDuration(group, `${stepIndex + 1}`, state.pair.a);
  for (let y = 1; y <= years; y += 1) {
    const r = groupRows[Math.min(stepIndex, groupRows.length - 1)];
    const annualA = componentAdjustedMonthly(r, 'A') * 12 * factor;
    const annualB = componentAdjustedMonthly(r, 'B') * 12 * factor;
    cumA += annualA; cumB += annualB;
    acc.push({ year: y, step: r.step, annualA, annualB, diff: annualA - annualB, cumA, cumB, cumDiff: cumA - cumB });
    remaining -= 1;
    if (remaining <= 0 && stepIndex < groupRows.length - 1) {
      stepIndex += 1;
      remaining = getDuration(group, `${stepIndex + 1}`, state.pair.a);
    }
  }
  return acc;
}

function renderSimulation(rows) {
  const sim = simulate(rows);
  const maxY = Math.max(...sim.flatMap((r) => [r.cumA, r.cumB])) || 1;
  const sx = (i) => 60 + (i / Math.max(sim.length - 1, 1)) * 900;
  const sy = (v) => 260 - (v / maxY) * 220;
  const path = (key) => sim.map((r, i) => `${i ? 'L' : 'M'}${sx(i)},${sy(r[key])}`).join(' ');
  els.lifetimeChart.innerHTML = `<svg viewBox="0 0 980 290"><line x1="50" y1="260" x2="950" y2="260" stroke="#9aaccc"/><path d="${path('cumA')}" stroke="#1d4ed8" fill="none" stroke-width="3"/><path d="${path('cumB')}" stroke="#d32f2f" fill="none" stroke-width="3"/><path d="${path('cumDiff')}" stroke="#0f8a5f" fill="none" stroke-width="2" stroke-dasharray="6 4"/></svg>`;
  els.lifetimeTable.innerHTML = `<table><thead><tr><th>Jahr</th><th>Stufe</th><th>Jahresbrutto A</th><th>Jahresbrutto B</th><th>Differenz</th></tr></thead><tbody>${sim.map((r) => `<tr><td>${r.year}</td><td>${r.step}</td><td>${fmt(r.annualA)}</td><td>${fmt(r.annualB)}</td><td>${fmt(r.diff)}</td></tr>`).join('')}</tbody></table>`;
}

function qualityChecks(rows) {
  const byGroup = new Map();
  rows.forEach((r) => {
    const list = byGroup.get(r.group) || [];
    list.push(r);
    byGroup.set(r.group, list);
  });
  let monotone = true; let outliers = 0; let rounded = 0;
  byGroup.forEach((list) => {
    list.sort((a, b) => a.sNum - b.sNum);
    for (let i = 1; i < list.length; i += 1) {
      if (list[i].a < list[i - 1].a || list[i].b < list[i - 1].b) monotone = false;
      if (Math.abs(list[i].a - list[i - 1].a) > 800 || Math.abs(list[i].b - list[i - 1].b) > 800) outliers += 1;
    }
    list.forEach((r) => { if (Math.round(r.a) === r.a || Math.round(r.b) === r.b) rounded += 1; });
  });
  return { monotone, outliers, rounded };
}

function renderSources(rows) {
  const { a, b } = state.pair;
  const q = qualityChecks(rows);
  els.validityInfo.textContent = `Gültigkeitsstand: A=${a.meta.valid_from || 'n/a'} • B=${b.meta.valid_from || 'n/a'} • Quelle: ${a.meta.source_url || 'n/a'}`;
  els.versionInfo.textContent = `Version: A=${a.meta.version || a.name} • B=${b.meta.version || b.name}`;
  els.sources.innerHTML = `<table><thead><tr><th>Tarif</th><th>Quellen</th><th>Abgeleitet/Original</th><th>Hinweise</th></tr></thead><tbody>
    <tr><td>${a.name}</td><td>${a.meta.source_url || '—'}</td><td>${a.meta.derived === 'true' ? 'abgeleitet' : 'original/unklar'}</td><td>${a.meta.notes || '—'}</td></tr>
    <tr><td>${b.name}</td><td>${b.meta.source_url || '—'}</td><td>${b.meta.derived === 'true' ? 'abgeleitet' : 'original/unklar'}</td><td>${b.meta.notes || '—'}</td></tr>
  </tbody></table>`;
  els.governance.innerHTML = `<div class="cards">
    <div class="card"><div class="k">Monotone Steigerung geprüft</div><div class="v">${q.monotone ? 'Ja' : 'Auffällig'}</div></div>
    <div class="card"><div class="k">Ausreißer markiert</div><div class="v">${q.outliers}</div></div>
    <div class="card"><div class="k">Rundungsartefakte markiert</div><div class="v">${q.rounded}</div></div>
    <div class="card"><div class="k">Änderungsverlauf</div><div class="v">${a.meta.commit_hash || 'n/a'} / ${b.meta.commit_hash || 'n/a'}</div></div>
  </div>`;
}

function exportDetail(asExcel = false) {
  const rows = state.filtered;
  if (!rows.length) return;
  const data = [['group', 'step', 'tariff_a', 'tariff_b', 'delta_abs', 'delta_rel']]
    .concat(rows.map((r) => {
      const d = deltaValues(r);
      return [r.group, r.step, r.a.toFixed(2), r.b.toFixed(2), d.abs.toFixed(2), d.rel.toFixed(4)];
    }));
  const sep = asExcel ? '\t' : ',';
  const mime = asExcel ? 'application/vnd.ms-excel' : 'text/csv;charset=utf-8';
  const blob = new Blob([data.map((r) => r.join(sep)).join('\n')], { type: mime });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = asExcel ? 'tarifvergleich.xls' : 'tarifvergleich.csv';
  a.click();
}

function exportHeatmapPng() {
  if (!state.heatmapSvg) return;
  const svg = new Blob([state.heatmapSvg], { type: 'image/svg+xml;charset=utf-8' });
  const url = URL.createObjectURL(svg);
  const img = new Image();
  img.onload = () => {
    const canvas = document.createElement('canvas');
    canvas.width = img.width || 1200;
    canvas.height = img.height || 800;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0);
    canvas.toBlob((blob) => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'heatmap.png';
      a.click();
    });
    URL.revokeObjectURL(url);
  };
  img.src = url;
}

async function refresh() {
  const [a, b] = await Promise.all([loadTable(els.tariffASelect.value), loadTable(els.tariffBSelect.value)]);
  state.pair = { a, b };
  const filtered = applyFilters(extractRows(a, b));
  state.filtered = filtered;
  if (!filtered.length) {
    els.kpiTiles.innerHTML = '<div class="card">Keine Daten nach Filterung.</div>';
    return;
  }
  renderOverview(filtered);
  renderDetail(filtered);
  renderHeatmap(filtered);
  renderSimulation(filtered);
  renderSources(filtered);
}

async function init() {
  await resolveTablesBase();
  if (!tableList.length) throw new Error('Keine Tabellen in index.json');
  const options = tableList.map((n) => `<option value="${n}">${n}</option>`).join('');
  els.tariffASelect.innerHTML = options;
  els.tariffBSelect.innerHTML = options;
  els.tariffASelect.value = tableList[0];
  els.tariffBSelect.value = tableList[1] || tableList[0];
  await refresh();
}

[els.applyBtn, els.tariffASelect, els.tariffBSelect, els.referenceMode, els.heatmapMode, els.detailGroupSelect, els.simGroup]
  .forEach((el) => el.addEventListener('change', refresh));
els.exportCsv.addEventListener('click', () => exportDetail(false));
els.exportExcel.addEventListener('click', () => exportDetail(true));
els.exportPng.addEventListener('click', exportHeatmapPng);

init().catch((err) => {
  document.body.innerHTML = `<pre>Fehler beim Initialisieren: ${err.message}</pre>`;
});
})();
