# TVData Static API

Die TVData Static API macht die im Repository gepflegten Tarif- und Besoldungsdaten ohne eigenen Applikationsserver nachnutzbar. GitHub Actions transformiert die CSV-Quelldaten bei jeder Änderung in versionierte JSON- und CSV-Ressourcen und veröffentlicht sie über GitHub Pages.

## Basis-URL

Nach Aktivierung von **Settings → Pages → Source: GitHub Actions**:

```text
https://stfnrpplngr.github.io/TVData/
```

Die stabile Hauptversion liegt unter:

```text
https://stfnrpplngr.github.io/TVData/v1/
```

## Ressourcen

| Ressource | Inhalt |
|---|---|
| `v1/index.json` | Manifest, Datenstand, Zählwerte und Ressourcenverweise |
| `v1/tables/index.json` | Katalog aller Tarif- und Besoldungstabellen |
| `v1/tables/{id}.json` | Tabelle mit Gruppen, Stufen und Stufenlaufzeiten |
| `v1/allowances/index.json` | Katalog aller Zulagen |
| `v1/allowances/{id}.json` | Zulage mit Optionen und Werten |
| `v1/pensions/index.json` | Katalog der Zusatzversorgungssysteme |
| `v1/pensions/{id}.json` | Metadaten eines Zusatzversorgungssystems |
| `v1/values.json` | Flache Liste sämtlicher Entgelt- und Besoldungswerte |
| `v1/values.csv` | Normalisierte Werte für BI, Tabellenkalkulation und DataFrames |
| `v1/all.json` | Gesamter Datenbestand für Offline- und Batch-Verarbeitung |
| `v1/openapi.json` | OpenAPI-3.1-Beschreibung |
| `v1/schemas/` | JSON-Schemata der zentralen Ressourcentypen |
| `client/tvdata-client.js` | Browserfähiger JavaScript-Client ohne Abhängigkeiten |

## Schnellstart

### JavaScript mit `fetch`

```javascript
const table = await fetch(
  "https://stfnrpplngr.github.io/TVData/v1/tables/tv-l.json"
).then((response) => response.json());

const grade = table.grades.find((entry) => entry.grade === "14");
console.log(grade.steps["5"]);
```

### JavaScript-Client

```javascript
import { TVDataClient } from
  "https://stfnrpplngr.github.io/TVData/client/tvdata-client.js";

const api = new TVDataClient({
  baseUrl: "https://stfnrpplngr.github.io/TVData/v1",
});

const tables = await api.listTables({
  kind: "civil_service",
  query: "Sachsen-Anhalt",
});

const salary = await api.getSalary("tv-l", "14", "5");
```

### Python

```python
from urllib.request import urlopen
import json

url = "https://stfnrpplngr.github.io/TVData/v1/tables/tv-l.json"
with urlopen(url) as response:
    table = json.load(response)

row = next(item for item in table["grades"] if item["grade"] == "14")
print(row["steps"]["5"])
```

## Datenmodell

Eine Tabellenressource enthält insbesondere:

- `kind`: `collective_agreement` oder `civil_service`
- `valid_from`: Gültigkeitsbeginn aus den Quelldaten
- `pay_grade_prefix`: beispielsweise `E`, `A`, `B`, `R` oder `W`
- `grades[].steps`: monatliche Bruttowerte in Euro
- `grades[].advancement_years`: reguläre Stufenlaufzeiten
- `meta.allowances`: verknüpfte Zulagen
- `meta.prv`: verknüpfte Zusatzversorgungssysteme
- `source`: Repository, Commit und Quelldateien
- `content_sha256`: Prüfsumme des normalisierten Datensatzes

Sonderstufen und historisch gewachsene Spaltenbezeichnungen bleiben unverändert erhalten. Der Parser unterstützt sowohl `name,value` als auch `key,value` in Metadateien und durchsucht die Datenverzeichnisse rekursiv.

## Versionierung

Die URL enthält die Major-Version (`v1`). Innerhalb einer Major-Version bleiben Feldbedeutungen und Ressourcentypen kompatibel. Neue optionale Felder sind zulässig; inkompatible Änderungen erfordern eine neue Major-Version.

Die CSV-Dateien bleiben führend. Die API-Artefakte werden reproduzierbar durch `scripts/build_api.py` erzeugt und nicht manuell gepflegt.

## Lokaler Build

```bash
python -m unittest discover -s scripts/tests -p "test_build_api.py" -v
python scripts/build_api.py --root . --output _site
python -m http.server 8000 --directory _site
```

Danach ist das API-Portal unter `http://localhost:8000` erreichbar.

## Betriebsmodell und Grenzen

Die Schnittstelle ist eine statische Read-only-API. Dadurch entstehen keine dauerhaften Serverkosten, die Angriffsfläche bleibt klein und jede Version ist auf einen Quell-Commit zurückführbar. Serverseitige Filter, Schreibzugriffe und komplexe Berechnungsendpunkte sind bewusst nicht Bestandteil von `v1`; für analytische Verarbeitung stehen `values.json`, `values.csv` und `all.json` bereit.

Die API liefert strukturierte Tarif- und Besoldungsdaten, aber keine rechtsverbindliche Auskunft. Nachnutzende Anwendungen sollten Gültigkeitsdatum, Quelle und Quell-Commit sichtbar machen und fachliche Plausibilitätsprüfungen vorsehen.
