from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from Parser.core import ParserError
except ImportError:  # direct execution with src/Parser on sys.path
    from core import ParserError


OUI_MANIFEST_SCHEMA_VERSION = "1.0.0"
OUI_VENDOR_RULE_ID = "asset.vendor-oui.v1"
IEEE_MA_L_SOURCE_URL = "https://standards-oui.ieee.org/oui/oui.csv"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _normalized_assignment(value: str) -> str:
    compact = re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()
    if len(compact) != 6 or re.fullmatch(r"[0-9A-F]{6}", compact) is None:
        raise ParserError(f"Invalid MA-L assignment in OUI database: {value!r}")
    return compact


def _normalized_mac_compact(value: str) -> str:
    compact = re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()
    if len(compact) != 12 or re.fullmatch(r"[0-9A-F]{12}", compact) is None:
        raise ParserError(f"Invalid asset MAC address for OUI lookup: {value!r}")
    return compact


def is_globally_administered_unicast(value: str) -> bool:
    compact = _normalized_mac_compact(value)
    first_octet = int(compact[:2], 16)
    if compact in {"000000000000", "FFFFFFFFFFFF"}:
        return False
    return (first_octet & 0x03) == 0


@dataclass(frozen=True)
class OuiDatabase:
    database_version: str
    file_name: str
    file_sha256: str
    entry_count: int
    source_name: str
    source_url: str | None
    entries: dict[str, str]

    def lookup(self, mac_address: str) -> tuple[str, str] | None:
        if not is_globally_administered_unicast(mac_address):
            return None
        compact = _normalized_mac_compact(mac_address)
        assignment = compact[:6]
        organization = self.entries.get(assignment)
        if organization is None:
            return None
        return assignment, organization

    def evidence(self, assignment: str) -> dict[str, Any]:
        return {
            "sourceType": "oui-database",
            "sourceId": f"{self.database_version}:{self.file_name}",
            "path": f"assignment:{assignment}",
            "sourceSha256": self.file_sha256,
            "note": None,
        }


def load_oui_database(manifest_path: str | Path) -> OuiDatabase:
    manifest_path = Path(manifest_path).resolve()
    if not manifest_path.is_file():
        raise ParserError(f"OUI manifest not found: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ParserError(f"Invalid OUI manifest: {manifest_path}") from exc

    if manifest.get("schemaVersion") != OUI_MANIFEST_SCHEMA_VERSION:
        raise ParserError(
            f"Unsupported OUI manifest schemaVersion: {manifest.get('schemaVersion')!r}"
        )

    database_version = str(manifest.get("databaseVersion") or "").strip()
    file_name = str(manifest.get("file") or "").strip()
    expected_sha = str(manifest.get("sha256") or "").strip().upper()
    entry_count = manifest.get("entryCount")
    source = manifest.get("source") or {}

    if not database_version:
        raise ParserError("OUI manifest databaseVersion is required")
    if not file_name or Path(file_name).name != file_name:
        raise ParserError("OUI manifest file must be a simple relative file name")
    if re.fullmatch(r"[0-9A-F]{64}", expected_sha) is None:
        raise ParserError("OUI manifest sha256 must contain exactly 64 hex characters")
    if not isinstance(entry_count, int) or entry_count < 0:
        raise ParserError("OUI manifest entryCount must be a non-negative integer")
    if manifest.get("registry") != "MA-L":
        raise ParserError("Phase 4.5 OUI database must use registry MA-L")

    database_path = (manifest_path.parent / file_name).resolve()
    if database_path.parent != manifest_path.parent:
        raise ParserError("OUI database file must reside next to its manifest")
    if not database_path.is_file():
        raise ParserError(f"OUI database not found: {database_path}")

    actual_sha = _sha256_file(database_path)
    if actual_sha != expected_sha:
        raise ParserError(
            f"OUI database SHA-256 mismatch: expected {expected_sha}, got {actual_sha}"
        )

    entries: dict[str, str] = {}
    try:
        with database_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"Registry", "Assignment", "Organization Name"}
            if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
                raise ParserError(
                    "OUI database CSV must contain Registry, Assignment and Organization Name"
                )
            for row in reader:
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                if str(row.get("Registry") or "").strip() != "MA-L":
                    raise ParserError("OUI database contains a non-MA-L registry row")
                assignment = _normalized_assignment(str(row.get("Assignment") or ""))
                organization = str(row.get("Organization Name") or "").strip()
                if not organization:
                    raise ParserError(
                        f"OUI database assignment {assignment} has no organization name"
                    )
                existing = entries.get(assignment)
                if existing is not None and existing != organization:
                    raise ParserError(
                        f"Conflicting OUI organizations for assignment {assignment}"
                    )
                entries[assignment] = organization
    except UnicodeError as exc:
        raise ParserError(f"OUI database is not valid UTF-8: {database_path}") from exc

    if len(entries) != entry_count:
        raise ParserError(
            f"OUI manifest entryCount mismatch: expected {entry_count}, got {len(entries)}"
        )

    return OuiDatabase(
        database_version=database_version,
        file_name=file_name,
        file_sha256=actual_sha,
        entry_count=len(entries),
        source_name=str(source.get("name") or "IEEE Registration Authority MA-L"),
        source_url=str(source.get("url")).strip() if source.get("url") else None,
        entries=entries,
    )
