/** Lightweight browser client for the TVData Static API. */
export class TVDataClient {
  constructor({ baseUrl = "./v1", fetchImpl = globalThis.fetch } = {}) {
    if (typeof fetchImpl !== "function") throw new TypeError("A fetch implementation is required.");
    this.baseUrl = String(baseUrl).replace(/\/+$/, "");
    this.fetch = fetchImpl;
    this.cache = new Map();
  }

  async request(path, { cache = true } = {}) {
    const url = `${this.baseUrl}/${String(path).replace(/^\/+/, "")}`;
    if (cache && this.cache.has(url)) return this.cache.get(url);
    const promise = this.fetch(url, { headers: { Accept: "application/json" } }).then(async response => {
      if (!response.ok) {
        const error = new Error(`TVData request failed: ${response.status} ${response.statusText}`);
        error.status = response.status; error.url = url; throw error;
      }
      return response.json();
    });
    if (cache) this.cache.set(url, promise);
    try { return await promise; } catch (error) { this.cache.delete(url); throw error; }
  }

  getManifest() { return this.request("index.json"); }
  getTable(id) { return this.request(`tables/${encodeURIComponent(id)}.json`); }
  getAllowance(id) { return this.request(`allowances/${encodeURIComponent(id)}.json`); }
  getPension(id) { return this.request(`pensions/${encodeURIComponent(id)}.json`); }
  getValues() { return this.request("values.json"); }
  getAll() { return this.request("all.json"); }
  clearCache() { this.cache.clear(); }

  async listTables({ kind, query, validAt } = {}) {
    let items = [...(await this.request("tables/index.json")).items];
    if (kind) items = items.filter(item => item.kind === kind);
    if (query) items = filter(items, query);
    if (validAt) {
      const date = parseDate(validAt);
      items = items.filter(item => !item.valid_from || parseDate(item.valid_from) <= date);
    }
    return items;
  }

  async listAllowances({ query } = {}) {
    const items = (await this.request("allowances/index.json")).items;
    return query ? filter(items, query) : [...items];
  }

  async listPensions({ query } = {}) {
    const items = (await this.request("pensions/index.json")).items;
    return query ? filter(items, query) : [...items];
  }

  async getSalary(id, grade, step) {
    const table = await this.getTable(id);
    const row = table.grades.find(item => String(item.grade) === String(grade));
    if (!row) throw new RangeError(`Unknown grade "${grade}" in table "${id}".`);
    const key = String(step);
    if (!(key in row.steps)) throw new RangeError(`Unknown step "${step}" in table "${id}".`);
    return {
      table_id: table.id, table_name: table.name, valid_from: table.valid_from,
      pay_grade: `${table.pay_grade_prefix ?? ""}${grade}`, grade: String(grade), step: key,
      monthly_gross: row.steps[key], advancement_years: row.advancement_years?.[key] ?? null,
      currency: "EUR", period: "month"
    };
  }
}

function filter(items, query) {
  const needle = String(query).trim().toLocaleLowerCase("de");
  return items.filter(item => [item.id, item.name, item.path, item.pay_grade_prefix]
    .filter(Boolean).some(value => String(value).toLocaleLowerCase("de").includes(needle)));
}

function parseDate(value) {
  const timestamp = Date.parse(String(value).trim().replace(/\./g, "-"));
  if (Number.isNaN(timestamp)) throw new TypeError(`Invalid date: ${value}`);
  return timestamp;
}

if (typeof globalThis !== "undefined") globalThis.TVDataClient = TVDataClient;
