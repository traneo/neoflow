import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from weaviate.classes.config import ReferenceProperty, DataType, Property
from weaviate.classes.query import Filter

from neoflow.config import Config
from neoflow.models import Ticket
from neoflow.weaviate_client import create_weaviate_client

logger = logging.getLogger(__name__)


def _create_collections(client, config: Config):
    """Create the Tickets and Comments collections in Weaviate."""
    if client.collections.exists("Tickets") and client.collections.exists("Comments"):
        return

    if not client.collections.exists("Tickets"):
        client.collections.create(
            name="Tickets",
            description="Ticket URLs, questions, and ticket numbers",
            vector_config=config.get_weaviate_vector_config(),
            properties=[
                Property(name="title", data_type=DataType.TEXT),
                Property(name="question", data_type=DataType.TEXT),
                Property(name="reference", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="url", data_type=DataType.TEXT, skip_vectorization=True),
                Property(name="chunk_index", data_type=DataType.INT, skip_vectorization=True),
                Property(name="total_chunks", data_type=DataType.INT, skip_vectorization=True),
                Property(name="pack_name", data_type=DataType.TEXT, skip_vectorization=True),
            ],
        )

    if not client.collections.exists("Comments"):
        client.collections.create(
            name="Comments",
            description="Comments related to tickets, linked by reference",
            vector_config=config.get_weaviate_vector_config(),
            properties=[
                    Property(name="message", data_type=DataType.TEXT),
                    Property(name="reference", data_type=DataType.TEXT, skip_vectorization=True),
                    Property(name="chunk_index", data_type=DataType.INT, skip_vectorization=True),
                    Property(name="total_chunks", data_type=DataType.INT, skip_vectorization=True),
                    Property(name="pack_name", data_type=DataType.TEXT, skip_vectorization=True),
            ],
            references=[
                ReferenceProperty(name="hasTicket", target_collection="Tickets")
            ],
        )

    logger.info("Created Tickets and Comments collections")


def _ensure_pack_name_property(collection):
    try:
        collection.config.add_property(
            Property(name="pack_name", data_type=DataType.TEXT, skip_vectorization=True)
        )
    except Exception:
        pass


def _delete_existing_pack_tickets(tickets_col, comments_col, pack_name: str):
    for collection in (comments_col, tickets_col):
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


def _process_file(file_path: str, tickets_col, comments_col, batch_size: int, pack_name: str):
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
                "pack_name": pack_name,
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
                        "pack_name": pack_name,
                    }
            )

def import_tickets(
    config: Config,
    tickets_dir: str | None = None,
    pack_name: str = "manual-import",
    replace_existing: bool = True,
):
    """Import all ticket JSON files into Weaviate."""
    tickets_dir = tickets_dir or config.importer.tickets_dir
    if not os.path.isdir(tickets_dir):
        raise FileNotFoundError(f"Tickets directory not found: {tickets_dir}")

    files = sorted(f for f in os.listdir(tickets_dir) if f.endswith(".json"))
    total = len(files)
    logger.info(f"Found {total} ticket files to import")

    with create_weaviate_client(config) as client:
        _create_collections(client, config)

        tickets_col = client.collections.use("Tickets")
        comments_col = client.collections.use("Comments")
        _ensure_pack_name_property(tickets_col)
        _ensure_pack_name_property(comments_col)

        if replace_existing:
            _delete_existing_pack_tickets(tickets_col, comments_col, pack_name)

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
                    pack_name,
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
