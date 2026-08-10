from __future__ import annotations

import ipaddress
import re
import xml.etree.ElementTree as ET
from typing import Any

try:
    from .core import ParseContext, ParserError, bool_text, natural_enabled, ref, resolve_interface_ref, stable_id, text
except ImportError:  # direct script/test execution
    from core import ParseContext, ParserError, bool_text, natural_enabled, ref, resolve_interface_ref, stable_id, text


def parse_system(root: ET.Element, ctx: ParseContext) -> dict[str, Any]:
    node = root.find("system")
    if node is None:
        raise ParserError("Missing /opnsense/system")
    webgui, ssh, firmware = node.find("webgui"), node.find("ssh"), node.find("firmware")
    auth_mode = text(webgui, "authmode") if webgui is not None else None
    auth_backends = [part.strip() for part in auth_mode.split(",") if part.strip()] if auth_mode else []
    raw_port = text(webgui, "port") if webgui is not None else None
    web_port = int(raw_port) if raw_port and raw_port.isdigit() else None
    raw_ssh = text(ssh, "enabled") if ssh is not None else None
    ssh_enabled = bool_text(raw_ssh)
    if ssh_enabled is None and raw_ssh:
        ssh_enabled = True
    return {
        "id": stable_id("system", natural_id="opnsense"), "classification": "CONFIRMED", "evidence": ctx.evidence(node),
        "hostname": text(node, "hostname"), "domain": text(node, "domain"), "timezone": text(node, "timezone"),
        "edition": text(firmware, "type") if firmware is not None else None, "version": None,
        "webGuiProtocol": text(webgui, "protocol") if webgui is not None else None, "webGuiPort": web_port,
        "sshEnabled": ssh_enabled, "authBackends": auth_backends,
    }


def _kind(name: str, device: str | None, node: ET.Element) -> str:
    lname, ldev = name.lower(), (device or "").lower()
    if lname == "lo0" or ldev == "lo0": return "loopback"
    if lname == "enc0" or ldev == "enc0": return "ipsec"
    if re.match(r"^ipsec\d+$", lname) or re.match(r"^ipsec\d+$", ldev): return "vti"
    if ldev.startswith("vlan"): return "vlan"
    if bool_text(text(node, "virtual")) is True: return "other"
    return "physical" if device else "unknown"


def _address(family: str, value: str | None, prefix: str | None) -> dict[str, Any] | None:
    if not value: return None
    lower = value.lower()
    assignment = {("IPv4","dhcp"):"dhcp",("IPv4","pppoe"):"pppoe",("IPv6","dhcp6"):"dhcp6",("IPv6","track6"):"track6"}.get((family,lower),"static")
    try: prefix_length = int(prefix) if prefix else None
    except ValueError: prefix_length = None
    return {"family": family, "address": value, "prefixLength": prefix_length, "assignment": assignment}


def parse_interfaces(root: ET.Element, ctx: ParseContext) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    container = root.find("interfaces")
    if container is None: return [], []
    interfaces, networks = [], []
    for node in list(container):
        name, device = node.tag, text(node, "if")
        identifier = stable_id("interface", natural_id=name)
        ctx.interface_by_name[name] = identifier
        if device: ctx.interface_by_device.setdefault(device, []).append(identifier)
        addresses = [item for item in (_address("IPv4",text(node,"ipaddr"),text(node,"subnet")), _address("IPv6",text(node,"ipaddrv6"),text(node,"subnetv6"))) if item]
        interfaces.append({"id":identifier,"classification":"CONFIRMED","evidence":ctx.evidence(node),"name":name,"device":device,"description":text(node,"descr"),"enabled":natural_enabled(node,"enable",False),"kind":_kind(name,device,node),"addresses":addresses,"parentRef":None})
        v4 = next((a for a in addresses if a["family"]=="IPv4" and a["assignment"]=="static" and a["prefixLength"] is not None),None)
        if v4:
            try: network = ipaddress.ip_interface(f"{v4['address']}/{v4['prefixLength']}").network
            except ValueError: continue
            networks.append({"id":stable_id("network",natural_id=f"{name}-ipv4"),"classification":"DERIVED","evidence":ctx.evidence(node,"Derived from interface IPv4 address and prefix"),"derivation":{"ruleId":"derive-interface-ipv4-network-v1","basis":"Network CIDR is calculated from the configured static IPv4 interface address and prefix length.","inputRefs":[identifier]},"name":text(node,"descr") or name,"cidr":str(network),"role":name,"interfaceRef":ref(identifier,"interface")})
    return interfaces, networks


def parse_vlans(root: ET.Element, ctx: ParseContext, interfaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    container = root.find("vlans")
    if container is None: return []
    by_id = {item["id"]:item for item in interfaces}; result=[]
    for node in container.findall("vlan"):
        tag_text, parent_device, vlan_device = text(node,"tag"), text(node,"if"), text(node,"vlanif")
        if not tag_text or not tag_text.isdigit(): continue
        uuid=node.attrib.get("uuid"); tag=int(tag_text)
        identifier=stable_id("vlan",natural_id=uuid if uuid else None,identity_parts=None if uuid else [parent_device or "",str(tag),vlan_device or ""])
        source_ref=ref(identifier,"vlan")
        parent_ref=resolve_interface_ref(ctx,parent_device,source_ref,node)
        if parent_ref is None: parent_ref=ref(stable_id("interface",natural_id=parent_device or f"unknown-parent-{tag}"),"interface")
        vlan_ref=resolve_interface_ref(ctx,vlan_device,source_ref,node) if vlan_device else None
        result.append({"id":identifier,"classification":"CONFIRMED","evidence":ctx.evidence(node),"tag":tag,"description":text(node,"descr"),"parentInterfaceRef":parent_ref,"vlanInterfaceRef":vlan_ref})
        if vlan_ref and vlan_ref["id"] in by_id: by_id[vlan_ref["id"]]["parentRef"]=parent_ref
    return result
