from __future__ import annotations

import re
from typing import Any

try:
    from Parser.core import ParserError, ref, stable_id
except ImportError:  # direct execution with src/Parser on sys.path
    from core import ParserError, ref, stable_id


ASSET_RULE_ID = "asset.from-dhcp-reservation.v1"


def normalize_mac(value: str | None) -> str | None:
    """Return canonical lowercase colon-separated MAC or None when absent."""
    if value is None or not value.strip():
        return None
    compact = re.sub(r"[^0-9A-Fa-f]", "", value)
    if len(compact) != 12 or re.fullmatch(r"[0-9A-Fa-f]{12}", compact) is None:
        raise ParserError(f"Invalid DHCP reservation MAC address: {value}")
    compact = compact.lower()
    return ":".join(compact[index:index + 2] for index in range(0, 12, 2))


def _unknown_attribute() -> dict[str, Any]:
    return {
        "classification": "UNKNOWN",
        "value": None,
        "evidence": [],
    }


def _evidence_key(item: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(item.get("sourceType") or ""),
        str(item.get("sourceId") or ""),
        str(item.get("path") or ""),
        str(item.get("sourceSha256") or ""),
        str(item.get("note") or ""),
    )


def _merge_evidence(reservations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for reservation in reservations:
        for evidence in reservation.get("evidence") or []:
            unique.setdefault(_evidence_key(evidence), dict(evidence))
    result = list(unique.values())
    result.sort(key=_evidence_key)
    if not result:
        raise ParserError("Asset source reservation has no evidence")
    return result


def _single_description(reservations: list[dict[str, Any]]) -> str | None:
    values = sorted({
        str(value).strip()
        for value in (item.get("description") for item in reservations)
        if value is not None and str(value).strip()
    })
    return values[0] if len(values) == 1 else None


def _fallback_asset_id(reservation: dict[str, Any]) -> str:
    reservation_id = str(reservation.get("id") or "")
    ip_address = str(reservation.get("ipAddress") or "")
    scope_ref = reservation.get("scopeRef") or {}
    scope_id = str(scope_ref.get("id") or "scope:none")
    if not reservation_id:
        raise ParserError("DHCP reservation has no stable ID")
    if not ip_address:
        raise ParserError(f"DHCP reservation {reservation_id} has no IP address")
    return stable_id(
        "asset",
        identity_parts=["dhcp-reservation", reservation_id, scope_id, ip_address],
    )


def build_assets(reservations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build deterministic asset records from resolved DHCP reservations only.

    Phase 4.4 intentionally does not perform OUI or hostname-based enrichment.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    normalized_mac_by_group: dict[str, str | None] = {}

    for reservation in reservations:
        reservation_id = str(reservation.get("id") or "")
        ip_address = str(reservation.get("ipAddress") or "")
        if not reservation_id:
            raise ParserError("DHCP reservation has no stable ID")
        if not ip_address:
            raise ParserError(f"DHCP reservation {reservation_id} has no IP address")

        normalized_mac = normalize_mac(reservation.get("macAddress"))
        if normalized_mac is not None:
            asset_id = stable_id("asset", natural_id=f"mac-{normalized_mac}")
        else:
            asset_id = _fallback_asset_id(reservation)

        groups.setdefault(asset_id, []).append(reservation)
        normalized_mac_by_group[asset_id] = normalized_mac

    assets: list[dict[str, Any]] = []
    for asset_id in sorted(groups):
        members = sorted(groups[asset_id], key=lambda item: str(item["id"]))
        normalized_mac = normalized_mac_by_group[asset_id]
        reservation_ids = sorted({str(item["id"]) for item in members})
        ip_addresses = sorted({str(item["ipAddress"]) for item in members})
        hostnames = sorted({
            str(value).strip()
            for value in (item.get("hostname") for item in members)
            if value is not None and str(value).strip()
        })

        if normalized_mac is not None:
            basis = (
                f"DHCP reservations sharing normalized MAC {normalized_mac} are merged "
                "into one asset; MAC is the preferred asset identity."
            )
            mac_addresses = [normalized_mac]
        else:
            basis = (
                "DHCP reservation has no MAC address; asset identity is derived from "
                "the reservation, scope and IP identity tuple."
            )
            mac_addresses = []

        assets.append({
            "id": asset_id,
            "classification": "DERIVED",
            "evidence": _merge_evidence(members),
            "derivation": {
                "ruleId": ASSET_RULE_ID,
                "basis": basis,
                "inputRefs": reservation_ids,
            },
            "ipAddresses": ip_addresses,
            "macAddresses": mac_addresses,
            "hostnames": hostnames,
            "description": _single_description(members),
            "sourceReservationRefs": [
                ref(identifier, "dhcp-reservation") for identifier in reservation_ids
            ],
            "vendor": _unknown_attribute(),
            "deviceType": _unknown_attribute(),
            "model": _unknown_attribute(),
        })

    return assets
