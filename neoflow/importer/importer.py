import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import weaviate
from weaviate.classes.config import Configure, ReferenceProperty, DataType, Property

from neoflow.config import Config
from neoflow.models import Ticket

logger = logging.getLogger(__name__)


def _create_collections(client, config: Config):
    """Create the Tickets and Comments collections in Weaviate."""
    for name in ("Tickets", "Comments"):
        if client.collections.exists(name):
            client.collections.delete(name)
            logger.info("Deleted existing collection: %s", name)

    client.collections.create(
        name="Tickets",
        description="Ticket URLs, questions, and ticket numbers",
        vector_config=config.get_weaviate_vector_config(),
        properties=[
            # --- Vectorized (used for semantic search) ---
            Property(name="title", data_type=DataType.TEXT),
            Property(name="question", data_type=DataType.TEXT),
            # --- Not vectorized (metadata for filtering / display) ---
            Property(name="reference", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="url", data_type=DataType.TEXT, skip_vectorization=True),
            Property(name="chunk_index", data_type=DataType.INT, skip_vectorization=True),
            Property(name="total_chunks", data_type=DataType.INT, skip_vectorization=True),
        ],       
    )

    client.collections.create(
        name="Comments",
        description="Comments related to tickets, linked by reference",
        vector_config=config.get_weaviate_vector_config(),
        properties=[
                # --- Vectorized (used for semantic search) ---
                Property(name="message", data_type=DataType.TEXT),
                # --- Not vectorized (metadata for filtering / display) ---
                Property(name="reference", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="chunk_index", data_type=DataType.INT, skip_vectorization=True),
                Property(name="total_chunks", data_type=DataType.INT, skip_vectorization=True),                
        ],     
        references=[
            ReferenceProperty(name="hasTicket", target_collection="Tickets")
        ],
    )

    logger.info("Created Tickets and Comments collections")


def _process_file(file_path: str, tickets_col, comments_col, batch_size: int):
    """Parse a ticket JSON file and insert into Weaviate collections."""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    ticket = Ticket.model_validate_json(content)


    limit = 3000  # bytes, to stay well within typical LLM context limits after vectorization
    chunk_question = False
    chunk_comments = False
    question_chunks = []
    comment_chunks = []


    if len(ticket.question or "") > limit:
        logger.warning(
            "Question exceeds chunk size for %s: %d bytes",
            ticket.reference,
            len(ticket.question.encode("utf-8"))
        )
        logger.warning("Question will be chunked into %d parts", (len(ticket.question.encode("utf-8")) // limit) + 1)
        chunk_question = True   

    if chunk_question:
        question_chunks = [
            ticket.question[i:i+limit] for i in range(0, len(ticket.question), limit)
        ]
    else:
        question_chunks = [ticket.question or ""]

    for tk in question_chunks:
        tickets_col.data.insert(
            properties={
                "reference": ticket.reference,
                "title": ticket.metadata.title or "",
                "question": tk,
                "url": ticket.metadata.url,
                "chunk_index": question_chunks.index(tk),
                "total_chunks": len(question_chunks),
            }
        )

    if not ticket.comments:
        return

    with comments_col.batch.fixed_size(batch_size=batch_size) as batch:
        for comment in ticket.comments:
            chunk_comments = False
            
            if (len(comment.encode("utf-8")) > limit):
                logger.warning(
                    "Comment exceeds chunk size for %s: %d bytes",
                    ticket.reference,
                    len(comment.encode("utf-8"))
                    
                )
                logger.warning("Comment will be chunked into %d parts", (len(comment.encode("utf-8")) // limit) + 1)
                chunk_comments = True

            cleaned = comment.replace("\n\u00b7 ", ":\n").replace("\n\n", "")

            if chunk_comments:
                comment_chunks = [
                    cleaned[i:i+limit] for i in range(0, len(cleaned), limit)
                ]
            else:
                comment_chunks = [cleaned]

            for cm in comment_chunks:
                batch.add_object(
                    properties={
                        "reference": ticket.reference,
                        "message": cm,
                        "chunk_index": comment_chunks.index(cm),
                        "total_chunks": len(comment_chunks),
                    }
            )

def import_tickets(config: Config):
    """Import all ticket JSON files into Weaviate."""
    tickets_dir = config.importer.tickets_dir
    files = sorted(f for f in os.listdir(tickets_dir) if f.endswith(".json"))
    total = len(files)
    logger.info(f"Found {total} ticket files to import")

    with weaviate.connect_to_local() as client:
        _create_collections(client, config)

        tickets_col = client.collections.use("Tickets")
        comments_col = client.collections.use("Comments")

        completed = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=config.importer.max_workers) as executor:

            import threading
            # threading.Semaphore(config.importer.max_workers)  # Limit concurrent file processing to avoid overload

            futures = {}
            for file_name in files:
                file_path = os.path.join(tickets_dir, file_name)
                future = executor.submit(
                    _process_file,
                    file_path,
                    tickets_col,
                    comments_col,
                    config.importer.batch_size,
                )
                futures[future] = file_name

            for future in as_completed(futures):
                file_name = futures[future]
                try:
                    future.result()
                    completed += 1
                except json.JSONDecodeError as e:
                    failed += 1
                    logger.warning("Invalid JSON in %s: %s", file_name, e)
                except KeyError as e:
                    failed += 1
                    logger.warning("Missing field in %s: %s", file_name, e)
                except Exception as e:
                    failed += 1
                    logger.error("Error processing %s: %s", file_name, e)

                if (completed + failed) % 100 == 0:
                    logger.info(f"Progress: {completed + failed}/{total} (failed: {failed})")

    logger.info("Import complete: %d succeeded, %d failed out of %d", completed, failed, total)
