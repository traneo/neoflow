# Knowledge Pack

Build, install, manage, and remove reusable NeoFlow data bundles.

Knowledge Packs package multiple data sources into a single `.nkp` artifact:
- Documentation folders
- Domain prompt files
- Ticket folders
- Code zip archives

Installed packs are tracked in `~/.neoflow/knowledge-pack.json` and indexed data is tagged with `pack-name` for clean uninstall.

## Table of Contents

- [Overview](#overview)
- [CLI Commands](#cli-commands)
- [Manifest Format](#manifest-format)
- [Package Lifecycle](#package-lifecycle)
- [Registry File](#registry-file)
- [Manual Import Cleanup](#manual-import-cleanup)
- [Troubleshooting](#troubleshooting)

## Overview

Use Knowledge Pack when you want a portable and versioned bundle of NeoFlow knowledge.

Typical flow:
1. Create content folders and a `manifest.json`
2. Run build to generate `<tag>-v<version>.nkp`
3. Run install to import all data into NeoFlow
4. Run list to verify installed packs
5. Run uninstall when you no longer need a pack

## CLI Commands

```bash
# Build
neoflow knowledge-pack --build <path/to/content>
neoflow knowledge-pack --build <path/to/content> -o <output/folder>

# Install
neoflow knowledge-pack --install <file.nkp>

# Uninstall
neoflow knowledge-pack --uninstall <pack-name-or-pack-name-without-extension>
neoflow knowledge-pack --uninstall <pack-name> --keep-domain

# List
neoflow knowledge-pack --list
```

### Build

```bash
neoflow knowledge-pack --build ./my_pack
```

What happens:
- Prints `Checking manifest info...`
- Validates all required manifest fields and paths
- Prints `Manifest is valid!` if checks pass
- Builds output file named `<metadata.tag>-v<metadata.version>.nkp`
- Writes artifact to current working directory, or `-o/--output` if provided

If validation fails, NeoFlow prints `Invalid manifest` plus specific validation errors.

### Install

```bash
neoflow knowledge-pack --install customer-knowledge-base-v1.0.0.nkp
```

What happens:
- Verifies package and validates the embedded `manifest.json`
- Shows package metadata and asks for confirmation
- Imports all sections in order: Documents → Domain → Tickets → Code Snippets
- Saves the pack in `~/.neoflow/knowledge-pack.json`
- Prints `knowledge pack Installed.` on success

Install protections:
- Rejects non-`.nkp` files
- Rejects invalid manifests
- Rejects already-installed exact package names

### Uninstall

```bash
neoflow knowledge-pack --uninstall customer-knowledge-base-v1.0.0
neoflow knowledge-pack --uninstall customer-knowledge-base-v1.0.0.nkp
neoflow knowledge-pack --uninstall customer-knowledge-base-v1.0.0.nkp --keep-domain
```

`--uninstall` accepts package names with or without `.nkp`.

What happens:
- Resolves package from `knowledge-pack.json`
- Deletes Weaviate objects tagged with that pack name from:
  - `Documentation`
  - `CodeSnippets`
  - `Tickets`
  - `Comments`
- Removes copied domain prompt files unless `--keep-domain` is set
- Removes pack entry from `knowledge-pack.json`
- Prints `knowledge pack Removed.` on success

### List

```bash
neoflow knowledge-pack --list
```

Shows installed pack metadata:
- `name`
- `version`
- `description`
- `pack-name`

## Manifest Format

Each pack root must contain one `manifest.json`.

Required metadata fields:
- `name`
- `version` (must follow semver `X.Y.Z`)
- `description`
- `author`
- `license`
- `knowledge_cap_date`
- `creation_date`
- `tag`

Required top-level sections:
- `Documentation` (list of directories)
- `Domain` (list of files)
- `Tickets` (list of directories)
- `CodeSnippets` (list of objects with `name` and non-empty `files` list)

Example:

```json
{
  "metadata": {
    "name": "Customer Knowledge Base",
    "version": "1.0.0",
    "description": "A knowledge base for an internal platform.",
    "author": "Tadeu",
    "license": "MIT",
    "creation_date": "2024-06-01",
    "knowledge_cap_date": "2024-05-23",
    "tag": "customer-knowledge-base"
  },
  "Documentation": ["documentation"],
  "Domain": ["domain/platform.md"],
  "Tickets": ["tickets"],
  "CodeSnippets": [
    {
      "name": "Platform-SDK",
      "files": ["zip_file/platform-sdk-master.zip"]
    }
  ]
}
```

Validation rules include path existence checks for every referenced directory/file.

## Package Lifecycle

### Build internals
- Reads and validates `manifest.json`
- Zips the full pack root into `.nkp`

### Install internals
- Unzips to a temp directory
- Re-validates manifest before importing
- Imports docs, tickets, and code snippets with `pack-name` tag
- Copies domain files to `~/.neoflow/agent_system_prompt`
- Appends pack metadata to `knowledge-pack.json`

### Uninstall internals
- Uses `pack-name` to delete imported Weaviate data
- Removes copied domain files (unless `--keep-domain`)
- Removes pack entry from registry

## Registry File

NeoFlow tracks installed packs in:

```text
~/.neoflow/knowledge-pack.json
```

Structure:

```json
{
  "metadata": {
    "version": "<neoflow-version>"
  },
  "knowledge-pack": [
    {
      "name": "knowledge-pack-name",
      "version": "1.0.0",
      "description": "description",
      "tag": "knowledge-pack-tag",
      "pack-name": "knowledge-pack-tag-v1.0.0.nkp",
      "domains": ["platform.md"]
    }
  ]
}
```

## Manual Import Cleanup

Data imported through `neoflow import ...` is tagged as `manual-import`.

To remove all manually imported data:

```bash
neoflow knowledge-pack --uninstall manual-import
```

This removes all Weaviate objects associated with manual imports and does not require a registry entry.

## Troubleshooting

- `knowledge pack invalid, unable to install it!`
  - The package is missing a valid `manifest.json` or contains invalid paths/fields.
- `Package already installed: ...`
  - Uninstall that exact package name first, then install again.
- `Knowledge pack not found: ...`
  - Run `neoflow knowledge-pack --list` and use the listed `pack-name`.
- `Not able to install/uninstall knowledge pack!`
  - Verify Weaviate connectivity and NeoFlow configuration.
