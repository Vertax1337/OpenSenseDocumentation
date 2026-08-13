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
  --database-version 2026-08-13
```

3. Review and commit both generated files:

```text
data/oui/oui-2026-08-13.csv
data/oui/manifest.json
```

The update tool:

- accepts the IEEE-format CSV
- keeps only `MA-L` rows
- strips organization addresses because runtime vendor attribution only needs assignment and organization name
- normalizes to UTF-8 without BOM
- uses LF line endings
- sorts assignment/vendor rows deterministically
- writes a SHA-256-bound manifest
- records the SHA-256 of the downloaded source file
- records unique assignment count, row count and ambiguous assignments

## Ambiguous assignments

The IEEE public listing can contain more than one organization name for the same 24-bit MA-L assignment. This is not resolved by choosing the first row or by inventing precedence.

The local snapshot retains all distinct assignment/vendor rows. The manifest records the ambiguous prefixes. Runtime vendor enrichment behaves as follows:

```text
one organization for MA-L assignment
-> Vendor DERIVED

multiple organizations for same MA-L assignment
-> Vendor UNKNOWN
```

This preserves the project rule that ambiguous source data must not be guessed.

## Runtime validation

Before vendor enrichment, the runtime verifies:

```text
manifest.schemaVersion
manifest.registry == MA-L
manifest.file
manifest.sha256 == actual snapshot SHA-256
manifest.entryCount == parsed unique assignment count
manifest.rowCount == parsed assignment/vendor row count
manifest.ambiguousAssignmentCount == detected ambiguous assignment count
manifest.ambiguousAssignments == detected ambiguous assignments
```

A hash/count/format mismatch is a hard error.

## Vendor safety rule

Vendor is derived only for globally administered unicast MAC addresses with an exact and unambiguous 24-bit MA-L match.

Locally administered/randomized MACs, multicast/group addresses, broadcast/null MACs, unknown prefixes and ambiguous MA-L assignments stay `UNKNOWN`.

## 2026-08-13 production snapshot preparation

The official IEEE MA-L CSV downloaded on 2026-08-13 was normalized successfully with the current contract.

Prepared snapshot metadata:

```text
databaseVersion: 2026-08-13
unique assignments: 39924
assignment/vendor rows: 39927
ambiguous assignments: 2
source SHA-256: 8FAA8AC4707DCC08E47895C4083B3C674EF996CFFD95C11C5ECD8115B7DE4D2F
snapshot SHA-256: C8040AFCB4CDCD3D8E73B08AB9F3E94B817519ABF0B763806121093A49DDD49D
```

The generated snapshot and manifest must be committed together. A manifest without its referenced snapshot is invalid and would intentionally fail the build.
