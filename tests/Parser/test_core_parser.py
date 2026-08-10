from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "Parser"))

from opnsense_parser import ParserError, parse_opnsense_config, stable_id, write_model  # noqa: E402

FIXTURE = ROOT / "tests" / "Fixtures" / "Parser" / "core-config.sanitized.xml"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def write_report(path: Path, xml_path: Path, status: str = "Clean", output_sha: str | None = None):
    report = {
        "sanitizerVersion": "1.1.0",
        "status": status,
        "source": {
            "fileName": "config.xml",
            "sha256": "1" * 64,
        },
        "output": {
            "fileName": "config.sanitized.xml",
            "sha256": output_sha or sha256_file(xml_path),
        },
        "residualFindings": [],
    }
    path.write_text(json.dumps(report), encoding="utf-8")


def build_validator():
    schema_dir = ROOT / "schemas"
    root_schema = json.loads((schema_dir / "infrastructure-model.schema.json").read_text(encoding="utf-8"))
    registry = Registry()
    for schema_path in sorted(schema_dir.glob("*.schema.json")):
        document = json.loads(schema_path.read_text(encoding="utf-8"))
        registry = registry.with_resource(document["$id"], Resource.from_contents(document))
    return Draft202012Validator(root_schema, registry=registry, format_checker=FormatChecker())


class CoreParserTests(unittest.TestCase):
    def parse_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "report.json"
            write_report(report, FIXTURE)
            return parse_opnsense_config(FIXTURE, report)

    def test_output_is_schema_valid(self):
        model = self.parse_fixture()
        errors = list(build_validator().iter_errors(model))
        self.assertEqual([], errors, errors[0].message if errors else "")

    def test_same_input_produces_identical_model(self):
        a = self.parse_fixture()
        b = self.parse_fixture()
        self.assertEqual(a, b)

    def test_model_matches_cross_platform_semantic_fingerprint(self):
        model = self.parse_fixture()
        model = json.loads(json.dumps(model))
        model["modelId"] = "model:sha256:000000000000000000000000"
        model["source"]["sanitizedSha256"] = "0" * 64

        def scrub(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key == "sourceSha256" and child is not None:
                        value[key] = "0" * 64
                    else:
                        scrub(child)
            elif isinstance(value, list):
                for child in value:
                    scrub(child)

        scrub(model)
        canonical = json.dumps(model, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        expected = (ROOT / "tests" / "Expected" / "Parser" / "core-model.sha256").read_text(encoding="ascii").strip()
        self.assertEqual(expected, actual)

    def test_stable_id_matches_phase2_algorithm_known_vector(self):
        self.assertEqual("interface:lan", stable_id("Interface", natural_id=" LAN "))
        self.assertEqual(
            "asset:sha256:612f197baa4b231e592d4c87",
            stable_id("Asset", identity_parts=["02:00:00:00:00:60", "192.0.2.60"]),
        )

    def test_system_and_interfaces_are_parsed_without_inventing_wan_ip(self):
        model = self.parse_fixture()
        self.assertEqual("fw-example", model["system"]["hostname"])
        self.assertEqual(["Local Database", "TOTP-Server"], model["system"]["authBackends"])
        wan = next(item for item in model["interfaces"] if item["name"] == "wan")
        self.assertEqual("dhcp", wan["addresses"][0]["address"])
        self.assertEqual("dhcp", wan["addresses"][0]["assignment"])
        lan_net = next(item for item in model["networks"] if item["role"] == "lan")
        self.assertEqual("192.0.2.0/24", lan_net["cidr"])
        self.assertEqual("DERIVED", lan_net["classification"])

    def test_vlan_references_assigned_parent_and_vlan_interface(self):
        model = self.parse_fixture()
        vlan = model["vlans"][0]
        self.assertEqual(20, vlan["tag"])
        self.assertEqual("interface:opt1", vlan["parentInterfaceRef"]["id"])
        self.assertEqual("interface:opt2", vlan["vlanInterfaceRef"]["id"])
        opt2 = next(item for item in model["interfaces"] if item["name"] == "opt2")
        self.assertEqual("interface:opt1", opt2["parentRef"]["id"])

    def test_aliases_preserve_empty_and_dynamic_state(self):
        model = self.parse_fixture()
        empty = next(item for item in model["aliases"] if item["name"] == "EMPTY_NET")
        dynamic = next(item for item in model["aliases"] if item["name"] == "THREAT_FEED")
        ports = next(item for item in model["aliases"] if item["name"] == "APP_PORTS")
        self.assertFalse(empty["resolved"])
        self.assertEqual([], empty["content"])
        self.assertTrue(dynamic["dynamic"])
        self.assertFalse(dynamic["resolved"])
        self.assertEqual(["443", "8443"], ports["content"])

    def test_gateway_route_and_ipsec_are_parsed(self):
        model = self.parse_fixture()
        gateway = model["gateways"][0]
        route = model["routes"][0]
        vpn = model["vpn"][0]
        self.assertEqual("VPNGW", gateway["name"])
        self.assertFalse(gateway["monitoringEnabled"])
        self.assertEqual(gateway["id"], route["gatewayRef"]["id"])
        self.assertEqual("route-based", vpn["mode"])
        self.assertIsNone(vpn["localEndpoint"])
        self.assertEqual("198.51.100.10", vpn["remoteEndpoint"])
        self.assertEqual(gateway["id"], vpn["gatewayRef"]["id"])
        self.assertEqual("interface:ipsec1", vpn["tunnelInterfaceRef"]["id"])
        vti = next(item for item in model["interfaces"] if item["name"] == "ipsec1")
        self.assertTrue(any(addr["address"] == "169.254.100.1" for addr in vti["addresses"]))

    def test_nat_and_firewall_association_is_deterministic(self):
        model = self.parse_fixture()
        nat = next(item for item in model["nat"] if item["kind"] == "port-forward")
        fw = next(item for item in model["firewallRules"] if item["description"] == "Published service")
        self.assertEqual(nat["id"], fw["associatedNatRefs"][0]["id"])
        self.assertEqual(fw["id"], nat["associatedFirewallRuleRefs"][0]["id"])
        disabled = next(item for item in model["firewallRules"] if item["description"] == "Disabled test")
        self.assertFalse(disabled["enabled"])
        self.assertEqual(2, disabled["order"])

    def test_no_nat_alias_reference_is_preserved_even_when_alias_empty(self):
        model = self.parse_fixture()
        no_nat = next(item for item in model["nat"] if item["kind"] == "no-nat")
        self.assertEqual("alias", no_nat["destination"]["kind"])
        self.assertEqual("EMPTY_NET", no_nat["destination"]["value"])
        self.assertIsNotNone(no_nat["destination"]["ref"])

    def test_unknown_gateway_becomes_unresolved_reference_instead_of_being_dropped(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            xml_path = temp / "config.sanitized.xml"
            xml_text = FIXTURE.read_text(encoding="utf-8").replace(
                "<gateway>VPNGW</gateway><descr>Remote app network</descr>",
                "<gateway>MISSING_GW</gateway><descr>Remote app network</descr>",
            )
            xml_path.write_text(xml_text, encoding="utf-8")
            report = temp / "report.json"
            write_report(report, xml_path)
            model = parse_opnsense_config(xml_path, report)
            route = model["routes"][0]
            self.assertEqual("gateway:missing_gw", route["gatewayRef"]["id"])
            self.assertTrue(any(item["targetIdentifier"] == "MISSING_GW" for item in model["unresolvedReferences"]))

    def test_report_must_be_clean_and_match_xml_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            report = Path(temp) / "report.json"
            write_report(report, FIXTURE, status="RequiresReview")
            with self.assertRaises(ParserError):
                parse_opnsense_config(FIXTURE, report)

            write_report(report, FIXTURE, output_sha="0" * 64)
            with self.assertRaises(ParserError):
                parse_opnsense_config(FIXTURE, report)

    def test_writer_uses_utf8_lf_and_reproducible_content(self):
        model = self.parse_fixture()
        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / "a.json"
            b = Path(temp) / "b.json"
            write_model(model, a)
            write_model(model, b)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertNotIn(b"\r\n", a.read_bytes())
            self.assertFalse(a.read_bytes().startswith(b"\xef\xbb\xbf"))


if __name__ == "__main__":
    unittest.main()
