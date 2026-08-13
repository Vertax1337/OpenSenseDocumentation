#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import defaultdict
from pathlib import Path

DEFAULT_SOURCE_URL = "https://standards-oui.ieee.org/oui/oui.csv"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def normalize_assignment(value: str) -> str:
    value = re.sub(r"[^0-9A-Fa-f]", "", value or "").upper()
    if re.fullmatch(r"[0-9A-F]{6}", value) is None:
        raise ValueError(f"Invalid MA-L assignment: {value!r}")
    return value


def normalize_source(source_path: Path) -> tuple[str, int, int, list[str], str]:
    raw = source_path.read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    required = {"Registry", "Assignment", "Organization Name"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("Source CSV must contain Registry, Assignment and Organization Name")

    rows: set[tuple[str, str]] = set()
    organizations: dict[str, set[str]] = defaultdict(set)
    for row in reader:
        if not any(str(value or "").strip() for value in row.values()):
            continue
        if str(row.get("Registry") or "").strip() != "MA-L":
            continue
        assignment = normalize_assignment(str(row.get("Assignment") or ""))
        organization = str(row.get("Organization Name") or "").strip()
        if not organization:
            raise ValueError(f"Assignment {assignment} has no organization name")
        rows.add((assignment, organization))
        organizations[assignment].add(organization)

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Registry", "Assignment", "Organization Name"])
    for assignment, organization in sorted(rows):
        writer.writerow(["MA-L", assignment, organization])

    ambiguous = sorted(k for k, values in organizations.items() if len(values) > 1)
    return output.getvalue(), len(organizations), len(rows), ambiguous, sha256_bytes(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize an IEEE MA-L CSV snapshot.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--database-version", required=True)
    parser.add_argument("--output-dir", default="data/oui")
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not source.is_file():
        parser.error(f"Source file not found: {source}")
    version = str(args.database_version).strip()
    if re.fullmatch(r"[A-Za-z0-9._-]+", version) is None:
        parser.error("Invalid database-version")

    normalized, entries, rows, ambiguous, source_sha = normalize_source(source)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"oui-{version}.csv"
    snapshot = output_dir / file_name
    snapshot.write_text(normalized, encoding="utf-8", newline="\n")
    snapshot_sha = sha256_bytes(normalized.encode("utf-8"))

    manifest = {
        "schemaVersion": "1.0.0",
        "databaseVersion": version,
        "registry": "MA-L",
        "file": file_name,
        "sha256": snapshot_sha,
        "entryCount": entries,
        "rowCount": rows,
        "ambiguousAssignmentCount": len(ambiguous),
        "ambiguousAssignments": ambiguous,
        "source": {
            "name": "IEEE Registration Authority MA-L public listing",
            "url": args.source_url,
            "sourceSha256": source_sha,
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Wrote {entries} unique MA-L assignments ({rows} rows) to {snapshot}")
    print(f"Ambiguous MA-L assignments: {len(ambiguous)}")
    print(f"Snapshot SHA-256: {snapshot_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
