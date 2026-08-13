from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from Enrichment.OUI.oui import load_oui_database  # noqa: E402


def _load_update_tool():
    path = ROOT / "tools" / "update_oui_database.py"
    spec = importlib.util.spec_from_file_location("update_oui_database", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load OUI update tool: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OuiProductionContractTests(unittest.TestCase):
    def test_ambiguous_assignment_is_retained_but_not_used_as_vendor(self):
        csv_content = (
            "Registry,Assignment,Organization Name\n"
            "MA-L,001122,Vendor A\n"
            "MA-L,001122,Vendor B\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            csv_path = temp_dir / "oui-test.csv"
            csv_path.write_text(csv_content, encoding="utf-8", newline="\n")
            sha = hashlib.sha256(csv_content.encode("utf-8")).hexdigest().upper()
            manifest_path = temp_dir / "manifest.json"
            manifest_path.write_text(
                json.dumps({
                    "schemaVersion": "1.0.0",
                    "databaseVersion": "test-ambiguous",
                    "registry": "MA-L",
                    "file": csv_path.name,
                    "sha256": sha,
                    "entryCount": 1,
                    "rowCount": 2,
                    "ambiguousAssignmentCount": 1,
                    "ambiguousAssignments": ["001122"],
                    "source": {"name": "Synthetic test", "url": None, "sourceSha256": "0" * 64},
                }),
                encoding="utf-8",
            )
            database = load_oui_database(manifest_path)

        self.assertEqual(1, database.entry_count)
        self.assertEqual(2, database.row_count)
        self.assertEqual(1, database.ambiguous_assignment_count)
        self.assertIsNone(database.lookup("00:11:22:33:44:55"))

    def test_update_tool_preserves_ambiguous_assignment_deterministically(self):
        module = _load_update_tool()
        source_content = (
            "Registry,Assignment,Organization Name,Organization Address\r\n"
            "MA-L,001122,Vendor B,Address B\r\n"
            "MA-L,001122,Vendor A,Address A\r\n"
            "MA-L,00AABB,Vendor C,Address C\r\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            source_path = Path(temp) / "oui.csv"
            source_path.write_text(source_content, encoding="utf-8", newline="")
            normalized, entries, rows, ambiguous, source_sha = module.normalize_source(source_path)

        self.assertEqual(2, entries)
        self.assertEqual(3, rows)
        self.assertEqual(["001122"], ambiguous)
        self.assertEqual(hashlib.sha256(source_content.encode("utf-8")).hexdigest().upper(), source_sha)
        self.assertEqual(
            "Registry,Assignment,Organization Name\n"
            "MA-L,001122,Vendor A\n"
            "MA-L,001122,Vendor B\n"
            "MA-L,00AABB,Vendor C\n",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()
