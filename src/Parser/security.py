from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

try:
    from .core import ParseContext, bool_text, enabled_from_disabled, network_endpoint, port_spec, ref, resolve_interface_ref, stable_id, text
except ImportError:  # direct script/test execution
    from core import ParseContext, bool_text, enabled_from_disabled, network_endpoint, port_spec, ref, resolve_interface_ref, stable_id, text


def _phase1_encryption(node: ET.Element) -> str | None:
    enc=node.find("encryption-algorithm")
    if enc is None: return None
    name,keylen=text(enc,"name"),text(enc,"keylen")
    return f"{name}{keylen}" if name and keylen else name


def parse_ipsec(root: ET.Element, ctx: ParseContext, gateways: list[dict[str, Any]], interfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    container=root.find("ipsec")
    if container is None: return []
    p2_by_ikeid={}
    for p2 in container.findall("phase2"):
        ikeid=text(p2,"ikeid")
        if ikeid: p2_by_ikeid.setdefault(ikeid,[]).append(p2)
    interfaces_by_id={item["id"]:item for item in interfaces}; result=[]
    for p1 in container.findall("phase1"):
        ikeid=text(p1,"ikeid"); p2s=p2_by_ikeid.get(ikeid or "",[]); route_based=[p for p in p2s if (text(p,"mode") or "").lower()=="route-based"]
        mode="route-based" if route_based else ("policy-based" if p2s else "unknown")
        uuid=p1.attrib.get("uuid")
        identifier=stable_id("vpn",natural_id=uuid or (f"ipsec-ike-{ikeid}" if ikeid else None),identity_parts=None if (uuid or ikeid) else [text(p1,"remote-gateway") or "",text(p1,"descr") or ""])
        evidence=ctx.evidence(p1)
        for p2 in p2s: evidence.extend(ctx.evidence(p2,"Associated IPsec phase2"))
        tunnel_interface_ref=None; gateway_ref=None
        if route_based:
            remotes={text(p,"tunnel_remote") for p in route_based if text(p,"tunnel_remote")}; locals_={text(p,"tunnel_local") for p in route_based if text(p,"tunnel_local")}
            if len(remotes)==1:
                tunnel_remote=next(iter(remotes)); matches=[g for g in gateways if g.get("address")==tunnel_remote]
                if len(matches)==1:
                    gateway=matches[0]; gateway_ref=ref(gateway["id"],"gateway")
                    if gateway.get("interfaceRef") is not None:
                        tunnel_interface_ref=gateway["interfaceRef"]; interface_record=interfaces_by_id.get(tunnel_interface_ref["id"])
                        if interface_record is not None and len(locals_)==1:
                            tunnel_local=next(iter(locals_)); family="IPv6" if ":" in tunnel_local else "IPv4"
                            if not any(a.get("family")==family and a.get("address")==tunnel_local for a in interface_record["addresses"]):
                                interface_record["addresses"].append({"family":family,"address":tunnel_local,"prefixLength":None,"assignment":"static"})
                                interface_record["evidence"].extend(ctx.evidence(route_based[0],"VTI local address matched through exact tunnel_remote -> gateway address relation"))
        result.append({"id":identifier,"classification":"CONFIRMED","evidence":evidence,"vpnType":"ipsec","enabled":enabled_from_disabled(p1,True),"mode":mode,"name":text(p1,"descr"),"localEndpoint":None,"remoteEndpoint":text(p1,"remote-gateway"),"tunnelInterfaceRef":tunnel_interface_ref,"gatewayRef":gateway_ref,"ikeVersion":text(p1,"iketype"),"encryption":_phase1_encryption(p1),"integrity":text(p1,"hash-algorithm")})
    return result


def _nat_identity(node: ET.Element, kind: str) -> list[str]:
    src=text(node.find("source"),"network") or text(node.find("source"),"address") or "any"
    dst=text(node.find("destination"),"network") or text(node.find("destination"),"address") or "any"
    return [kind,text(node,"interface") or "",text(node,"protocol") or "",src,dst,text(node,"dstport") or text(node.find("destination"),"port") or "",text(node,"target") or "",text(node,"local-port") or "",text(node,"descr") or ""]


def parse_nat(root: ET.Element, ctx: ParseContext) -> tuple[list[dict[str, Any]], dict[str,str]]:
    container=root.find("nat")
    if container is None: return [],{}
    result=[]; associations={}
    outbound=container.find("outbound")
    if outbound is not None:
        for node in outbound.findall("rule"):
            kind="no-nat" if bool_text(text(node,"nonat")) is True else "outbound-nat"; identifier=stable_id("nat",identity_parts=_nat_identity(node,kind)); source_ref=ref(identifier,"nat")
            result.append({"id":identifier,"classification":"CONFIRMED","evidence":ctx.evidence(node),"kind":kind,"enabled":enabled_from_disabled(node,True),"interfaceRef":resolve_interface_ref(ctx,text(node,"interface"),source_ref,node),"protocol":text(node,"protocol") or text(node,"ipprotocol"),"source":network_endpoint(ctx,node.find("source"),source_ref),"destination":network_endpoint(ctx,node.find("destination"),source_ref),"sourcePort":port_spec(text(node,"sourceport") or text(node.find("source"),"port")),"destinationPort":port_spec(text(node,"dstport") or text(node.find("destination"),"port")),"translation":None if kind=="no-nat" else text(node,"target"),"translationPort":None,"description":text(node,"descr"),"associatedFirewallRuleRefs":[]})
    for node in container.findall("rule"):
        association=text(node,"associated-rule-id"); identifier=stable_id("nat",natural_id=association if association else None,identity_parts=None if association else _nat_identity(node,"port-forward")); source_ref=ref(identifier,"nat")
        if association: associations[association]=identifier
        result.append({"id":identifier,"classification":"CONFIRMED","evidence":ctx.evidence(node),"kind":"port-forward","enabled":enabled_from_disabled(node,True),"interfaceRef":resolve_interface_ref(ctx,text(node,"interface"),source_ref,node),"protocol":text(node,"protocol"),"source":network_endpoint(ctx,node.find("source"),source_ref),"destination":network_endpoint(ctx,node.find("destination"),source_ref),"sourcePort":port_spec(text(node.find("source"),"port")),"destinationPort":port_spec(text(node.find("destination"),"port")),"translation":text(node,"target"),"translationPort":text(node,"local-port"),"description":text(node,"descr"),"associatedFirewallRuleRefs":[]})
    return result,associations


def parse_firewall(root: ET.Element, ctx: ParseContext, nat_records: list[dict[str, Any]], associations: dict[str,str]) -> list[dict[str, Any]]:
    container=root.find("filter")
    if container is None: return []
    result=[]; nat_by_id={item["id"]:item for item in nat_records}
    for order,node in enumerate(container.findall("rule")):
        uuid=node.attrib.get("uuid"); association=text(node,"associated-rule-id")
        identifier=stable_id("firewall-rule",natural_id=uuid if uuid else None,identity_parts=None if uuid else [str(order),association or "",text(node,"interface") or "",text(node,"descr") or ""]); source_ref=ref(identifier,"firewall-rule")
        interface_tokens=[p.strip() for p in (text(node,"interface") or "").split(",") if p.strip()]; interface_refs=[]
        for token in interface_tokens:
            resolved=resolve_interface_ref(ctx,token,source_ref,node)
            if resolved is not None: interface_refs.append(resolved)
        if not interface_refs:
            interface_refs.append(ref(stable_id("interface",natural_id=interface_tokens[0] if interface_tokens else "unknown"),"interface"))
            if not interface_tokens: ctx.add_unresolved(source_ref=source_ref,target_type="interface",target_identifier="<missing>",reason="Firewall rule has no interface token",node=node)
        nat_id=associations.get(association or ""); associated_nat=[ref(nat_id,"nat")] if nat_id else []
        action=(text(node,"type") or "pass").lower(); action=action if action in {"pass","block","reject","match"} else "other"
        direction=(text(node,"direction") or "unknown").lower(); direction=direction if direction in {"in","out","any"} else "unknown"
        record={"id":identifier,"classification":"CONFIRMED","evidence":ctx.evidence(node),"enabled":enabled_from_disabled(node,True),"order":order,"action":action,"interfaceRefs":interface_refs,"direction":direction,"protocol":text(node,"protocol") or "any","source":network_endpoint(ctx,node.find("source"),source_ref),"destination":network_endpoint(ctx,node.find("destination"),source_ref),"sourcePort":port_spec(text(node.find("source"),"port")),"destinationPort":port_spec(text(node.find("destination"),"port")),"associatedNatRefs":associated_nat,"quick":bool_text(text(node,"quick")),"log":bool_text(text(node,"log")),"description":text(node,"descr")}
        result.append(record)
        if nat_id and nat_id in nat_by_id: nat_by_id[nat_id]["associatedFirewallRuleRefs"].append(ref(identifier,"firewall-rule"))
    return result
