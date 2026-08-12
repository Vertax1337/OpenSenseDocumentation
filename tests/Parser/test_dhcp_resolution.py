from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "Parser"))

from core import ParseContext, ParserError  # noqa: E402
from dhcp import parse_dhcp_facts  # noqa: E402
from opnsense_parser import parse_opnsense_config  # noqa: E402
from system_interfaces import parse_interfaces  # noqa: E402
from Rules.ServiceResolution.dhcp_resolution import resolve_dhcp_model  # noqa: E402

FIXTURES = ROOT / "tests" / "Fixtures" / "Parser" / "DHCP"
EXPECTED = ROOT / "tests" / "Expected" / "DHCP" / "kea-and-legacy.expected.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def parse_fixture(name: str):
    path = FIXTURES / name
    tree = ET.parse(path)
    root = tree.getroot()
    parent_map = {child: parent for parent in tree.iter() for child in parent}
    ctx = ParseContext(
        input_path=path,
        report_path=path.with_suffix(".report.json"),
        source_sha=sha256_file(path),
        source_id=name,
        parent_map=parent_map,
        interface_by_name={},
        interface_by_device={},
        alias_by_name={},
        gateway_by_name={},
        unresolved=[],
    )
    interfaces, networks = parse_interfaces(root, ctx)
    facts = parse_dhcp_facts(root, ctx)
    return facts, interfaces, networks


def build_dhcp_validator():
    schema_dir = ROOT / "schemas"
    registry = Registry()
    for schema_path in sorted(schema_dir.glob("*.schema.json")):
        document = json.loads(schema_path.read_text(encoding="utf-8"))
        registry = registry.with_resource(
            document["$id"], Resource.from_contents(document)
        )
    contract = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "urn:opensense-documentation:schema:dhcp-assets:1.0.0#/$defs/dhcpModel",
    }
    return Draft202012Validator(contract, registry=registry)


class DhcpAuthorityResolutionTests(unittest.TestCase):
    def resolve_fixture(self, name: str):
        facts, interfaces, networks = parse_fixture(name)
        return resolve_dhcp_model(facts, interfaces, networks)

    def test_mixed_interface_authority_is_resolved_per_interface(self):
        model = self.resolve_fixture("mixed-interface-authority.xml")
        services = {
            (item["implementation"], item["interfaceRefs"][0]["id"]): item
            for item in model["services"]
        }

        kea_lan = services[("kea", "interface:lan")]
        legacy_lan = services[("isc-dhcpd", "interface:lan")]
        legacy_opt4 = services[("isc-dhcpd", "interface:opt4")]

        self.assertTrue(kea_lan["enabled"])
        self.assertTrue(kea_lan["authoritative"])
        self.assertFalse(legacy_lan["enabled"])
        self.assertFalse(legacy_lan["authoritative"])
        self.assertTrue(legacy_opt4["enabled"])
        self.assertTrue(legacy_opt4["authoritative"])

    def test_kea_and_legacy_critical_pool_regression(self):
        model = self.resolve_fixture("kea-and-legacy.xml")
        authoritative = [
            item for item in model["services"] if item["authoritative"]
        ]
        self.assertEqual(1, len(authoritative))
        self.assertEqual("kea", authoritative[0]["implementation"])
        self.assertEqual(
            "interface:lan", authoritative[0]["interfaceRefs"][0]["id"]
        )

        kea_scope = next(
            item for item in model["scopes"]
            if item["serviceRef"]["id"] == authoritative[0]["id"]
        )
        legacy_scope = next(
            item for item in model["scopes"]
            if item["serviceRef"]["id"] == "dhcp-service:isc-dhcpd-ipv4-lan"
        )
        self.assertEqual(
            [{"start": "192.0.2.50", "end": "192.0.2.199"}],
            kea_scope["pools"],
        )
        self.assertEqual(
            [{"start": "192.0.2.10", "end": "192.0.2.245"}],
            legacy_scope["pools"],
        )

    def test_kea_and_legacy_matches_golden_contract_exactly(self):
        model = self.resolve_fixture("kea-and-legacy.xml")
        expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
        self.assertEqual(expected, model)

    def test_legacy_only_becomes_authoritative(self):
        model = self.resolve_fixture("legacy-only.xml")
        self.assertEqual(1, len(model["services"]))
        service = model["services"][0]
        self.assertEqual("isc-dhcpd", service["implementation"])
        self.assertTrue(service["enabled"])
        self.assertTrue(service["authoritative"])

    def test_reservations_are_linked_to_resolved_scope_and_service(self):
        model = self.resolve_fixture("kea-reservations.xml")
        self.assertEqual(3, len(model["reservations"]))
        reservation = next(
            item for item in model["reservations"]
            if item["hostname"] == "ap-lab-01"
        )
        self.assertEqual("CONFIRMED", reservation["classification"])
        self.assertEqual(
            "dhcp-scope:11111111-1111-4111-8111-111111111111",
            reservation["scopeRef"]["id"],
        )
        self.assertEqual(
            "dhcp-service:kea-ipv4-lan",
            reservation["serviceRef"]["id"],
        )

    def test_resolved_dhcp_model_is_schema_valid(self):
        for fixture in (
            "legacy-only.xml",
            "kea-only.xml",
            "kea-and-legacy.xml",
            "kea-reservations.xml",
            "mixed-interface-authority.xml",
        ):
            model = self.resolve_fixture(fixture)
            errors = list(build_dhcp_validator().iter_errors(model))
            self.assertEqual(
                [], errors, f"{fixture}: {errors[0].message if errors else ''}"
            )

    def test_kea_and_legacy_both_enabled_fail_hard(self):
        facts, interfaces, networks = parse_fixture("kea-and-legacy-both-enabled.xml")
        with self.assertRaisesRegex(ParserError, "Conflicting enabled DHCP services"):
            resolve_dhcp_model(facts, interfaces, networks)

    def test_duplicate_enabled_kea_services_fail_hard(self):
        facts, interfaces, networks = parse_fixture("kea-only.xml")
        duplicate = dict(facts["services"][0])
        duplicate["evidence"] = list(duplicate["evidence"])
        facts["services"].append(duplicate)
        with self.assertRaisesRegex(ParserError, "Conflicting enabled DHCP services"):
            resolve_dhcp_model(facts, interfaces, networks)

    def test_full_parser_wires_resolved_dhcp_into_canonical_model(self):
        fixture = FIXTURES / "kea-and-legacy.xml"
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "sanitization-report.json"
            report.write_text(
                json.dumps({
                    "sanitizerVersion": "1.1.0",
                    "status": "Clean",
                    "source": {
                        "fileName": "config.xml",
                        "sha256": "1" * 64,
                    },
                    "output": {
                        "fileName": "config.sanitized.xml",
                        "sha256": sha256_file(fixture),
                    },
                    "residualFindings": [],
                }),
                encoding="utf-8",
            )
            model = parse_opnsense_config(fixture, report)

        self.assertTrue(model["dhcp"]["services"])
        kea = next(
            item for item in model["dhcp"]["services"]
            if item["implementation"] == "kea"
        )
        self.assertTrue(kea["authoritative"])


if __name__ == "__main__":
    unittest.main()
