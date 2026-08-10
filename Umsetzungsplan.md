# Umsetzungsplan – OpenSenseDocumentation

> **Status:** Source of Truth für die Entwicklung  
> **Repository:** `Vertax1337/OpenSenseDocumentation` (GitHub bis zum verifizierten Azure-DevOps-Cutover)  
> **Zielplattform:** Azure DevOps über die bestehende DevOps-Bootstrap-Struktur  
> **Ziel:** Deterministische, reproduzierbare MSP-Kundendokumentation aus OPNsense-Konfigurationen erzeugen  
> **Grundsatz:** Technische Fakten werden **nicht** durch ein LLM erfunden oder frei interpretiert. Parser, Regeln, Korrelation, Validierung, Diagramme und Dokumentstruktur müssen deterministisch sein.  
> **Plattform-Grundsatz:** Azure-DevOps-Projekte, Repositories, Kunden-Trennung, zentrale Pipeline-Basis und übergeordnete Policies werden **nicht** in OpenSenseDocumentation neu erfunden. Dafür ist der bestehende DevOps-Bootstrap die übergeordnete Source of Truth.

---

## 1. Zielbild

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
      Facts         Inferences        Findings
        │               │                │
        └───────────────┴────────────────┘
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

Optional kann eine KI **nachgelagert** Formulierungen verbessern oder Management-Zusammenfassungen erzeugen. Sie darf jedoch keine technischen Fakten hinzufügen oder verändern.

---

# 2. Wichtigste Erkenntnisse aus dem Proof of Concept

## 2.1 Sanitizing statt direkter KI-Verarbeitung

Die originale `config.xml` ist vertraulich und darf nicht direkt an eine KI übergeben werden.

Die bereinigte XML bleibt erhalten, weil sie die vollständige OPNsense-Struktur bewahrt und damit als nachvollziehbare technische Zwischenquelle dient.

### Der Sanitizer muss mindestens behandeln

- Passwörter und Passwort-Hashes
- OTP-/TOTP-Seeds
- API-Keys und Tokens
- Pre-Shared Keys
- Private Keys
- SNMP Communities
- LDAP-/RADIUS-/SMTP-Credentials
- WireGuard-/OpenVPN-/IPsec-Secrets
- Business-Edition Subscription-/Activation-Key
- eingebettete Credentials in Strings
- zukünftige verdächtige Credential-Feldnamen

### Zusätzlich entfernen

- `created`
- `updated`
- `revision`

Diese Audit-Blöcke enthalten unter anderem Administratornamen und Quell-IP-Adressen, sind für die technische Netzwerkdokumentation jedoch nicht erforderlich.

### Wichtig

`Clean` bedeutet:

> Keine bekannten Secrets wurden nach der aktuellen Sanitizer-Regelbasis gefunden.

`Clean` bedeutet **nicht**:

> Die Datei ist anonymisiert.

Interne IP-Adressen, Hostnamen, Domains, MAC-Adressen, Aliases und Netzwerkbezeichnungen bleiben absichtlich erhalten.

---

# 3. Bereits aufgetretene Fehler und verbindliche Gegenmaßnahmen

## 3.1 Relative Output-Pfade

### Fehler

Relative Pfade wie:

```powershell
.\generated\config.sanitized.xml
```

führten in der ersten Version zu Fehlern bei `.NET Directory.CreateDirectory()`.

### Gegenmaßnahme

- PowerShell-native Pfadauflösung verwenden
- `New-Item -ItemType Directory -Force`
- explizit erkennen, wenn ein erwartetes Verzeichnis bereits als Datei existiert

---

## 3.2 PowerShell `List[object]` / `@(...)` Engine-Problem

### Fehler

Kombinationen wie:

```powershell
$list = New-Object System.Collections.Generic.List[object]
@($list)
```

führten unter Windows PowerShell 5.1 zu:

```text
Die Argumenttypen stimmen nicht überein.
```

### Gegenmaßnahme

Verbindlich:

```powershell
$list.ToArray()
```

verwenden.

---

## 3.3 Business Subscription-Key wurde zunächst nicht erkannt

### Fehler

`/opnsense/system/firmware/subscription` blieb zunächst erhalten.

### Gegenmaßnahme

Pfadbezogene Secret-Regel implementieren.

Nicht pauschal jedes XML-Element namens `subscription` löschen, da Plugins harmlose gleichnamige Felder besitzen können.

---

## 3.4 Lokale Vollpfade im Sanitization Report

### Fehler

Der Report enthielt lokale OneDrive-/Benutzerpfade.

### Gegenmaßnahme

Im Report nur speichern:

- Dateiname
- Dateigröße
- SHA-256
- Sanitizer-Version
- Redaction Counts
- Status

Keine lokalen Vollpfade.

---

## 3.5 Falscher DHCP-Pool durch Legacy-Konfiguration

### Kritischer Fehler

In der OPNsense-Config existierten gleichzeitig:

- Legacy `<dhcpd>`-Konfiguration
- aktive Kea-DHCPv4-Konfiguration

Der erste Dokumentationslauf wertete den Legacy-Bereich aus und dokumentierte:

```text
192.168.1.10 - 192.168.1.245
```

Tatsächlich aktiv war Kea mit:

```text
192.168.1.50 - 192.168.1.199
```

### Gegenmaßnahme

Der Generator darf XML-Blöcke nicht unabhängig voneinander als gleichwertig betrachten.

Es wird eine **Authoritative-Service-Resolution** implementiert.

Beispiel DHCP:

```text
Kea DHCP4 enabled = 1
        │
        ▼
Kea ist authoritative Quelle
für die dokumentierten LAN-DHCP-Daten
        │
        ▼
Legacy dhcpd wird nur noch als
Legacy-/Prüfkonfiguration ausgewiesen
```

Diese Prioritätslogik muss im Code stehen und darf nicht einem LLM überlassen werden.

---

## 3.6 DHCP Reservations wurden zunächst übersehen

### Erkenntnis

Die Kea-Reservations sind eine wertvolle Infrastrukturquelle.

Daraus lassen sich deterministisch entnehmen:

- IP-Adresse
- MAC-Adresse
- Hostname
- Beschreibung
- Subnetz
- DHCP-Kontext

Beispiele aus dem Proof of Concept:

- `Cisco-Phone-Adapter`
- `Zentrale-TASKalfa3554ci`
- mehrere `CDE4100x`-Geräte
- abteilungsbezogene Drucker-/Gerätenamen

### Konsequenz

DHCP Reservations werden fester Bestandteil des Infrastruktur-/Asset-Inventars.

---

## 3.7 OUI-Herstellerzuordnung

### Erkenntnis

Aus MAC-Adressen kann über eine versionierte OUI-Datenbasis der Hersteller abgeleitet werden.

### Wichtig

Der OUI beweist nur die Organisation / den Hersteller, **nicht** das konkrete Gerätemodell.

Daher wird unterschieden:

```text
CONFIRMED
IP, MAC, Hostname, DHCP Reservation

DERIVED
Hersteller via OUI

INFERRED
Gerätetyp aus Hostname/Beschreibung
```

Beispiel:

```text
Hostname: Zentrale-TASKalfa3554ci   -> confirmed
Vendor: Kyocera                     -> derived via OUI
Device Type: Printer                -> inferred from hostname
Model: TASKalfa 3554ci              -> inferred from hostname
```

---

## 3.8 NAT und Firewall wurden isoliert statt als Flow dokumentiert

### Fehler

Die erste Dokumentation zeigte z. B. Afros und Tagetik nur als voneinander getrennte NAT- und Firewall-Regeln.

Für einen neuen MSP-Mitarbeiter war nicht unmittelbar ersichtlich, dass diese gemeinsam einen Sonderpfad bilden.

### Gegenmaßnahme

Eine Correlation Engine muss zusammengehörige Objekte zu Business Flows verbinden.

Beispiel:

```text
Azure APP
10.43.0.0/24
     │
     ▼
IPsec / enc0
     │
     ▼
Firewall Allow
10.43.0.0/24 -> 85.32.49.226
     │
     ▼
Outbound NAT
10.43.0.0/16 -> 85.32.49.226/32
SNAT -> WAN-IP
     │
     ▼
Internet / Afros
```

---

## 3.9 Unterschiedliche Source Scopes müssen Findings erzeugen

Im Afros-/Tagetik-Beispiel:

```text
Firewall Source: 10.43.0.0/24
NAT Source:      10.43.0.0/16
```

Dies darf nicht still vereinheitlicht werden.

Der Generator erzeugt stattdessen ein Finding:

```text
Source scopes differ between firewall and NAT rules.
Verify whether this is intentional.
```

---

## 3.10 Generative Diagramme dürfen keine technischen Werte erzeugen

### Kritischer Fehler

Ein optisch sehr professionelles generatives Diagramm erfand unter anderem:

- nicht vorhandene Interface-Namen
- falsche VLAN-ID
- falsche IP-Netze
- falsche Azure-Netze
- nicht bestätigte WAN-Adressen

### Konsequenz

Generative Bildmodelle werden **nicht** für technische Netzdiagramme verwendet.

Diagramme werden ausschließlich aus `infrastructure-model.json` erzeugt.

Erlaubt ist nur deterministisches Styling.

---

## 3.11 Netzwerkübersicht darf zwischen Dokumentversionen nicht verschwinden

### Fehler

Bei einer Dokumentrevision wurde die professionelle Gesamt-Netzwerkübersicht nicht mehr eingebettet.

### Gegenmaßnahme

Die Dokumentstruktur ist versioniert und fest definiert.

Pflichtseiten dürfen nicht dynamisch entfallen.

---

# 4. Architekturprinzipien

## 4.1 Eine einzige technische Wahrheit

`infrastructure-model.json` ist die einzige Quelle für:

- Tabellen
- Texte
- Diagramme
- Findings
- Business Flows
- Quick Reference
- spätere Diffs

Dokument und Diagramm dürfen niemals unterschiedliche Datenquellen verwenden.

---

## 4.2 Facts, Derived Data, Inferences und Findings strikt trennen

### Fact

Direkt aus der Config belegt.

Beispiel:

```text
LAN IPv4 = 192.168.1.1/24
```

### Derived

Deterministisch aus einem Fakt + definierter Datenbasis abgeleitet.

Beispiel:

```text
MAC OUI -> Hersteller Kyocera
```

### Inference

Plausible Interpretation, deren Basis transparent ausgewiesen wird.

Beispiel:

```text
Hostname enthält TASKalfa3554ci -> wahrscheinlich Kyocera-Drucker
```

### Finding

Technischer Prüfpunkt, Konflikt oder bekannte Abweichung.

Beispiel:

```text
Gateway Monitoring disabled
```

oder:

```text
Firewall /24 differs from NAT /16
```

---

## 4.3 Verantwortungsgrenze zu Azure DevOps

OpenSenseDocumentation ist **nicht** für den Aufbau einer eigenen Azure-DevOps-Projekt- oder Kundenstruktur verantwortlich.

Verbindlich gilt:

> **Azure DevOps Deployment erfolgt über die bestehende DevOps-Bootstrap-Struktur.**

Der DevOps-Bootstrap ist die übergeordnete Source of Truth für:

- Azure-DevOps-Projekt- und Repository-Struktur
- standardisierte Kunden-Trennung
- zentrale Pipeline-Grundstruktur und wiederverwendbare Pipeline-Templates
- übergeordnete Repository-/Branch-/Policy-Konfiguration
- Bereitstellung der vorgesehenen Ziel-Repositories

OpenSenseDocumentation ist dagegen verantwortlich für:

- Sanitizer
- Canonical Infrastructure Model
- Parser
- Rule-/Correlation-Engine
- Enrichment
- Validierung
- Diagramm- und Dokument-Renderer
- fachliche Testfälle und Golden Files
- den technischen Pipeline-Contract für den Dokumentationsbuild

Dadurch wird keine zweite Bootstrap-/Kundenlogik innerhalb dieses Repositories aufgebaut.

Eine separate Migrationsphase zur Neuerfindung der Azure-DevOps-Struktur ist **nicht** Bestandteil dieses Projekts. Die Migration des Repositories wird als Deployment-/Plattformaufgabe innerhalb der bestehenden Bootstrap-Struktur durchgeführt.

---

# 5. Provenance / Evidence

Jedes relevante Objekt muss seine Quelle kennen.

Beispiel:

```json
{
  "network": "10.43.0.0/16",
  "gateway": "VPNGW",
  "description": "Azure APP vNet",
  "status": "active",
  "evidence": {
    "source": "config.sanitized.xml",
    "xpath": "/opnsense/staticroutes/route[...]"
  }
}
```

Ziel:

> Jede Aussage in der Dokumentation soll bei Bedarf bis zur XML-Quelle zurückverfolgbar sein.

---

# 6. Canonical Infrastructure Model

## 6.1 Ziel

Die XML bleibt vollständig erhalten, wird aber zusätzlich in ein stabiles, versioniertes Dokumentationsmodell überführt.

### Beispielstruktur

```json
{
  "schemaVersion": "1.0.0",
  "source": {},
  "system": {},
  "interfaces": [],
  "networks": [],
  "vlans": [],
  "dhcp": {},
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
  "findings": []
}
```

---

# 7. Deterministische Regeln

Diese Regeln müssen als Code / Rule Engine umgesetzt werden.

## 7.1 DHCP

- aktive DHCP-Implementierung eindeutig bestimmen
- Kea aktiv -> Kea authoritative
- Legacy `dhcpd` nur als Legacy/Review anzeigen
- Pool muss innerhalb des Subnetzes liegen
- Gateway/DNS/Domain/NTP übernehmen
- Reservations vollständig auslesen
- Reservations außerhalb Pool sind zulässig, aber dokumentieren
- doppelte IP-/MAC-/Hostname-Kollisionen als Findings melden

## 7.2 Firewall

- `disabled=1` niemals als aktiven Flow darstellen
- Action, Interface, Direction, Protocol, Source, Destination, Port exakt übernehmen
- Associated NAT Rule verknüpfen
- `any` nicht umformulieren
- Reihenfolge erhalten, sofern für Bewertung relevant

## 7.3 NAT

- Inbound / Port Forward
- Outbound NAT
- No-NAT
- Disabled Rules strikt getrennt
- NAT und Firewall miteinander korrelieren

## 7.4 Interfaces

- Interface ohne bestätigte IP != bestätigtes L3-Netz
- WAN DHCP/DHCPv6 -> aktuelle IP nicht erfinden
- virtuelle Interfaces klar markieren
- VTI / IPsec Interfaces erkennen

## 7.5 Aliases

- leerer Alias bleibt leer / unresolved
- keine Inhalte erfinden
- external aliases als dynamisch kennzeichnen
- Alias-Verwendung in Firewall/NAT referenzieren

## 7.6 DNS

- System DNS
- Unbound Status
- Conditional Forwarding
- DNSBL / SafeSearch
- Forward Target mit Routing/VPN korrelieren

## 7.7 VPN / Routing

- Phase 1 / Phase 2
- route-based / policy-based unterscheiden
- VTI und Gateway zusammenführen
- statische Routen über Gateway referenzieren
- Monitoring Status auswerten

## 7.8 Certificates

- öffentliche X.509-Zertifikate programmatisch dekodieren
- Subject / SAN
- NotBefore / NotAfter
- Issuer
- Self-Signed
- Ablaufstatus
- privater Schlüssel bleibt redigiert

## 7.9 Services

Aktivitätsstatus ermitteln für z. B.:

- CrowdSec
- Unbound
- DNSBL
- Zenarmor
- Monit
- Netdata
- HAProxy
- Apache
- ACME
- WireGuard
- OpenVPN

Keine reine Plugin-Liste mit „installiert“ mit „aktiv“ verwechseln.

## 7.10 Cron / Maintenance

- aktive und deaktivierte Jobs trennen
- Firmware Auto Update dokumentieren
- Reboot Jobs dokumentieren
- Plugin Periodicals dokumentieren

---

# 8. Asset-/Infrastruktur-Inventar

DHCP Reservations werden als eigenes Infrastrukturmodell behandelt.

## 8.1 Felder

- IP
- MAC
- Hostname
- Description
- Subnet
- DHCP Source
- Vendor
- Vendor Confidence
- Device Type
- Device Type Confidence
- Evidence

## 8.2 Confidence Levels

```text
CONFIRMED
Direkt aus OPNsense

DERIVED
Deterministisch mit versionierter externer Datenbasis

INFERRED
Interpretation aus Hostname/Beschreibung

UNKNOWN
Nicht belastbar ableitbar
```

---

# 9. Versionierte OUI-Datenbank

Für reproduzierbare Ergebnisse wird keine Live-OUI-API bei jedem Build verwendet.

Stattdessen:

```text
data/
└── oui/
    └── oui-YYYY-MM.csv
```

Das Build Manifest referenziert die verwendete OUI-Version.

Damit gilt:

```text
gleiche Config
+ gleicher Parser
+ gleiches Ruleset
+ gleiche OUI DB
+ gleiches Template
=
gleiche Dokumentation
```

---

# 10. Business-Flow Engine

## 10.1 Ziel

Ein Techniker soll Sonderkonfigurationen sofort als vollständigen Datenfluss erkennen.

Nicht nur Einzelregeln auflisten.

## 10.2 Beispiel-Flows aus dem Proof of Concept

### FLOW-AFROS

- Origin: Azure APP
- VPN / ingress: IPsec / enc0
- Firewall Source: `10.43.0.0/24`
- Destination: `85.32.49.226`
- Outbound NAT Source: `10.43.0.0/16`
- NAT Translation: WAN IP
- Egress: WAN
- Finding: Firewall /24 vs NAT /16

### FLOW-TAGETIK

Analog Afros mit Ziel `93.51.162.71`.

### FLOW-ALARM

- Internet
- WAN TCP/UDP 54123
- Port Forward
- internes Ziel `192.168.1.201:54123`

### FLOW-DNS-AD

- Domain `cannon.local`
- Unbound Conditional Forward
- `10.41.1.4:53/TCP`
- Route über Azure DC vNet / VPNGW

### FLOW-AZURE-NONAT

- LAN
- Alias `AZURE_NETZ`
- No-NAT
- Interface `ipsec1`
- leerer/unaufgelöster Alias als Finding

---

# 11. Findings Engine

Findings werden priorisiert.

## P1 – Kritisch / kurzfristig prüfen

Beispiele:

- technisch widersprüchliche aktive Konfiguration
- Secret-Residual gefunden
- aktiver DHCP-Dienst nicht eindeutig bestimmbar
- fehlerhafte Route-/Gateway-Referenz
- Dokumentbuild wäre faktisch nicht belastbar

## P2 – Betriebsrelevant

Beispiele:

- Gateway Monitoring deaktiviert
- abgelaufenes Zertifikat
- breite WAN-Freigabe
- leere aktive Aliases
- Firewall/NAT Scope-Unterschiede

## P3 – Dokumentations-/Optimierungspunkt

Beispiele:

- Legacy-Konfiguration vorhanden
- unbeschriebene Rules
- fehlende Business-Beschreibung
- nicht zuordenbare Assets

---

# 12. Validierung vor Dokumenterstellung

Vor DOCX/PDF muss ein deterministischer Validator laufen.

## Pflichtprüfungen

```text
[ ] Sanitizer Status Clean
[ ] Keine Residual Secrets
[ ] Infrastructure Model gegen JSON Schema valide
[ ] Aktiver DHCP-Dienst eindeutig bestimmt
[ ] DHCP Pools innerhalb Subnetzen
[ ] Reservations ohne Konflikte
[ ] Alle aktiven Firewallregeln verarbeitet
[ ] Alle aktiven NAT-Regeln verarbeitet
[ ] Disabled Rules nicht in Active Flows
[ ] Alle Gateways auflösbar
[ ] Alle statischen Routen referenzieren bekannte Gateways
[ ] Business Flow Referenzen konsistent
[ ] Diagramme verwenden ausschließlich Model IDs
[ ] Keine nicht belegten Werte im Dokument
```

Bei P1-Validierungsfehlern:

```text
BUILD FAILED
```

Keine möglicherweise falsche Kundendokumentation erzeugen.

---

# 13. Dokumentstruktur – MSP Operational Documentation

Die Kapitelstruktur wird fest versioniert.

## Pflichtstruktur

1. Titelblatt
2. Quick Reference / Übersichtsseite
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

## Verbindliche Layout-Regel

**Jedes Hauptkapitel beginnt auf einer neuen Seite.**

Technische Umsetzung im DOCX-Renderer:

```text
Heading 1 -> pageBreakBefore = true
```

Ausnahmen:

- Titelblatt
- Quick Reference
- Inhaltsverzeichnis

---

# 14. Quick Reference

Die Quick-Reference-Seite muss einem neuen Mitarbeiter innerhalb von 1–2 Minuten beantworten:

- Welche Firewall?
- Welche primären Netze?
- Wie erfolgt Internetzugang?
- Welche VPNs existieren?
- Welche Azure-/Remote-Netze existieren?
- Welcher DHCP-Dienst ist aktiv?
- Welche kritischen Sonderflows existieren?
- Welche Security-Systeme sind aktiv?
- Wie wird überwacht?
- Welche P1/P2 Findings existieren?

---

# 15. Netzwerkdiagramme

## 15.1 Kein generatives Bildmodell für technische Inhalte

Nicht erlaubt:

```text
Prompt -> Image AI -> technisches Diagramm
```

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

## 15.2 Standardisierte Symboltypen

- Internet / Provider -> Cloud
- Firewall -> Firewall Appliance
- Switch -> Switch
- Server -> Server
- Client -> Endpoint
- Printer -> Printer
- Access Point -> Wireless AP
- VPN -> Tunnel / Lock
- Azure -> Azure Cloud
- Network -> Security Zone

## 15.3 Darstellungsregeln

- bestätigte Verbindungen: durchgezogen
- abgeleitete Beziehungen: klar markiert
- unbestätigte L3-Zuordnung: gestrichelt
- deaktivierte Flows nicht als aktiv darstellen
- Unknown nicht durch Fantasiewerte ersetzen

## 15.4 Pflichtdiagramme

1. Gesamt-Netzwerkübersicht
2. Routing/VPN-Detail
3. Business-Flow-Diagramm

Optional später:

4. Asset-/DHCP-Map
5. Security-Service-Map

---

# 16. Management / Administration

Dokumentieren, soweit aus der Config ableitbar:

- WebGUI HTTPS
- Management Interface / Bindings
- Auth Backend
- TOTP/MFA vorhanden
- SSH aktiv/deaktiviert
- administrative lokale Accounts ohne Secrets
- Management-Dienste
- Netdata
- Monit

Nicht automatisch ableitbar:

- Password Vault Location
- Break-Glass-Prozess
- Remote Support Tool
- MSP Eskalationspfad

Diese werden als manuelle Metadatenfelder vorgesehen.

---

# 17. Monitoring / Alerting

Auswerten:

- Monit enabled
- Interval
- SMTP Relay
- aktive Empfänger
- überwachte Ressourcen
- CPU/RAM/Disk Thresholds
- Gateway Monitoring
- VPN Monitoring
- Netdata

Automatisches Finding bei:

```text
VPN / Gateway aktiv
AND
Gateway Monitoring disabled
AND
kein alternativer aktiver VPN-Monitor erkannt
```

---

# 18. Security Services

Eigene Übersicht für aktive Security-Komponenten.

Beispiele:

- CrowdSec Agent
- CrowdSec LAPI
- CrowdSec Firewall Bouncer
- Unbound DNSBL
- SafeSearch
- Zenarmor
- IDS/IPS, soweit belastbar ableitbar

Installierte Plugins werden getrennt von aktiven Diensten ausgewiesen.

---

# 19. Zertifikate

Öffentliche Zertifikatsdaten programmatisch dekodieren.

Dokumentieren:

- Purpose / Description
- Subject
- SAN
- Issuer
- Not Before
- Not After
- Self-Signed
- Status

Finding erzeugen für:

- abgelaufen
- läuft kurzfristig ab
- WebGUI verwendet abgelaufenes Zertifikat
- ACME deaktiviert, sofern relevant

---

# 20. Build Manifest

Jeder Build erhält ein Manifest.

Beispiel:

```json
{
  "customer": "cannon.internal",
  "source": {
    "file": "config.xml",
    "sha256": "..."
  },
  "sanitizer": "1.0.3",
  "parser": "1.0.0",
  "schema": "1.0.0",
  "ruleset": "1.0.0",
  "template": "1.0.0",
  "diagramTheme": "1.0.0",
  "ouiDatabase": "2026-08"
}
```

Ziel:

> Jeder Dokumentstand muss reproduzierbar sein.

---

# 21. Repository-Struktur

Die folgende Struktur beschreibt **nur das OpenSenseDocumentation-Tooling-Repository**. Die Azure-DevOps-Projektstruktur und die kundenbezogene Repository-Erzeugung liegen außerhalb dieses Repositories und werden durch den bestehenden DevOps-Bootstrap bereitgestellt.

```text
OpenSenseDocumentation/
│
├── src/
│   ├── Sanitizer/
│   │   └── Sanitize-OPNsenseConfig.ps1
│   │
│   ├── Parser/
│   │   ├── System/
│   │   ├── Interfaces/
│   │   ├── DHCP/
│   │   ├── DNS/
│   │   ├── Firewall/
│   │   ├── NAT/
│   │   ├── Routing/
│   │   ├── VPN/
│   │   ├── Services/
│   │   ├── Monitoring/
│   │   ├── Certificates/
│   │   └── Cron/
│   │
│   ├── Rules/
│   │   ├── ServiceResolution/
│   │   ├── FlowCorrelation/
│   │   ├── Findings/
│   │   └── Validation/
│   │
│   ├── Enrichment/
│   │   └── OUI/
│   │
│   ├── Renderer/
│   │   ├── Document/
│   │   └── Diagram/
│   │
│   └── Build/
│
├── schemas/
│   └── infrastructure-model.schema.json
│
├── data/
│   └── oui/
│
├── templates/
│   ├── document/
│   └── diagrams/
│
├── assets/
│   └── icons/
│
├── tests/
│   ├── Fixtures/
│   ├── Expected/
│   └── Integration/
│
├── docs/
│
├── output/
│   └── .gitkeep
│
├── README.md
└── Umsetzungsplan.md
```

### 21.1 Azure-DevOps-Einordnung

Nach dem Cutover wird dieses Repository in das durch den DevOps-Bootstrap vorgesehene Azure-Repos-Ziel überführt.

Nicht Bestandteil von OpenSenseDocumentation sind:

- Erzeugung von Kundenprojekten
- Erzeugung kundenspezifischer Firewall-Repositories
- Definition einer konkurrierenden Projekt-/Repo-Namenskonvention
- Aufbau einer zweiten Pipeline-Template-Plattform
- Aufbau einer zweiten Branch-/Policy-Bootstrap-Logik

Diese Aufgaben bleiben beim DevOps-Bootstrap.

---

# 22. Teststrategie

## 22.1 Sanitizer Tests

Fixtures für:

- Password
- Hash
- OTP
- API Key
- PSK
- Private Key
- SNMP Community
- Business Subscription
- Embedded Credentials
- Third Party Plugin Credentials

Erwartung:

```text
Secret entfernt
Struktur erhalten
Residual Check = Clean
```

## 22.2 DHCP Tests

### Fixture: Legacy only

Expected:

```text
Authoritative DHCP = Legacy
```

### Fixture: Kea only

Expected:

```text
Authoritative DHCP = Kea
```

### Fixture: Kea + Legacy

Expected:

```text
Authoritative DHCP = Kea
Legacy block = Review/Legacy only
```

### Reservation Tests

- IP/MAC/Hostname übernommen
- OUI enrichment korrekt
- confidence korrekt
- keine Modellfantasie

## 22.3 Firewall/NAT Tests

- disabled Rules nicht aktiv
- associated NAT korrekt verknüpft
- Portforward Flow entsteht
- Outbound NAT Flow entsteht
- No-NAT korrekt markiert

## 22.4 Afros Regression Test

Expected:

```text
FLOW-AFROS exists
Destination = 85.32.49.226
Firewall source = 10.43.0.0/24
NAT source = 10.43.0.0/16
Finding source scope mismatch exists
```

## 22.5 Diagram Tests

- keine Werte außerhalb Infrastructure Model
- alle Pflichtdiagramme vorhanden
- keine deaktivierten Regeln als aktive Verbindung
- keine erfundenen Interfaces

## 22.6 Document Tests

- Quick Reference vorhanden
- Gesamtübersicht vorhanden
- jedes Hauptkapitel startet auf neuer Seite
- NAT startet auf neuer Seite
- Business Flows vorhanden
- Asset Inventar vorhanden
- Findings vorhanden

---

# 23. CI / Azure DevOps Prozess

Die CI/CD-Zielplattform ist Azure DevOps. Die dafür benötigte übergeordnete Plattformstruktur wird vom bestehenden DevOps-Bootstrap bereitgestellt und **nicht** innerhalb von OpenSenseDocumentation neu aufgebaut.

Verantwortung des DevOps-Bootstraps:

- Bereitstellung des Ziel-Repositories in Azure Repos
- zentrale Pipeline-Grundstruktur bzw. wiederverwendbare Pipeline-Templates
- standardisierte Kunden-/Repository-Trennung
- übergeordnete Branch-/Policy-Konfiguration

Verantwortung von OpenSenseDocumentation:

- fachliche Build-Schritte und deren Reihenfolge
- benötigte Runtime-/Tool-Versionen
- Sanitizer-, Schema-, Parser-, Rule-, Renderer- und Regressionstests
- Definition der erzeugten Build-Artefakte
- deterministische Validierung und Build-Abbruchregeln

Die derzeit vorhandenen GitHub-Actions-Workflows sind während der Übergangszeit Entwicklungs-/Migrationsartefakte. Sie sind **nicht** die langfristige Plattform-Source-of-Truth.

Der spätere Azure-Pipelines-Contract muss die zentrale Bootstrap-/Template-Struktur konsumieren, anstatt parallel eine eigene Pipeline-Plattform aufzubauen.

Zielpipeline:

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
      └─ Generate Build Manifest
```

Dabei bleibt die fachliche Pipeline identisch, unabhängig davon, ob sie während der Übergangszeit auf GitHub Actions oder nach dem Cutover auf Azure Pipelines ausgeführt wird.

---

# 24. Infrastructure Diff

Spätere Ausbaustufe:

Bei jeder neuen Config-Version wird zusätzlich ein Diff zum letzten erfolgreichen Build erzeugt.

Beispiel:

```text
CHANGED

Firewall:
+ WAN 8443 -> 192.168.1.50

DHCP:
+ 192.168.1.72 Lager-Scanner-02

VPN:
~ Azure APP route
  10.43.0.0/16 -> 10.43.0.0/17

Services:
- CrowdSec disabled
```

Nutzen:

- Change Review
- Kundenhistorie
- unerwartete Änderungen erkennen
- Troubleshooting

---

# 25. Rolle der KI

## Erlaubt

- sprachliche Glättung
- Management Summary
- verständliche Erklärung bereits vorhandener Findings
- optional Troubleshooting-Text aus strukturierten Fakten

## Nicht erlaubt

- technische Werte erfinden
- aktive Dienste selbst bestimmen
- DHCP-Priorität frei interpretieren
- Firewall/NAT-Korrelation frei erfinden
- Diagramminhalte selbst setzen
- unbekannte physische Infrastruktur ergänzen

### LLM Contract

Wenn eine KI eingesetzt wird, erhält sie ausschließlich strukturierte Fakten wie:

```json
{
  "facts": [],
  "businessFlows": [],
  "findings": []
}
```

und die Anweisung:

```text
Do not introduce any fact that is not represented in the input model.
```

---

# 26. Nicht aus OPNsense belastbar ableitbar

Folgende Bereiche benötigen andere Datenquellen:

- physische Switch-Topologie
- Switchport-Belegung
- Trunk-/Access-Port-Konfiguration
- Patchfelder / Verkabelung
- tatsächliche Access-Point-Uplinks
- aktive Endgeräte ohne DHCP-Reservation
- aktueller WAN-Wert bei DHCP
- Provider / Vertragsdaten
- Standort / Rack / Seriennummer, sofern nicht separat erfasst
- Azure-seitige UDR / NSG / Gateway-Konfiguration vollständig

Diese Felder dürfen niemals geraten werden.

---

# 27. Zukünftige Multi-Source-Erweiterung

Das Canonical Infrastructure Model soll später weitere Collector-Quellen aufnehmen können.

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

Damit kann später z. B. der Afros-Flow auch auf Azure-Seite vollständig mit UDR, NSG und VPN Gateway verifiziert werden.

Die Bereitstellung der hierfür erforderlichen Azure-DevOps-Projekte und kundenspezifischen Repositories bleibt Aufgabe des DevOps-Bootstraps. Das Canonical Infrastructure Model definiert nur die technische Zusammenführung der Datenquellen.

---

# 28. Umsetzungsphasen

## Phase 0 – Repository-Basis

- [ ] Repository-Struktur anlegen
- [ ] README erstellen
- [ ] `Umsetzungsplan.md` als Source of Truth pflegen
- [ ] Versionierungsstrategie festlegen
- [ ] Pester-Teststruktur anlegen

## Phase 1 – Sanitizer stabilisieren

- [ ] Sanitizer v1.x übernehmen
- [ ] alle bisherigen Fixes integrieren
- [ ] Secret Rule Tests
- [ ] PowerShell 5.1 Tests
- [ ] PowerShell 7 Tests
- [ ] Sanitization Report Schema

### Definition of Done

```text
Alle bekannten Secrets werden entfernt.
Keine Netzwerkstruktur wird unnötig zerstört.
Residual Check funktioniert.
Tests laufen reproduzierbar.
```

---

## Phase 2 – Canonical Schema

- [ ] `infrastructure-model.schema.json`
- [ ] Facts / Derived / Inferred / Findings definieren
- [ ] Evidence-Struktur definieren
- [ ] Versionierung des Schemas

### Definition of Done

Ein Infrastructure Model kann unabhängig von DOCX/Diagrammen validiert werden.

---

## Phase 3 – Core Parser

Implementieren:

- [ ] System
- [ ] Interfaces
- [ ] VLANs
- [ ] Gateways
- [ ] Static Routes
- [ ] Aliases
- [ ] Firewall
- [ ] NAT
- [ ] IPsec

### Definition of Done

Alle aktiven und deaktivierten Objekte werden korrekt und mit Evidence ins Modell übernommen.

---

## Phase 4 – DHCP / Asset Inventory

- [ ] Kea Parser
- [ ] Legacy DHCP Parser
- [ ] Authoritative Service Resolution
- [ ] Reservations
- [ ] OUI Enrichment
- [ ] Confidence Model
- [ ] Conflict Validation

### Kritischer Regression Test

Kea + Legacy darf niemals wieder zum falschen aktiven Pool führen.

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

- [ ] NAT <-> Firewall
- [ ] Firewall <-> Interface
- [ ] Route <-> Gateway
- [ ] Gateway <-> VPN
- [ ] DNS Forward <-> Route/VPN
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
- [ ] overly broad exposure indicators
- [ ] unresolved references

---

## Phase 9 – Diagram Renderer

- [ ] SVG theme
- [ ] standard icon library
- [ ] network overview
- [ ] routing/VPN detail
- [ ] business-flow diagram
- [ ] Confirmed / Derived / Inferred styling
- [ ] no generative technical values

---

## Phase 10 – Document Renderer

- [ ] DOCX template
- [ ] Quick Reference
- [ ] Inhaltsverzeichnis
- [ ] all mandatory chapters
- [ ] `Heading 1 -> pageBreakBefore`
- [ ] tables from model only
- [ ] diagrams embedded
- [ ] PDF conversion

---

## Phase 11 – End-to-End Validation

- [ ] sanitized XML -> model
- [ ] model -> validation
- [ ] model -> diagrams
- [ ] model -> DOCX
- [ ] DOCX -> PDF
- [ ] build manifest
- [ ] golden-file comparison

---

## Phase 12 – Azure DevOps Automation

Phase 12 implementiert **keine eigene DevOps-Projekt-/Repository-Bootstrap-Logik**. Sie bindet OpenSenseDocumentation an die bereits vorhandene DevOps-Bootstrap-Struktur an.

- [ ] GitHub-Repository mit vollständiger Git-Historie in das vom DevOps-Bootstrap vorgesehene Azure-Repos-Ziel migrieren
- [ ] bestehende GitHub-Actions-Prüfungen fachlich auf Azure Pipelines abbilden
- [ ] zentrale Pipeline-Templates der Bootstrap-Struktur konsumieren statt zu duplizieren
- [ ] benötigte Build-Validation/Policies an die Bootstrap-Vorgaben anbinden
- [ ] Config Change Detection
- [ ] automatic documentation build
- [ ] Pipeline Artifacts für Modell, Reports, Diagramme, DOCX/PDF
- [ ] build report
- [ ] infrastructure diff
- [ ] GitHub erst nach verifiziertem Azure-DevOps-Cutover read-only/archiviert setzen

### Definition of Done

```text
Azure DevOps Deployment nutzt die bestehende DevOps-Bootstrap-Struktur.
OpenSenseDocumentation enthält keine konkurrierende Kunden-/Repository-Provisionierungslogik.
Die fachlichen Regressionstests laufen auf der Zielpipeline erfolgreich.
Der Azure-DevOps-Build erzeugt dieselben deterministischen Modell-/Dokumentationsartefakte.
GitHub ist nach erfolgreichem Cutover nicht mehr die operative Source of Truth.
```

---

# 29. Qualitätsziele

## Determinismus

Bei identischem Input und identischen Tool-/Datenversionen müssen entstehen:

```text
identisches Infrastructure Model
identische Findings
identische Diagrammdaten
inhaltlich identisches Dokument
```

## Nachvollziehbarkeit

Jede relevante technische Aussage muss Evidence besitzen.

## Sicherheit

Keine bekannte Secret-Klasse darf in KI-/Dokumentationsartefakte gelangen.

## MSP-Tauglichkeit

Ein neuer Mitarbeiter soll nach 5–10 Minuten mindestens beantworten können:

- Wie ist der Kunde logisch aufgebaut?
- Welche Netze existieren?
- Wie funktioniert Azure/VPN?
- Welche Sonderflows existieren?
- Welche externen Freigaben existieren?
- Welcher DHCP-Dienst ist tatsächlich aktiv?
- Welche Infrastruktur lässt sich aus Reservations ableiten?
- Welche Security-Dienste sind aktiv?
- Wie wird überwacht?
- Welche bekannten Findings existieren?

---

# 30. Definition of Done für Version 1.0

Version 1.0 gilt erst als abgeschlossen, wenn alle folgenden Punkte erfüllt sind:

```text
[ ] Original config.xml bleibt unverändert
[ ] Sanitizer ist getestet und reproduzierbar
[ ] Canonical Infrastructure Model ist versioniert
[ ] Kea/Legacy Prioritätslogik ist getestet
[ ] DHCP Reservations werden als Assets erfasst
[ ] OUI Enrichment ist versioniert
[ ] Active/Disabled Regeln werden korrekt getrennt
[ ] NAT/Firewall/Route/VPN werden korreliert
[ ] Afros/Tagetik als End-to-End Flows erkannt
[ ] Findings Engine aktiv
[ ] Zertifikate werden geprüft
[ ] Monitoring / Services dokumentiert
[ ] Gesamt-Netzwerkübersicht vorhanden
[ ] Business-Flow-Diagramm vorhanden
[ ] Diagramme enthalten keine erfundenen Werte
[ ] Quick Reference vorhanden
[ ] jedes Hauptkapitel startet auf neuer Seite
[ ] DOCX und PDF werden automatisiert erzeugt
[ ] Build Manifest vorhanden
[ ] Validierung kann Build bei P1-Problemen stoppen
[ ] Regression Tests decken alle bisher gefundenen Fehler ab
[ ] Azure DevOps Deployment erfolgt über die bestehende DevOps-Bootstrap-Struktur
[ ] OpenSenseDocumentation dupliziert keine Kunden-/Repository-Bootstrap-Logik
```

---

# 31. Leitentscheidung

Die wichtigste Architekturentscheidung dieses Projekts lautet:

> **OPNsense XML wird deterministisch sanitisiert, geparst, korreliert und validiert. Das daraus erzeugte Canonical Infrastructure Model ist die einzige technische Quelle für Dokumentation und Diagramme.**

Die KI ist nur noch eine optionale sprachliche Schicht und niemals die technische Wahrheitsquelle.

Für die Plattform gilt ergänzend:

> **Azure DevOps Deployment erfolgt über die bestehende DevOps-Bootstrap-Struktur. OpenSenseDocumentation definiert keine konkurrierende Azure-DevOps-Projekt-, Kunden- oder Repository-Provisionierungslogik.**

Damit wird aus dem bisherigen Proof of Concept ein reproduzierbarer MSP-Dokumentationsgenerator, der sich sauber in die bestehende Azure-DevOps-Gesamtarchitektur einfügt.
