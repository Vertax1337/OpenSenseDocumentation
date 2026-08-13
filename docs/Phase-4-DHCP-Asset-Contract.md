# Phase 4 – DHCP / Asset Inventory Contract

## Status

Phase 4.1 bis Phase 4.4 sind implementiert und auf Azure Pipelines für Windows und Linux verifiziert.

Phase 4.5 erweitert den bereits verifizierten Asset Builder um deterministisches OUI-Enrichment sowie versionierte Device-Type-/Model-Inference. Die technische Implementierung wird mit synthetischen, lokal versionierten Fixtures abgesichert. Ein produktiver IEEE-MA-L-Snapshot unter `data/oui/` wird getrennt vom normalen Build gepflegt und ist noch zu provisionieren; bis dahin bleibt `vendor=UNKNOWN`.

Der bestehende Canonical-Model-Contract `1.0.0` bleibt unverändert. Die vorhandenen `attributedString`-Felder können `CONFIRMED`, `DERIVED`, `INFERRED` und `UNKNOWN` bereits ausdrücken.

## Architekturgrenze

```text
Sanitized OPNsense XML
        │
        ▼
Parse DHCP Facts
        │
        ▼
Resolve authoritative service
        │
        ▼
Build Assets
        │
        ▼
Enrich
        │
        ▼
Validate
```

Der Parser darf weder aktive DHCP-Implementierungen noch Vendor, Device Type oder Model aus Wahrscheinlichkeiten bestimmen. Nicht eindeutig belegbare Werte bleiben `UNKNOWN`.

## Source-Struktur

### Kea DHCPv4

```text
/opnsense/OPNsense/Kea/dhcp4
```

Relevante Strukturen:

```text
general/enabled
general/interfaces
general/valid_lifetime
subnets/subnet4[@uuid]
subnets/subnet4/subnet
subnets/subnet4/pools
subnets/subnet4/option_data/*
reservations/reservation[@uuid]
reservations/reservation/subnet
reservations/reservation/ip_address
reservations/reservation/hw_address
reservations/reservation/client_id
reservations/reservation/hostname
reservations/reservation/description
```

### Legacy DHCP

```text
/opnsense/dhcpd/<interface>
```

Ein vorhandener Legacy-Block ist zunächst ein Konfigurations-Fact. Ein Legacy-Service gilt nur dann als `enabled`, wenn der jeweilige Interface-Block einen aktiv ausgewerteten `enable`-Marker besitzt. Ein vorhandener Block ohne Enable-Marker bleibt erhalten, wird aber nicht als aktiver Dienst interpretiert.

## Service-Kardinalität

Phase 4 emittiert für IPv4 genau einen Service-Record pro Kombination aus:

```text
DHCP implementation + interface + IP family
```

Beispiele:

```text
dhcp-service:kea-ipv4-lan
dhcp-service:isc-dhcpd-ipv4-lan
dhcp-service:isc-dhcpd-ipv4-opt4
```

`interfaceRefs` enthält bei diesen Records genau einen Eintrag.

## Authoritative Service Resolution

`authoritative` wird deterministisch durch `dhcp.authority.v1` bestimmt.

`enabled` beschreibt den aus `config.xml` belegten konfigurierten Sollzustand. Daraus darf bei konkurrierenden DHCP-Implementierungen kein tatsächlicher Runtime-Zustand erfunden werden.

Für IPv4 gilt:

1. Kea ist auf einem Interface nur dann `enabled`, wenn `general/enabled` aktiv ist und das Interface explizit in `general/interfaces` aufgeführt ist.
2. Legacy ISC DHCP ist nur dann `enabled`, wenn `dhcpd/<interface>` einen aktiven `enable`-Marker besitzt.
3. Genau ein konfiguriert aktivierter Service pro Interface/IP-Familie wird `authoritative=true`.
4. Kea enabled + vorhandener Legacy-Block ohne `enable` → Kea authoritative, Legacy retained/disabled/non-authoritative.
5. Ausschließlich Legacy enabled → Legacy authoritative.
6. Zwei oder mehr configured-enabled DHCP-Services auf demselben Interface/IP-Familie → harter Konfigurationskonflikt / Build-Abbruch.
7. Es existiert kein erfundener Kea-Vorrang vor einem ebenfalls enabled ISC-Service.
8. Deaktivierte oder nur strukturell vorhandene DHCP-Blöcke sind niemals authoritative.

Service-Records nach der Resolution sind `DERIVED` und behalten ihre Source-Evidence.

## Scope-Zuordnung

### Legacy

Der Scope ist strukturell an seinen Container gebunden:

```text
/opnsense/dhcpd/lan  -> interface:lan
/opnsense/dhcpd/opt4 -> interface:opt4
```

### Kea

Eine Kea-Subnetz-Zuordnung wird nur erzeugt, wenn das Subnetz genau einem IPv4-Netz eines von Kea zugewiesenen Interfaces entspricht:

```text
Kea assigned interfaces
+
subnet4/subnet
+
parsed interface networks
        │
        ▼
exactly one match -> deterministic interfaceRef
```

Kein Match oder mehrere Matches werden nicht über Namen oder Reihenfolge geraten.

Scope-Records mit abgeleiteter Interface-Zuordnung sind `DERIVED` mit `dhcp.scope-interface.v1`.

## Pools

Verbindliche Validierungen für Phase 4.6:

- Start und Ende sind gültige IPv4-Adressen.
- `start <= end`.
- beide Grenzen liegen innerhalb des Scope-Subnetzes.
- eine Reservation darf außerhalb des dynamischen Pools liegen, solange sie innerhalb des Scope-Subnetzes liegt.

## Reservations

Kea-Reservations referenzieren ihren Scope über `reservation/subnet` auf die UUID eines `subnet4`-Records.

Der Reservation-Parser übernimmt ausschließlich Source-Facts:

- IP-Adresse
- MAC-Adresse
- Client-ID, soweit später im Modell benötigt
- Hostname
- Description
- Service-/Scope-Beziehung
- Evidence

Der Reservation-Parser leitet weder Vendor noch Device Type noch Model ab.

Reservations bleiben `CONFIRMED`, sofern Source- und Scope-Beziehung explizit belegt sind.

## Asset Builder – Phase 4.4

Phase 4.4 ist implementiert und auf Azure Pipelines für Windows und Linux verifiziert.

Identitätsregel:

```text
MAC vorhanden
-> MAC normalisieren
-> normalisierte MAC als bevorzugte Identitätsbasis

keine MAC
-> deterministische Reservation-/Scope-/IP-Identity-Tuple
```

Weitere Regeln:

- mehrere Reservations derselben normalisierten MAC werden zu einem Asset zusammengeführt
- IP-Adressen, Hostnames, Evidence und `sourceReservationRefs` werden deterministisch sortiert
- widersprüchliche Descriptions werden nicht geraten; `description=null`
- ungültige nichtleere MAC-Adressen führen zum harten Parserfehler
- Vendor, Device Type und Model bleiben vor Enrichment explizit `UNKNOWN`

## OUI Enrichment – Phase 4.5

### Kein Live-Lookup im normalen Build

Ein normaler Dokumentationsbuild verwendet keine externe OUI-API und lädt keine Registrierungsdaten aus dem Internet.

Der produktive Vertrag lautet:

```text
downloaded IEEE MA-L CSV
        │
        ▼
tools/update_oui_database.py
        │
        ├─ UTF-8 / LF normalisieren
        ├─ MA-L-Assignments deterministisch sortieren
        ├─ Snapshot SHA-256 berechnen
        └─ manifest.json erzeugen
        │
        ▼
data/oui/
├── oui-<version>.csv
└── manifest.json
        │
        ▼
normal build: read-only
```

Der Snapshot-Update ist ein kontrollierter Wartungsschritt außerhalb des normalen Dokumentbuilds.

### Manifest-/Hash-Vertrag

`manifest.json` enthält mindestens:

```text
schemaVersion
databaseVersion
registry = MA-L
file
sha256
entryCount
source.name
source.url
source.sourceSha256
```

Vor jeder Nutzung wird die SHA-256 des lokalen Snapshots gegen das Manifest geprüft. Abweichungen führen zum harten Fehler.

### Vendor-Attribution

Regel-ID:

```text
asset.vendor-oui.v1
```

Vendor wird nur `DERIVED`, wenn:

1. mindestens eine normalisierte Asset-MAC vorhanden ist,
2. die MAC ein globally administered unicast address ist,
3. der 24-Bit-MA-L-Prefix genau einem Eintrag des versionierten lokalen Snapshots entspricht,
4. alle verwertbaren Vendor-Matches desselben Assets denselben Organization-Namen liefern.

Andernfalls bleibt Vendor `UNKNOWN`.

Insbesondere werden **keine** Vendor-Werte aus lokal administrierten/randomisierten MAC-Adressen abgeleitet. Gruppen-/Multicast-Adressen, Broadcast, Null-MACs und unbekannte Prefixes bleiben ebenfalls `UNKNOWN`.

Die OUI-Evidence verwendet:

```text
sourceType = oui-database
sourceId   = <databaseVersion>:<snapshot-file>
path       = assignment:<MA-L-prefix>
sourceSha256 = <snapshot SHA-256>
```

## Confidence / Device-Type / Model Inference – Phase 4.5

Die bestehende Modellklassifikation ist zugleich der verbindliche Confidence-Vertrag:

```text
Vendor      via versioniertem OUI Match -> DERIVED
Device Type via versionierter Regel     -> INFERRED
Model       via versionierter Regel     -> INFERRED
kein belastbarer Match                  -> UNKNOWN
```

Es wird kein zusätzliches unversioniertes Confidence-Feld eingeführt.

Produktive Inference-Regeln liegen versioniert unter:

```text
data/rules/asset-inference.json
```

Der Vertrag enthält:

```text
schemaVersion
rulesetVersion
rules[]
```

Eine Regel enthält:

```text
id
target       = deviceType | model
sourceField  = hostnames | description | vendor
pattern      = regulärer Ausdruck
value        = deterministischer Zielwert
```

Regeln werden case-insensitive ausgewertet und deterministisch nach Rule-ID sortiert.

Mehrere Regeln dürfen denselben Zielwert bestätigen. Treffen jedoch Regeln mit unterschiedlichen Zielwerten auf dasselbe Asset zu, wird **keine Priorität geraten**; der Wert bleibt `UNKNOWN`.

Der initiale produktive Rule-Katalog ist absichtlich leer. Fachliche Inference-Regeln werden erst nach expliziter Freigabe ergänzt und erfordern Rule-ID/Ruleset-Version sowie Regressionstests. Die synthetischen Tests verwenden einen separaten versionierten Test-Ruleset, um die Engine einschließlich Konfliktverhalten zu prüfen.

## Synthetische Fixtures

DHCP-/Asset-Fixtures:

```text
tests/Fixtures/Parser/DHCP/
```

Enrichment-Fixtures:

```text
tests/Fixtures/Enrichment/OUI/
├── oui-test.csv
└── manifest.json

tests/Fixtures/Enrichment/Rules/
└── asset-inference-test.json
```

Die Enrichment-Fixtures sind vollständig synthetisch. Der OUI-Testdatensatz ist nur ein IEEE-formatiger Testvertrag und keine produktive Herstellerdatenbank.

## Kritische Regressionen

### Kea + deaktiviertes Legacy

```text
Kea enabled auf LAN
Legacy-LAN-Konfiguration vorhanden, aber disabled
-> Kea authoritative
-> Legacy retained but non-authoritative
-> Kea Pool bleibt produktiv relevant
```

### Active/Active DHCP

```text
Kea enabled auf LAN
+
ISC DHCP enabled auf LAN
-> keine erfundene Priorität
-> ParserError / BUILD FAILED
```

### OUI / Inference

```text
globally administered MAC + exakter lokaler OUI Match
-> Vendor DERIVED

locally administered/randomized MAC
-> Vendor UNKNOWN

kein OUI Match
-> Vendor UNKNOWN

genau eine versionierte Inference liefert einen Wert
-> Device Type / Model INFERRED

mehrere widersprüchliche Inference-Werte
-> UNKNOWN
```

## Schema-Preflight

`schemas/dhcp-assets.schema.json` kann Phase 4.5 ohne Schemaänderung ausdrücken:

- Asset Records
- Vendor / Device Type / Model als `attributedString`
- Evidence
- Derivation
- `UNKNOWN`

Schema-Version `1.0.0` bleibt bestehen.

## Verifikationsstand

- Phase 4.1 Testbasis: implementiert und Azure-CI Windows/Linux verifiziert.
- Phase 4.2 DHCP Fact Parser: implementiert und Azure-CI Windows/Linux verifiziert.
- Phase 4.3 Authoritative Service Resolution: implementiert und Azure-CI Windows/Linux verifiziert.
- Phase 4.4 Asset Builder: implementiert und Azure-CI Windows/Linux verifiziert.
- Phase 4.5 OUI-/Inference-Engine: Implementierung und synthetische Regressionen vorbereitet; Azure-CI-Verifikation ausstehend.
- Produktiver IEEE-MA-L-Snapshot: noch nicht provisioniert; ohne Snapshot bleibt Vendor deterministisch `UNKNOWN`.

## Noch offen

- Phase 4.5 Parser-/Enrichment-Regressionen auf Azure Ubuntu und Windows verifizieren
- produktiven IEEE-MA-L-Snapshot über `tools/update_oui_database.py` erzeugen und versioniert committen
- fachlich freigegebene produktive Device-Type-/Model-Regeln bei Bedarf ergänzen
- Phase 4.6 Conflict Validation für Pool-/Reservation-/Asset-Konflikte
- Proof-of-Concept-Gegenprüfung mit realer sanitisierter Konfiguration außerhalb des öffentlichen Tooling-Repositories
