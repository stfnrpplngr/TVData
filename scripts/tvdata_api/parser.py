from __future__ import annotations
import csv, hashlib, json, os, re, unicodedata
from pathlib import Path
from typing import Any

LIST_FIELDS = {"allowances", "prv", "options", "options_label_de", "options_label_en"}
NUMERIC = re.compile(r"^-?(?:\d+|\d+\.\d+)$")

class BuildError(RuntimeError):
    pass

def scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return None
    if NUMERIC.fullmatch(value):
        return float(value) if "." in value else int(value)
    return value

def read_meta(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not path.exists():
        return {}, []
    data, rows = {}, []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if "value" not in fields:
            raise BuildError(f"{path}: requires a 'value' column")
        key_col = "name" if "name" in fields else "key" if "key" in fields else fields[0]
        for row in reader:
            key = (row.get(key_col) or "").strip()
            raw = (row.get("value") or "").strip()
            if not key:
                continue
            value = [x.strip() for x in raw.split(";") if x.strip()] if key in LIST_FIELDS else scalar(raw)
            data[key] = value
            item = {"name": key, "value": value}
            comment = (row.get("comment") or "").strip()
            if comment:
                item["comment"] = comment
            rows.append(item)
    return data, rows

def read_matrix(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"columns": [], "rows": []}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return {"columns": [], "rows": []}
        columns = [x.strip() for x in header[1:]]
        rows = []
        for number, row in enumerate(reader, 2):
            if not row or not any(x.strip() for x in row):
                continue
            key = row[0].strip()
            if not key:
                raise BuildError(f"{path}:{number}: empty first column")
            values = row[1:] + [""] * max(0, len(columns) - len(row[1:]))
            rows.append({"key": key, "values": {c: scalar(v) for c, v in zip(columns, values)}})
    return {"columns": columns, "rows": rows}

def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower() or "item"

def discover(root: Path, required: set[str]) -> list[Path]:
    if not root.exists():
        return []
    return sorted((Path(p) for p, _, files in os.walk(root) if required <= set(files)), key=lambda p: p.as_posix().casefold())

def unique_ids(paths: list[Path], root: Path) -> dict[Path, str]:
    groups: dict[str, list[Path]] = {}
    for path in paths:
        groups.setdefault(slug(path.name), []).append(path)
    return {path: (leaf if len(groups[leaf]) == 1 else slug("--".join(path.relative_to(root).parts))) for leaf, group in groups.items() for path in group}

def digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()
