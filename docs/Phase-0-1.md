# Phase 0 / Phase 1 – Implementierungsstand

Diese Datei dokumentiert den initialen Code-Stand ergänzend zum verbindlichen `Umsetzungsplan.md`.

## Phase 0

Umgesetzt:

- Repository-Grundstruktur
- `README.md`
- SemVer-Strategie (`VERSION` = `0.1.0`)
- Pester-Teststruktur
- GitHub Actions für Windows PowerShell 5.1 und PowerShell 7
- `.gitignore` gegen versehentliches Committen realer OPNsense-Konfigurationen und generierter Kundendaten

## Phase 1

Sanitizer-Version: `1.1.0`

Enthält die bisherigen Regression-Fixes:

1. Original-XML wird nie überschrieben.
2. Relative Output-/Reportpfade werden über den PowerShell FileSystem Provider aufgelöst.
3. Verzeichnisse werden mit `New-Item -ItemType Directory -Force` angelegt.
4. Ein bestehender Dateipfad an Stelle eines erwarteten Verzeichnisses führt zu einem Fehler.
5. PowerShell-`List[object]`-Regression verwendet `.ToArray()` statt `@($genericList)`.
6. Business-Edition-`system/firmware/subscription` wird redigiert.
7. `created`, `updated`, `revision` werden entfernt.
8. Embedded URL-/Argument-Credentials werden redigiert.
9. Residual Scan verhindert ein unkritisches `Clean`, wenn bekannte Secret-Muster verbleiben.
10. Report enthält keine lokalen Vollpfade.
11. Redaction-/Residual-Listen werden vor Reportausgabe sortiert.
12. `sanitization-report.schema.json` Version `1.0.0` ist definiert.

## Testfixture-Regel

Alle committed Testfixtures sind synthetisch. Reale Kundenkonfigurationen, reale Secrets oder reale Kundennetzdaten dürfen nicht in dieses öffentliche Repository übernommen werden.
