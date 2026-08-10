from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PARSER_VERSION = "0.1.0"
RULESET_VERSION = "0.0.0"
SCHEMA_VERSION = "1.0.0"
ID_STRATEGY_VERSION = "1.0.0"
CANONICALIZATION_VERSION = "1.0.0"


class ParserError(RuntimeError):
    pass


def text(node: ET.Element | None, child: str | None = None) -> str | None:
    if node is None:
        return None
    target = node.find(child) if child else node
    if target is None or target.text is None:
        return None
    value = target.text.strip()
    return value if value else None


def bool_text(value: str | None) -> bool | None:
    if value is None:
        return None
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if value in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return None


def enabled_from_disabled(node: ET.Element, default: bool = True) -> bool:
    value = bool_text(text(node, "disabled"))
    return default if value is None else not value


def natural_enabled(node: ET.Element, child: str = "enable", default: bool = False) -> bool:
    value = bool_text(text(node, child))
    return default if value is None else value


def normalize_token(value: str) -> str:
    token = value.strip().lower()
    token = re.sub(r"[^a-z0-9._~-]+", "-", token)
    token = re.sub(r"-{2,}", "-", token).strip("-")
    if not token:
        raise ParserError("Stable ID token is empty after normalization")
    return token


def stable_id(namespace: str, natural_id: str | None = None, identity_parts: Iterable[str] | None = None) -> str:
    """Match the Phase-2 PowerShell Stable-ID strategy exactly for the supported identity data."""
    namespace = normalize_token(namespace)
    if natural_id is not None:
        return f"{namespace}:{normalize_token(natural_id)}"
    if identity_parts is None:
        raise ParserError("Either natural_id or identity_parts is required")
    encoded: list[str] = []
    for part in identity_parts:
        if part is None:
            raise ParserError("Identity parts must not contain null")
        value = str(part)
        utf16_units = len(value.encode("utf-16-le")) // 2
        encoded.append(f"{utf16_units}:{value}")
    digest = hashlib.sha256("|".join(encoded).encode("utf-8")).hexdigest()[:24]
    return f"{namespace}:sha256:{digest}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def ref(identifier: str, type_name: str) -> dict[str, str]:
    return {"id": identifier, "type": type_name}


@dataclass
class ParseContext:
    input_path: Path
    report_path: Path
    source_sha: str
    source_id: str
    parent_map: dict[ET.Element, ET.Element]
    interface_by_name: dict[str, str]
    interface_by_device: dict[str, list[str]]
    alias_by_name: dict[str, str]
    gateway_by_name: dict[str, str]
    unresolved: list[dict[str, Any]]

    def xpath(self, node: ET.Element) -> str:
        parts: list[str] = []
        current: ET.Element | None = node
        while current is not None:
            parent = self.parent_map.get(current)
            if parent is None:
                parts.append(current.tag)
                break
            siblings = [child for child in list(parent) if child.tag == current.tag]
            parts.append(f"{current.tag}[{siblings.index(current)+1}]" if len(siblings) > 1 else current.tag)
            current = parent
        return "/" + "/".join(reversed(parts))

    def evidence(self, node: ET.Element, note: str | None = None) -> list[dict[str, Any]]:
        return [{
            "sourceType": "opnsense-config",
            "sourceId": self.source_id,
            "path": self.xpath(node),
            "sourceSha256": self.source_sha,
            "note": note,
        }]

    def add_unresolved(self, *, source_ref: dict[str, str], target_type: str, target_identifier: str, reason: str, node: ET.Element) -> None:
        identifier = stable_id("unresolved", identity_parts=[source_ref["id"], target_type, target_identifier, reason])
        if any(item["id"] == identifier for item in self.unresolved):
            return
        self.unresolved.append({
            "id": identifier,
            "sourceRef": source_ref,
            "targetType": target_type,
            "targetIdentifier": target_identifier,
            "reason": reason,
            "evidence": self.evidence(node),
        })


def resolve_interface_ref(ctx: ParseContext, token: str | None, source_ref: dict[str, str], node: ET.Element) -> dict[str, str] | None:
    if not token:
        return None
    if token in ctx.interface_by_name:
        return ref(ctx.interface_by_name[token], "interface")
    if token in ctx.interface_by_device:
        candidates = ctx.interface_by_device[token]
        if len(candidates) == 1:
            return ref(candidates[0], "interface")
        ctx.add_unresolved(source_ref=source_ref, target_type="interface", target_identifier=token, reason="Interface device maps to multiple parsed logical interfaces", node=node)
        return None
    ctx.add_unresolved(source_ref=source_ref, target_type="interface", target_identifier=token, reason="Interface reference does not match a parsed interface name or device", node=node)
    return None


def network_endpoint(ctx: ParseContext, node: ET.Element | None, source_ref: dict[str, str]) -> dict[str, Any]:
    if node is None:
        return {"kind": "unknown", "value": None, "ref": None}
    if node.find("any") is not None:
        return {"kind": "any", "value": None, "ref": None}
    address = text(node, "address")
    if address:
        kind = "network" if "/" in address and not address.endswith("/32") and not address.endswith("/128") else "host"
        return {"kind": kind, "value": address, "ref": None}
    network = text(node, "network")
    if network:
        logical = network[:-2] if network.endswith("ip") and network[:-2] in ctx.interface_by_name else network
        if logical in ctx.interface_by_name:
            return {"kind": "interface", "value": network, "ref": ref(ctx.interface_by_name[logical], "interface")}
        if network in ctx.alias_by_name:
            return {"kind": "alias", "value": network, "ref": ref(ctx.alias_by_name[network], "alias")}
        try:
            ipaddress.ip_network(network, strict=False)
            return {"kind": "network", "value": network, "ref": None}
        except ValueError:
            pass
        ctx.add_unresolved(source_ref=source_ref, target_type="alias-or-interface", target_identifier=network, reason="Network token does not match a parsed interface or alias", node=node)
        return {"kind": "unknown", "value": network, "ref": None}
    return {"kind": "unknown", "value": None, "ref": None}


def port_spec(value: str | None) -> dict[str, Any]:
    if not value:
        return {"kind": "any", "value": None}
    value = value.strip()
    if ":" in value or "-" in value:
        return {"kind": "range", "value": value}
    if value.isdigit():
        return {"kind": "single", "value": value}
    return {"kind": "alias", "value": value}


def load_and_verify_report(input_path: Path, report_path: Path) -> tuple[dict[str, Any], str]:
    try:
        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise ParserError(f"Could not read sanitization report: {exc}") from exc
    if report.get("status") != "Clean":
        raise ParserError("Sanitization report status must be Clean before parsing")
    if report.get("residualFindings"):
        raise ParserError("Sanitization report contains residual findings")
    actual_sha = sha256_file(input_path)
    expected_sha = str((report.get("output") or {}).get("sha256") or "").upper()
    if not expected_sha:
        raise ParserError("Sanitization report does not contain output.sha256")
    if actual_sha != expected_sha:
        raise ParserError(f"Sanitized XML SHA-256 does not match report: actual={actual_sha} expected={expected_sha}")
    return report, actual_sha
