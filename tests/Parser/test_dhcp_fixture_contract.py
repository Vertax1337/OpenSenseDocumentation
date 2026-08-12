from __future__ import annotations

import hashlib
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "Fixtures" / "Parser" / "DHCP"
EXPECTED = ROOT / "tests" / "Expected" / "DHCP" / "kea-and-legacy.expected.json"

REQUIRED_FIXTURES = {
    "legacy-only.xml",
    "kea-only.xml",
    "kea-and-legacy.xml",
    "kea-reservations.xml",
    "duplicate-ip.xml",
    "invalid-pool.xml",
    "reservation-outside-pool.xml",
    "asset-enrichment.xml",
    "mixed-interface-authority.xml",
    "pool-outside-subnet.xml",
}

FORBIDDEN_CUSTOMER_MARKERS = (
    "cannon",
    "192.168.1.",
    "172.16.0.",
    "AdminBSSE",
    "TASKalfa",
    "CDE410",
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def build_dhcp_validator():
    schema_dir = ROOT / "schemas"
    registry = Registry()
    for schema_path in sorted(schema_dir.glob("*.schema.json")):
        document = json.loads(schema_path.read_text(encoding="utf-8"))
        registry = registry.with_resource(document["$id"], Resource.from_contents(document))
    contract = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "urn:opensense-documentation:schema:dhcp-assets:1.0.0#/$defs/dhcpModel",
    }
    return Draft202012Validator(contract, registry=registry)


class DhcpFixtureContractTests(unittest.TestCase):
    def test_required_phase4_fixtures_exist_and_are_xml(self):
        actual = {path.name for path in FIXTURES.glob("*.xml")}
        self.assertTrue(REQUIRED_FIXTURES.issubset(actual))
        for path in sorted(FIXTURES.glob("*.xml")):
            root = ET.parse(path).getroot()
            self.assertEqual("opnsense", root.tag, path.name)

    def test_fixtures_do_not_contain_known_customer_markers(self):
        for path in sorted(FIXTURES.glob("*.xml")):
            text = path.read_text(encoding="utf-8")
            for marker in FORBIDDEN_CUSTOMER_MARKERS:
                self.assertNotIn(marker, text, f"{marker!r} leaked into {path.name}")

    def test_kea_and_legacy_fixture_encodes_the_critical_regression(self):
        root = ET.parse(FIXTURES / "kea-and-legacy.xml").getroot()
        self.assertEqual("1", root.findtext("./OPNsense/Kea/dhcp4/general/enabled"))
        self.assertEqual("lan", root.findtext("./OPNsense/Kea/dhcp4/general/interfaces"))
        self.assertEqual("192.0.2.50-192.0.2.199", root.findtext("./OPNsense/Kea/dhcp4/subnets/subnet4/pools"))
        self.assertEqual("192.0.2.10", root.findtext("./dhcpd/lan/range/from"))
        self.assertEqual("192.0.2.245", root.findtext("./dhcpd/lan/range/to"))
        self.assertIsNone(root.find("./dhcpd/lan/enable"))
        self.assertIsNone(root.find("./dhcpd/opt4/enable"))

    def test_mixed_interface_fixture_encodes_per_interface_authority_input(self):
        root = ET.parse(FIXTURES / "mixed-interface-authority.xml").getroot()
        self.assertEqual("lan", root.findtext("./OPNsense/Kea/dhcp4/general/interfaces"))
        self.assertEqual("1", root.findtext("./dhcpd/lan/enable"))
        self.assertEqual("1", root.findtext("./dhcpd/opt4/enable"))

    def test_expected_kea_and_legacy_dhcp_contract_is_schema_valid(self):
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        errors = list(build_dhcp_validator().iter_errors(expected))
        self.assertEqual([], errors, errors[0].message if errors else "")
        kea = next(item for item in expected["services"] if item["implementation"] == "kea")
        legacy_lan = next(
            item for item in expected["services"]
            if item["implementation"] == "isc-dhcpd" and item["interfaceRefs"][0]["id"] == "interface:lan"
        )
        self.assertTrue(kea["authoritative"])
        self.assertTrue(kea["enabled"])
        self.assertFalse(legacy_lan["authoritative"])
        self.assertFalse(legacy_lan["enabled"])
        scope = next(item for item in expected["scopes"] if item["serviceRef"]["id"] == kea["id"])
        self.assertEqual([{"start": "192.0.2.50", "end": "192.0.2.199"}], scope["pools"])

    def test_expected_contract_is_bound_to_fixture_hash(self):
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        fixture_sha = sha256_file(FIXTURES / "kea-and-legacy.xml")
        evidence_hashes = {
            evidence["sourceSha256"]
            for collection in ("services", "scopes", "reservations")
            for record in expected[collection]
            for evidence in record["evidence"]
            if evidence.get("sourceSha256")
        }
        self.assertEqual({fixture_sha}, evidence_hashes)


if __name__ == "__main__":
    unittest.main()
