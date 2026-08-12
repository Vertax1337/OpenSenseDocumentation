from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

try:
    from .core import ParseContext, bool_text, text
except ImportError:  # direct script/test execution
    from core import ParseContext, bool_text, text


def _split_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item for item in (part.strip() for part in re.split(r"[\s,;]+", value)) if item]


def _integer(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


def _legacy_enabled(node: ET.Element) -> bool:
    """Match OPNsense ISC DHCP enable-marker semantics without inventing state."""
    marker = node.find("enable")
    if marker is None:
        return False
    parsed = bool_text(text(marker))
    return True if parsed is None else parsed


def _parse_pool_ranges(value: str | None) -> list[dict[str, str | None]]:
    """Preserve pool text even when later validation must reject it."""
    if not value:
        return []
    result: list[dict[str, str | None]] = []
    for raw in (part.strip() for part in re.split(r"[\n,;]+", value)):
        if not raw:
            continue
        if "-" in raw:
            start, end = (part.strip() for part in raw.split("-", 1))
            result.append({"raw": raw, "start": start or None, "end": end or None})
        else:
            result.append({"raw": raw, "start": None, "end": None})
    return result


def _legacy_scope_fact(interface_node: ET.Element, ctx: ParseContext) -> dict[str, Any]:
    range_node = interface_node.find("range")
    start = text(range_node, "from") if range_node is not None else None
    end = text(range_node, "to") if range_node is not None else None
    pools = []
    if start or end:
        pools.append({"raw": f"{start or ''}-{end or ''}", "start": start, "end": end})
    return {
        "implementation": "isc-dhcpd",
        "interface": interface_node.tag,
        "sourceKey": f"isc-dhcpd-ipv4-{interface_node.tag}",
        "subnet": None,
        "pools": pools,
        "gateway": text(interface_node, "gateway"),
        "dnsServers": [value for node in interface_node.findall("dnsserver") if (value := text(node))],
        "domainName": text(interface_node, "domain"),
        "searchDomains": _split_values(text(interface_node, "domainsearchlist")),
        "ntpServers": [value for node in interface_node.findall("ntpserver") if (value := text(node))],
        "leaseTimeSeconds": _integer(text(interface_node, "defaultleasetime")),
        "evidence": ctx.evidence(interface_node),
    }


def _parse_legacy(root: ET.Element, ctx: ParseContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    services: list[dict[str, Any]] = []
    scopes: list[dict[str, Any]] = []
    reservations: list[dict[str, Any]] = []
    container = root.find("dhcpd")
    if container is None:
        return services, scopes, reservations

    for interface_node in list(container):
        interface_name = interface_node.tag
        services.append({
            "implementation": "isc-dhcpd",
            "interface": interface_name,
            "ipFamily": "IPv4",
            "enabled": _legacy_enabled(interface_node),
            "legacy": True,
            "evidence": ctx.evidence(interface_node),
        })
        scopes.append(_legacy_scope_fact(interface_node, ctx))

        for index, node in enumerate(interface_node.findall("staticmap"), start=1):
            reservations.append({
                "implementation": "isc-dhcpd",
                "sourceKey": node.attrib.get("uuid") or f"{interface_name}-staticmap-{index}",
                "scopeSourceKey": f"isc-dhcpd-ipv4-{interface_name}",
                "interface": interface_name,
                "ipAddress": text(node, "ipaddr"),
                "macAddress": text(node, "mac"),
                "clientId": text(node, "cid"),
                "hostname": text(node, "hostname"),
                "description": text(node, "descr"),
                "evidence": ctx.evidence(node),
            })

    return services, scopes, reservations


def _kea_options(subnet_node: ET.Element) -> dict[str, Any]:
    options = subnet_node.find("option_data")
    if options is None:
        return {
            "gateway": None,
            "dnsServers": [],
            "domainName": None,
            "searchDomains": [],
            "ntpServers": [],
        }
    return {
        "gateway": (_split_values(text(options, "routers")) or [None])[0],
        "dnsServers": _split_values(text(options, "domain_name_servers")),
        "domainName": text(options, "domain_name"),
        "searchDomains": _split_values(text(options, "domain_search")),
        "ntpServers": _split_values(text(options, "ntp_servers")),
    }


def _parse_kea(root: ET.Element, ctx: ParseContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    services: list[dict[str, Any]] = []
    scopes: list[dict[str, Any]] = []
    reservations: list[dict[str, Any]] = []
    dhcp4 = root.find("./OPNsense/Kea/dhcp4")
    if dhcp4 is None:
        return services, scopes, reservations

    general = dhcp4.find("general")
    global_enabled = bool_text(text(general, "enabled")) is True if general is not None else False
    assigned_interfaces = _split_values(text(general, "interfaces")) if general is not None else []
    lease_time = _integer(text(general, "valid_lifetime")) if general is not None else None
    service_evidence = ctx.evidence(general if general is not None else dhcp4)

    if assigned_interfaces:
        for interface_name in assigned_interfaces:
            services.append({
                "implementation": "kea",
                "interface": interface_name,
                "ipFamily": "IPv4",
                "enabled": global_enabled,
                "legacy": False,
                "evidence": service_evidence,
            })
    else:
        services.append({
            "implementation": "kea",
            "interface": None,
            "ipFamily": "IPv4",
            "enabled": global_enabled,
            "legacy": False,
            "evidence": service_evidence,
        })

    subnets = dhcp4.find("subnets")
    if subnets is not None:
        for index, node in enumerate(subnets.findall("subnet4"), start=1):
            source_key = node.attrib.get("uuid") or f"kea-subnet4-{index}"
            options = _kea_options(node)
            scopes.append({
                "implementation": "kea",
                "interface": None,
                "assignedInterfaces": list(assigned_interfaces),
                "sourceKey": source_key,
                "subnet": text(node, "subnet"),
                "pools": _parse_pool_ranges(text(node, "pools")),
                "gateway": options["gateway"],
                "dnsServers": options["dnsServers"],
                "domainName": options["domainName"],
                "searchDomains": options["searchDomains"],
                "ntpServers": options["ntpServers"],
                "leaseTimeSeconds": lease_time,
                "evidence": ctx.evidence(node),
            })

    reservation_container = dhcp4.find("reservations")
    if reservation_container is not None:
        for index, node in enumerate(reservation_container.findall("reservation"), start=1):
            reservations.append({
                "implementation": "kea",
                "sourceKey": node.attrib.get("uuid") or f"kea-reservation-{index}",
                "scopeSourceKey": text(node, "subnet"),
                "interface": None,
                "ipAddress": text(node, "ip_address"),
                "macAddress": text(node, "hw_address"),
                "clientId": text(node, "client_id"),
                "hostname": text(node, "hostname"),
                "description": text(node, "description"),
                "evidence": ctx.evidence(node),
            })

    return services, scopes, reservations


def parse_dhcp_facts(root: ET.Element, ctx: ParseContext) -> dict[str, list[dict[str, Any]]]:
    """Extract DHCP source facts only; authoritative resolution is Phase 4.3."""
    kea_services, kea_scopes, kea_reservations = _parse_kea(root, ctx)
    legacy_services, legacy_scopes, legacy_reservations = _parse_legacy(root, ctx)
    return {
        "services": kea_services + legacy_services,
        "scopes": kea_scopes + legacy_scopes,
        "reservations": kea_reservations + legacy_reservations,
    }
