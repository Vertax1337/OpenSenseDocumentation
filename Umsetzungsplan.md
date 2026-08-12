# Umsetzungsplan – OpenSenseDocumentation

> **Status:** Verbindliche fachliche Source of Truth für die Entwicklung  
> **Operatives Repository:** Azure DevOps `BSSE-CloudOps / 10-Automation / 10-Automation-OPNsenseDocumentation`  
> **GitHub-Migrationsmirror:** `Vertax1337/OpenSenseDocumentation`  
> **Projektstand:** `0.3.0`  
> **Aktuelle fachliche Phase:** Phase 4 – DHCP / Asset Inventory  
> **CI/CD-Zielplattform:** Azure DevOps über die bestehende DevOps-Bootstrap-Struktur  
> **CI-Status:** Phase 1–3 auf Azure Pipelines erfolgreich verifiziert (Windows PowerShell 5.1, PowerShell 7, Schema, Parser Ubuntu/Windows)  
> **Grundsatz:** Technische Fakten werden nicht durch ein LLM erfunden oder frei interpretiert. Parser, Regeln, Korrelation, Validierung, Diagramme und Dokumentstruktur müssen deterministisch sein.

---

# 1. Zielbild

Aus einer OPNsense-`config.xml` soll automatisiert eine belastbare MSP-Betriebsdokumentation entstehen, mit der ein neuer Mitarbeiter ohne Vorwissen einen Kunden technisch einordnen, typische Störungen analysieren und Sonderkonfigurationen nachvollziehen kann.

Der Zielprozess lautet:

```text
OPNsense config.xml
        │
        ▼
Sanitize-OPNsenseConfig.ps1
        │
        ├─ Secrets redigieren
        ├─ Audit-Metadaten entfernen
        └─ Residual Secret Check
        │
        ▼
config.sanitized.xml
        │
        ▼
Deterministischer Parser
        │
        ▼
infrastructure-model.json
        │
        ├───────────────┬────────────────┐
        ▼               ▼                ▼
      Facts          Derived         Inferences
        │               │                │
        └───────────────┴────────────────┘
                        │
                        ▼
                Rule / Findings Engine
                        │
                        ▼
              Correlation / Flow Engine
                        │
                        ▼
                 Business Flows
                        │
          ┌─────────────┴─────────────┐
          ▼                           ▼
  Document Renderer            Diagram Renderer
          │                           │
          ▼                           ▼
        DOCX                         SVG
          │                           │
          └─────────────┬─────────────┘
                        ▼
                       PDF
```

Optional darf eine KI nachgelagert Formulierungen verbessern oder Management-Zusammenfassungen erzeugen. Sie darf jedoch keine technischen Fakten hinzufügen, verändern, priorisieren oder technische Beziehungen frei erfinden.

---

# 2. Nicht verhandelbare Architekturregeln

## 2.1 Eine technische Wahrheit

`infrastructure-model.json` ist nach dem Parsing die einzige technische Datenquelle für:

- Tabellen
- technische Texte
- Quick Reference
- Findings
- Business Flows
- Diagramme
- spätere Infrastructure Diffs
- DOCX/PDF-Rendering

Renderer dürfen `config.sanitized.xml` nicht direkt erneut interpretieren.

## 2.2 Unknown wird erhalten, nicht erraten

Wenn eine Beziehung oder ein Wert nicht eindeutig ableitbar ist:

- kein wahrscheinlicher Wert einsetzen
- keine Namensähnlichkeit als technische Zuordnung verwenden
- keine physische Topologie erfinden
- stattdessen `UNKNOWN`, `unresolvedReferences` oder einen späteren Review-/Finding-Zustand verwenden

## 2.3 Active und Disabled strikt trennen

Deaktivierte Regeln oder Dienste bleiben dokumentierbar, dürfen aber niemals als aktiver Flow oder aktiver Betriebszustand dargestellt werden.

## 2.4 Gleicher Input muss gleiches Ergebnis erzeugen

Für den semantischen Build gilt:

```text
gleiche sanitisierte Config
+ gleicher Sanitizer
+ gleicher Parser
+ gleiches Schema
+ gleiches Ruleset
+ gleiche Enrichment-Datenbasis
+ gleiches Template
+ gleiche Renderer-Version
=
gleiche technische Dokumentation
```

---

# 3. Sanitizing und Sicherheitsgrenze

Die originale `config.xml` ist vertraulich und wird niemals direkt als Dokumentationsinput an eine externe KI übergeben.

Die sanitisierte XML ist **nicht anonymisiert**. Interne IP-Adressen, Netze, Hostnamen, Domains, MAC-Adressen, Aliases und technische Beschreibungen bleiben absichtlich erhalten, weil sie für die Dokumentation benötigt werden.

## 3.1 Sanitizer muss mindestens behandeln

- Passwörter und Passwort-Hashes
- OTP-/TOTP-/HOTP-Seeds
- API-Keys und Tokens
- Pre-Shared Keys
- Private Keys
- SNMP Communities
- LDAP-/RADIUS-/SMTP-Credentials
- WireGuard-/OpenVPN-/IPsec-Secrets
- Business-Edition Subscription-/Activation-Key
- eingebettete Credentials in URLs oder Argumenten
- bekannte Credential-Feldnamen von Plugins

## 3.2 Zusätzlich entfernen

- `created`
- `updated`
- `revision`

## 3.3 Bedeutung von `Clean`

`Clean` bedeutet:

> Nach der aktuellen Sanitizer-Regelbasis wurden keine bekannten Residual-Secrets gefunden.

`Clean` bedeutet nicht:

> Die Datei enthält keine internen oder vertraulichen Infrastrukturinformationen.

## 3.4 Verbindliche Regression-Fixes

Bereits aufgetreten und dauerhaft zu schützen:

1. Relative Output-/Report-Pfade müssen funktionieren.
2. Verzeichnisse werden PowerShell-nativ mit `New-Item -ItemType Directory -Force` angelegt.
3. Ein erwartetes Verzeichnis, das als Datei existiert, muss zum Fehler führen.
4. PowerShell-5.1-Generic-List-Regression verwendet `.ToArray()` statt `@($genericList)`.
5. `system/firmware/subscription` wird pfadbezogen redigiert.
6. Audit-Metadaten `created`, `updated`, `revision` werden entfernt.
7. Embedded Credentials werden redigiert.
8. Residual Scan entscheidet über `Clean`.
9. Reports enthalten keine lokalen Vollpfade.
10. Original-XML wird niemals überschrieben.
11. Bereits redigierte Basic-Auth-URLs dürfen vom Residual Scan nicht erneut als Secret klassifiziert werden.
12. Pester-Tests verwenden keine automatische PowerShell-Variable `$input` als Testpfadvariable.
13. CI pinnt Pester explizit auf die Pester-5-Linie, damit ein Major-Upgrade die PS5.1/PS7-Testsemantik nicht unkontrolliert verändert.

---

# 4. Canonical Infrastructure Model

## 4.1 Root-Struktur

Das versionierte Modell enthält mindestens:

```json
{
  "schemaVersion": "1.0.0",
  "modelId": "...",
  "producer": {},
  "source": {},
  "system": {},
  "interfaces": [],
  "networks": [],
  "vlans": [],
  "dhcp": {
    "services": [],
    "scopes": [],
    "reservations": []
  },
  "assets": [],
  "dns": {},
  "aliases": [],
  "gateways": [],
  "routes": [],
  "vpn": [],
  "nat": [],
  "firewallRules": [],
  "services": [],
  "monitoring": [],
  "cronJobs": [],
  "certificates": [],
  "businessFlows": [],
  "findings": [],
  "unresolvedReferences": []
}
```

## 4.2 Klassifikationen

### CONFIRMED

Direkt aus der sanitisieren OPNsense-Konfiguration belegt.

### DERIVED

Deterministisch aus bestätigten/abgeleiteten Eingaben und einer versionierten Regel oder Datenbasis berechnet.

Beispiele:

- Interface-IP + Prefix → Network CIDR
- MAC OUI → Hersteller

### INFERRED

Deterministische, aber interpretative Einordnung aus expliziten Eingangsdaten.

Beispiel:

- Hostname enthält `TASKalfa3554ci` → wahrscheinlich `Printer`, Modell `TASKalfa 3554ci`

### FINDING

Ergebnis einer Rule Engine. Findings besitzen stabile Rule-ID, Severity, betroffene Referenzen und Evidence.

## 4.3 Evidence / Provenance

Jeder relevante technische Record muss auf seine Quelle zurückführbar sein.

Beispiel:

```json
{
  "sourceType": "opnsense-config",
  "sourceId": "config.sanitized.xml",
  "path": "/opnsense/staticroutes/route[3]",
  "sourceSha256": "..."
}
```

## 4.4 Stable IDs

Priorität:

1. stabile OPNsense-UUID / natürlicher Schlüssel / Interface-Name
2. deterministischer SHA-256-Fallback aus dokumentierter Identity-Tuple

## 4.5 Kein stiller Schema-Drift

Wenn ein Parser ein neues Modellfeld benötigt:

1. Schema anpassen
2. Fixtures ergänzen
3. Versionierung prüfen
4. Dokumentation anpassen
5. erst danach den Parser ändern

---

# 5. Core-Parser-Regeln

## 5.1 Harte Eingangsbedingungen

Der Parser verarbeitet eine sanitisierte Datei nur, wenn:

```text
sanitization-report.status == Clean
residualFindings == 0
report.output.sha256 == tatsächliche XML-SHA256
XML Root == <opnsense>
```

Andernfalls: Build-Abbruch.

## 5.2 Interfaces

- WAN DHCP/DHCP6 speichert nur den konfigurierten dynamischen Zustand.
- Eine aktuelle WAN-IP wird niemals erfunden.
- Statische Interface-IP + Prefix dürfen deterministisch zu einem Netzwerk-CIDR abgeleitet werden.
- Interface ohne bestätigte L3-Adresse ist kein bestätigtes L3-Netz.

## 5.3 VLAN

- Zuordnung ausschließlich über explizite Device-/Parent-Information.
- Unklare Referenz → `unresolvedReferences`.

## 5.4 Gateway / Static Routes

- Routen referenzieren Gateways über Stable IDs.
- Unbekanntes Gateway wird nicht geraten.

## 5.5 Route-based IPsec

Öffentliche Phase-1-Gegenstelle, lokale/remote VTI-Adresse, Tunnel-Interface und Gateway bleiben getrennte technische Fakten.

Eine VTI-/Gateway-Verknüpfung erfolgt nur bei eindeutiger Übereinstimmung, z. B.:

```text
phase2.tunnel_remote == gateway.address
```

## 5.6 NAT / Firewall

- Disabled State erhalten.
- Firewall-Reihenfolge erhalten.
- NAT/Firewall-Association nur über explizite IDs/Referenzen.
- Business-Flow-Korrelation erfolgt erst in Phase 7.

---

# 6. DHCP – verbindliche Fachregeln für Phase 4

Der DHCP-Parser liest Konfiguration. Die Entscheidung, welche Implementierung authoritative ist, erfolgt separat über die Service-Resolution.

## 6.1 Kea und Legacy werden beide erhalten

Nicht:

```text
Kea gefunden → Legacy löschen
```

sondern:

```text
Kea Facts
+
Legacy Facts
      │
      ▼
Authoritative Service Resolution
```

## 6.2 Authoritative Resolution erfolgt pro Interface

Beispiel:

```text
Kea DHCPv4 enabled
AND
LAN ist Kea zugewiesen
→ Kea authoritative für LAN/IPv4
```

Eine vorhandene Legacy-LAN-Konfiguration bleibt erhalten, wird aber als `legacy=true`, `authoritative=false` dokumentiert.

## 6.3 Kritische Regression

Der bereits aufgetretene Fehler darf niemals zurückkehren:

```text
Legacy Pool: 192.168.1.10 - 192.168.1.245
Kea Pool:    192.168.1.50 - 192.168.1.199
Kea enabled auf LAN

EXPECTED:
Authoritative Pool = Kea .50 - .199
```

## 6.4 DHCP Scope

Pro Scope dokumentieren:

- Service
- Interface
- Subnet
- Pool(s)
- Gateway
- DNS
- Domain Name
- Search Domains
- NTP
- Lease Time
- Evidence

## 6.5 Reservations

Reservations sind zunächst ausschließlich Source-Facts:

- IP
- MAC
- Hostname
- Description
- Service
- Scope
- Evidence

Der Reservation-Parser darf aus Hostnamen noch keinen Gerätetyp ableiten.

---

# 7. Asset Inventory und Enrichment

## 7.1 Asset Builder

Primäre Asset-Identität:

```text
MAC vorhanden
→ normalisierte MAC als bevorzugte Identität

keine MAC
→ deterministische Reservation-/Scope-/IP-Identität
```

## 7.2 OUI Enrichment

Keine Live-API während eines normalen Builds.

Stattdessen versionierte lokale Datenbasis:

```text
data/oui/
├── oui-YYYY-MM.csv
└── manifest.json
```

Der Hersteller ist `DERIVED`, nicht `CONFIRMED`.

Für lokal administrierte/randomisierte oder nicht sinnvoll auflösbare MACs wird kein Hersteller geraten.

## 7.3 Device-Type-/Model-Inference

Ausschließlich versionierte, deterministische Regeln.

Beispiel:

```text
Hostname: Zentrale-TASKalfa3554ci
Hostname                 = CONFIRMED
Vendor Kyocera           = DERIVED via OUI
Device Type Printer      = INFERRED via Namensregel
Model TASKalfa 3554ci    = INFERRED via Namensregel
```

Wenn die Quelle keine belastbare Einordnung erlaubt, bleibt der Wert `UNKNOWN`.

---

# 8. Validierung

## 8.1 Harte Fehler

Beispiele:

- Residual Secret
- ungültiges Canonical Model
- DHCP Pool außerhalb des Subnetzes
- Pool Start > Pool End
- gleiche Reservation-IP mit unterschiedlichen MACs im gleichen Scope
- nicht eindeutige authoritative DHCP-Resolution
- nicht auflösbare Pflichtreferenz, sofern sie für einen belastbaren Build zwingend erforderlich ist

Harte Fehler führen zu:

```text
BUILD FAILED
```

## 8.2 Review-Zustände

Technisch mögliche, aber prüfenswerte Situationen dürfen das Modell erhalten.

Beispiele:

- gleicher Hostname auf mehreren MACs
- Legacy-Konfiguration parallel zu einer eindeutig aktiven Implementierung
- Reservation außerhalb des dynamischen Pools, aber innerhalb des Subnetzes

## 8.3 Keine Fehlklassifikation

Eine Reservation außerhalb des dynamischen Pools ist nicht automatisch ein Fehler.

---

# 9. DNS / Services / Monitoring – Ziel Phase 5

Auswerten:

- System DNS
- Unbound
- Conditional Forwarding
- DNSBL / SafeSearch
- CrowdSec
- Zenarmor
- Netdata
- Monit
- HAProxy
- Apache
- ACME
- WireGuard / OpenVPN, soweit vorhanden
- Cron Jobs

Installiert und aktiv müssen getrennt bewertet werden.

---

# 10. Certificates – Ziel Phase 6

Öffentliche Zertifikatsdaten programmatisch dekodieren:

- Subject
- SAN
- Issuer
- Not Before
- Not After
- Self-Signed
- Status
- Used-By-Referenzen

Private Keys bleiben redigiert.

---

# 11. Business-Flow Engine – Ziel Phase 7

Ein Techniker soll Sonderkonfigurationen als vollständigen Datenfluss erkennen, nicht nur als isolierte NAT-/Firewall-/Routing-Regeln.

Beispiele aus dem Proof of Concept:

## FLOW-AFROS

- Origin Azure APP
- VPN / ingress IPsec
- Firewall Source `10.43.0.0/24`
- Destination `85.32.49.226`
- Outbound NAT Source `10.43.0.0/16`
- SNAT WAN-IP
- Egress WAN

## FLOW-TAGETIK

Analog mit Ziel `93.51.162.71`.

## FLOW-ALARM

- Internet
- WAN TCP/UDP 54123
- Port Forward
- internes Ziel `192.168.1.201:54123`

## FLOW-DNS

- Conditional Forward
- Zielserver
- Route
- Gateway
- VPN

## FLOW-AZURE-NONAT

- LAN
- Alias `AZURE_NETZ`
- No-NAT
- IPsec Interface
- leerer/unaufgelöster Alias bleibt Review-/Finding-Kandidat

---

# 12. Findings Engine – Ziel Phase 8

## P1

Build oder technische Belastbarkeit gefährdet.

Beispiele:

- Residual Secret
- widersprüchliche aktive Konfiguration
- DHCP authoritative nicht eindeutig
- ungültige Pflichtreferenz

## P2

Betriebsrelevant.

Beispiele:

- Gateway Monitoring deaktiviert
- abgelaufenes verwendetes Zertifikat
- breite WAN-Freigabe
- leerer aktiver Alias
- Firewall-/NAT-Scope-Unterschied

## P3

Dokumentations-/Optimierungspunkt.

Beispiele:

- Legacy-Konfiguration
- unbeschriebene Rules
- nicht zuordenbare Assets
- fehlende Business-Beschreibung

---

# 13. Dokumentstruktur – Ziel Phase 10

Pflichtstruktur:

1. Titelblatt
2. Quick Reference
3. Netzwerkübersicht – Gesamtbild
4. Inhaltsverzeichnis
5. Systemübersicht
6. Netzwerkarchitektur / Interfaces / Netze
7. Infrastruktur- und Asset-Inventar
8. DHCP
9. DNS / Namensauflösung
10. Routing / Gateways / VPN
11. NAT
12. Firewall
13. Sonderkonfigurationen / Business Flows
14. Security- und Filterdienste
15. Monitoring / Alerting
16. Wartung / Cron / Firmware
17. Management / Administration
18. Zertifikate
19. Backup / Restore
20. Findings / offene Punkte
21. Nicht aus OPNsense ableitbar
22. Build-/Quelleninformationen

Verbindliche Layout-Regel:

```text
Heading 1 → pageBreakBefore = true
```

Pflichtseiten dürfen zwischen Dokumentversionen nicht versehentlich verschwinden.

---

# 14. Netzwerkdiagramme – Ziel Phase 9

Generative Bildmodelle dürfen keine technischen Diagramminhalte erzeugen.

Erlaubt:

```text
infrastructure-model.json
        │
        ▼
Deterministic Diagram Renderer
        │
        ├─ SVG
        └─ optional draw.io
```

Pflichtdiagramme:

1. Gesamt-Netzwerkübersicht
2. Routing/VPN-Detail
3. Business-Flow-Diagramm

Darstellungsprinzipien:

- confirmed Beziehungen: eindeutig
- derived/inferred Beziehungen: unterscheidbar
- unbestätigte L3-Zuordnung: nicht als bestätigte Verbindung darstellen
- disabled Flows: nicht als aktiv darstellen
- Diagramme verwenden ausschließlich Model IDs

---

# 15. Monitoring / Administration

Soweit aus der Config ableitbar:

- WebGUI-Protokoll / Bindings
- Auth Backends
- MFA/TOTP vorhanden
- SSH Status
- administrative lokale Accounts ohne Secrets
- Monitoring-Komponenten
- Alerting-Empfänger
- CPU/RAM/Disk Thresholds
- Gateway-/VPN-Monitoring

Nicht aus der Config geraten werden:

- Password Vault Location
- Break-Glass-Prozess
- Remote-Support-Tool
- MSP-Eskalationspfad

Dafür sind später manuelle Metadaten vorgesehen.

---

# 16. Build Manifest

Jeder produktive Dokumentbuild erhält ein Manifest, z. B.:

```json
{
  "source": {
    "file": "config.xml",
    "sha256": "..."
  },
  "sanitizer": "1.1.0",
  "parser": "...",
  "ruleset": "...",
  "schema": "1.0.0",
  "template": "...",
  "diagramTheme": "...",
  "ouiDatabase": "..."
}
```

Build-Zeitstempel gehören in das Manifest, nicht in `infrastructure-model.json`.

---

# 17. Teststrategie

## 17.1 Sanitizer

Synthetische Fixtures für:

- Password
- Hash
- OTP
- API Key
- PSK
- Private Key
- SNMP
- Business Subscription
- Embedded Credentials
- Plugin Credentials

## 17.2 Schema

Positive und negative Fixtures.

Negative Regressionen mindestens für:

- DERIVED ohne Derivation
- unbekannte Root-Property
- ungültige Finding-Severity

## 17.3 Core Parser

Prüfen:

- gleicher Input → gleiches Modell
- Schema-Konformität
- Stable IDs
- WAN DHCP ohne erfundene IP
- VLAN Referenzen
- Gateway / Route
- IPsec / VTI / Gateway
- NAT / Firewall Association
- Disabled State
- Unresolved References
- Sanitizer Status / SHA Mismatch

## 17.4 DHCP / Assets

Fixtures:

```text
legacy-only.xml
kea-only.xml
kea-and-legacy.xml
kea-reservations.xml
duplicate-ip.xml
invalid-pool.xml
reservation-outside-pool.xml
asset-enrichment.xml
```

Kritischer Golden Test:

```text
Kea + Legacy
→ Kea authoritative
→ Legacy retained but non-authoritative
```

## 17.5 Diagram / Dokument

Später prüfen:

- keine Werte außerhalb des Canonical Models
- Pflichtdiagramme vorhanden
- Pflichtkapitel vorhanden
- Quick Reference vorhanden
- jedes Hauptkapitel beginnt auf neuer Seite
- NAT startet auf neuer Seite
- Business Flows vorhanden
- Asset Inventar vorhanden
- Findings vorhanden

---

# 18. Azure DevOps – Verantwortungsgrenze

Verbindlich gilt:

> **Azure DevOps Deployment erfolgt über die bestehende DevOps-Bootstrap-Struktur.**

Der DevOps-Bootstrap ist die übergeordnete Source of Truth für:

- Azure-DevOps-Projekt- und Repository-Struktur
- standardisierte Kunden-/Repository-Trennung
- zentrale Pipeline-Grundstruktur
- wiederverwendbare Pipeline-Templates
- übergeordnete Branch-/Policy-Konfiguration
- Bereitstellung der vorgesehenen Ziel-Repositories

OpenSenseDocumentation ist verantwortlich für:

- fachliche Build-Schritte
- Runtime-/Tool-Anforderungen
- Sanitizer
- Canonical Model
- Parser
- Rule-/Correlation-Engine
- Enrichment
- Validierung
- Renderer
- fachliche Tests / Golden Files
- Build-Abbruchregeln
- Build-Artefaktvertrag

Innerhalb dieses Repositories wird **keine zweite Kunden-/Repository-Bootstrap-Logik** aufgebaut.

Die Azure-Pipelines-Migrationsbaseline unter `/pipelines/azure-pipelines.yml` ist auf dem Azure-Repos-Ziel registriert und für Phase 1–3 erfolgreich verifiziert. Der erfolgreiche Zielplattform-Lauf umfasst:

- Sanitizer / Windows PowerShell 5.1
- Sanitizer / PowerShell 7
- Canonical Model Schema
- Core Parser / Ubuntu / Python 3.12
- Core Parser / Windows / Python 3.12

Die vorhandenen GitHub-Actions-Workflows bleiben vorerst als Migrations-/Vergleichsartefakte erhalten. Sie sind nicht mehr die operative CI/CD-Source-of-Truth und werden erst nach Abschluss der noch offenen Repository-/Policy-Aufräumarbeiten entfernt bzw. archiviert.

---

# 19. Azure-Pipelines-Contract

Die fachliche Pipeline bleibt unabhängig von der CI-Plattform:

```text
config.xml changed
      │
      ▼
Sanitize
      │
      ▼
Secret Scan
      │
      ▼
Parse
      │
      ▼
Normalize
      │
      ▼
Enrich
      │
      ▼
Correlate
      │
      ▼
Validate
      │
      ▼
Tests
      │
      ├─ Render SVG
      ├─ Render DOCX
      ├─ Render PDF
      └─ Build Manifest
```

Die aktuell verifizierte Azure-Pipelines-Baseline ist absichtlich repository-lokal gehalten, um den Plattform-Cutover unabhängig zu validieren. Wiederverwendbare, allgemeine Jobs werden erst anschließend in die zentrale Bootstrap-/Template-Struktur ausgelagert; die fachliche Pipeline darf dadurch nicht verändert werden.

---

# 20. Kunden- und Testdaten

Reale Kundenkonfigurationen oder aus realen Kundendaten erzeugte Modelle gehören nicht in das öffentliche Tooling-Repository.

Committed Testfixtures müssen synthetisch sein.

Kundenspezifische Repositories und deren Trennung werden über den DevOps-Bootstrap bereitgestellt.

---

# 21. Nicht aus OPNsense belastbar ableitbar

Ohne weitere Collector-/Metadatenquellen nicht raten:

- physische Switch-Topologie
- Switchport-Belegung
- Trunk-/Access-Port-Konfiguration
- Patchfelder / Verkabelung
- tatsächliche AP-Uplinks
- aktive Endgeräte ohne Reservation/weitere Quelle
- aktuelle WAN-IP bei DHCP
- Provider / Vertragsdaten
- Standort / Rack / Seriennummer, sofern nicht separat erfasst
- vollständige Azure UDR / NSG / Gateway-Konfiguration

---

# 22. Zukünftige Multi-Source-Erweiterung

Ziel:

```text
OPNsense
UniFi
Windows DNS/DHCP/AD
Azure
Hyper-V / VMware
        │
        ▼
Canonical Infrastructure Model
        │
        ▼
Gemeinsame Kundendokumentation
```

Die Plattform-/Repository-Provisionierung bleibt Aufgabe des DevOps-Bootstraps. Das Canonical Model definiert nur die technische Zusammenführung.

---

# 23. Infrastructure Diff

Spätere Ausbaustufe:

```text
CHANGED

Firewall:
+ WAN 8443 -> 192.168.1.50

DHCP:
+ Reservation Lager-Scanner-02

VPN:
~ Azure APP route geändert

Services:
- CrowdSec disabled
```

Nutzen:

- Change Review
- Kundenhistorie
- unerwartete Änderungen
- Troubleshooting

---

# 24. Rolle der KI

## Erlaubt

- sprachliche Glättung
- Management Summary
- verständliche Erklärung bereits vorhandener Findings
- optional Troubleshooting-Text aus strukturierten Fakten

## Nicht erlaubt

- technische Werte erfinden
- aktive Dienste selbst bestimmen
- DHCP-Priorität frei interpretieren
- Firewall/NAT/VPN-Korrelation frei erfinden
- Diagramminhalte selbst setzen
- unbekannte physische Infrastruktur ergänzen

LLM Contract:

```text
Do not introduce any fact that is not represented in the input model.
```

---

# 25. Repository-Struktur – Ziel

```text
OpenSenseDocumentation/
│
├── src/
│   ├── Sanitizer/
│   ├── Model/
│   ├── Parser/
│   ├── Rules/
│   │   ├── ServiceResolution/
│   │   ├── FlowCorrelation/
│   │   ├── Findings/
│   │   └── Validation/
│   ├── Enrichment/
│   │   ├── OUI/
│   │   └── Assets/
│   ├── Renderer/
│   │   ├── Document/
│   │   └── Diagram/
│   └── Build/
│
├── schemas/
├── data/
│   └── oui/
├── templates/
│   ├── document/
│   └── diagrams/
├── assets/
│   └── icons/
├── tests/
│   ├── Fixtures/
│   ├── Expected/
│   ├── Parser/
│   └── Integration/
├── tools/
├── docs/
├── output/
├── README.md
├── VERSION
└── Umsetzungsplan.md
```

---

# 26. Umsetzungsstatus und Roadmap

## Statuslegende

- `[x]` = im Repository implementiert bzw. als fachlicher Vertrag umgesetzt
- `[ ]` = noch offen
- **Lokal verifiziert** = Tests/Proof-of-Concept lokal erfolgreich durchgeführt
- **CI verifiziert** = erst setzen, wenn ein erfolgreicher Workflow-/Pipeline-Lauf tatsächlich nachweisbar ist

---

## Phase 0 – Repository-Basis

**Status: implementiert, Azure-CI-Baseline verifiziert.**

- [x] Repository-Struktur anlegen
- [x] README erstellen
- [x] `Umsetzungsplan.md` als Source of Truth pflegen
- [x] Semantic-Versioning-Strategie festlegen
- [x] Pester-Teststruktur anlegen
- [x] `.gitignore` gegen reale Kundenconfigs / generierte Kundendaten
- [x] GitHub-Actions-Baseline für Übergangszeit anlegen
- [x] Azure-Pipelines-Baseline unter `/pipelines/` anlegen

**Verifikation:**

- [x] Implementierungsstand im Repository dokumentiert
- [x] Azure Pipelines lädt Haupt-YAML und Templates erfolgreich
- [x] Microsoft-hosted Agent-Ausführung erfolgreich verifiziert

---

## Phase 1 – Sanitizer stabilisieren

**Status: implementiert und Azure-CI verifiziert, Sanitizer-Baseline `1.1.0`.**

- [x] Sanitizer v1.x übernehmen
- [x] alle bekannten bisherigen Fixes integrieren
- [x] Secret Rule Tests anlegen
- [x] Windows-PowerShell-5.1-Testpfad anlegen
- [x] PowerShell-7-Testpfad anlegen
- [x] `sanitization-report.schema.json` definieren
- [x] Residual Secret Scan
- [x] Business Subscription pfadbezogen redigieren
- [x] Audit-Metadaten entfernen
- [x] relative Output-/Report-Pfade absichern
- [x] Generic-List-/PowerShell-5.1-Regression absichern
- [x] redigierte Basic-Auth-URL gegen Residual-Scan-False-Positive absichern
- [x] Pester-5-Version für CI explizit pinnen

### Definition of Done

```text
Alle bekannten Secret-Klassen werden nach aktueller Regelbasis redigiert.
Original XML bleibt unverändert.
Netzwerkstruktur bleibt erhalten.
Residual Check kontrolliert den Status Clean.
Report enthält keine lokalen Vollpfade.
```

**Verifikation:**

- [x] synthetische Regression-Fixtures vorhanden
- [x] Azure CI Windows PowerShell 5.1 erfolgreich verifiziert
- [x] Azure CI PowerShell 7 erfolgreich verifiziert

---

## Phase 2 – Canonical Schema

**Status: implementiert und Azure-CI verifiziert, Schema `1.0.0`.**

- [x] `infrastructure-model.schema.json`
- [x] modulare Schema-Contracts
- [x] CONFIRMED / DERIVED / INFERRED / FINDING definieren
- [x] Evidence-/Provenance-Struktur definieren
- [x] Stable-ID-Strategie definieren und implementieren
- [x] Schema-Versionierung definieren
- [x] Canonical JSON Serialization definieren
- [x] positive Schema-Fixtures
- [x] negative Regression-Fixtures
- [x] `unresolvedReferences` als Vertrag definieren

### Definition of Done

```text
Ein Infrastructure Model kann unabhängig von DOCX und Diagrammen validiert werden.
Parser und Renderer haben einen versionierten technischen Vertrag.
```

**Verifikation:**

- [x] Schema-/Fixture-Validierung lokal durchgeführt
- [x] Azure Schema-CI erfolgreich verifiziert

---

## Phase 3 – Core Parser

**Status: implementiert, lokal und Azure-CI verifiziert.**

- [x] System
- [x] Interfaces
- [x] abgeleitete statische IPv4-Netze
- [x] VLANs
- [x] Gateways
- [x] Static Routes
- [x] Aliases
- [x] Firewall
- [x] NAT
- [x] IPsec
- [x] Stable IDs und Evidence für Records
- [x] `unresolvedReferences`
- [x] harte Prüfung von Sanitizer-Status und SHA-256
- [x] synthetische Parser-Regressionstests
- [x] semantischer Golden-Fingerprint
- [x] Windows-/Linux-CI-Definition

### Definition of Done

```text
Alle Phase-3-Kernobjekte werden deterministisch und mit Evidence in das Canonical Model überführt.
Unknown wird nicht geraten.
Die Ausgabe ist schema-valide.
```

**Verifikation:**

- [x] synthetische Regressionstests lokal erfolgreich
- [x] reale sanitisierte Proof-of-Concept-Config lokal schema-valide verarbeitet
- [x] Azure Parser-CI auf Ubuntu / Python 3.12 erfolgreich verifiziert
- [x] Azure Parser-CI auf Windows / Python 3.12 erfolgreich verifiziert
- [x] semantischer Golden-Fingerprint auf der Zielpipeline erfolgreich geprüft

---

## Phase 4 – DHCP / Asset Inventory

**Status: nächster fachlicher Implementierungsschritt.**

### 4.1 Testbasis

- [ ] `legacy-only.xml`
- [ ] `kea-only.xml`
- [ ] `kea-and-legacy.xml`
- [ ] `kea-reservations.xml`
- [ ] `duplicate-ip.xml`
- [ ] `invalid-pool.xml`
- [ ] `reservation-outside-pool.xml`
- [ ] `asset-enrichment.xml`
- [ ] Golden Expected Output für Kea+Legacy

### 4.2 DHCP Parser

- [ ] Kea DHCPv4 Parser
- [ ] Legacy DHCP Parser
- [ ] Services
- [ ] Scopes
- [ ] Reservations

### 4.3 Authoritative Service Resolution

- [ ] Resolution pro Interface / IP-Familie
- [ ] Kea authoritative, wenn enabled und Interface zugewiesen
- [ ] Legacy parallel erhalten, aber non-authoritative
- [ ] uneindeutige Situation als harter Validierungsfehler behandeln

### 4.4 Asset Builder

- [ ] Reservations in deterministische Asset Records überführen
- [ ] MAC-normalisierte primäre Identität
- [ ] Fallback Stable-ID ohne MAC
- [ ] Source Reservation Refs

### 4.5 OUI / Confidence / Inference

- [ ] versionierte lokale OUI-Datenbasis
- [ ] OUI Manifest / SHA-256
- [ ] Vendor `DERIVED`
- [ ] Device Type `INFERRED` nur über versionierte Regeln
- [ ] Model `INFERRED` nur über versionierte Regeln
- [ ] `UNKNOWN` bleibt möglich und zulässig
- [ ] keine Live-OUI-API im normalen Build

### 4.6 Conflict Validation

- [ ] Pool innerhalb Subnetz
- [ ] Pool Start <= Pool End
- [ ] Duplicate IP / unterschiedliche MAC erkennen
- [ ] Reservations außerhalb Subnetz ablehnen
- [ ] Reservations außerhalb dynamischem Pool zulassen
- [ ] Hostname-Duplikate als Review statt automatischem Build-Fehler klassifizieren

### Kritischer Regression Test

```text
Kea + Legacy auf LAN
→ Kea authoritative
→ Kea Pool wird als produktiv dokumentiert
→ Legacy Pool bleibt als Legacy erhalten
→ Legacy darf niemals den produktiven Pool überschreiben
```

### Definition of Done Phase 4

- [ ] Kea vollständig geparst
- [ ] Legacy vollständig geparst
- [ ] authoritative Service pro Interface bestimmt
- [ ] Reservations vollständig übernommen
- [ ] Assets deterministisch erzeugt
- [ ] OUI Enrichment versioniert
- [ ] Confidence-Klassen korrekt
- [ ] Conflict Validation aktiv
- [ ] Canonical Model schema-valid
- [ ] Windows/Linux semantisch identisches Ergebnis
- [ ] Proof-of-Concept-Config lokal gegengeprüft

---

## Phase 5 – DNS / Services / Monitoring

- [ ] Unbound
- [ ] Conditional Forwarding
- [ ] DNSBL / SafeSearch
- [ ] CrowdSec
- [ ] Zenarmor
- [ ] Netdata
- [ ] Monit
- [ ] HAProxy
- [ ] Apache
- [ ] ACME
- [ ] Cron Jobs

---

## Phase 6 – Certificates

- [ ] public cert decode
- [ ] expiry evaluation
- [ ] WebGUI certificate correlation
- [ ] ACME status correlation
- [ ] certificate findings

---

## Phase 7 – Correlation / Business Flows

- [ ] NAT ↔ Firewall
- [ ] Firewall ↔ Interface
- [ ] Route ↔ Gateway
- [ ] Gateway ↔ VPN
- [ ] DNS Forward ↔ Route/VPN
- [ ] Alias references
- [ ] Afros regression flow
- [ ] Tagetik regression flow
- [ ] Alarmanlage flow
- [ ] Azure No-NAT flow

---

## Phase 8 – Findings Engine

- [ ] Severity Model
- [ ] Scope mismatch
- [ ] empty active alias
- [ ] gateway monitoring disabled
- [ ] expired certificate
- [ ] legacy active-like config
- [ ] broad exposure indicators
- [ ] unresolved references

---

## Phase 9 – Diagram Renderer

- [ ] SVG Theme
- [ ] standardisierte Symbolbibliothek
- [ ] Netzwerkübersicht
- [ ] Routing/VPN Detail
- [ ] Business-Flow-Diagramm
- [ ] Confirmed / Derived / Inferred Styling
- [ ] keine generativen technischen Werte

---

## Phase 10 – Document Renderer

- [ ] DOCX Template
- [ ] Quick Reference
- [ ] Inhaltsverzeichnis
- [ ] alle Pflichtkapitel
- [ ] `Heading 1 -> pageBreakBefore`
- [ ] Tabellen nur aus Canonical Model
- [ ] Diagramme einbetten
- [ ] PDF Conversion

---

## Phase 11 – End-to-End Validation

- [ ] sanitized XML → model
- [ ] model → validation
- [ ] model → diagrams
- [ ] model → DOCX
- [ ] DOCX → PDF
- [ ] build manifest
- [ ] golden-file comparison

---

## Phase 12 – Azure DevOps Automation

Phase 12 implementiert keine eigene DevOps-Projekt-/Repository-Bootstrap-Logik. Sie bindet OpenSenseDocumentation an die bestehende DevOps-Bootstrap-Struktur an.

- [x] GitHub-Repository mit Git-Historie in das vom DevOps-Bootstrap vorgesehene Azure-Repos-Ziel migriert
- [x] bestehende Sanitizer-/Schema-/Parser-Prüfungen fachlich auf Azure Pipelines abgebildet
- [x] Azure-Pipelines-Migrationsbaseline erfolgreich auf Microsoft-hosted Agents ausgeführt
- [x] Azure DevOps als operative CI/CD-Source-of-Truth für OpenSenseDocumentation festgelegt
- [ ] zentrale Pipeline-Templates der Bootstrap-Struktur konsumieren
- [ ] Build Validation / Policies an Bootstrap-Vorgaben anbinden
- [ ] Config Change Detection
- [ ] automatischer Dokumentationsbuild
- [ ] Pipeline Artifacts für Modell, Reports, Diagramme, DOCX/PDF
- [ ] Build Report
- [ ] Infrastructure Diff
- [ ] GitHub-Migrationsmirror nach Abschluss der offenen Cutover-Aufräumarbeiten read-only/archiviert setzen

### Definition of Done

```text
Azure DevOps Deployment nutzt die bestehende DevOps-Bootstrap-Struktur.
OpenSenseDocumentation enthält keine konkurrierende Kunden-/Repository-Provisionierungslogik.
Die fachlichen Regressionstests laufen auf der Zielpipeline erfolgreich.
Der Azure-DevOps-Build erzeugt dieselben deterministischen Modell-/Dokumentationsartefakte.
GitHub ist nach erfolgreichem Cutover nicht mehr die operative Source of Truth.
```

**Aktueller Teilstatus:** Die Component-CI für Phase 1–3 ist auf Azure DevOps verifiziert. Die vollständige produktive Kunden-/Dokumentationsautomation sowie zentrale Template-/Policy-Anbindung bleiben Phase 12 und sind noch offen.

---

# 27. Empfohlener nächster Ablauf

Der Plattform-Cutover der Component-CI ist abgeschlossen. Der weitere fachliche Ausbau erfolgt ab jetzt gegen die Azure-DevOps-Zielplattform.

```text
1. Phase-0–3-Status im Source-of-Truth synchronisieren          ✅
2. DevOps-Bootstrap / Azure-Repos-Ziel gegenprüfen             ✅
3. Repository mit Git-Historie nach Azure DevOps migrieren     ✅
4. Sanitizer-/Schema-/Parser-Tests in Azure Pipelines abbilden ✅
5. deterministische Regressionen auf Azure DevOps verifizieren ✅
6. Azure DevOps als operative CI/CD-Source-of-Truth festlegen  ✅
7. Phase 4 – DHCP / Asset Inventory implementieren             ← NÄCHSTER SCHRITT
```

Die vollständige produktive Automatisierung bleibt Phase 12. Zentrale Pipeline-Templates, Build Policies und die spätere Kundenpipeline werden nicht vorgezogen, solange sie für die aktuelle fachliche Phase nicht benötigt werden.

---

# 28. Qualitätsziele

## Determinismus

Bei identischem Input und identischen Tool-/Datenversionen müssen entstehen:

```text
identisches Infrastructure Model
identische Findings
identische Diagrammdaten
inhaltlich identisches Dokument
```

## Nachvollziehbarkeit

Jede relevante technische Aussage besitzt Evidence oder ist explizit als Derived/Inference/Finding klassifiziert.

## Sicherheit

Keine bekannte Secret-Klasse darf in nachgelagerte Dokumentations-/KI-Artefakte gelangen.

## MSP-Tauglichkeit

Ein neuer Mitarbeiter soll innerhalb weniger Minuten mindestens beantworten können:

- Wie ist der Kunde logisch aufgebaut?
- Welche Netze existieren?
- Wie funktioniert VPN/Azure-Anbindung?
- Welche Sonderflows existieren?
- Welche externen Freigaben existieren?
- Welcher DHCP-Dienst ist tatsächlich authoritative?
- Welche Assets lassen sich aus Reservations ableiten?
- Welche Security-Dienste sind aktiv?
- Wie wird überwacht?
- Welche Findings existieren?

---

# 29. Definition of Done für Version 1.0

Version 1.0 gilt erst als abgeschlossen, wenn:

```text
[ ] Original config.xml bleibt unverändert
[ ] Sanitizer ist getestet und reproduzierbar
[ ] Canonical Infrastructure Model ist versioniert
[ ] Kea/Legacy-Prioritätslogik ist getestet
[ ] DHCP Reservations werden als Assets erfasst
[ ] OUI Enrichment ist versioniert
[ ] Active/Disabled Regeln werden korrekt getrennt
[ ] NAT/Firewall/Route/VPN werden korreliert
[ ] Afros/Tagetik werden als End-to-End Flows erkannt
[ ] Findings Engine ist aktiv
[ ] Zertifikate werden geprüft
[ ] Monitoring / Services werden dokumentiert
[ ] Gesamt-Netzwerkübersicht ist vorhanden
[ ] Business-Flow-Diagramm ist vorhanden
[ ] Diagramme enthalten keine erfundenen Werte
[ ] Quick Reference ist vorhanden
[ ] jedes Hauptkapitel startet auf neuer Seite
[ ] DOCX und PDF werden automatisiert erzeugt
[ ] Build Manifest ist vorhanden
[ ] P1-Validierung kann den Build stoppen
[ ] Regressionstests decken alle bisher gefundenen kritischen Fehler ab
[ ] Azure DevOps ist operative Source of Truth
```

Hinweis: Die Punkte werden in dieser globalen Version-1.0-Liste erst abgehakt, wenn die vollständige End-to-End-Funktion inklusive Zielpipeline verifiziert ist. Einzelne Teilkomponenten können in den Phasen bereits implementiert sein.

---

# 30. Leitentscheidung

Die wichtigste Architekturentscheidung dieses Projekts lautet:

> **OPNsense XML wird deterministisch sanitisiert, geparst, korreliert und validiert. Das daraus erzeugte Canonical Infrastructure Model ist die einzige technische Quelle für Dokumentation und Diagramme.**

Die KI ist nur eine optionale sprachliche Schicht und niemals die technische Wahrheitsquelle.

Die Azure-DevOps-Plattformstruktur wird nicht in diesem Projekt neu erfunden, sondern über den bestehenden DevOps-Bootstrap bereitgestellt.
