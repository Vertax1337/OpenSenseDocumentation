# Versioned OUI data

OpenSenseDocumentation performs **no live OUI lookup during a normal build**.

The runtime expects an optional, repository-local snapshot:

```text
data/oui/
├── oui-<database-version>.csv
└── manifest.json
```

If `manifest.json` is absent, the build does not contact an external service. Asset `vendor` values remain `UNKNOWN`.

## Source

The Phase-4.5 contract targets the IEEE Registration Authority **MA-L** public listing because MA-L assignments include an OUI used as a 24-bit prefix for EUI-48/MAC addresses.

The source URL recorded by the update tool is:

```text
https://standards-oui.ieee.org/oui/oui.csv
```

The source file is downloaded only as a controlled maintenance step, never by the normal documentation build.

## Create or update a snapshot

1. Download the IEEE MA-L `oui.csv` file to a temporary local path.
2. Run:

```bash
python tools/update_oui_database.py \
  --source path/to/oui.csv \
  --database-version 2026-08
```

3. Review and commit both generated files:

```text
data/oui/oui-2026-08.csv
data/oui/manifest.json
```

The update tool:

- accepts the IEEE-format CSV
- keeps only `MA-L` rows
- normalizes to UTF-8 without BOM
- uses LF line endings
- sorts assignments deterministically
- writes a SHA-256-bound manifest
- records the SHA-256 of the downloaded source file

## Runtime validation

Before vendor enrichment, the runtime verifies:

```text
manifest.schemaVersion
manifest.registry == MA-L
manifest.file
manifest.sha256 == actual snapshot SHA-256
manifest.entryCount == parsed assignment count
```

A hash/count/format mismatch is a hard error.

## Vendor safety rule

Vendor is derived only for globally administered unicast MAC addresses with an exact 24-bit MA-L match.

Locally administered/randomized MACs, multicast/group addresses, broadcast/null MACs and unknown prefixes stay `UNKNOWN`.

## Current repository status

The deterministic loader, manifest/hash contract and synthetic regression fixtures are implemented in Phase 4.5.

A productive IEEE snapshot is intentionally **not synthesized or guessed**. Until a real downloaded IEEE MA-L source is normalized and committed through the update tool, productive vendor enrichment remains `UNKNOWN`.
