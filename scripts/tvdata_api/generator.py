from __future__ import annotations
import csv, json, shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .parser import discover, digest, read_matrix, read_meta, unique_ids

VERSION = "1"

def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def source(root: Path, repo: str, ref: str, files: list[Path]) -> dict[str, Any]:
    return {"repository": repo or None, "ref": ref or None, "files": [p.relative_to(root).as_posix() for p in files if p.exists()]}

def table(root: Path, path: Path, item_id: str, repo: str, ref: str) -> dict[str, Any]:
    tp, ap, mp = path / "Table.csv", path / "Adv.csv", path / "Meta.csv"
    meta, meta_rows = read_meta(mp)
    pay, progression = read_matrix(tp), read_matrix(ap)
    advancement = {row["key"]: row["values"] for row in progression["rows"]}
    text = f"{path} {meta.get('name_de','')} {meta.get('name_en','')}".casefold()
    payload = {
        "api_version": VERSION, "id": item_id, "type": "remuneration_table",
        "kind": "civil_service" if any(x in text for x in ("beamte", "besoldung", "civil service")) else "collective_agreement",
        "path": path.relative_to(root).as_posix(), "name": str(meta.get("name_de") or path.name),
        "meta": meta, "meta_rows": meta_rows, "pay_grade_prefix": meta.get("pay_grad_name"),
        "valid_from": meta.get("valid_from"), "columns": pay["columns"],
        "grades": [{"grade": row["key"], "steps": row["values"], "advancement_years": advancement.get(row["key"], {})} for row in pay["rows"]],
        "source": source(root, repo, ref, [tp, ap, mp]),
    }
    payload["content_sha256"] = digest({k: v for k, v in payload.items() if k != "source"})
    return payload

def allowance(root: Path, path: Path, item_id: str, repo: str, ref: str) -> dict[str, Any]:
    tp, mp = path / "Table.csv", path / "Meta.csv"
    meta, meta_rows = read_meta(mp); data = read_matrix(tp)
    payload = {"api_version": VERSION, "id": item_id, "type": "allowance", "path": path.relative_to(root).as_posix(),
               "name": str(meta.get("label_de") or path.name), "meta": meta, "meta_rows": meta_rows, "columns": data["columns"],
               "grades": [{"grade": row["key"], "options": row["values"]} for row in data["rows"]], "source": source(root, repo, ref, [tp, mp])}
    payload["content_sha256"] = digest({k: v for k, v in payload.items() if k != "source"})
    return payload

def pension(root: Path, path: Path, item_id: str, repo: str, ref: str) -> dict[str, Any]:
    mp = path / "Meta.csv"; meta, meta_rows = read_meta(mp)
    payload = {"api_version": VERSION, "id": item_id, "type": "supplementary_pension", "path": path.relative_to(root).as_posix(),
               "name": str(meta.get("label_de") or path.name), "meta": meta, "meta_rows": meta_rows, "source": source(root, repo, ref, [mp])}
    payload["content_sha256"] = digest({k: v for k, v in payload.items() if k != "source"})
    return payload

def compact(item: dict[str, Any], url: str) -> dict[str, Any]:
    meta = item.get("meta", {})
    return {"id": item["id"], "type": item["type"], "kind": item.get("kind"), "name": item["name"], "path": item["path"],
            "valid_from": item.get("valid_from"), "pay_grade_prefix": item.get("pay_grade_prefix"), "allowances": meta.get("allowances", []),
            "pensions": meta.get("prv", []), "url": url, "content_sha256": item["content_sha256"]}

def openapi() -> dict[str, Any]:
    json_response = {"200": {"description": "OK", "content": {"application/json": {"schema": {"type": "object"}}}}}
    csv_response = {"200": {"description": "OK", "content": {"text/csv": {"schema": {"type": "string"}}}}}
    paths: dict[str, Any] = {}
    for path in ("index.json", "tables/index.json", "allowances/index.json", "pensions/index.json", "values.json", "all.json"):
        paths[f"/{path}"] = {"get": {"operationId": "get_" + path.replace("/", "_").replace(".", "_"), "responses": json_response}}
    paths["/values.csv"] = {"get": {"operationId": "get_values_csv", "responses": csv_response}}
    for resource in ("tables", "allowances", "pensions"):
        paths[f"/{resource}/{{id}}.json"] = {"get": {"operationId": f"get_{resource}_by_id", "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string"}}], "responses": {**json_response, "404": {"description": "Not found"}}}}
    return {"openapi": "3.1.0", "info": {"title": "TVData Static API", "version": VERSION, "description": "Versioned read-only API for German public-sector remuneration and civil-service salary data."}, "servers": [{"url": "https://stfnrpplngr.github.io/TVData/v1"}], "paths": paths}

def build(root: Path, output: Path, source_repository: str = "", source_ref: str = "") -> dict[str, Any]:
    root, output = root.resolve(), output.resolve()
    if output.exists(): shutil.rmtree(output)
    output.mkdir(parents=True)
    roots = root / "tables", root / "allowances", root / "prv"
    paths = discover(roots[0], {"Table.csv", "Meta.csv"}), discover(roots[1], {"Table.csv", "Meta.csv"}), discover(roots[2], {"Meta.csv"})
    maps = unique_ids(paths[0], roots[0]), unique_ids(paths[1], roots[1]), unique_ids(paths[2], roots[2])
    tables = [table(root, p, maps[0][p], source_repository, source_ref) for p in paths[0]]
    allowances = [allowance(root, p, maps[1][p], source_repository, source_ref) for p in paths[1]]
    pensions = [pension(root, p, maps[2][p], source_repository, source_ref) for p in paths[2]]
    api = output / "v1"
    for name, items in (("tables", tables), ("allowances", allowances), ("pensions", pensions)):
        for item in items: write_json(api / name / f"{item['id']}.json", item)
        write_json(api / name / "index.json", {"api_version": VERSION, "items": [compact(x, f"{name}/{x['id']}.json") for x in items]})
    values = [{"table_id": t["id"], "table_name": t["name"], "kind": t["kind"], "valid_from": t.get("valid_from"), "pay_grade_prefix": t.get("pay_grade_prefix"), "grade": g["grade"], "step": step, "monthly_gross": gross, "advancement_years": g["advancement_years"].get(step), "currency": "EUR", "period": "month"} for t in tables for g in t["grades"] for step, gross in g["steps"].items() if gross is not None]
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = {"api_version": VERSION, "generated_at": generated, "source": {"repository": source_repository or None, "ref": source_ref or None}, "counts": {"tables": len(tables), "collective_agreements": sum(t["kind"] == "collective_agreement" for t in tables), "civil_service_tables": sum(t["kind"] == "civil_service" for t in tables), "allowances": len(allowances), "pensions": len(pensions), "salary_values": len(values)}, "resources": {"tables": "tables/index.json", "allowances": "allowances/index.json", "pensions": "pensions/index.json", "all": "all.json", "values_json": "values.json", "values_csv": "values.csv", "openapi": "openapi.json", "javascript_client": "../client/tvdata-client.js"}}
    write_json(api / "index.json", manifest)
    write_json(api / "all.json", {"api_version": VERSION, "generated_at": generated, "tables": tables, "allowances": allowances, "pensions": pensions})
    write_json(api / "values.json", {"api_version": VERSION, "generated_at": generated, "items": values})
    fields = ["table_id", "table_name", "kind", "valid_from", "pay_grade_prefix", "grade", "step", "monthly_gross", "advancement_years", "currency", "period"]
    with (api / "values.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(values)
    write_json(api / "openapi.json", openapi())
    schemas = {"table.schema.json": ["api_version", "id", "type", "name", "grades"], "allowance.schema.json": ["api_version", "id", "type", "name", "grades"], "pension.schema.json": ["api_version", "id", "type", "name", "meta"]}
    for filename, required in schemas.items(): write_json(api / "schemas" / filename, {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "required": required})
    asset_root = root / "api"
    if asset_root.exists():
        for item in asset_root.rglob("*"):
            if item.is_file():
                destination = output / item.relative_to(asset_root); destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(item, destination)
    (output / ".nojekyll").write_text("")
    return manifest
