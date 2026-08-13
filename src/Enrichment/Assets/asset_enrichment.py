from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from Parser.core import ParserError
except ImportError:  # direct execution with src/Parser on sys.path
    from core import ParserError

try:
    from Enrichment.OUI.oui import OUI_VENDOR_RULE_ID, OuiDatabase, load_oui_database
except ImportError:  # direct execution with src/Enrichment/Assets on sys.path
    oui_path = Path(__file__).resolve().parents[1] / "OUI"
    import sys
    if str(oui_path) not in sys.path:
        sys.path.insert(0, str(oui_path))
    from oui import OUI_VENDOR_RULE_ID, OuiDatabase, load_oui_database


INFERENCE_RULE_SCHEMA_VERSION = "1.0.0"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_oui_manifest_path() -> Path:
    return _repo_root() / "data" / "oui" / "manifest.json"


def default_inference_rules_path() -> Path:
    return _repo_root() / "data" / "rules" / "asset-inference.json"


def _unknown_attribute() -> dict[str, Any]:
    return {
        "classification": "UNKNOWN",
        "value": None,
        "evidence": [],
    }


@dataclass(frozen=True)
class InferenceRule:
    rule_id: str
    target: str
    source_field: str
    pattern_text: str
    value: str
    pattern: re.Pattern[str]


@dataclass(frozen=True)
class InferenceRuleset:
    ruleset_version: str
    file_name: str
    file_sha256: str
    rules: tuple[InferenceRule, ...]


def load_inference_rules(path: str | Path) -> InferenceRuleset:
    path = Path(path).resolve()
    if not path.is_file():
        raise ParserError(f"Asset inference rules not found: {path}")

    raw = path.read_bytes()
    file_sha = hashlib.sha256(raw).hexdigest().upper()
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ParserError(f"Invalid asset inference rule file: {path}") from exc

    if document.get("schemaVersion") != INFERENCE_RULE_SCHEMA_VERSION:
        raise ParserError(
            f"Unsupported asset inference schemaVersion: {document.get('schemaVersion')!r}"
        )
    ruleset_version = str(document.get("rulesetVersion") or "").strip()
    if not ruleset_version:
        raise ParserError("Asset inference rulesetVersion is required")
    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list):
        raise ParserError("Asset inference rules must be an array")

    allowed_targets = {"deviceType", "model"}
    allowed_source_fields = {"hostnames", "description", "vendor"}
    seen_ids: set[str] = set()
    rules: list[InferenceRule] = []
    for item in raw_rules:
        if not isinstance(item, dict):
            raise ParserError("Each asset inference rule must be an object")
        rule_id = str(item.get("id") or "").strip()
        target = str(item.get("target") or "").strip()
        source_field = str(item.get("sourceField") or "").strip()
        pattern_text = str(item.get("pattern") or "")
        value = str(item.get("value") or "").strip()

        if not rule_id:
            raise ParserError("Asset inference rule id is required")
        if rule_id in seen_ids:
            raise ParserError(f"Duplicate asset inference rule id: {rule_id}")
        seen_ids.add(rule_id)
        if target not in allowed_targets:
            raise ParserError(f"Unsupported asset inference target: {target}")
        if source_field not in allowed_source_fields:
            raise ParserError(
                f"Unsupported asset inference sourceField: {source_field}"
            )
        if not pattern_text:
            raise ParserError(f"Asset inference rule {rule_id} has no pattern")
        if not value:
            raise ParserError(f"Asset inference rule {rule_id} has no value")
        try:
            compiled = re.compile(pattern_text, re.IGNORECASE)
        except re.error as exc:
            raise ParserError(
                f"Invalid regex in asset inference rule {rule_id}: {exc}"
            ) from exc
        rules.append(
            InferenceRule(
                rule_id=rule_id,
                target=target,
                source_field=source_field,
                pattern_text=pattern_text,
                value=value,
                pattern=compiled,
            )
        )

    rules.sort(key=lambda item: item.rule_id)
    return InferenceRuleset(
        ruleset_version=ruleset_version,
        file_name=path.name,
        file_sha256=file_sha,
        rules=tuple(rules),
    )


def _vendor_attribute(asset: dict[str, Any], database: OuiDatabase | None) -> dict[str, Any]:
    if database is None:
        return _unknown_attribute()

    matches: list[tuple[str, str, str]] = []
    for mac_address in sorted(set(asset.get("macAddresses") or [])):
        result = database.lookup(str(mac_address))
        if result is None:
            continue
        assignment, organization = result
        matches.append((organization, assignment, str(mac_address)))

    organizations = sorted({organization for organization, _, _ in matches})
    if len(organizations) != 1:
        return _unknown_attribute()

    organization = organizations[0]
    matched = sorted(
        [item for item in matches if item[0] == organization],
        key=lambda item: (item[1], item[2]),
    )
    evidence_by_assignment: dict[str, dict[str, Any]] = {}
    for _, assignment, _ in matched:
        evidence_by_assignment.setdefault(
            assignment,
            database.evidence(assignment),
        )

    matched_macs = ", ".join(item[2] for item in matched)
    assignments = ", ".join(sorted(evidence_by_assignment))
    return {
        "classification": "DERIVED",
        "value": organization,
        "evidence": [
            evidence_by_assignment[key] for key in sorted(evidence_by_assignment)
        ],
        "derivation": {
            "ruleId": OUI_VENDOR_RULE_ID,
            "basis": (
                f"Globally administered unicast MAC address(es) {matched_macs} "
                f"match MA-L assignment(s) {assignments} in OUI database "
                f"{database.database_version}."
            ),
            "inputRefs": [str(asset["id"])],
        },
    }


def _source_values(asset: dict[str, Any], field: str) -> list[str]:
    if field == "hostnames":
        return sorted({
            str(value).strip()
            for value in asset.get("hostnames") or []
            if value is not None and str(value).strip()
        })
    if field == "description":
        value = asset.get("description")
        return [str(value).strip()] if value is not None and str(value).strip() else []
    if field == "vendor":
        vendor = asset.get("vendor") or {}
        if vendor.get("classification") == "UNKNOWN":
            return []
        value = vendor.get("value")
        return [str(value).strip()] if value is not None and str(value).strip() else []
    raise ParserError(f"Unsupported asset inference source field: {field}")


def _inferred_attribute(
    asset: dict[str, Any],
    target: str,
    ruleset: InferenceRuleset | None,
) -> dict[str, Any]:
    if ruleset is None:
        return _unknown_attribute()

    matches: list[tuple[InferenceRule, str]] = []
    for rule in ruleset.rules:
        if rule.target != target:
            continue
        for value in _source_values(asset, rule.source_field):
            if rule.pattern.search(value):
                matches.append((rule, value))

    inferred_values = sorted({rule.value for rule, _ in matches})
    if len(inferred_values) != 1:
        return _unknown_attribute()

    inferred_value = inferred_values[0]
    matching_rules = sorted(
        {
            rule.rule_id: rule
            for rule, _ in matches
            if rule.value == inferred_value
        }.values(),
        key=lambda item: item.rule_id,
    )
    matched_inputs = sorted({
        f"{rule.source_field}={value}"
        for rule, value in matches
        if rule.value == inferred_value
    })

    evidence = [
        {
            "sourceType": "rule-engine",
            "sourceId": f"{ruleset.ruleset_version}:{ruleset.file_name}",
            "path": f"/rules/{rule.rule_id}",
            "sourceSha256": ruleset.file_sha256,
            "note": None,
        }
        for rule in matching_rules
    ]
    return {
        "classification": "INFERRED",
        "value": inferred_value,
        "evidence": evidence,
        "derivation": {
            "ruleId": matching_rules[0].rule_id
            if len(matching_rules) == 1
            else f"asset.{target}.ruleset.v1",
            "basis": (
                f"Versioned asset inference rule(s) "
                f"{', '.join(rule.rule_id for rule in matching_rules)} matched "
                f"{'; '.join(matched_inputs)}."
            ),
            "inputRefs": [str(asset["id"])],
        },
    }


def enrich_assets(
    assets: list[dict[str, Any]],
    *,
    oui_manifest_path: str | Path | None = None,
    inference_rules_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    explicit_oui_manifest = oui_manifest_path is not None
    explicit_inference_rules = inference_rules_path is not None

    manifest_path = (
        Path(oui_manifest_path).resolve()
        if explicit_oui_manifest
        else default_oui_manifest_path()
    )
    rules_path = (
        Path(inference_rules_path).resolve()
        if explicit_inference_rules
        else default_inference_rules_path()
    )

    if manifest_path.is_file():
        database: OuiDatabase | None = load_oui_database(manifest_path)
    elif explicit_oui_manifest:
        raise ParserError(f"OUI manifest not found: {manifest_path}")
    else:
        database = None

    if rules_path.is_file():
        ruleset: InferenceRuleset | None = load_inference_rules(rules_path)
    elif explicit_inference_rules:
        raise ParserError(f"Asset inference rules not found: {rules_path}")
    else:
        ruleset = None

    result: list[dict[str, Any]] = []
    for source_asset in assets:
        asset = copy.deepcopy(source_asset)
        if not asset.get("id"):
            raise ParserError("Asset enrichment input is missing a stable ID")
        asset["vendor"] = _vendor_attribute(asset, database)
        asset["deviceType"] = _inferred_attribute(asset, "deviceType", ruleset)
        asset["model"] = _inferred_attribute(asset, "model", ruleset)
        result.append(asset)

    result.sort(key=lambda item: str(item["id"]))
    return result
