#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from .opnsense_parser import ParserError, parse_opnsense_config, write_model
except ImportError:  # direct script execution
    from opnsense_parser import ParserError, parse_opnsense_config, write_model


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert sanitized OPNsense config.xml into Canonical Infrastructure Model JSON")
    parser.add_argument("--input", required=True, help="Path to config.sanitized.xml")
    parser.add_argument("--report", required=True, help="Path to sanitization-report.json")
    parser.add_argument("--output", required=True, help="Path to infrastructure-model.json")
    args = parser.parse_args()

    try:
        model = parse_opnsense_config(args.input, args.report)
        write_model(model, args.output)
    except ParserError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Canonical Infrastructure Model written to {Path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
