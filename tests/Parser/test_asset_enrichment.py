from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from Enrichment.Assets.asset_builder import build_assets  # noqa: E402
from Enrichment.Assets.asset_enrichment import enrich_assets  # noqa: E402
from Enrichment.OUI.oui import (  # noqa: E402
    OUI_VENDOR_RULE_ID,
    is_globally_administered_unicast,
    load_oui_database,
)
from Parser.core import ParserError  # noqa: E402
from Parser.opnsense_parser import parse_opnsense_config  # noqa: E402

DHCP_FIXTURES = ROOT / "tests" / "Fixtures" / "Parser" / "DHCP"
OUI_FIXTURES = ROOT / "tests" / "Fixtures" / "Enrichment" / "OUI"
RULE_FIXTURES = ROOT / "tests" / "Fixtures" / "Enrichment" / "Rules"
OUI_MANIFEST = OUI_FIXTURES / "manifest.json"
INFERENCE_RULES = RULE_FIXTURES / "asset-inference-test.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


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
            "path": f"/synthetic/{identifier}",
            "sourceSha256": "0" * 64,
            "note": None,
        }],
        "serviceRef": {
            "id": "dhcp-service:kea-ipv4-lan",
            "type": "dhcp-service",
        },
        "scopeRef": {
            "id": "dhcp-scope:synthetic",
            "type": "dhcp-scope",
        },
        "ipAddress": ip_address,
        "macAddress": mac_address,
        "hostname": hostname,
        "description": description,
    }


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
        "$ref": (
            "urn:opensense-documentation:schema:dhcp-assets:1.0.0"
            "#/$defs/assetRecord"
        ),
    }
    return Draft202012Validator(contract, registry=registry)


class AssetEnrichmentTests(unittest.TestCase):
    def enrich_reservation(
        self,
        *,
        identifier: str,
        ip_address: str,
        mac_address: str | None,
        hostname: str | None,
        description: str | None = None,
    ):
        assets = build_assets([
            synthetic_reservation(
                identifier,
                ip_address,
                mac_address,
                hostname,
                description,
            )
        ])
        return enrich_assets(
            assets,
            oui_manifest_path=OUI_MANIFEST,
            inference_rules_path=INFERENCE_RULES,
        )[0]

    def test_oui_manifest_hash_and_lookup_are_deterministic(self):
        database = load_oui_database(OUI_MANIFEST)
        self.assertEqual("test-2026-08", database.database_version)
        self.assertEqual(3, database.entry_count)
        self.assertEqual(
            ("001122", "Example Devices Inc."),
            database.lookup("00:11:22:33:44:55"),
        )
        self.assertEqual(
            ("001122", "Example Devices Inc."),
            database.lookup("00-11-22-AA-BB-CC"),
        )

    def test_oui_manifest_hash_mismatch_fails_hard(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            csv_path = temp_dir / "oui-test.csv"
            csv_path.write_bytes((OUI_FIXTURES / "oui-test.csv").read_bytes())
            manifest = json.loads(OUI_MANIFEST.read_text(encoding="utf-8"))
            manifest["sha256"] = "0" * 64
            manifest_path = temp_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ParserError, "SHA-256 mismatch"):
                load_oui_database(manifest_path)

    def test_globally_administered_mac_derives_vendor(self):
        asset = self.enrich_reservation(
            identifier="dhcp-reservation:vendor",
            ip_address="192.0.2.100",
            mac_address="00:11:22:33:44:55",
            hostname="edge-device-01",
        )
        vendor = asset["vendor"]
        self.assertEqual("DERIVED", vendor["classification"])
        self.assertEqual("Example Devices Inc.", vendor["value"])
        self.assertEqual(OUI_VENDOR_RULE_ID, vendor["derivation"]["ruleId"])
        self.assertEqual("oui-database", vendor["evidence"][0]["sourceType"])

    def test_locally_administered_mac_never_derives_vendor(self):
        self.assertFalse(is_globally_administered_unicast("02:11:22:33:44:55"))
        asset = self.enrich_reservation(
            identifier="dhcp-reservation:local",
            ip_address="192.0.2.101",
            mac_address="02:11:22:33:44:55",
            hostname="edge-device-02",
        )
        self.assertEqual("UNKNOWN", asset["vendor"]["classification"])
        self.assertIsNone(asset["vendor"]["value"])
        self.assertEqual([], asset["vendor"]["evidence"])

    def test_unknown_oui_remains_unknown(self):
        asset = self.enrich_reservation(
            identifier="dhcp-reservation:unknown-oui",
            ip_address="192.0.2.102",
            mac_address="08:99:88:77:66:55",
            hostname="edge-device-03",
        )
        self.assertEqual("UNKNOWN", asset["vendor"]["classification"])

    def test_device_type_is_inferred_only_by_versioned_rule(self):
        asset = self.enrich_reservation(
            identifier="dhcp-reservation:printer",
            ip_address="192.0.2.103",
            mac_address="00:11:22:33:44:56",
            hostname="printer-lab-01",
        )
        device_type = asset["deviceType"]
        self.assertEqual("INFERRED", device_type["classification"])
        self.assertEqual("Printer", device_type["value"])
        self.assertEqual(
            "asset.device-type.printer.v1",
            device_type["derivation"]["ruleId"],
        )
        self.assertEqual("rule-engine", device_type["evidence"][0]["sourceType"])

    def test_conflicting_inference_rules_leave_value_unknown(self):
        asset = self.enrich_reservation(
            identifier="dhcp-reservation:conflict",
            ip_address="192.0.2.104",
            mac_address="00:11:22:33:44:57",
            hostname="conflict-device-01",
        )
        self.assertEqual("UNKNOWN", asset["deviceType"]["classification"])
        self.assertIsNone(asset["deviceType"]["value"])

    def test_model_is_inferred_only_by_versioned_rule(self):
        asset = self.enrich_reservation(
            identifier="dhcp-reservation:model",
            ip_address="192.0.2.105",
            mac_address="04:11:22:33:44:55",
            hostname="sensor-model-x100-01",
        )
        model = asset["model"]
        self.assertEqual("INFERRED", model["classification"])
        self.assertEqual("X100", model["value"])
        self.assertEqual("asset.model.x100.v1", model["derivation"]["ruleId"])

    def test_enriched_assets_are_schema_valid(self):
        assets = [
            self.enrich_reservation(
                identifier="dhcp-reservation:schema-vendor",
                ip_address="192.0.2.106",
                mac_address="00:11:22:33:44:58",
                hostname="printer-lab-02",
            ),
            self.enrich_reservation(
                identifier="dhcp-reservation:schema-unknown",
                ip_address="192.0.2.107",
                mac_address="02:11:22:33:44:58",
                hostname="unknown-device-01",
            ),
        ]
        validator = build_asset_validator()
        for asset in assets:
            errors = list(validator.iter_errors(asset))
            self.assertEqual(
                [],
                errors,
                errors[0].message if errors else "",
            )

    def test_full_parser_preserves_unknown_without_approved_production_enrichment(self):
        fixture = DHCP_FIXTURES / "asset-enrichment.xml"
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

        printer = next(
            asset for asset in model["assets"]
            if "printer-lab-01" in asset["hostnames"]
        )
        phone_adapter = next(
            asset for asset in model["assets"]
            if "phone-adapter-01" in asset["hostnames"]
        )
        unknown = next(
            asset for asset in model["assets"]
            if "device-unknown-01" in asset["hostnames"]
        )

        for asset in (printer, phone_adapter, unknown):
            self.assertEqual("UNKNOWN", asset["vendor"]["classification"])
            self.assertEqual("UNKNOWN", asset["deviceType"]["classification"])
            self.assertEqual("UNKNOWN", asset["model"]["classification"])


if __name__ == "__main__":
    unittest.main()
