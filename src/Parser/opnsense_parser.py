#!/usr/bin/env python3
"""Deterministic OPNsense core parser for the Canonical Infrastructure Model."""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

try:
    from .core import CANONICALIZATION_VERSION, ID_STRATEGY_VERSION, PARSER_VERSION, RULESET_VERSION, SCHEMA_VERSION, ParseContext, ParserError, load_and_verify_report, stable_id, text
    from .dhcp import parse_dhcp_facts
    from .network_objects import parse_aliases, parse_gateways, parse_routes
    from .security import parse_firewall, parse_ipsec, parse_nat
    from .system_interfaces import parse_interfaces, parse_system, parse_vlans
except ImportError:  # direct script/test execution
    from core import CANONICALIZATION_VERSION, ID_STRATEGY_VERSION, PARSER_VERSION, RULESET_VERSION, SCHEMA_VERSION, ParseContext, ParserError, load_and_verify_report, stable_id, text
    from dhcp import parse_dhcp_facts
    from network_objects import parse_aliases, parse_gateways, parse_routes
    from security import parse_firewall, parse_ipsec, parse_nat
    from system_interfaces import parse_interfaces, parse_system, parse_vlans

try:
    from Rules.ServiceResolution.dhcp_resolution import resolve_dhcp_model
except ImportError:  # direct script/test execution with src/Parser on sys.path
    rules_path = Path(__file__).resolve().parents[1] / "Rules" / "ServiceResolution"
    if str(rules_path) not in sys.path:
        sys.path.insert(0, str(rules_path))
    from dhcp_resolution import resolve_dhcp_model

try:
    from Enrichment.Assets.asset_builder import build_assets
    from Enrichment.Assets.asset_enrichment import enrich_assets
except ImportError:  # direct script/test execution with src/Parser on sys.path
    assets_path = Path(__file__).resolve().parents[1] / "Enrichment" / "Assets"
    if str(assets_path) not in sys.path:
        sys.path.insert(0, str(assets_path))
    from asset_builder import build_assets
    from asset_enrichment import enrich_assets


def _dns_defaults(root: ET.Element) -> dict[str, Any]:
    servers=[]; system=root.find("system")
    if system is not None:
        for node in system.findall("dnsserver"):
            value=text(node)
            if value and value not in servers: servers.append(value)
    return {"systemServers":servers,"unboundEnabled":None,"forwardingEnabled":None,"dnsblEnabled":None,"safeSearchEnabled":None,"forwards":[]}


def parse_opnsense_config(input_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    input_path,report_path=Path(input_path).resolve(),Path(report_path).resolve()
    if not input_path.is_file(): raise ParserError(f"Input XML not found: {input_path}")
    if not report_path.is_file(): raise ParserError(f"Sanitization report not found: {report_path}")
    report,source_sha=load_and_verify_report(input_path,report_path)
    try: tree=ET.parse(input_path)
    except ET.ParseError as exc: raise ParserError(f"Invalid XML: {exc}") from exc
    root=tree.getroot()
    if root.tag!="opnsense": raise ParserError(f"Unexpected root element: {root.tag}")
    parent_map={child:parent for parent in tree.iter() for child in parent}; source_id=str((report.get("output") or {}).get("fileName") or input_path.name)
    ctx=ParseContext(input_path,report_path,source_sha,source_id,parent_map,{}, {}, {}, {}, [])
    system=parse_system(root,ctx); interfaces,networks=parse_interfaces(root,ctx); vlans=parse_vlans(root,ctx,interfaces); aliases=parse_aliases(root,ctx); gateways=parse_gateways(root,ctx); routes=parse_routes(root,ctx); vpn=parse_ipsec(root,ctx,gateways,interfaces); nat,associations=parse_nat(root,ctx); firewall=parse_firewall(root,ctx,nat,associations)
    dhcp_facts=parse_dhcp_facts(root,ctx); dhcp=resolve_dhcp_model(dhcp_facts,interfaces,networks); assets=enrich_assets(build_assets(dhcp["reservations"]))
    output_meta,source_meta=report.get("output") or {},report.get("source") or {}
    return {
        "schemaVersion":SCHEMA_VERSION,"modelId":stable_id("model",identity_parts=[source_sha]),
        "producer":{"parserVersion":PARSER_VERSION,"rulesetVersion":RULESET_VERSION,"schemaVersion":SCHEMA_VERSION,"idStrategyVersion":ID_STRATEGY_VERSION,"canonicalizationVersion":CANONICALIZATION_VERSION},
        "source":{"sourceType":"OPNsense config.xml","originalFileName":source_meta.get("fileName"),"originalSha256":source_meta.get("sha256"),"sanitizedFileName":output_meta.get("fileName") or input_path.name,"sanitizedSha256":source_sha,"sanitizerVersion":str(report.get("sanitizerVersion") or "0.0.0"),"sanitizationStatus":"Clean"},
        "system":system,"interfaces":interfaces,"networks":networks,"vlans":vlans,
        "dhcp":dhcp,"assets":assets,"dns":_dns_defaults(root),"aliases":aliases,"gateways":gateways,"routes":routes,"vpn":vpn,"nat":nat,"firewallRules":firewall,
        "services":[],"monitoring":[],"cronJobs":[],"certificates":[],"businessFlows":[],"findings":[],"unresolvedReferences":sorted(ctx.unresolved,key=lambda item:item["id"]),
    }


def write_model(model: dict[str, Any], output_path: str | Path) -> None:
    output=Path(output_path); output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(model,ensure_ascii=False,indent=2,sort_keys=False)+"\n",encoding="utf-8",newline="\n")
