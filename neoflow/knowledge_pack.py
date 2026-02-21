"""Knowledge pack lifecycle management for NeoFlow."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Callable

import weaviate
from weaviate.config import AdditionalConfig, Timeout

from neoflow.config import Config
from neoflow.init import get_neoflow_agent_system_prompt_dir, get_neoflow_home_path

MANIFEST_FILENAME = "manifest.json"
REGISTRY_FILENAME = "knowledge-pack.json"
MANUAL_IMPORT_PACK_NAME = "manual-import"
_SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass
class ManifestValidationResult:
    manifest: dict
    errors: list[str]


def get_registry_path() -> Path:
    return get_neoflow_home_path() / REGISTRY_FILENAME


def get_neoflow_version() -> str:
    try:
        return metadata.version("neoflow")
    except Exception:
        return "unknown"


def _default_registry() -> dict:
    return {
        "metadata": {"version": get_neoflow_version()},
        "knowledge-pack": [],
    }


def _normalize_registry(raw: dict | None) -> dict:
    registry = _default_registry()
    if isinstance(raw, dict):
        metadata_block = raw.get("metadata")
        if isinstance(metadata_block, dict):
            registry["metadata"].update(metadata_block)
        packs = raw.get("knowledge-pack")
        if isinstance(packs, list):
            registry["knowledge-pack"] = packs
    registry["metadata"]["version"] = get_neoflow_version()
    return registry


def load_registry() -> dict:
    registry_path = get_registry_path()
    if not registry_path.exists():
        return _default_registry()
    with open(registry_path, "r", encoding="utf-8") as file:
        return _normalize_registry(json.load(file))


def save_registry(registry: dict) -> None:
    normalized = _normalize_registry(registry)
    registry_path = get_registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as file:
        json.dump(normalized, file, indent=2)


def load_manifest(package_root: Path) -> dict:
    manifest_path = package_root / MANIFEST_FILENAME
    with open(manifest_path, "r", encoding="utf-8") as file:
        return json.load(file)


def _find_manifest_root(extract_root: Path) -> Path:
    direct = extract_root / MANIFEST_FILENAME
    if direct.is_file():
        return extract_root

    manifests = list(extract_root.rglob(MANIFEST_FILENAME))
    if len(manifests) != 1:
        raise ValueError("Package must contain exactly one manifest.json")
    return manifests[0].parent


def package_filename(manifest: dict) -> str:
    metadata_block = manifest["metadata"]
    return f"{metadata_block['tag']}-v{metadata_block['version']}.nkp"


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_manifest(manifest: dict, package_root: Path) -> list[str]:
    errors: list[str] = []

    metadata_block = manifest.get("metadata")
    if not isinstance(metadata_block, dict):
        errors.append("missing section: metadata")
        return errors

    required_metadata = [
        "name",
        "version",
        "description",
        "author",
        "license",
        "knowledge_cap_date",
        "creation_date",
        "tag",
    ]
    for field_name in required_metadata:
        if not _is_non_empty_string(metadata_block.get(field_name)):
            errors.append(f"metadata.{field_name} is required")

    version_value = metadata_block.get("version")
    if _is_non_empty_string(version_value) and not _SEMVER_PATTERN.match(version_value.strip()):
        errors.append("metadata.version must follow semver format X.Y.Z")

    for section in ("Documentation", "Domain", "Tickets", "CodeSnippets"):
        if section not in manifest:
            errors.append(f"missing section: {section}")

    documentation = manifest.get("Documentation")
    if documentation is not None and not isinstance(documentation, list):
        errors.append("Documentation must be a list")
    elif isinstance(documentation, list):
        for item in documentation:
            if not _is_non_empty_string(item):
                errors.append("Documentation entries must be non-empty strings")
                continue
            path = (package_root / item).resolve()
            if not path.is_dir():
                errors.append(f"Documentation path not found: {item}")

    domains = manifest.get("Domain")
    if domains is not None and not isinstance(domains, list):
        errors.append("Domain must be a list")
    elif isinstance(domains, list):
        for item in domains:
            if not _is_non_empty_string(item):
                errors.append("Domain entries must be non-empty strings")
                continue
            path = (package_root / item).resolve()
            if not path.is_file():
                errors.append(f"Domain file not found: {item}")

    tickets = manifest.get("Tickets")
    if tickets is not None and not isinstance(tickets, list):
        errors.append("Tickets must be a list")
    elif isinstance(tickets, list):
        for item in tickets:
            if not _is_non_empty_string(item):
                errors.append("Tickets entries must be non-empty strings")
                continue
            path = (package_root / item).resolve()
            if not path.is_dir():
                errors.append(f"Tickets path not found: {item}")

    code_snippets = manifest.get("CodeSnippets")
    if code_snippets is not None and not isinstance(code_snippets, list):
        errors.append("CodeSnippets must be a list")
    elif isinstance(code_snippets, list):
        for index, snippet in enumerate(code_snippets):
            prefix = f"CodeSnippets[{index}]"
            if not isinstance(snippet, dict):
                errors.append(f"{prefix} must be an object")
                continue
            if not _is_non_empty_string(snippet.get("name")):
                errors.append(f"{prefix}.name is required")
            files = snippet.get("files")
            if not isinstance(files, list) or not files:
                errors.append(f"{prefix}.files must be a non-empty list")
                continue
            for file_item in files:
                if not _is_non_empty_string(file_item):
                    errors.append(f"{prefix}.files entries must be non-empty strings")
                    continue
                path = (package_root / file_item).resolve()
                if not path.is_file():
                    errors.append(f"CodeSnippets file not found: {file_item}")

    return errors


def validate_manifest_from_path(package_root: Path) -> ManifestValidationResult:
    manifest = load_manifest(package_root)
    errors = validate_manifest(manifest, package_root)
    return ManifestValidationResult(manifest=manifest, errors=errors)


def build_knowledge_pack(source_path: str, output_dir: str | None = None) -> tuple[Path, dict]:
    package_root = Path(source_path).expanduser().resolve()
    if not package_root.is_dir():
        raise ValueError(f"Path not found: {source_path}")

    validation = validate_manifest_from_path(package_root)
    if validation.errors:
        raise ValueError("Invalid manifest")

    out_dir = Path(output_dir).expanduser().resolve() if output_dir else Path.cwd().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    output_file = out_dir / package_filename(validation.manifest)

    with zipfile.ZipFile(output_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for full_path in package_root.rglob("*"):
            if full_path.is_file():
                archive.write(full_path, arcname=str(full_path.relative_to(package_root)))

    return output_file, validation.manifest


def normalize_pack_query(value: str) -> str:
    raw = value.strip()
    if raw.endswith(".nkp"):
        return raw
    return f"{raw}.nkp"


def resolve_registry_entry(registry: dict, pack_query: str) -> dict | None:
    candidates = {pack_query.strip(), normalize_pack_query(pack_query)}
    for entry in registry.get("knowledge-pack", []):
        pack_name = entry.get("pack-name")
        if isinstance(pack_name, str) and pack_name in candidates:
            return entry
    return None


def _weaviate_client(config: Config):
    wv = config.weaviate
    additional_config = AdditionalConfig(
        timeout=Timeout(
            init=wv.timeout_init,
            query=wv.timeout_query,
            insert=wv.timeout_insert,
        )
    )

    if wv.host in {"localhost", "127.0.0.1"}:
        return weaviate.connect_to_local(
            port=wv.port,
            additional_config=additional_config,
        )

    return weaviate.connect_to_custom(
        http_host=wv.host,
        http_port=wv.port,
        http_secure=False,
        grpc_host=wv.host,
        grpc_port=50051,
        grpc_secure=False,
        additional_config=additional_config,
    )


def _delete_by_pack_name(collection, pack_name: str) -> int:
    from weaviate.classes.query import Filter

    total_deleted = 0
    while True:
        result = collection.query.fetch_objects(
            filters=Filter.by_property("pack_name").equal(pack_name),
            limit=200,
            return_properties=["pack_name"],
        )
        if not result.objects:
            break

        for obj in result.objects:
            collection.data.delete_by_id(obj.uuid)
            total_deleted += 1

    return total_deleted


def remove_pack_data_from_weaviate(pack_name: str, config: Config) -> dict[str, int]:
    deleted = {
        "Documentation": 0,
        "CodeSnippets": 0,
        "Tickets": 0,
        "Comments": 0,
    }

    with _weaviate_client(config) as client:
        for collection_name in ("Documentation", "CodeSnippets", "Tickets", "Comments"):
            if client.collections.exists(collection_name):
                collection = client.collections.use(collection_name)
                deleted[collection_name] = _delete_by_pack_name(collection, pack_name)

    return deleted


def install_knowledge_pack(
    package_file: str,
    config: Config,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> dict:
    from neoflow.importer.code_indexer import index_zip_file
    from neoflow.importer.documentation import import_documentation
    from neoflow.importer.importer import import_tickets

    package_path = Path(package_file).expanduser().resolve()
    if not package_path.is_file():
        raise ValueError(f"File not found: {package_file}")
    if package_path.suffix.lower() != ".nkp":
        raise ValueError("Install only supports .nkp files")

    pack_name = package_path.name
    registry = load_registry()
    if resolve_registry_entry(registry, pack_name):
        raise ValueError(f"Package already installed: {pack_name}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(package_path, "r") as archive:
            archive.extractall(temp_root)

        package_root = _find_manifest_root(temp_root)
        validation = validate_manifest_from_path(package_root)
        if validation.errors:
            raise ValueError("Invalid manifest")

        manifest = validation.manifest
        total_steps = 4

        if progress_callback:
            progress_callback(1, total_steps, "Documents")

        for docs_path in manifest.get("Documentation", []):
            import_documentation(str((package_root / docs_path).resolve()), config, pack_name=pack_name)

        domain_names: list[str] = []
        target_domain_dir = get_neoflow_agent_system_prompt_dir()
        target_domain_dir.mkdir(parents=True, exist_ok=True)
        if progress_callback:
            progress_callback(2, total_steps, "Domain")
        for domain_path in manifest.get("Domain", []):
            source_file = (package_root / domain_path).resolve()
            target_file = target_domain_dir / source_file.name
            shutil.copy2(source_file, target_file)
            domain_names.append(source_file.name)

        if progress_callback:
            progress_callback(3, total_steps, "Tickets")
        for ticket_path in manifest.get("Tickets", []):
            import_tickets(
                config,
                tickets_dir=str((package_root / ticket_path).resolve()),
                pack_name=pack_name,
                replace_existing=False,
            )

        if progress_callback:
            progress_callback(4, total_steps, "Code Snippets")
        for snippet in manifest.get("CodeSnippets", []):
            snippet_name = snippet["name"]
            for zip_file in snippet["files"]:
                index_zip_file(
                    str((package_root / zip_file).resolve()),
                    snippet_name,
                    config,
                    pack_name=pack_name,
                )

    metadata_block = manifest["metadata"]
    registry_entry = {
        "name": metadata_block["name"],
        "version": metadata_block["version"],
        "description": metadata_block["description"],
        "tag": metadata_block["tag"],
        "pack-name": pack_name,
        "domains": domain_names,
    }
    registry["knowledge-pack"].append(registry_entry)
    save_registry(registry)

    return registry_entry


def uninstall_knowledge_pack(pack_query: str, config: Config, keep_domain: bool = False) -> dict:
    target = pack_query.strip()
    if target == MANUAL_IMPORT_PACK_NAME:
        deleted = remove_pack_data_from_weaviate(MANUAL_IMPORT_PACK_NAME, config)
        return {
            "name": MANUAL_IMPORT_PACK_NAME,
            "pack-name": MANUAL_IMPORT_PACK_NAME,
            "domains_removed": [],
            "weaviate_deleted": deleted,
            "manual_import": True,
        }

    registry = load_registry()
    entry = resolve_registry_entry(registry, target)
    if not entry:
        raise ValueError(f"Knowledge pack not found: {pack_query}")

    pack_name = entry.get("pack-name", "")
    if not isinstance(pack_name, str) or not pack_name:
        raise ValueError("Invalid pack entry: missing pack-name")

    deleted = remove_pack_data_from_weaviate(pack_name, config)

    removed_domains: list[str] = []
    if not keep_domain:
        domain_dir = get_neoflow_agent_system_prompt_dir()
        for domain_name in entry.get("domains", []):
            if not isinstance(domain_name, str):
                continue
            domain_file = domain_dir / domain_name
            if domain_file.exists():
                domain_file.unlink()
                removed_domains.append(domain_name)

    registry["knowledge-pack"] = [
        item
        for item in registry.get("knowledge-pack", [])
        if item.get("pack-name") != pack_name
    ]
    save_registry(registry)

    return {
        "name": entry.get("name", ""),
        "pack-name": pack_name,
        "domains_removed": removed_domains,
        "weaviate_deleted": deleted,
        "manual_import": False,
    }


def list_knowledge_packs() -> list[dict]:
    registry = load_registry()
    return registry.get("knowledge-pack", [])
