# Phase 3 – Deterministischer Core Parser

## Ziel

Phase 3 überführt die dokumentationsrelevanten OPNsense-Kernobjekte aus `config.sanitized.xml` in das Canonical Infrastructure Model. Der Parser ist keine KI-Komponente und trifft keine freien Interpretationen.

## Laufzeit und Sprache

Der Core Parser ist in Python implementiert und benötigt zur Laufzeit nur die Python-Standardbibliothek. JSON-Schema-Validierung wird in Tests/CI mit den bereits versionierten CI-Abhängigkeiten durchgeführt.

Die Entscheidung trennt die Aufgaben bewusst:

```text
PowerShell Sanitizer
        ↓
config.sanitized.xml + sanitization-report.json
        ↓
Python Core Parser
        ↓
infrastructure-model.json
```

Der Sanitizer bleibt Windows-PowerShell-5.1/PowerShell-7-kompatibel; das Canonical Model kann anschließend plattformunabhängig erzeugt werden.

## Harte Eingangsbedingungen

Der Parser verarbeitet eine Datei nur, wenn:

1. `sanitization-report.json.status == Clean`
2. `residualFindings` leer oder nicht vorhanden sind
3. `report.output.sha256` exakt der tatsächlichen SHA-256 der XML entspricht
4. die XML ein `<opnsense>`-Root-Element besitzt

Damit kann keine veraltete, vertauschte oder ungeprüfte sanitisierte XML versehentlich dokumentiert werden.

## Phase-3-Datenbereiche

Deterministisch umgesetzt sind:

- System
- Interfaces
- statische IPv4-Netze aus Interface-IP + Prefix
- VLANs
- Aliases
- Gateways
- Static Routes
- IPsec Phase 1/2
- NAT: Outbound NAT, No-NAT und Port Forward
- Firewall Rules

Noch nicht Bestandteil dieser Phase:

- Kea/Legacy DHCP und Reservations
- Asset-/OUI-Enrichment
- vollständige DNS-/Unbound-Auswertung
- Services/Monitoring/Cron
- Zertifikatsdekodierung
- Business-Flow-Korrelation
- Findings Engine

Die entsprechenden Root-Bereiche werden schema-konform leer/default ausgegeben und in den späteren Phasen gefüllt.

## Evidence / Provenance

Jeder geparste technische Record erhält Evidence mit `sourceType`, `sourceId`, XML-Pfad und SHA-256 der sanitiserten Config. Damit bleibt jede Aussage auf die konkrete XML-Quelle zurückführbar.

## Stable IDs

Die Stable-ID-Strategie aus Phase 2 wird sprachgleich in Python umgesetzt. Priorität haben OPNsense UUIDs bzw. stabile natürliche IDs; nur wenn diese fehlen, wird eine SHA-256-ID aus einer expliziten Identity-Tuple gebildet.

Die Hash-Tuple verwendet dieselbe Length-Prefix-Strategie wie die PowerShell-Implementierung. Python- und Pester-Tests verwenden denselben festen Testvektor.

## Interfaces und Netze

WAN mit DHCP/DHCP6 wird als konfigurierter dynamischer Zustand gespeichert. Der Parser erfindet keine aktuelle WAN-Adresse.

Für statische IPv4-Interfaces wird das zugehörige Netz deterministisch abgeleitet, z. B. `192.0.2.1/24 -> 192.0.2.0/24`. Der Network Record ist `DERIVED` und enthält Derivation plus Evidence.

## VLAN-Referenzen

VLANs werden ausschließlich über explizite Device-Namen aus der Config mit Parent- und VLAN-Interface verknüpft. Ist eine Referenz nicht eindeutig auflösbar, wird sie nicht geraten, sondern als `unresolvedReference` erhalten.

## Aliases

Erfasst werden Name, Typ, Enabled, Dynamic, Resolved, Content und Description. Ein leerer Alias bleibt leer; externe/dynamische Aliases werden nicht als statisch aufgelöst dargestellt.

## Gateways und Static Routes

Static Routes referenzieren Gateway Records über Stable IDs. Wenn eine Route ein unbekanntes Gateway referenziert, bleibt die Zielreferenz erhalten und zusätzlich entsteht ein `unresolvedReference`.

## Route-based IPsec

Öffentliche Phase-1-Gegenstelle, VTI-Adressen, Tunnel-Interface und Gateway werden getrennt behandelt.

`VPN.remoteEndpoint` ist die öffentliche `phase1.remote-gateway`. Eine VTI-Verknüpfung wird nur hergestellt, wenn `phase2.tunnel_remote` exakt zu genau einem `gateway.address` passt. Nur dann werden `gatewayRef` und `tunnelInterfaceRef` gesetzt und `phase2.tunnel_local` als lokale VTI-Adresse am Interface ergänzt.

Keine Namensähnlichkeit oder wahrscheinliche Zuordnung ist zulässig.

## NAT / Firewall

`<disabled>1</disabled>` wird als `enabled=false` übernommen. Deaktivierte Regeln bleiben im Modell vorhanden.

Firewall Rules erhalten die originale XML-Reihenfolge als `order` (0-basiert).

OPNsense `associated-rule-id` wird deterministisch genutzt, um Port-Forward-NAT und zugehörige Firewall Rule bidirektional zu referenzieren. Die fachliche Business-Flow-Korrelation erfolgt erst in Phase 7.

## Unresolved References

Nicht auflösbare Beziehungen werden explizit gespeichert. Das zentrale Prinzip lautet: **Unknown wird erhalten, nicht erraten.**

## Reproduzierbarkeit

Die Tests prüfen unter anderem identischen Input, semantischen Fingerprint-Vergleich, JSON-Schema-Konformität, Stable IDs, WAN-DHCP ohne erfundene IP, VLAN-Referenzen, leere/dynamische Aliases, Gateway/Route/IPsec, NAT/Firewall Association, Disabled State, No-NAT Alias References, Unresolved References sowie Sanitizer-Status/SHA-Mismatch.

## CI

`.github/workflows/parser.yml` führt dieselben Parser-Regressionstests auf Ubuntu und Windows aus. Beide Runner vergleichen ihr Ergebnis gegen denselben versionierten semantischen Modell-Fingerprint.

## Definition of Done Phase 3

- [x] System wird geparst
- [x] Interfaces werden geparst
- [x] VLANs werden geparst
- [x] Gateways werden geparst
- [x] Static Routes werden geparst
- [x] Aliases werden geparst
- [x] Firewall wird geparst
- [x] NAT wird geparst
- [x] IPsec wird geparst
- [x] jeder Record besitzt Stable ID und Evidence
- [x] unbekannte Referenzen bleiben als `unresolvedReferences` erhalten
- [x] Parser-Ausgabe ist gegen das Canonical Schema validierbar
- [x] synthetische Regressionstests bestehen lokal
- [x] reale sanitisierte Proof-of-Concept-Config wurde lokal schema-valide verarbeitet
- [ ] GitHub CI erfolgreich verifiziert

Die letzte Checkbox wird erst gesetzt, wenn ein erfolgreicher Workflow-Run tatsächlich vorliegt.
