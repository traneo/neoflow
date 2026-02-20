"""Import text files from a documentation folder into a Weaviate vector collection."""

import logging
import os

import weaviate
from weaviate.classes.config import Configure
from weaviate.config import AdditionalConfig, Timeout

from neoflow.config import Config
from neoflow.importer.code_indexer import chunk_content

logger = logging.getLogger(__name__)

COLLECTION_NAME = "Documentation"


def _create_documentation_collection(client, config: Config):
    """Create the Documentation collection in Weaviate."""
    if client.collections.exists(COLLECTION_NAME):
        client.collections.delete(COLLECTION_NAME)
        logger.info("Deleted existing collection: %s", COLLECTION_NAME)

    client.collections.create(
        name=COLLECTION_NAME,
        description="Imported documentation files for contextual search",
        vector_config=config.get_weaviate_vector_config(),
    )
    logger.info("Created %s collection", COLLECTION_NAME)


def _connect_weaviate(config: Config):
    """Create a Weaviate client connection."""
    wv = config.weaviate
    return weaviate.connect_to_local(
        additional_config=AdditionalConfig(
            timeout=Timeout(
                init=wv.timeout_init,
                query=wv.timeout_query,
                insert=wv.timeout_insert,
            )
        )
    )


def import_documentation(doc_path: str, config: Config):
    """Walk a directory, read UTF-8 files, chunk, and insert into the Documentation collection.

    Args:
        doc_path: Path to the documentation directory.
        config: Application configuration.
    """
    doc_path = os.path.abspath(doc_path)
    logger.info("Importing documentation from: %s", doc_path)

    files: list[str] = []
    for dirpath, _, filenames in os.walk(doc_path):
        for fname in filenames:
            files.append(os.path.join(dirpath, fname))

    logger.info("Found %d files in %s", len(files), doc_path)

    with _connect_weaviate(config) as client:
        _create_documentation_collection(client, config)
        collection = client.collections.use(COLLECTION_NAME)

        indexed = 0
        skipped = 0

        for full_path in files:
            rel_path = os.path.relpath(full_path, doc_path)

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (UnicodeDecodeError, OSError) as e:
                logger.debug("Skipping binary/unreadable file %s: %s", rel_path, e)
                skipped += 1
                continue

            if not content.strip():
                logger.debug("Skipping empty file: %s", rel_path)
                skipped += 1
                continue

            chunks = chunk_content(content, config.llm_provider.chunk_size_bytes)
            for chunk in chunks:
                collection.data.insert(
                    properties={
                        "file_path": rel_path,
                        "content": chunk,
                        "source_dir": doc_path,
                    }
                )
                indexed += 1

        logger.info(
            "Documentation import: indexed %d chunks from %d files (%d skipped)",
            indexed, len(files) - skipped, skipped,
        )

    return indexed
