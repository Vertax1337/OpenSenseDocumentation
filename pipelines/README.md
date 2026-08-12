# Azure Pipelines

Dieser Ordner enthält die Azure-DevOps-CI-Baseline für `OPNsenseDocumentation`.

## Einstiegspunkt

Die Pipeline wird in Azure DevOps einmalig auf folgende YAML-Datei registriert:

```text
/pipelines/azure-pipelines.yml
```

Azure DevOps:

```text
Pipelines
→ New Pipeline
→ Azure Repos Git
→ OPNsenseDocumentation
→ Existing Azure Pipelines YAML file
→ Branch: main
→ Path: /pipelines/azure-pipelines.yml
```

## Struktur

```text
pipelines/
├── azure-pipelines.yml
└── templates/
    ├── sanitizer-tests.yml
    ├── schema-tests.yml
    └── parser-tests.yml
```

Die Baseline bildet die derzeitigen GitHub-Actions-Prüfungen fachlich ab:

- Sanitizer: Windows PowerShell 5.1 und PowerShell 7
- Canonical Model Schema: Python 3.13, Schema-Fixtures und Canonical-JSON-Reproduzierbarkeit
- Core Parser: Python 3.12 auf Ubuntu und Windows, Regressionstests und Schema-Validierung

## Übergangsphase GitHub → Azure DevOps

Bis die Azure-Pipeline erfolgreich verifiziert wurde, bleiben die bestehenden `.github/workflows/*.yml` erhalten.

Der vorläufige Sync-Prozess lautet:

```powershell
git pull origin main
git push azure main
```

Dabei ist vor dem finalen Cutover GitHub weiterhin die Entwicklungs-Source-of-Truth und Azure Repos die synchronisierte Zielkopie.

Nach erfolgreicher Azure-Pipeline-Verifikation wird Azure DevOps zur operativen Source-of-Truth. Erst danach werden die GitHub-Actions-Workflows entfernt und das GitHub-Repository archiviert/read-only gesetzt.

## Pull Requests

Azure-Repos-PR-Validierung wird später über eine Branch Policy auf `main` konfiguriert:

```text
Repos
→ Branches
→ main
→ Branch policies
→ Build validation
```

Daher ist im YAML-Einstiegspunkt `pr: none` gesetzt.

## Zentrale Pipeline-Templates

Diese Dateien sind bewusst zunächst self-contained, damit die GitHub-Actions-Migration ohne Abhängigkeit von noch nicht verifizierten zentralen Templates getestet werden kann.

Nach erfolgreichem Cutover kann die gemeinsame Infrastruktur schrittweise auf die vom DevOps-Bootstrap bereitgestellten zentralen `PipelineTemplates` umgestellt werden. Die fachlichen Tests bleiben in diesem Repository.
