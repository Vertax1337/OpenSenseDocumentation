#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from pathlib import Path


DEFAULT_SOURCE_URL = "https://standards-oui.ieee.org/oui/oui.csv"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def normalize_assignment(value: str) -> str:
    compact = re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()
    if len(compact) != 6 or re.fullmatch(r"[0-9A-F]{6}", compact) is None:
        raise ValueError(f"Invalid MA-L assignment: {value!r}")
    return compact


def normalize_source(source_path: Path) -> tuple[str, int, str]:
    raw = source_path.read_bytes()
    source_sha = sha256_bytes(raw)
    text = raw.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    required = {"Registry", "Assignment", "Organization Name"}
    if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
        raise ValueError(
            "Source CSV must contain Registry, Assignment and Organization Name"
        )

    rows: dict[str, tuple[str, str]] = {}
    for row in reader:
        if not any(str(value or "").strip() for value in row.values()):
            continue
        if str(row.get("Registry") or "").strip() != "MA-L":
            continue
        assignment = normalize_assignment(str(row.get("Assignment") or ""))
        organization = str(row.get("Organization Name") or "").strip()
        address = str(row.get("Organization Address") or "").strip()
        if not organization:
            raise ValueError(f"Assignment {assignment} has no organization name")
        existing = rows.get(assignment)
        candidate = (organization, address)
        if existing is not None and existing != candidate:
            raise ValueError(f"Conflicting source rows for assignment {assignment}")
        rows[assignment] = candidate

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Registry", "Assignment", "Organization Name", "Organization Address"])
    for assignment in sorted(rows):
        organization, address = rows[assignment]
        writer.writerow(["MA-L", assignment, organization, address])

    return buffer.getvalue(), len(rows), source_sha


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Normalize a downloaded IEEE Registration Authority MA-L CSV into "
            "the versioned local OUI snapshot used by OpenSenseDocumentation."
        )
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to a previously downloaded IEEE MA-L oui.csv file",
    )
    parser.add_argument(
        "--database-version",
        required=True,
        help="Version label for the local snapshot, e.g. 2026-08",
    )
    parser.add_argument(
        "--output-dir",
        default="data/oui",
        help="Target directory for snapshot and manifest (default: data/oui)",
    )
    parser.add_argument(
        "--source-url",
        default=DEFAULT_SOURCE_URL,
        help="Source URL recorded in the manifest",
    )
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        parser.error(f"Source file not found: {source_path}")

    version = str(args.database_version).strip()
    if re.fullmatch(r"[A-Za-z0-9._-]+", version) is None:
        parser.error(
            "database-version may contain only letters, digits, dot, underscore and hyphen"
        )

    normalized, entry_count, source_sha = normalize_source(source_path)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"oui-{version}.csv"
    output_path = output_dir / file_name
    output_path.write_text(normalized, encoding="utf-8", newline="\n")
    output_sha = sha256_bytes(normalized.encode("utf-8"))

    manifest = {
        "schemaVersion": "1.0.0",
        "databaseVersion": version,
        "registry": "MA-L",
        "file": file_name,
        "sha256": output_sha,
        "entryCount": entry_count,
        "source": {
            "name": "IEEE Registration Authority MA-L public listing",
            "url": args.source_url,
            "sourceSha256": source_sha,
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"Wrote {entry_count} MA-L assignments to {output_path}")
    print(f"Snapshot SHA-256: {output_sha}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
