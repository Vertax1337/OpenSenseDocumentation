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

## Sicherheit

Eine originale OPNsense-`config.xml` enthält sensible Konfigurationsdaten und darf nicht in dieses öffentliche Repository committed werden.

Auch eine sanitisierte Datei ist **nicht anonymisiert**. Interne IP-Adressen, Domains, Hostnamen, MAC-Adressen, Netzwerkbezeichnungen und Topologieinformationen bleiben für die Dokumentation absichtlich erhalten.

Testfixtures in diesem Repository müssen ausschließlich synthetische Daten enthalten.

## Tests

Lokal mit Pester 5:

```powershell
Invoke-Pester -Path ./tests -CI
```

Die CI testet auf Windows gegen:

- Windows PowerShell 5.1
- PowerShell 7

## Versionierung

Das Projekt verwendet Semantic Versioning (`MAJOR.MINOR.PATCH`).

- Repository-/Generatorversion: [`VERSION`](./VERSION)
- Komponenten wie Sanitizer, Schema, Ruleset und Templates besitzen zusätzlich eigene Versionen.
- Jeder spätere Dokumentbuild erhält ein Build-Manifest mit allen verwendeten Komponentenständen.

## Nächster Schritt

Phase 2: Versioniertes `infrastructure-model.schema.json` als Canonical Infrastructure Model definieren.
