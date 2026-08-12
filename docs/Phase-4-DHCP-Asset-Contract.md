# Phase 4 – DHCP / Asset Inventory Contract

## Status

Phase 4.1 definiert den verbindlichen DHCP-/Asset-Vertrag und die synthetische Regressionstestbasis. Der produktive DHCP-Parser, die Authoritative-Service-Resolution, der Asset Builder, OUI-Enrichment und die Conflict Validation werden erst in den nachfolgenden Teilphasen implementiert.

Der bestehende Canonical-Model-Contract `1.0.0` bleibt für diesen Schritt unverändert. Es ist aktuell keine Schema-Erweiterung erforderlich.

## Architekturgrenze

Phase 4 bleibt in die bereits beschlossene Verarbeitungskette eingebettet:

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

Der Parser darf weder aktive DHCP-Implementierungen noch Gerätetypen aus Wahrscheinlichkeiten bestimmen. Unklare Zuordnungen werden nicht geraten.

## Source-Struktur

Die Phase-4-Fixtures orientieren sich an der strukturellen Form eines sanitisierten OPNsense-Exports. Kundenspezifische Werte werden nicht übernommen.

### Kea DHCPv4

Kea DHCPv4 wird unter folgendem Pfad erwartet:

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

Legacy DHCP wird unter folgendem Pfad erwartet:

```text
/opnsense/dhcpd/<interface>
```

Ein vorhandener Legacy-Block ist zunächst ein Konfigurations-Fact. Für Phase 4 gilt ein Legacy-Service nur dann als `enabled`, wenn der jeweilige Interface-Block einen aktiv ausgewerteten `enable`-Marker besitzt. Ein vorhandener Block ohne Enable-Marker bleibt erhalten, wird aber nicht als aktiver Dienst interpretiert.

## Service-Kardinalität

Obwohl `dhcpServiceRecord.interfaceRefs` im Schema ein Array ist, emittiert Phase 4 für IPv4 genau einen Service-Record pro Kombination aus:

```text
DHCP implementation + interface + IP family
```

Damit enthält `interfaceRefs` bei durch Phase 4 erzeugten Records genau einen Eintrag.

Beispiele:

```text
dhcp-service:kea-ipv4-lan
dhcp-service:isc-dhcpd-ipv4-lan
dhcp-service:isc-dhcpd-ipv4-opt4
```

Diese Kardinalitätsregel ermöglicht eine eindeutige Authoritative-Service-Resolution pro Interface ohne Änderung des bestehenden Schema-Shape.

## Authoritative Service Resolution

Die endgültige Eigenschaft `authoritative` ist kein frei interpretierter Source-Wert. Sie wird deterministisch durch das versionierte Regelwerk `dhcp.authority.v1` bestimmt.

Für IPv4 gilt:

1. Kea ist auf einem Interface nur dann enabled, wenn `general/enabled` aktiv ist und das Interface explizit in `general/interfaces` aufgeführt wird.
2. Ein aktivierter Kea-Service hat für dieses Interface Vorrang.
3. Parallel vorhandene Legacy-Konfiguration bleibt erhalten, wird dort aber `authoritative=false`.
4. Existiert kein aktivierter Kea-Service und genau ein aktivierter Legacy-Service, ist dieser authoritative.
5. Deaktivierte bzw. nur noch strukturell vorhandene Legacy-Blöcke sind niemals authoritative.
6. Eine nicht eindeutig auflösbare aktive Situation darf nicht geraten werden und muss in der Validierungsphase zum harten Fehler führen.

Service-Records nach der Resolution sind `DERIVED`, weil `authoritative` aus mehreren Source-Facts und einer versionierten Regel entsteht. Die ursprüngliche Source-Evidence bleibt erhalten.

## Scope-Zuordnung

### Legacy

Der Legacy-Scope ist strukturell an seinen Container gebunden:

```text
/opnsense/dhcpd/lan     -> interface:lan
/opnsense/dhcpd/opt4    -> interface:opt4
```

### Kea

Ein Kea-Subnetz enthält nicht zwingend selbst einen logischen OPNsense-Interface-Namen. Die Zuordnung wird ausschließlich dann erzeugt, wenn das Subnetz genau einem IPv4-Netz eines von Kea zugewiesenen Interfaces entspricht.

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

Kein Match oder mehrere Matches werden nicht durch Namen oder Reihenfolge aufgelöst. Diese Fälle werden als unresolved/validation-relevant erhalten.

Scope-Records mit deterministisch abgeleiteter Interface-Zuordnung sind `DERIVED` mit Regel `dhcp.scope-interface.v1`.

## Pools

Phase 4 behandelt den Pool als IPv4-Range mit `start` und `end`.

Verbindliche Validierungen:

- Start und Ende müssen gültige IPv4-Adressen sein.
- `start <= end`.
- beide Grenzen müssen innerhalb des Scope-Subnetzes liegen.
- eine Reservation darf außerhalb des dynamischen Pools liegen, solange sie innerhalb des Scope-Subnetzes liegt.

## Reservations

Kea-Reservations referenzieren ihren Scope explizit über den Wert in `reservation/subnet`, der auf die UUID eines `subnet4`-Records zeigt.

Der Reservation-Parser übernimmt ausschließlich Source-Facts:

- IP-Adresse
- MAC-Adresse
- Client-ID, soweit später im Modell benötigt
- Hostname
- Description
- Service-/Scope-Beziehung
- Evidence

Der Reservation-Parser leitet weder Vendor noch Device Type noch Model ab.

Reservations bleiben `CONFIRMED`, sofern ihre Source- und Scope-Beziehung explizit aus der Konfiguration belegt ist.

## Asset Builder

Der Asset Builder wird erst in Phase 4.4 implementiert. Verbindliche Identitätsregel:

```text
MAC vorhanden
-> normalisierte MAC als bevorzugte Identitätsbasis

keine MAC
-> deterministische Reservation-/Scope-/IP-Identity-Tuple
```

Vendor, Device Type und Model werden getrennt attribuiert. `UNKNOWN` ist ein zulässiger Endzustand.

## Synthetische Fixtures

Die Testbasis liegt unter:

```text
tests/Fixtures/Parser/DHCP/
```

| Fixture | Zweck |
|---|---|
| `legacy-only.xml` | aktiver Legacy-DHCP als alleinige Implementierung |
| `kea-only.xml` | aktiver Kea-DHCP als alleinige Implementierung |
| `kea-and-legacy.xml` | kritische Regression: Kea gewinnt auf LAN, Legacy bleibt erhalten |
| `kea-reservations.xml` | Kea-Reservation-Shape und explizite Subnet-Referenzen |
| `duplicate-ip.xml` | gleiche Reservation-IP mit unterschiedlichen MACs |
| `invalid-pool.xml` | Pool Start größer Pool Ende |
| `reservation-outside-pool.xml` | zulässige Reservation außerhalb des dynamischen Pools, aber innerhalb des Subnetzes |
| `asset-enrichment.xml` | synthetische Asset-Basis ohne echte Kundendaten |
| `mixed-interface-authority.xml` | Kea auf einem Interface, Legacy auf mehreren Interfaces; Resolution muss pro Interface erfolgen |
| `pool-outside-subnet.xml` | Pool liegt außerhalb des Scope-Subnetzes |

Alle Fixtures verwenden ausschließlich Dokumentationsnetze, synthetische Hostnamen und lokal administrierte Test-MACs.

## Golden Contract

`tests/Expected/DHCP/kea-and-legacy.expected.json` definiert den fachlichen Golden Contract für die kritische Regression.

Erwartung:

```text
Kea + Legacy auf LAN
-> Kea enabled=true
-> Kea authoritative=true
-> Legacy LAN retained
-> Legacy LAN authoritative=false
-> Kea Pool ist der produktiv relevante Pool
-> Legacy Pool überschreibt den Kea Pool niemals
```

Der Golden Contract ist ein fokussierter `dhcpModel`-Contract und kein vollständiges `infrastructure-model.json`. Dadurch kann Phase 4.1 den Vertrag prüfen, bevor Phase 4.2 den produktiven Parser implementiert.

## Schema-Preflight

Der vorhandene Schema-Vertrag `schemas/dhcp-assets.schema.json` kann die für Phase 4 benötigten Objekte bereits ausdrücken:

- DHCP Services
- Scopes
- Pools
- Reservations
- Assets
- Attribution für Vendor / Device Type / Model

Die pro-Interface-Semantik wird über die oben definierte Record-Kardinalität hergestellt. Deshalb ist für Phase 4.1 keine Änderung an Schema-Version `1.0.0` erforderlich.

Eine spätere Schemaänderung ist nur zulässig, wenn eine konkrete Parser-/Validierungsanforderung mit dem bestehenden Vertrag nicht ausdrückbar ist. In diesem Fall gilt weiterhin: Schema und Fixtures zuerst, Parser danach.

## Noch offen

- Phase 4.2: Kea-/Legacy-DHCP-Parser
- Phase 4.3: Authoritative Service Resolution als produktive Rule-Komponente
- Phase 4.4: Asset Builder
- Phase 4.5: versioniertes OUI-Enrichment und Inference-Regeln
- Phase 4.6: Conflict Validation
- Windows-/Linux-CI-Verifikation der implementierten Phase-4-Funktion
- Proof-of-Concept-Gegenprüfung mit realer sanitisierter Konfiguration außerhalb des öffentlichen Tooling-Repositories
