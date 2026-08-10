# OpenSenseDocumentation

Deterministischer Generator für MSP-Kundendokumentationen auf Basis von OPNsense-`config.xml`-Dateien.

> **Source of Truth:** [`Umsetzungsplan.md`](./Umsetzungsplan.md)

## Grundprinzip

Technische Fakten werden nicht durch ein LLM bestimmt. Der produktive Zielpfad ist:

```text
config.xml
  -> Sanitizer
  -> config.sanitized.xml
  -> deterministischer Parser
  -> infrastructure-model.json
  -> Rule/Correlation Engine
  -> Validator
  -> Diagramm-/Dokument-Renderer
  -> DOCX/PDF
```

KI ist später nur optional für sprachliche Glättung zulässig und darf keine technischen Fakten hinzufügen.

## Aktueller Implementierungsstand

### Phase 0 – Repository-Basis

- Repository-Struktur vorbereitet
- SemVer-Versionierung festgelegt
- Pester-Teststruktur angelegt
- GitHub-Actions-Testmatrix für Windows PowerShell 5.1 und PowerShell 7 vorbereitet

### Phase 1 – Sanitizer

- `Sanitize-OPNsenseConfig.ps1` Version **1.1.0**
- Originaldatei wird niemals überschrieben
- bekannte Credential-/Key-Felder werden redigiert
- OPNsense Business-Subscription-Key wird pfadbezogen redigiert
- `created` / `updated` / `revision` Audit-Metadaten werden entfernt
- eingebettete Credentials werden erkannt
- Residual-Secret-Scan vor Status `Clean`
- Report enthält keine lokalen Vollpfade
- relative Output-/Reportpfade werden PowerShell-nativ aufgelöst
- Regression gegen den PowerShell-`List[object]`/`@(...)`-Engine-Bug

### Phase 2 – Canonical Infrastructure Model

- JSON Schema **1.0.0**
- JSON Schema Draft 2020-12
- strikter Root-Contract ohne stille Zusatzfelder
- `CONFIRMED / DERIVED / INFERRED / FINDING`
- Evidence / Provenance als Pflichtbestandteil technischer Records
- stabile namespaced IDs plus SHA-256-Fallback
- versionierte ID- und Canonicalization-Strategie
- Referenzobjekte für Beziehungen zwischen technischen Records
- `unresolvedReferences` statt still verworfener Referenzen
- Asset-Enrichment mit eigener Confidence je Vendor / Device Type / Model
- reproduzierbare JSON-Serialisierung
- positive und negative Schema-Fixtures
- eigene Schema-CI

Details: [`docs/Phase-2-Canonical-Infrastructure-Model.md`](./docs/Phase-2-Canonical-Infrastructure-Model.md)

## Verwendung des Sanitizers

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File ".\src\Sanitizer\Sanitize-OPNsenseConfig.ps1" `
  -InputPath ".\config.xml" `
  -OutputPath ".\generated\config.sanitized.xml" `
  -ReportPath ".\generated\sanitization-report.json"
```

PowerShell 7:

```powershell
pwsh -NoProfile `
  -File "./src/Sanitizer/Sanitize-OPNsenseConfig.ps1" `
  -InputPath "./config.xml" `
  -OutputPath "./generated/config.sanitized.xml" `
  -ReportPath "./generated/sanitization-report.json"
```

## Canonical Model Schema validieren

```bash
python -m pip install -r requirements-ci.txt
python tools/validate_schema.py
```

Deterministische JSON-Serialisierung:

```bash
python tools/canonicalize_json.py input.json output.json
```

## Sicherheit

Eine originale OPNsense-`config.xml` enthält sensible Konfigurationsdaten und darf nicht in dieses öffentliche Repository committed werden.

Auch eine sanitisierte Datei ist **nicht anonymisiert**. Interne IP-Adressen, Domains, Hostnamen, MAC-Adressen, Netzwerkbezeichnungen und Topologieinformationen bleiben für die Dokumentation absichtlich erhalten.

Testfixtures in diesem Repository müssen ausschließlich synthetische Daten enthalten.

## Tests

Lokal mit Pester 5:

```powershell
Invoke-Pester -Path ./tests -CI
```

Die PowerShell-CI testet auf Windows gegen:

- Windows PowerShell 5.1
- PowerShell 7

Die Schema-CI validiert zusätzlich:

- JSON-Schema-Metaschema
- gültige Modell-Fixtures
- absichtlich ungültige Regression-Fixtures
- reproduzierbare Canonical-JSON-Ausgabe

## Versionierung

Das Projekt verwendet Semantic Versioning (`MAJOR.MINOR.PATCH`).

- Repository-/Generatorversion: [`VERSION`](./VERSION)
- Sanitizer: aktuell `1.1.0`
- Canonical Infrastructure Model Schema: aktuell `1.0.0`
- Stable-ID-Strategie: aktuell `1.0.0`
- Canonicalization-Strategie: aktuell `1.0.0`
- Komponenten wie Ruleset und Templates erhalten eigene Versionen.
- Jeder spätere Dokumentbuild erhält ein Build-Manifest mit allen verwendeten Komponentenständen.

## Nächster Schritt

**Phase 3 – Core Parser**

Als Nächstes werden System, Interfaces, VLANs, Gateways, statische Routen, Aliases, Firewall, NAT und IPsec deterministisch aus `config.sanitized.xml` in das Canonical Infrastructure Model überführt. Jeder Record muss dabei eine stabile ID und Evidence besitzen.
