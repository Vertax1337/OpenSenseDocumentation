from __future__ import annotations

import ipaddress
from typing import Any

try:
    from Parser.core import ParserError, ref, stable_id
except ImportError:  # direct execution from src/Parser on sys.path
    from core import ParserError, ref, stable_id


AUTHORITY_RULE_ID = "dhcp.authority.v1"
SCOPE_INTERFACE_RULE_ID = "dhcp.scope-interface.v1"


def _service_id(implementation: str, ip_family: str, interface_name: str) -> str:
    family_token = "ipv4" if ip_family == "IPv4" else "ipv6"
    return stable_id("dhcp-service", natural_id=f"{implementation}-{family_token}-{interface_name}")


def _scope_id(source_key: str) -> str:
    return stable_id("dhcp-scope", natural_id=source_key)


def _reservation_id(source_key: str) -> str:
    return stable_id("dhcp-reservation", natural_id=source_key)


def _ipv4_network(value: str) -> ipaddress.IPv4Network:
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise ParserError(f"Invalid DHCP IPv4 subnet: {value}") from exc
    if not isinstance(network, ipaddress.IPv4Network):
        raise ParserError(f"DHCP scope is not IPv4: {value}")
    return network


def _authority_basis(
    service: dict[str, Any],
    group: list[dict[str, Any]],
    authoritative: bool,
) -> str:
    interface_name = str(service["interface"])
    implementation = str(service["implementation"])
    enabled = bool(service["enabled"])

    if authoritative and implementation == "kea":
        return (
            f"Kea DHCPv4 is enabled and explicitly assigned to {interface_name}; "
            "Kea takes precedence over legacy DHCP on the same interface."
        )
    if authoritative:
        return (
            f"{implementation} is the only enabled DHCP implementation for "
            f"{interface_name}/IPv4."
        )
    if implementation == "isc-dhcpd" and enabled and any(
        item["implementation"] == "kea" and item["enabled"] for item in group
    ):
        return (
            f"Legacy DHCP is enabled on {interface_name} but remains non-authoritative "
            "because enabled Kea DHCPv4 is assigned to the same interface."
        )
    if implementation == "isc-dhcpd" and not enabled and any(
        item["implementation"] == "kea" and item["enabled"] for item in group
    ):
        return (
            f"Legacy DHCP configuration is retained for {interface_name} but is disabled; "
            "enabled Kea DHCPv4 is assigned to the same interface."
        )
    if not enabled:
        return (
            f"{implementation} DHCP configuration is retained for {interface_name} "
            "but is disabled and therefore non-authoritative."
        )
    return (
        f"{implementation} DHCP remains non-authoritative for {interface_name}/IPv4 "
        f"under {AUTHORITY_RULE_ID}."
    )


def _resolve_services(
    facts: list[dict[str, Any]],
    interface_by_name: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str, str], dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for fact in facts:
        interface_name = fact.get("interface")
        ip_family = str(fact.get("ipFamily") or "IPv4")
        if not interface_name:
            if fact.get("enabled"):
                raise ParserError(
                    f"Enabled {fact.get('implementation')} DHCP {ip_family} has no assigned interface"
                )
            continue
        if interface_name not in interface_by_name:
            raise ParserError(
                f"DHCP service references unknown interface: {interface_name}"
            )
        grouped.setdefault((str(interface_name), ip_family), []).append(fact)

    services: list[dict[str, Any]] = []
    service_map: dict[tuple[str, str, str], dict[str, Any]] = {}

    for (interface_name, ip_family), group in sorted(grouped.items()):
        enabled_kea = [
            item for item in group
            if item.get("implementation") == "kea" and bool(item.get("enabled"))
        ]
        enabled_non_kea = [
            item for item in group
            if item.get("implementation") != "kea" and bool(item.get("enabled"))
        ]

        if len(enabled_kea) > 1:
            raise ParserError(
                f"Ambiguous DHCP authority on {interface_name}/{ip_family}: "
                "multiple enabled Kea services"
            )

        authoritative_fact: dict[str, Any] | None = None
        if enabled_kea:
            non_legacy_competitors = [
                item for item in enabled_non_kea
                if item.get("implementation") != "isc-dhcpd"
            ]
            if non_legacy_competitors:
                raise ParserError(
                    f"Ambiguous DHCP authority on {interface_name}/{ip_family}: "
                    "enabled Kea and another non-legacy implementation"
                )
            authoritative_fact = enabled_kea[0]
        else:
            if len(enabled_non_kea) > 1:
                raise ParserError(
                    f"Ambiguous DHCP authority on {interface_name}/{ip_family}: "
                    "multiple enabled non-Kea services"
                )
            authoritative_fact = enabled_non_kea[0] if enabled_non_kea else None

        interface = interface_by_name[interface_name]
        interface_id = str(interface["id"])

        for fact in group:
            implementation = str(fact["implementation"])
            key = (implementation, ip_family, interface_name)
            if key in service_map:
                raise ParserError(
                    f"Duplicate DHCP service fact for {implementation}/{interface_name}/{ip_family}"
                )
            identifier = _service_id(implementation, ip_family, interface_name)
            authoritative = fact is authoritative_fact
            record = {
                "id": identifier,
                "classification": "DERIVED",
                "evidence": list(fact["evidence"]),
                "derivation": {
                    "ruleId": AUTHORITY_RULE_ID,
                    "basis": _authority_basis(fact, group, authoritative),
                    "inputRefs": [interface_id],
                },
                "implementation": implementation,
                "enabled": bool(fact.get("enabled")),
                "authoritative": authoritative,
                "interfaceRefs": [ref(interface_id, "interface")],
                "legacy": bool(fact.get("legacy")),
            }
            services.append(record)
            service_map[key] = record

    services.sort(key=lambda item: item["id"])
    return services, service_map


def _networks_for_interface(
    networks: list[dict[str, Any]],
    interface_id: str,
) -> list[ipaddress.IPv4Network]:
    result: list[ipaddress.IPv4Network] = []
    for network in networks:
        interface_ref = network.get("interfaceRef") or {}
        if interface_ref.get("id") != interface_id:
            continue
        cidr = network.get("cidr")
        if not cidr:
            continue
        parsed = _ipv4_network(str(cidr))
        if parsed not in result:
            result.append(parsed)
    return result


def _pool_records(raw_pools: list[dict[str, Any]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for pool in raw_pools:
        start = pool.get("start")
        end = pool.get("end")
        if not start or not end:
            raise ParserError(
                f"DHCP pool cannot be represented in the canonical model: {pool.get('raw')!r}"
            )
        result.append({"start": str(start), "end": str(end)})
    return result


def _resolve_scopes(
    facts: list[dict[str, Any]],
    services: dict[tuple[str, str, str], dict[str, Any]],
    interfaces: dict[str, dict[str, Any]],
    networks: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    scopes: list[dict[str, Any]] = []
    scope_map: dict[tuple[str, str], dict[str, Any]] = {}

    for fact in facts:
        implementation = str(fact["implementation"])
        source_key = str(fact["sourceKey"])

        if implementation == "isc-dhcpd":
            interface_name = str(fact.get("interface") or "")
            if interface_name not in interfaces:
                raise ParserError(
                    f"Legacy DHCP scope references unknown interface: {interface_name}"
                )
            interface = interfaces[interface_name]
            interface_id = str(interface["id"])
            candidates = _networks_for_interface(networks, interface_id)
            if len(candidates) != 1:
                raise ParserError(
                    f"Legacy DHCP scope on {interface_name} requires exactly one parsed IPv4 network; "
                    f"found {len(candidates)}"
                )
            subnet = str(candidates[0])
        elif implementation == "kea":
            raw_subnet = fact.get("subnet")
            if not raw_subnet:
                raise ParserError(f"Kea DHCP scope {source_key} has no subnet")
            subnet_network = _ipv4_network(str(raw_subnet))
            assigned = [str(item) for item in fact.get("assignedInterfaces") or []]
            matches: list[str] = []
            for interface_name in assigned:
                interface = interfaces.get(interface_name)
                if interface is None:
                    continue
                interface_networks = _networks_for_interface(
                    networks, str(interface["id"])
                )
                if subnet_network in interface_networks:
                    matches.append(interface_name)
            if len(matches) != 1:
                raise ParserError(
                    f"Kea DHCP scope {source_key} must match exactly one assigned interface network; "
                    f"found {len(matches)}"
                )
            interface_name = matches[0]
            interface = interfaces[interface_name]
            interface_id = str(interface["id"])
            subnet = str(subnet_network)
        else:
            raise ParserError(
                f"Unsupported DHCP scope implementation in Phase 4.3: {implementation}"
            )

        service_key = (implementation, "IPv4", interface_name)
        service = services.get(service_key)
        if service is None:
            raise ParserError(
                f"DHCP scope {source_key} has no resolved service for "
                f"{implementation}/{interface_name}/IPv4"
            )

        identifier = _scope_id(source_key)
        input_refs = [str(service["id"]), interface_id]
        record = {
            "id": identifier,
            "classification": "DERIVED",
            "evidence": list(fact["evidence"]),
            "derivation": {
                "ruleId": SCOPE_INTERFACE_RULE_ID,
                "basis": (
                    "Legacy DHCP scope is structurally bound to its interface block."
                    if implementation == "isc-dhcpd"
                    else "Kea subnet uniquely matches the parsed IPv4 network of one Kea-assigned interface."
                ),
                "inputRefs": input_refs,
            },
            "serviceRef": ref(str(service["id"]), "dhcp-service"),
            "interfaceRef": ref(interface_id, "interface"),
            "subnet": subnet,
            "pools": _pool_records(list(fact.get("pools") or [])),
            "gateway": fact.get("gateway"),
            "dnsServers": list(fact.get("dnsServers") or []),
            "domainName": fact.get("domainName"),
            "searchDomains": list(fact.get("searchDomains") or []),
            "ntpServers": list(fact.get("ntpServers") or []),
            "leaseTimeSeconds": fact.get("leaseTimeSeconds"),
        }
        key = (implementation, source_key)
        if key in scope_map:
            raise ParserError(
                f"Duplicate DHCP scope source key for {implementation}: {source_key}"
            )
        scopes.append(record)
        scope_map[key] = record

    scopes.sort(key=lambda item: item["id"])
    return scopes, scope_map


def _resolve_reservations(
    facts: list[dict[str, Any]],
    scopes: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    reservations: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for fact in facts:
        implementation = str(fact["implementation"])
        source_key = str(fact["sourceKey"])
        scope_source_key = fact.get("scopeSourceKey")
        if not scope_source_key:
            raise ParserError(
                f"DHCP reservation {source_key} has no scope reference"
            )
        scope = scopes.get((implementation, str(scope_source_key)))
        if scope is None:
            raise ParserError(
                f"DHCP reservation {source_key} references unknown scope "
                f"{scope_source_key}"
            )
        ip_address = fact.get("ipAddress")
        if not ip_address:
            raise ParserError(
                f"DHCP reservation {source_key} has no IP address"
            )

        identifier = _reservation_id(source_key)
        if identifier in seen_ids:
            raise ParserError(f"Duplicate DHCP reservation ID: {identifier}")
        seen_ids.add(identifier)

        reservations.append({
            "id": identifier,
            "classification": "CONFIRMED",
            "evidence": list(fact["evidence"]),
            "serviceRef": dict(scope["serviceRef"]),
            "scopeRef": ref(str(scope["id"]), "dhcp-scope"),
            "ipAddress": str(ip_address),
            "macAddress": fact.get("macAddress"),
            "hostname": fact.get("hostname"),
            "description": fact.get("description"),
        })

    reservations.sort(key=lambda item: item["id"])
    return reservations


def resolve_dhcp_model(
    facts: dict[str, list[dict[str, Any]]],
    interfaces: list[dict[str, Any]],
    networks: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Resolve parsed DHCP facts into the canonical DHCP model.

    Authority is resolved per interface and IP family. Kea takes precedence over
    legacy ISC DHCP only when Kea is enabled and explicitly assigned to that
    interface. Ambiguous active configurations fail instead of being guessed.
    """
    interface_by_name = {
        str(item["name"]): item for item in interfaces if item.get("name")
    }
    services, service_map = _resolve_services(
        list(facts.get("services") or []), interface_by_name
    )
    scopes, scope_map = _resolve_scopes(
        list(facts.get("scopes") or []),
        service_map,
        interface_by_name,
        networks,
    )
    reservations = _resolve_reservations(
        list(facts.get("reservations") or []), scope_map
    )
    return {
        "services": services,
        "scopes": scopes,
        "reservations": reservations,
    }
