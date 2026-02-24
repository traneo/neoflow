#!/usr/bin/env bash
set -euo pipefail

if ! command -v neoflow >/dev/null 2>&1; then
  echo "Error: 'neoflow' is not installed or not in PATH."
  echo "Please install neoflow globally first, then re-run this script."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCS_DIR="${REPO_ROOT}/docs"

if [[ ! -d "${DOCS_DIR}" ]]; then
  echo "Error: docs directory not found at ${DOCS_DIR}"
  exit 1
fi

PACK_TAG="neoflow-docs"
PACK_VERSION="${PACK_VERSION:-$(date +%Y.%m.%d)}"
TODAY="$(date +%F)"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

PACK_SRC_DIR="${TMP_DIR}/pack-src"
PACK_DOCS_DIR="${PACK_SRC_DIR}/documentation"
PACK_SNIPPETS_DIR="${PACK_SRC_DIR}/zip_file"
PACK_DOMAIN_DIR="${PACK_SRC_DIR}/domain"

mkdir -p "${PACK_DOCS_DIR}"
cp -a "${DOCS_DIR}/." "${PACK_DOCS_DIR}/"

# Keep only the pack root manifest.json.
# Nested manifests (for example from docs/tools/*) make install validation fail.
find "${PACK_DOCS_DIR}" -type f -name "manifest.json" -delete

mkdir -p "${PACK_SNIPPETS_DIR}"
mkdir -p "${PACK_DOMAIN_DIR}"

# Copy tool development domain prompt
cp "${DOCS_DIR}/agent_system_prompt/neoflow_tools_dev.md" "${PACK_DOMAIN_DIR}/"

zip_dir_to_file() {
  local source_dir="$1"
  local out_file="$2"

  if [[ ! -d "${source_dir}" ]]; then
    return 0
  fi

  python3 - <<'PY' "${source_dir}" "${out_file}"
import pathlib
import sys
import zipfile

source = pathlib.Path(sys.argv[1]).resolve()
out_file = pathlib.Path(sys.argv[2]).resolve()
out_file.parent.mkdir(parents=True, exist_ok=True)

with zipfile.ZipFile(out_file, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for full_path in source.rglob("*"):
        if full_path.is_file():
            archive.write(full_path, arcname=str(full_path.relative_to(source)))
PY
}

zip_dir_to_file "${DOCS_DIR}/tools/simple" "${PACK_SNIPPETS_DIR}/tools-simple.zip"
zip_dir_to_file "${DOCS_DIR}/tools/medium" "${PACK_SNIPPETS_DIR}/tools-medium.zip"
zip_dir_to_file "${DOCS_DIR}/tools/complex" "${PACK_SNIPPETS_DIR}/tools-complex.zip"

cat > "${PACK_SRC_DIR}/manifest.json" <<EOF
{
  "metadata": {
    "name": "NeoFlow Documentation",
    "version": "${PACK_VERSION}",
    "description": "Knowledge pack generated from the NeoFlow docs directory.",
    "author": "NeoFlow",
    "license": "MIT",
    "creation_date": "${TODAY}",
    "knowledge_cap_date": "${TODAY}",
    "tag": "${PACK_TAG}"
  },
  "Documentation": ["documentation"],
  "Domain": ["domain/neoflow_tools_dev.md"],
  "Tickets": [],
  "CodeSnippets": [
    {
      "name": "tools-simple-example",
      "files": ["zip_file/tools-simple.zip"]
    },
    {
      "name": "tools-medium-example",
      "files": ["zip_file/tools-medium.zip"]
    },
    {
      "name": "tools-complex-example",
      "files": ["zip_file/tools-complex.zip"]
    }
  ]
}
EOF

echo "Building knowledge pack from ${DOCS_DIR}..."
neoflow knowledge-pack --build "${PACK_SRC_DIR}" -o "${TMP_DIR}"

PACKAGE_FILE="${TMP_DIR}/${PACK_TAG}-v${PACK_VERSION}.nkp"
if [[ ! -f "${PACKAGE_FILE}" ]]; then
  echo "Error: expected package was not created: ${PACKAGE_FILE}"
  exit 1
fi

echo "Installing ${PACKAGE_FILE}..."
printf 'y\n' | neoflow knowledge-pack --install "${PACKAGE_FILE}"

echo "Done. Knowledge pack installed successfully."
echo "Tip: run 'neoflow knowledge-pack --list' to verify installation."
