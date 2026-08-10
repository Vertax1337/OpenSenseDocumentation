# Phase 2 – Canonical Infrastructure Model

## Status

Implementierter Baseline-Vertrag: Schema-Version `1.0.0`.

Das Canonical Infrastructure Model ist die einzige technische Vertrags- und Datenbasis zwischen Parsern, Rule/Correlation Engine, Validator, Dokument-Renderer, Diagramm-Renderer und einer optionalen nachgelagerten LLM-Sprachschicht. Sobald der Parser aktiv ist, dürfen Renderer `config.sanitized.xml` nicht direkt lesen.

## JSON-Schema-Dialekt

Der Root-Contract verwendet JSON Schema Draft 2020-12:

```json
"$schema": "https://json-schema.org/draft/2020-12/schema"
```

Schema-ID:

```text
urn:opensense-documentation:schema:infrastructure-model:1.0.0
```

Zur Wartbarkeit ist das Schema modularisiert:

```text
schemas/
├── infrastructure-model.schema.json
├── common.schema.json
├── network.schema.json
├── dhcp-assets.schema.json
└── operations.schema.json
```

Alle Module verwenden versionierte absolute URN-Referenzen. `infrastructure-model.schema.json` bleibt der öffentliche Validierungseinstieg.

## Reproduzierbarkeits-Metadaten

`producer` enthält zwingend:

- Parser-Version
- Ruleset-Version
- Schema-Version
- Stable-ID-Strategie-Version
- Canonicalization-Version

Das Canonical Infrastructure Model besitzt absichtlich **keinen Build-Zeitstempel**. Ein Uhrzeitwert würde bei identischem technischen Input byte-identische Ergebnisse verhindern. Build-Zeit gehört später in `build-manifest.json`, nicht in das technische Wahrheitsmodell.

Empfohlene Identity-Tuple für `modelId`:

```text
sanitizedSha256
schemaVersion
parserVersion
rulesetVersion
idStrategyVersion
canonicalizationVersion
```

Damit erzeugen identischer Input und identische Komponentenstände dieselbe Model-ID.

## Root-Contract

Jedes Modell enthält alle Top-Level-Collections – auch wenn sie leer sind:

- `schemaVersion`
- `modelId`
- `producer`
- `source`
- `system`
- `interfaces`
- `networks`
- `vlans`
- `dhcp`
- `assets`
- `dns`
- `aliases`
- `gateways`
- `routes`
- `vpn`
- `nat`
- `firewallRules`
- `services`
- `monitoring`
- `cronJobs`
- `certificates`
- `businessFlows`
- `findings`
- `unresolvedReferences`

Unbekannte Top-Level-Felder werden abgelehnt.

## Klassifikationsvertrag

### CONFIRMED

Direkt aus der sanitisieren OPNsense-Konfiguration belegt. Mindestens ein Evidence-Eintrag ist Pflicht. Technische Werte dürfen nicht über die Quelle hinaus ergänzt werden.

### DERIVED

Deterministisch aus bestätigten/abgeleiteten Inputs und einer versionierten Regel oder Datenbasis berechnet. Beispiele: Interface-IP + Prefix → Netzwerk-CIDR, DHCP-Reservation → Asset, MAC-OUI → Hersteller.

Pflichtfelder zusätzlich:

- `derivation.ruleId`
- `derivation.basis`
- `derivation.inputRefs`

### INFERRED

Deterministische, aber interpretative Einordnung aus expliziten Eingangsdaten. Beispiel: Hostname enthält `TASKalfa3554ci` → Gerätetyp `Printer`, Modell `TASKalfa 3554ci`. Diese Werte dürfen niemals als CONFIRMED ausgegeben werden.

### FINDING

Ergebnis einer Rule Engine und kein Source-Fact. Findings besitzen Severity `P1`, `P2` oder `P3`, eine stabile Rule-ID, betroffene Objekt-Referenzen, Evidence und Lifecycle-Status.

## Evidence / Provenance

Evidence ist für technische Records verpflichtend und enthält:

- `sourceType`
- `sourceId`
- exakten Source-Pfad
- optional SHA-256 der Quelle
- optional Notiz

Für OPNsense wird ein deterministischer XPath-artiger Pfad verwendet.

```json
{
  "sourceType": "opnsense-config",
  "sourceId": "config.sanitized.xml",
  "path": "/opnsense/staticroutes/route[3]",
  "sourceSha256": "..."
}
```

## Stable IDs

Alle technischen Objekte besitzen namespaced Stable IDs.

Priorität:

1. stabiler OPNsense-UUID/Key/Interface-Name
2. deterministischer Hash einer dokumentierten Identity-Tuple

Beispiele:

```text
interface:lan
route:bd8be173-bad5-47c0-9702-386ef25f8114
asset:sha256:18bc214bf0e4952c622643f5
```

`src/Model/OpenSenseDocumentation.Model.psm1` implementiert diesen Vertrag. Hash-IDs verwenden geordnete, längenpräfixierte Werte, UTF-8, SHA-256 und die ersten 24 Hex-Zeichen. Dadurch können unterschiedliche Identity-Tuples nicht durch einfache Separator-Ambiguität kollidieren.

## Referenzen

Beziehungen werden ausschließlich als Objekt-Referenzen gespeichert:

```json
{
  "id": "gateway:vpngw",
  "type": "gateway"
}
```

JSON Schema validiert die Form. Die spätere deterministische Validierungsphase prüft zusätzlich, ob das referenzierte Ziel tatsächlich existiert und den erwarteten Typ besitzt. Nicht auflösbare Referenzen werden niemals still verworfen, sondern in `unresolvedReferences` erfasst.

## Asset-Enrichment

Vendor, Device Type und Model besitzen jeweils eine eigene Attribution mit:

- `CONFIRMED`
- `DERIVED`
- `INFERRED`
- `UNKNOWN`

`UNKNOWN` verwendet `value: null`. Dadurch kann eine DHCP-Reservation als bestätigte Asset-Quelle bestehen bleiben, während Hersteller oder Gerätetyp explizit unbekannt sind.

## Deterministische Reihenfolge

Standard:

- normale Objekt-Collections: `id` ordinal aufsteigend
- Evidence: `sourceType`, `sourceId`, `path`
- Service-Attribute: `key`
- Addresses: Family, Address, Prefix
- Findings: Severity, Category, ID
- Unresolved References: ID

Ausnahmen:

- Firewall-Regeln behalten die konfigurierte Reihenfolge über `order`
- Business-Flow-Steps verwenden explizites numerisches `order`
- NAT-Reihenfolge wird beibehalten, wenn sie semantisch relevant ist

Renderer dürfen keine eigene Sortierlogik erfinden.

## Canonical JSON Serialization

Für `infrastructure-model.json` gilt:

- UTF-8
- kein BOM
- LF
- Objekt-Keys ordinal sortiert
- Arrays bereits nach obigem Contract sortiert
- genau ein abschließender Zeilenumbruch

`tools/canonicalize_json.py` stellt die reproduzierbare Objekt-Key-Serialisierung bereit und bewahrt Array-Reihenfolgen.

## Kein stiller Schema-Drift

Wenn ein Parser ein neues Feld benötigt:

1. Schema ändern
2. Fixtures anpassen/ergänzen
3. Schema-Version passend erhöhen
4. Dokumentation aktualisieren
5. erst danach das Feld emittieren

Damit können Parseränderungen nicht unbemerkt die Kundendokumentation verändern.

## Versionierung

Initialer Contract: `1.0.0`.

- PATCH: Korrektur ohne semantische Shape-Änderung
- MINOR: rückwärtskompatible optionale Fähigkeit
- MAJOR: Breaking Change an Properties, Typen oder Required-Semantik

Root-`schemaVersion`, Producer-`schemaVersion`, Schema-`$id` und Dokumentation müssen übereinstimmen.

## Validierung

Lokal:

```bash
python -m pip install -r requirements-ci.txt
python tools/validate_schema.py
```

CI prüft:

1. alle Schema-Module gegen Draft 2020-12
2. jede `*.valid.json` Fixture muss bestehen
3. jede `*.invalid.json` Fixture muss fehlschlagen
4. Canonical-JSON-Serialisierung ist reproduzierbar

Aktuelle negative Regression-Fixtures schützen gegen:

- DERIVED Record ohne `derivation`
- unbekannte zusätzliche Root-Properties
- ungültige Finding-Severity

## Sicherheit

Alle Beispiele sind synthetisch. Reale Kunden-`config.xml`, sanitisierte Kundenkonfigurationen, interne IPs, Hostnamen, Domains, MAC-Adressen oder generierte Kundendokumentationen dürfen nicht in dieses öffentliche Repository committed werden.
