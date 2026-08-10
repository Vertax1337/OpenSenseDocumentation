#!/usr/bin/env python3
"""Validate the Canonical Infrastructure Model schema and regression fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "infrastructure-model.schema.json"
EXAMPLES = ROOT / "schemas" / "examples"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    schema = load_json(SCHEMA_PATH)

    schema_documents = [schema]
    schema_documents.extend(
        load_json(path)
        for path in sorted((ROOT / "schemas").glob("*.schema.json"))
        if path != SCHEMA_PATH
    )

    registry = Registry()
    for document in schema_documents:
        Draft202012Validator.check_schema(document)
        registry = registry.with_resource(document["$id"], Resource.from_contents(document))

    validator = Draft202012Validator(
        schema,
        registry=registry,
        format_checker=FormatChecker(),
    )

    failures: list[str] = []

    valid_files = sorted(EXAMPLES.glob("*.valid.json"))
    invalid_files = sorted(EXAMPLES.glob("*.invalid.json"))

    if not valid_files:
        failures.append("No *.valid.json fixtures found.")
    if not invalid_files:
        failures.append("No *.invalid.json fixtures found.")

    for path in valid_files:
        errors = sorted(validator.iter_errors(load_json(path)), key=lambda e: list(e.absolute_path))
        if errors:
            failures.append(f"{path.name} should be valid but failed: {errors[0].json_path}: {errors[0].message}")
        else:
            print(f"PASS valid   {path.name}")

    for path in invalid_files:
        errors = list(validator.iter_errors(load_json(path)))
        if not errors:
            failures.append(f"{path.name} should be invalid but passed.")
        else:
            print(f"PASS invalid {path.name}")

    if failures:
        print("\nSchema regression failures:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("\nCanonical Infrastructure Model schema validation succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
