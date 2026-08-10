from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

try:
    from .core import ParseContext, bool_text, enabled_from_disabled, natural_enabled, ref, resolve_interface_ref, stable_id, text
except ImportError:  # direct script/test execution
    from core import ParseContext, bool_text, enabled_from_disabled, natural_enabled, ref, resolve_interface_ref, stable_id, text


def parse_aliases(root: ET.Element, ctx: ParseContext) -> list[dict[str, Any]]:
    nodes=[]
    modern=root.find("OPNsense/Firewall/Alias/aliases"); legacy=root.find("aliases")
    if modern is not None: nodes.extend(modern.findall("alias"))
    if legacy is not None: nodes.extend(legacy.findall("alias"))
    result=[]
    for node in nodes:
        name=text(node,"name")
        if not name: continue
        identifier=stable_id("alias",natural_id=node.attrib.get("uuid") or name); ctx.alias_by_name[name]=identifier
        alias_type=text(node,"type") or "unknown"; dynamic=alias_type.lower() in {"external","url","urltable","geoip"}
        content=[line.strip() for line in re.split(r"[\r\n]+",text(node,"content") or "") if line.strip()]
        result.append({"id":identifier,"classification":"CONFIRMED","evidence":ctx.evidence(node),"name":name,"aliasType":alias_type,"enabled":natural_enabled(node,"enabled",True),"dynamic":dynamic,"resolved":bool(content) and not dynamic,"content":content,"description":text(node,"description") or text(node,"descr")})
    return result


def parse_gateways(root: ET.Element, ctx: ParseContext) -> list[dict[str, Any]]:
    nodes=[]
    modern=root.find("OPNsense/Gateways"); legacy=root.find("gateways")
    if modern is not None: nodes.extend(modern.findall("gateway_item"))
    if legacy is not None: nodes.extend(legacy.findall("gateway_item"))
    result=[]
    for node in nodes:
        name=text(node,"name")
        if not name: continue
        identifier=stable_id("gateway",natural_id=node.attrib.get("uuid") or name); ctx.gateway_by_name[name]=identifier; source_ref=ref(identifier,"gateway")
        monitor_disable=bool_text(text(node,"monitor_disable"))
        result.append({"id":identifier,"classification":"CONFIRMED","evidence":ctx.evidence(node),"name":name,"enabled":enabled_from_disabled(node,True),"interfaceRef":resolve_interface_ref(ctx,text(node,"interface"),source_ref,node),"address":text(node,"gateway"),"monitoringEnabled":None if monitor_disable is None else not monitor_disable,"monitorAddress":text(node,"monitor"),"description":text(node,"descr")})
    return result


def parse_routes(root: ET.Element, ctx: ParseContext) -> list[dict[str, Any]]:
    container=root.find("staticroutes")
    if container is None: return []
    result=[]
    for node in container.findall("route"):
        destination,gateway_name=text(node,"network"),text(node,"gateway")
        if not destination or not gateway_name: continue
        uuid=node.attrib.get("uuid"); identifier=stable_id("route",natural_id=uuid if uuid else None,identity_parts=None if uuid else [destination,gateway_name,text(node,"descr") or ""]); source_ref=ref(identifier,"route")
        gateway_id=ctx.gateway_by_name.get(gateway_name)
        if gateway_id is None:
            gateway_id=stable_id("gateway",natural_id=gateway_name)
            ctx.add_unresolved(source_ref=source_ref,target_type="gateway",target_identifier=gateway_name,reason="Static route references a gateway that was not parsed",node=node)
        result.append({"id":identifier,"classification":"CONFIRMED","evidence":ctx.evidence(node),"destination":destination,"gatewayRef":ref(gateway_id,"gateway"),"enabled":enabled_from_disabled(node,True),"description":text(node,"descr")})
    return result
