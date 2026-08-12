from __future__ import annotations

import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "Parser"))

from core import ParseContext  # noqa: E402
from dhcp import parse_dhcp_facts  # noqa: E402

FIXTURES = ROOT / "tests" / "Fixtures" / "Parser" / "DHCP"


def parse_fixture(name: str):
    path = FIXTURES / name
    tree = ET.parse(path)
    root = tree.getroot()
    parent_map = {child: parent for parent in tree.iter() for child in parent}
    ctx = ParseContext(
        input_path=path,
        report_path=path.with_suffix(".report.json"),
        source_sha="0" * 64,
        source_id=name,
        parent_map=parent_map,
        interface_by_name={},
        interface_by_device={},
        alias_by_name={},
        gateway_by_name={},
        unresolved=[],
    )
    return parse_dhcp_facts(root, ctx)


class DhcpParserFactTests(unittest.TestCase):
    def test_kea_only_extracts_service_scope_and_options(self):
        facts = parse_fixture("kea-only.xml")
        self.assertEqual(1, len(facts["services"]))
        service = facts["services"][0]
        self.assertEqual("kea", service["implementation"])
        self.assertEqual("lan", service["interface"])
        self.assertTrue(service["enabled"])
        self.assertFalse(service["legacy"])

        scope = facts["scopes"][0]
        self.assertEqual("11111111-1111-4111-8111-111111111111", scope["sourceKey"])
        self.assertEqual("192.0.2.0/24", scope["subnet"])
        self.assertEqual(
            [{"raw": "192.0.2.50-192.0.2.199", "start": "192.0.2.50", "end": "192.0.2.199"}],
            scope["pools"],
        )
        self.assertEqual("192.0.2.1", scope["gateway"])
        self.assertEqual(["192.0.2.1"], scope["dnsServers"])
        self.assertEqual("example.invalid", scope["domainName"])
        self.assertEqual(["example.invalid"], scope["searchDomains"])
        self.assertEqual(["192.0.2.1"], scope["ntpServers"])
        self.assertEqual(4000, scope["leaseTimeSeconds"])

    def test_legacy_only_extracts_service_scope_and_static_reservation(self):
        facts = parse_fixture("legacy-only.xml")
        self.assertEqual(1, len(facts["services"]))
        service = facts["services"][0]
        self.assertEqual("isc-dhcpd", service["implementation"])
        self.assertEqual("lan", service["interface"])
        self.assertTrue(service["enabled"])
        self.assertTrue(service["legacy"])

        scope = facts["scopes"][0]
        self.assertEqual("isc-dhcpd-ipv4-lan", scope["sourceKey"])
        self.assertEqual(
            [{"raw": "192.0.2.100-192.0.2.180", "start": "192.0.2.100", "end": "192.0.2.180"}],
            scope["pools"],
        )
        self.assertEqual("192.0.2.1", scope["gateway"])
        self.assertEqual(["192.0.2.1"], scope["dnsServers"])
        self.assertEqual(["192.0.2.1"], scope["ntpServers"])

        reservation = facts["reservations"][0]
        self.assertEqual("isc-dhcpd", reservation["implementation"])
        self.assertEqual("isc-dhcpd-ipv4-lan", reservation["scopeSourceKey"])
        self.assertEqual("192.0.2.31", reservation["ipAddress"])
        self.assertEqual("02:00:5e:20:00:01", reservation["macAddress"])
        self.assertEqual("legacy-client-01", reservation["hostname"])
        self.assertEqual("Synthetic legacy reservation", reservation["description"])

    def test_kea_reservations_preserve_explicit_subnet_reference(self):
        facts = parse_fixture("kea-reservations.xml")
        self.assertEqual(3, len(facts["reservations"]))
        first = facts["reservations"][0]
        self.assertEqual("kea", first["implementation"])
        self.assertEqual("11111111-1111-4111-8111-111111111111", first["scopeSourceKey"])
        self.assertEqual("192.0.2.31", first["ipAddress"])
        self.assertEqual("02:00:5e:10:00:01", first["macAddress"])
        self.assertEqual("ap-lab-01", first["hostname"])
        self.assertIsNone(first["description"])

    def test_kea_and_legacy_are_both_retained_before_authority_resolution(self):
        facts = parse_fixture("kea-and-legacy.xml")
        services = {(item["implementation"], item["interface"]): item for item in facts["services"]}
        self.assertIn(("kea", "lan"), services)
        self.assertIn(("isc-dhcpd", "lan"), services)
        self.assertIn(("isc-dhcpd", "opt4"), services)
        self.assertTrue(services[("kea", "lan")]["enabled"])
        self.assertFalse(services[("isc-dhcpd", "lan")]["enabled"])
        self.assertFalse(services[("isc-dhcpd", "opt4")]["enabled"])
        self.assertNotIn("authoritative", services[("kea", "lan")])

    def test_invalid_pool_order_is_preserved_for_phase46_validation(self):
        facts = parse_fixture("invalid-pool.xml")
        scope = next(item for item in facts["scopes"] if item["implementation"] == "kea")
        self.assertEqual("192.0.2.200", scope["pools"][0]["start"])
        self.assertEqual("192.0.2.100", scope["pools"][0]["end"])

    def test_legacy_enable_marker_presence_counts_as_enabled_when_empty(self):
        root = ET.fromstring(
            "<opnsense><dhcpd><lan><enable/><range><from>192.0.2.10</from>"
            "<to>192.0.2.20</to></range></lan></dhcpd></opnsense>"
        )
        tree = ET.ElementTree(root)
        parent_map = {child: parent for parent in tree.iter() for child in parent}
        ctx = ParseContext(
            input_path=Path("synthetic.xml"),
            report_path=Path("synthetic.report.json"),
            source_sha="0" * 64,
            source_id="synthetic.xml",
            parent_map=parent_map,
            interface_by_name={},
            interface_by_device={},
            alias_by_name={},
            gateway_by_name={},
            unresolved=[],
        )
        facts = parse_dhcp_facts(root, ctx)
        self.assertTrue(facts["services"][0]["enabled"])


if __name__ == "__main__":
    unittest.main()
