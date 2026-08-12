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

from Enrichment.Assets.asset_builder import build_assets, normalize_mac  # noqa: E402
from Parser.core import ParseContext, ParserError  # noqa: E402
from Parser.dhcp import parse_dhcp_facts  # noqa: E402
from Parser.opnsense_parser import parse_opnsense_config  # noqa: E402
from Parser.system_interfaces import parse_interfaces  # noqa: E402
from Rules.ServiceResolution.dhcp_resolution import resolve_dhcp_model  # noqa: E402

FIXTURES = ROOT / "tests" / "Fixtures" / "Parser" / "DHCP"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def resolved_fixture(name: str, source_id: str | None = None):
    path = FIXTURES / name
    tree = ET.parse(path)
    root = tree.getroot()
    parent_map = {child: parent for parent in tree.iter() for child in parent}
    ctx = ParseContext(
        input_path=path,
        report_path=path.with_suffix(".report.json"),
        source_sha=sha256_file(path),
        source_id=source_id or name,
        parent_map=parent_map,
        interface_by_name={},
        interface_by_device={},
        alias_by_name={},
        gateway_by_name={},
        unresolved=[],
    )
    interfaces, networks = parse_interfaces(root, ctx)
    facts = parse_dhcp_facts(root, ctx)
    return resolve_dhcp_model(facts, interfaces, networks)


def build_asset_validator():
    schema_dir = ROOT / "schemas"
    registry = Registry()
    for schema_path in sorted(schema_dir.glob("*.schema.json")):
        document = json.loads(schema_path.read_text(encoding="utf-8"))
        registry = registry.with_resource(
            document["$id"], Resource.from_contents(document)
        )
    contract = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": "urn:opensense-documentation:schema:dhcp-assets:1.0.0#/$defs/assetRecord",
    }
    return Draft202012Validator(contract, registry=registry)


def synthetic_reservation(
    identifier: str,
    ip_address: str,
    mac_address: str | None,
    hostname: str | None,
    description: str | None = None,
):
    return {
        "id": identifier,
        "classification": "CONFIRMED",
        "evidence": [{
            "sourceType": "opnsense-config",
            "sourceId": "synthetic.xml",
            "path": f"/opnsense/OPNsense/Kea/dhcp4/reservations/{identifier}",
            "sourceSha256": "0" * 64,
            "note": None,
        }],
        "serviceRef": {"id": "dhcp-service:kea-ipv4-lan", "type": "dhcp-service"},
        "scopeRef": {
            "id": "dhcp-scope:11111111-1111-4111-8111-111111111111",
            "type": "dhcp-scope",
        },
        "ipAddress": ip_address,
        "macAddress": mac_address,
        "hostname": hostname,
        "description": description,
    }


class AssetBuilderTests(unittest.TestCase):
    def test_asset_enrichment_fixture_builds_one_asset_per_mac(self):
        dhcp = resolved_fixture("asset-enrichment.xml")
        assets = build_assets(dhcp["reservations"])

        self.assertEqual(3, len(assets))
        first = next(
            item for item in assets
            if item["macAddresses"] == ["02:aa:bb:00:00:01"]
        )
        self.assertEqual("asset:mac-02-aa-bb-00-00-01", first["id"])
        self.assertEqual(["192.0.2.70"], first["ipAddresses"])
        self.assertEqual(["printer-lab-01"], first["hostnames"])
        self.assertEqual("Office printer", first["description"])
        self.assertEqual(1, len(first["sourceReservationRefs"]))
        self.assertEqual("dhcp-reservation", first["sourceReservationRefs"][0]["type"])

        for attribute in ("vendor", "deviceType", "model"):
            self.assertEqual("UNKNOWN", first[attribute]["classification"])
            self.assertIsNone(first[attribute]["value"])
            self.assertEqual([], first[attribute]["evidence"])

    def test_mac_normalization_accepts_common_source_formats(self):
        self.assertEqual("aa:bb:cc:dd:ee:ff", normalize_mac("AA-BB-CC-DD-EE-FF"))
        self.assertEqual("aa:bb:cc:dd:ee:ff", normalize_mac("aabb.ccdd.eeff"))
        self.assertEqual("aa:bb:cc:dd:ee:ff", normalize_mac("aa:bb:cc:dd:ee:ff"))

    def test_same_normalized_mac_merges_reservations_into_one_asset(self):
        reservations = [
            synthetic_reservation(
                "dhcp-reservation:one",
                "192.0.2.80",
                "AA-BB-CC-DD-EE-FF",
                "device-a",
                "Shared device",
            ),
            synthetic_reservation(
                "dhcp-reservation:two",
                "192.0.2.81",
                "aabb.ccdd.eeff",
                "device-b",
                "Shared device",
            ),
        ]

        assets = build_assets(reservations)
        self.assertEqual(1, len(assets))
        asset = assets[0]
        self.assertEqual("asset:mac-aa-bb-cc-dd-ee-ff", asset["id"])
        self.assertEqual(["192.0.2.80", "192.0.2.81"], asset["ipAddresses"])
        self.assertEqual(["aa:bb:cc:dd:ee:ff"], asset["macAddresses"])
        self.assertEqual(["device-a", "device-b"], asset["hostnames"])
        self.assertEqual("Shared device", asset["description"])
        self.assertEqual(
            ["dhcp-reservation:one", "dhcp-reservation:two"],
            [item["id"] for item in asset["sourceReservationRefs"]],
        )

    def test_conflicting_descriptions_do_not_invent_one_asset_description(self):
        reservations = [
            synthetic_reservation(
                "dhcp-reservation:one",
                "192.0.2.80",
                "aa:bb:cc:dd:ee:ff",
                "device-a",
                "Description A",
            ),
            synthetic_reservation(
                "dhcp-reservation:two",
                "192.0.2.81",
                "aa:bb:cc:dd:ee:ff",
                "device-b",
                "Description B",
            ),
        ]
        self.assertIsNone(build_assets(reservations)[0]["description"])

    def test_missing_mac_uses_deterministic_fallback_identity(self):
        reservation = synthetic_reservation(
            "dhcp-reservation:no-mac",
            "192.0.2.90",
            None,
            "device-no-mac",
        )
        first = build_assets([reservation])[0]
        second = build_assets([reservation])[0]

        self.assertEqual(first, second)
        self.assertTrue(first["id"].startswith("asset:sha256:"))
        self.assertEqual([], first["macAddresses"])
        self.assertEqual(
            ["dhcp-reservation:no-mac"],
            [item["id"] for item in first["sourceReservationRefs"]],
        )

    def test_invalid_nonempty_mac_fails_instead_of_falling_back_silently(self):
        reservation = synthetic_reservation(
            "dhcp-reservation:bad-mac",
            "192.0.2.91",
            "not-a-mac",
            "device-bad-mac",
        )
        with self.assertRaisesRegex(ParserError, "Invalid DHCP reservation MAC"):
            build_assets([reservation])

    def test_assets_are_schema_valid_and_full_parser_populates_them(self):
        dhcp = resolved_fixture("asset-enrichment.xml")
        assets = build_assets(dhcp["reservations"])
        validator = build_asset_validator()
        for asset in assets:
            errors = list(validator.iter_errors(asset))
            self.assertEqual([], errors, errors[0].message if errors else "")

        fixture = FIXTURES / "asset-enrichment.xml"
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

        expected_full_parser_assets = build_assets(
            resolved_fixture(
                "asset-enrichment.xml",
                source_id="config.sanitized.xml",
            )["reservations"]
        )
        self.assertEqual(3, len(model["assets"]))
        self.assertEqual(expected_full_parser_assets, model["assets"])


if __name__ == "__main__":
    unittest.main()
