# OpenSenseDocumentation

Deterministischer Generator für MSP-Kundendokumentationen auf Basis von OPNsense-`config.xml`-Dateien.

> **Source of Truth:** [`Umsetzungsplan.md`](./Umsetzungsplan.md)  
> **Operative CI/CD-Zielplattform:** Azure DevOps `BSSE-CloudOps / 10-Automation / 10-Automation-OPNsenseDocumentation`  
> **GitHub:** temporärer Migrations-/Authoring-Mirror bis zum vollständigen Repository-/Policy-Cleanup

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
- Azure-Pipelines-Baseline unter `pipelines/` implementiert und erfolgreich verifiziert
- GitHub Actions bleiben vorerst als Migrations-/Vergleichsartefakte erhalten

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
- bereits redigierte Basic-Auth-URLs werden nicht als Residual Secret fehlklassifiziert
- Azure CI erfolgreich auf Windows PowerShell 5.1 und PowerShell 7 verifiziert

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
- Azure Schema-CI erfolgreich verifiziert

Details: [`docs/Phase-2-Canonical-Infrastructure-Model.md`](./docs/Phase-2-Canonical-Infrastructure-Model.md)

### Phase 3 – Deterministischer Core Parser

- Parser-Komponente **0.1.0** in Python (nur Standardbibliothek zur Laufzeit)
- Sanitization Report mit Status `Clean` und SHA-256-Match ist zwingende Eingangsbedingung
- System, Interfaces, statische IPv4-Netze, VLANs, Aliases, Gateways, statische Routen, IPsec, NAT und Firewall werden deterministisch geparst
- jeder technische Record besitzt Stable ID und Evidence/XPath
- unbekannte Referenzen werden als `unresolvedReferences` erhalten und niemals still verworfen
- aktive/deaktivierte Firewall-/NAT-/Route-Objekte bleiben getrennt
- NAT-associated Firewall Rules werden bidirektional referenziert
- route-based IPsec wird nur bei exaktem `tunnel_remote == gateway.address` mit Gateway/VTI verknüpft
- öffentliche IPsec-Gegenstelle bleibt getrennt von VTI-Adresse
- semantischer Fingerprint-Regressionstest für plattformübergreifend identische Modellinhalte
- Azure Parser-CI erfolgreich auf Ubuntu und Windows verifiziert

Details: [`docs/Phase-3-Core-Parser.md`](./docs/Phase-3-Core-Parser.md)

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

## Core Parser verwenden

```bash
python src/Parser/convert_opnsense_config.py \
  --input generated/config.sanitized.xml \
  --report generated/sanitization-report.json \
  --output generated/infrastructure-model.json
```

Der Parser verweigert die Verarbeitung bei:

- Sanitizer-Status ungleich `Clean`
- vorhandenen `residualFindings`
- SHA-256-Abweichung zwischen Report und sanitisierter XML
- ungültiger XML-Struktur

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

Parser-/Schema-Tests:

```bash
python -m pip install -r requirements-ci.txt
python -m unittest discover -s tests/Parser -v
python tools/validate_schema.py
```

Die Azure-PowerShell-CI testet auf Windows gegen:

- Windows PowerShell 5.1
- PowerShell 7

Die Azure-Parser-CI testet denselben semantischen Modell-Fingerprint auf:

- Ubuntu / Python 3.12
- Windows / Python 3.12

Der Canonical-Model-Schema-Job läuft auf Ubuntu mit Python 3.13. Alle fünf Azure-Pipelines-Jobs der Phase-1–3-Baseline wurden erfolgreich ausgeführt.

## Versionierung

Das Projekt verwendet Semantic Versioning (`MAJOR.MINOR.PATCH`).

- Repository-/Generatorversion: [`VERSION`](./VERSION)
- Core Parser: aktuell `0.1.0`
- Sanitizer: aktuell `1.1.0`
- Canonical Infrastructure Model Schema: aktuell `1.0.0`
- Stable-ID-Strategie: aktuell `1.0.0`
- Canonicalization-Strategie: aktuell `1.0.0`
- Komponenten wie Ruleset und Templates erhalten eigene Versionen.
- Jeder spätere Dokumentbuild erhält ein Build-Manifest mit allen verwendeten Komponentenständen.

## Nächster Schritt

**Phase 4 – DHCP / Asset Inventory**

Als Nächstes werden Kea und Legacy-DHCP getrennt geparst, die authoritative DHCP-Implementierung deterministisch bestimmt, Reservations übernommen und das Asset-Inventar mit versioniertem OUI-Enrichment aufgebaut. Der Regressionstest `Kea + Legacy -> Kea authoritative` ist dabei zwingend.
