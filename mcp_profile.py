"""Canonical semantic application profile for TVData pay systems.

The repository CSV files remain canonical for remuneration values.  This module
adds a thin semantic profile used by the MCP layer to describe and resolve those
files without changing their storage identifiers.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel


Regime = Literal["civil_service", "collective_agreement", "unknown"]
Scope = Literal["federal", "state", "municipal", "multi_state", "employer_specific", "sectoral", "unknown"]


class Jurisdiction(BaseModel):
    code: str
    name_de: str
    aliases: list[str]


class PaySystemIdentity(BaseModel):
    table_id: str
    regime: Regime
    family: str
    scope: Scope
    jurisdiction_code: str | None
    jurisdiction_name_de: str | None
    pay_scale: str | None
    variant: str | None
    pay_grade_prefix: str | None
    name_de: str | None
    name_en: str | None
    aliases: list[str]


JURISDICTIONS: dict[str, Jurisdiction] = {
    "BW": Jurisdiction(code="DE-BW", name_de="Baden-Württemberg", aliases=["bw", "baden-wuerttemberg", "baden württemberg", "baden-württemberg"]),
    "Bayern": Jurisdiction(code="DE-BY", name_de="Bayern", aliases=["by", "bayern"]),
    "Berlin": Jurisdiction(code="DE-BE", name_de="Berlin", aliases=["be", "berlin"]),
    "Brandenburg": Jurisdiction(code="DE-BB", name_de="Brandenburg", aliases=["bb", "brandenburg"]),
    "Bremen": Jurisdiction(code="DE-HB", name_de="Bremen", aliases=["hb", "bremen"]),
    "Bund": Jurisdiction(code="DE", name_de="Bund", aliases=["bund", "bundesrepublik", "bundesdienst", "federal"]),
    "Hamburg": Jurisdiction(code="DE-HH", name_de="Hamburg", aliases=["hh", "hamburg"]),
    "Hessen": Jurisdiction(code="DE-HE", name_de="Hessen", aliases=["he", "hessen"]),
    "LSA": Jurisdiction(code="DE-ST", name_de="Sachsen-Anhalt", aliases=["lsa", "st", "sachsen anhalt", "sachsen-anhalt"]),
    "MV": Jurisdiction(code="DE-MV", name_de="Mecklenburg-Vorpommern", aliases=["mv", "mecklenburg vorpommern", "mecklenburg-vorpommern"]),
    "NRW": Jurisdiction(code="DE-NW", name_de="Nordrhein-Westfalen", aliases=["nrw", "nw", "nordrhein westfalen", "nordrhein-westfalen"]),
    "Niedersachsen": Jurisdiction(code="DE-NI", name_de="Niedersachsen", aliases=["ni", "niedersachsen"]),
    "RLP": Jurisdiction(code="DE-RP", name_de="Rheinland-Pfalz", aliases=["rlp", "rp", "rheinland pfalz", "rheinland-pfalz"]),
    "SH": Jurisdiction(code="DE-SH", name_de="Schleswig-Holstein", aliases=["sh", "schleswig holstein", "schleswig-holstein"]),
    "Saarland": Jurisdiction(code="DE-SL", name_de="Saarland", aliases=["sl", "saarland"]),
    "Sachsen": Jurisdiction(code="DE-SN", name_de="Sachsen", aliases=["sn", "sachsen"]),
    "Thueringen": Jurisdiction(code="DE-TH", name_de="Thüringen", aliases=["th", "thueringen", "thüringen"]),
}

MULTI_STATE = Jurisdiction(
    code="DE-LAENDER",
    name_de="Länder",
    aliases=["laender", "länder", "bundeslaender", "bundesländer", "landesdienst", "tdl"],
)
MUNICIPAL = Jurisdiction(
    code="DE-KOMMUNAL",
    name_de="Kommunaler Bereich",
    aliases=["kommunal", "kommunen", "vka"],
)


def normalize_text(value: str) -> str:
    """Normalize German names and storage ids for deterministic alias matching."""
    text = value.casefold().strip()
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        text = text.replace(source, target)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = value.strip()
        if not clean:
            continue
        key = normalize_text(clean)
        if key and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def regime_for_table(table_id: str) -> Regime:
    folded = table_id.casefold()
    if folded.startswith("beamte-"):
        return "civil_service"
    if folded.startswith(("tv", "mtv")):
        return "collective_agreement"
    return "unknown"


def _beamte_parts(table_id: str) -> tuple[Jurisdiction | None, str | None, str | None]:
    suffix = table_id[len("Beamte-") :] if table_id.startswith("Beamte-") else ""
    jurisdiction: Jurisdiction | None = None
    jurisdiction_key = ""
    for key in sorted(JURISDICTIONS, key=len, reverse=True):
        if suffix == key or suffix.startswith(key + "-"):
            jurisdiction = JURISDICTIONS[key]
            jurisdiction_key = key
            break
    remainder = suffix[len(jurisdiction_key) :].lstrip("-") if jurisdiction_key else suffix
    parts = [part for part in remainder.split("-") if part]
    scale = parts[0] if parts else None
    variant = "-".join(parts[1:]) or None
    return jurisdiction, scale, variant


def _collective_identity(table_id: str) -> tuple[str, Scope, Jurisdiction | None, str | None]:
    if table_id == "TV-L" or table_id.startswith("TV-L-"):
        variant = table_id[len("TV-L") :].lstrip("-") or None
        return "TV-L", "multi_state", MULTI_STATE, variant
    if table_id.startswith("TVöD-"):
        variant = table_id[len("TVöD-") :] or None
        if variant == "Bund":
            return "TVöD", "federal", JURISDICTIONS["Bund"], variant
        if variant == "VKA":
            return "TVöD", "municipal", MUNICIPAL, variant
        return "TVöD", "sectoral", None, variant
    if table_id.startswith("TV-N-"):
        region = table_id[len("TV-N-") :]
        jurisdiction = JURISDICTIONS.get(region)
        return "TV-N", "state" if jurisdiction else "sectoral", jurisdiction, region or None
    if table_id == "TV-H" or table_id.startswith("TV-H-"):
        variant = table_id[len("TV-H") :].lstrip("-") or None
        return "TV-H", "state", JURISDICTIONS["Hessen"], variant
    if table_id == "TV-ITDZ-Berlin":
        return "TV-ITDZ", "state", JURISDICTIONS["Berlin"], None
    if table_id == "TV-ITZBund":
        return "TV-ITZBund", "federal", JURISDICTIONS["Bund"], None
    if table_id == "TV-BA":
        return "TV-BA", "federal", JURISDICTIONS["Bund"], None
    if table_id == "TV-Ärzte":
        return "TV-Ärzte", "multi_state", MULTI_STATE, None
    if table_id == "MTV-Autobahn":
        return "MTV-Autobahn", "employer_specific", JURISDICTIONS["Bund"], None
    if table_id in {"TV-Dataport", "TV-DGUV", "TV-DRV", "TV-V"}:
        return table_id, "employer_specific", None, None
    return table_id, "sectoral", None, None


def identity_for_table(table_id: str, meta: dict[str, str]) -> PaySystemIdentity:
    """Return the canonical MCP application-profile identity for one storage table."""
    regime = regime_for_table(table_id)
    pay_grade_prefix = meta.get("pay_grad_name") or None
    name_de = meta.get("name_de") or None
    name_en = meta.get("name_en") or None

    if regime == "civil_service":
        jurisdiction, scale, variant = _beamte_parts(table_id)
        family = "Beamtenbesoldung"
        scope: Scope = "federal" if jurisdiction and jurisdiction.code == "DE" else "state" if jurisdiction else "unknown"
    elif regime == "collective_agreement":
        family, scope, jurisdiction, variant = _collective_identity(table_id)
        scale = None
    else:
        family, scope, jurisdiction, scale, variant = table_id, "unknown", None, None, None

    # Jurisdiction-only terms are intentionally not standalone semantic aliases:
    # "Sachsen-Anhalt" should provide context, not compete with "TV-L" as a
    # tariff-family signal. Storage ids and full names still retain those tokens.
    aliases = [table_id, table_id.replace("-", " "), name_de or "", name_en or "", family]
    if jurisdiction:
        aliases.append(f"{family} {jurisdiction.name_de}")

    if regime == "civil_service":
        if scale:
            aliases.extend([f"{scale} Besoldung", f"Besoldung {scale}"])
            if jurisdiction:
                aliases.extend(
                    [
                        f"{scale} {jurisdiction.name_de}",
                        f"{scale}-Besoldung {jurisdiction.name_de}",
                        f"Beamte {jurisdiction.name_de} {scale}",
                    ]
                )
    elif family == "TV-L":
        aliases.extend(["TVL", "Tarifvertrag Länder", "Tarifvertrag der Länder", "TdL"])
    elif family == "TVöD":
        aliases.extend(["TVOED", "TVOD", "Tarifvertrag öffentlicher Dienst", "Tarifvertrag oeffentlicher Dienst"])
        if variant:
            aliases.extend([f"TVöD {variant}", f"TVOED {variant}"])

    return PaySystemIdentity(
        table_id=table_id,
        regime=regime,
        family=family,
        scope=scope,
        jurisdiction_code=jurisdiction.code if jurisdiction else None,
        jurisdiction_name_de=jurisdiction.name_de if jurisdiction else None,
        pay_scale=scale,
        variant=variant,
        pay_grade_prefix=pay_grade_prefix,
        name_de=name_de,
        name_en=name_en,
        aliases=_dedupe(aliases),
    )


def jurisdiction_from_query(query: str) -> Jurisdiction | None:
    normalized = normalize_text(query)
    candidates = [*JURISDICTIONS.values()]
    candidates.sort(key=lambda item: max((len(normalize_text(alias)) for alias in item.aliases), default=0), reverse=True)
    for jurisdiction in candidates:
        terms = [jurisdiction.name_de, *jurisdiction.aliases]
        for term in sorted(terms, key=lambda value: len(normalize_text(value)), reverse=True):
            needle = normalize_text(term)
            if needle and re.search(rf"(?:^|\s){re.escape(needle)}(?:$|\s)", normalized):
                return jurisdiction
    return None


def grade_prefix_from_query(query: str) -> str | None:
    match = re.search(r"(?i)(?:^|\s)(A|B|W|R|E|P|S)\s*\d{1,2}[a-zü]*(?:$|\s)", query.replace("-", " "))
    return match.group(1).upper() if match else None
